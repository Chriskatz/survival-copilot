"""Survival Co-pilot — Meshtastic BLE chatbot bridged to a local QVAC LLM.

Run:
    1. Quit the Meshtastic macOS app (BLE is single-owner).
    2. Start QVAC server:  qvac serve openai
    3. python bot/bot.py
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import signal
import subprocess
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


def _env_float(name: str):
    v = os.getenv(name)
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


# Base station's own location (Wio often has no GPS fix indoors). Set these to
# enable distance/bearing to senders. Falls back to the node's fixed position.
BASE_LAT = _env_float("BASE_LAT")
BASE_LON = _env_float("BASE_LON")
BASE_ALT = _env_float("BASE_ALT")

SYSTEM_PROMPT = (HERE / "system_prompt.txt").read_text(encoding="utf-8").strip()

REFUSE_MSG = "不在我的求生知識範圍 — 此頻道僅回答野外求生 / 急救 / 導航 / 救援問題,優先 SOS 求救"


def _is_chinese(text: str) -> bool:
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return cjk >= max(1, len(text) // 5)


_LANGDETECT_JS = HERE.parent / "tools" / "langdetect.mjs"
_NODE = shutil.which("node")


def detect_lang(text: str) -> tuple[str, str]:
    """Detect the query language to route the reply.

    Primary: QVAC ``@qvac/langdetect-text`` via ``tools/langdetect.mjs``.
    Fallback: CJK-ratio heuristic if the Node helper is missing or errors.
    Returns ``(routing, detail)`` where ``routing`` is ``"zh"`` or ``"en"``
    (the languages our corpus answers in) and ``detail`` is logged for audit.
    """
    if _NODE and _LANGDETECT_JS.exists():
        try:
            out = subprocess.run(
                [_NODE, str(_LANGDETECT_JS), text],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if out.returncode == 0 and out.stdout.strip():
                data = json.loads(out.stdout)
                code = (data.get("code") or "").lower()
                prob = data.get("probability") or 0.0
                routing = "zh" if code.startswith("zh") else "en"
                return routing, f"qvac-langdetect:{code} ({prob:.2f})"
        except Exception as e:  # noqa: BLE001
            log.debug("langdetect helper failed, using heuristic: %s", e)
    return ("zh" if _is_chinese(text) else "en"), "cjk-heuristic"


def _format_chunk_for_prompt(hit, lang: str) -> str:
    label = "出處" if lang == "zh" else "Source"
    return f"【{label} {hit.chunk['source']} > {hit.chunk['h2']}】\n{hit.text}"


def _fmt_age(ts) -> str:
    if not ts:
        return "?"
    age = int(time.time() - ts)
    if age < 90:
        return f"{age}s"
    if age < 5400:
        return f"{age // 60}m"
    return f"{age // 3600}h"


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _compass(deg) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][round(deg / 45) % 8]


def _fmt_dist(km) -> str:
    return f"{int(round(km * 1000))} m" if km < 1 else f"{km:.1f} km"


def _my_node_num(interface):
    try:
        return interface.myInfo.my_node_num
    except Exception:
        return None


def _base_position(interface):
    """Base station location: .env BASE_LAT/LON first, else the node's own
    (fixed) position. Returns (lat, lon, alt) with None for any unknown."""
    if BASE_LAT is not None and BASE_LON is not None:
        return BASE_LAT, BASE_LON, BASE_ALT
    try:
        pos = ((interface.getMyNodeInfo() or {}).get("position")) or {}
        if pos.get("latitude") is not None and pos.get("longitude") is not None:
            return pos["latitude"], pos["longitude"], pos.get("altitude")
    except Exception:
        pass
    return None, None, None


def sender_info(interface, node_num: int | None) -> str:
    """Best-effort one-line GPS + power snapshot for the sender.

    Read from the local node DB, which meshtastic-python fills from the
    sender's periodic Position / Telemetry broadcasts — NOT from the text
    packet. Values are LAST-KNOWN, not real-time. Never raises.
    """
    try:
        node = None
        if node_num is not None:
            node = (getattr(interface, "nodesByNum", None) or {}).get(node_num)
            if node is None:
                for n in (getattr(interface, "nodes", None) or {}).values():
                    if n.get("num") == node_num:
                        node = n
                        break
        if node is None:
            return "telemetry: node not in DB yet"

        pos = node.get("position") or {}
        dm = node.get("deviceMetrics") or {}

        if pos.get("latitude") is not None and pos.get("longitude") is not None:
            loc = f"📍 {pos['latitude']:.5f},{pos['longitude']:.5f}"
            if pos.get("altitude") is not None:
                loc += f" alt={pos['altitude']}m"
            if pos.get("groundSpeed") is not None:
                loc += f" spd={pos['groundSpeed']}"  # unit per firmware (m/s)
            if pos.get("groundTrack") is not None:
                loc += f" hdg={pos['groundTrack']}°"
            loc += f" (age {_fmt_age(pos.get('time'))})"

            blat, blon, balt = _base_position(interface)
            if blat is not None and node.get("num") != _my_node_num(interface):
                dist = _haversine_km(blat, blon, pos["latitude"], pos["longitude"])
                brg = _bearing_deg(blat, blon, pos["latitude"], pos["longitude"])
                loc += f" · ~{_fmt_dist(dist)} from base, bearing {brg:.0f}° {_compass(brg)}"
                if balt is not None and pos.get("altitude") is not None:
                    loc += f" · Δalt {int(pos['altitude'] - balt):+d}m"
        else:
            loc = "📍 no GPS"

        if dm.get("batteryLevel") is not None:
            pwr = f"🔋 {dm['batteryLevel']}%"
            if dm.get("voltage") is not None:
                pwr += f" {dm['voltage']:.2f}V"
        else:
            pwr = "🔋 no telemetry"

        link = (
            f"snr={node.get('snr')} hops={node.get('hopsAway')} "
            f"heard {_fmt_age(node.get('lastHeard'))} ago"
        )
        return f"{loc} | {pwr} | {link}"
    except Exception as e:
        return f"telemetry lookup failed: {e}"


def log_connected_node(interface) -> None:
    """Log the base station's OWN Meshtastic node (the one we connected over BLE)."""
    try:
        num = None
        try:
            num = interface.myInfo.my_node_num
        except Exception:
            pass

        my = None
        try:
            my = interface.getMyNodeInfo()
        except Exception:
            my = None
        user = (my or {}).get("user") or {}
        if not user:
            try:
                user = interface.getMyUser() or {}
            except Exception:
                user = {}

        fw = ""
        try:
            fw = getattr(interface.metadata, "firmware_version", "") or ""
        except Exception:
            fw = ""

        log.info(
            "Connected node: %s (%s) id=%s num=%s hw=%s%s",
            user.get("longName", "?"), user.get("shortName", "?"),
            user.get("id", "?"), num, user.get("hwModel", "?"),
            f" fw={fw}" if fw else "",
        )
        log.info("   node status: %s", sender_info(interface, num))
    except Exception as e:
        log.warning("Could not read connected node info: %s", e)


def ask_llm(question: str, retriever: Retriever) -> tuple[str, list]:
    hits = retriever.retrieve(question, k=DEFAULT_TOP_K, min_score=DEFAULT_MIN_SCORE)
    if not hits:
        return REFUSE_MSG, []

    context_lang, lang_detail = detect_lang(question)
    log.info("lang routing: %s (%s)", context_lang, lang_detail)
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

    def on_receive(self, packet: dict, interface) -> None:
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
            log.info("   sender: %s", sender_info(interface, sender))
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
    log_connected_node(iface)

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
