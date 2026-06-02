"""Survival Co-pilot — Meshtastic BLE chatbot bridged to a local QVAC LLM.

Run:
    1. Quit the Meshtastic macOS app (BLE is single-owner).
    2. Start QVAC server:  qvac serve openai
    3. python bot/bot.py
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pubsub import pub

from chunker import chunk_for_mesh
from reply import clean_reply
from retriever import DEFAULT_MIN_SCORE, DEFAULT_TOP_K, Retriever

try:
    from meshtastic.ble_interface import BLEInterface
except ImportError as e:
    sys.exit(f"meshtastic library not installed. pip install -r bot/requirements.txt\n  ({e})")


HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("copilot")


BLE_ADDRESS = os.getenv("MESH_BLE_ADDRESS") or None
QVAC_BASE_URL = os.getenv("QVAC_BASE_URL", "http://127.0.0.1:11434/v1")
QVAC_MODEL = os.getenv("QVAC_MODEL", "QWEN3_1_7B_INST_Q4")
TRIGGER_PREFIX = os.getenv("TRIGGER_PREFIX", "?")
REPLY_MODE = os.getenv("REPLY_MODE", "dm").lower()
SEND_INTERVAL_S = float(os.getenv("SEND_INTERVAL_S", "2.0"))
MAX_REPLY_CHARS = int(os.getenv("MAX_REPLY_CHARS", "600"))

SYSTEM_PROMPT = (HERE / "system_prompt.txt").read_text(encoding="utf-8").strip()

REFUSE_MSG = "不在我的求生知識範圍 — 此頻道僅回答野外求生 / 急救 / 導航 / 救援問題,優先 SOS 求救"


def _is_chinese(text: str) -> bool:
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return cjk >= max(1, len(text) // 5)


def _format_chunk_for_prompt(hit, lang: str) -> str:
    label = "出處" if lang == "zh" else "Source"
    return f"【{label} {hit.chunk['source']} > {hit.chunk['h2']}】\n{hit.text}"


def ask_llm(question: str, retriever: Retriever) -> tuple[str, list]:
    hits = retriever.retrieve(question, k=DEFAULT_TOP_K, min_score=DEFAULT_MIN_SCORE)
    if not hits:
        return REFUSE_MSG, []

    context_lang = "zh" if _is_chinese(question) else "en"
    context = "\n\n".join(
        _format_chunk_for_prompt(h, context_lang) for h in hits
    )
    if context_lang == "zh":
        user_msg = (
            "依以下【出處】段落回答。只准用段落內事實。\n\n"
            f"---\n{context}\n---\n\n"
            f"問題: {question}"
        )
    else:
        user_msg = (
            "Answer using ONLY the Source excerpts below. Do not invent facts.\n\n"
            f"---\n{context}\n---\n\n"
            f"Question: {question}"
        )

    lang_directive = (
        "\n\n# THIS REPLY MUST BE IN TRADITIONAL CHINESE (繁體中文) — NOT SIMPLIFIED, NOT ENGLISH."
        if context_lang == "zh"
        else "\n\n# THIS REPLY MUST BE IN ENGLISH ONLY — NO CHINESE CHARACTERS."
    )
    payload = {
        "model": QVAC_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + lang_directive},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": 400,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{QVAC_BASE_URL}/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
    answer = clean_reply(data["choices"][0]["message"]["content"])
    return answer, hits


class CopilotBot:
    def __init__(self, iface: BLEInterface, retriever: Retriever) -> None:
        self.iface = iface
        self.retriever = retriever
        self.my_node_num: int | None = None
        try:
            self.my_node_num = iface.myInfo.my_node_num  # type: ignore[union-attr]
        except Exception:
            log.warning("Could not read my_node_num; self-message filter disabled")

    def on_receive(self, packet: dict, interface) -> None:  # noqa: ARG002 — required by pubsub
        try:
            decoded = packet.get("decoded") or {}
            if decoded.get("portnum") != "TEXT_MESSAGE_APP":
                return
            text = (decoded.get("text") or "").strip()
            if not text:
                return

            sender = packet.get("from")
            if self.my_node_num is not None and sender == self.my_node_num:
                return

            channel = packet.get("channel", 0)
            to = packet.get("to")

            if TRIGGER_PREFIX and not text.startswith(TRIGGER_PREFIX):
                return
            question = text[len(TRIGGER_PREFIX):].strip() if TRIGGER_PREFIX else text
            if not question:
                return

            log.info("Q from %s ch%s: %s", sender, channel, question)
            hits: list = []
            try:
                answer, hits = ask_llm(question, self.retriever)
            except Exception as e:
                log.exception("LLM call failed")
                answer = f"co-pilot error: {e}"

            if hits:
                log.info(
                    "   RAG top-%d: %s",
                    len(hits),
                    ", ".join(f"{h.score:.2f} {h.chunk['source']}" for h in hits),
                )
            else:
                log.info("   RAG: no hit ≥ %.2f → REFUSE", DEFAULT_MIN_SCORE)

            if len(answer) > MAX_REPLY_CHARS:
                answer = answer[:MAX_REPLY_CHARS].rstrip() + "…"

            self.send_reply(answer, dest=sender, channel=channel)
        except Exception:
            log.exception("on_receive crashed")

    def send_reply(self, text: str, dest: int | None, channel: int) -> None:
        segments = chunk_for_mesh(text)
        if segments:
            segments[0] = f"[demo] {segments[0]}"
        total_bytes = sum(len(s.encode("utf-8")) for s in segments)
        log.info(
            "→ %d segment(s), %d bytes total, to %s (mode=%s)",
            len(segments), total_bytes, dest, REPLY_MODE,
        )
        log.info("   answer preview: %s", text[:80].replace("\n", " ⏎ "))
        for seg in segments:
            kwargs: dict = {"text": seg, "wantAck": False, "channelIndex": channel}
            if REPLY_MODE == "dm" and dest is not None:
                kwargs["destinationId"] = dest
            self.iface.sendText(**kwargs)
            time.sleep(SEND_INTERVAL_S)


def main() -> None:
    log.info("Loading RAG index…")
    retriever = Retriever()

    log.info("Connecting BLE… address=%r", BLE_ADDRESS)
    iface = BLEInterface(address=BLE_ADDRESS)
    log.info("Connected. QVAC=%s model=%s prefix=%r", QVAC_BASE_URL, QVAC_MODEL, TRIGGER_PREFIX)

    bot = CopilotBot(iface, retriever)
    pub.subscribe(bot.on_receive, "meshtastic.receive")

    sigint_count = 0

    def shutdown(signum, frame):  # noqa: ARG001
        nonlocal sigint_count
        sigint_count += 1
        if sigint_count == 1:
            log.info("Shutting down… (Ctrl+C again to force exit)")
            try:
                iface.close()
            except Exception:
                pass
        else:
            log.info("Force exit.")
            os._exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("Listening. Send a mesh message starting with %r to trigger.", TRIGGER_PREFIX)
    signal.pause()


if __name__ == "__main__":
    main()
