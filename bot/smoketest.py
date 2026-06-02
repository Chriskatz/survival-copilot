"""Hit the running qvac OpenAI-compatible server with the real system prompt.

Usage:
    python bot/smoketest.py "被毒蛇咬到了怎麼辦,三步驟"

Run from inside the venv after `qvac serve openai` is up.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from reply import clean_reply, likely_simplified
from retriever import DEFAULT_MIN_SCORE, DEFAULT_TOP_K, Retriever

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

BASE_URL = os.getenv("QVAC_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL = os.getenv("QVAC_MODEL", "co-pilot")
SYSTEM_PROMPT = (HERE / "system_prompt.txt").read_text(encoding="utf-8").strip()


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or "被毒蛇咬到了怎麼辦,三步驟"
    print(f"--- model={MODEL} url={BASE_URL} ---")
    print(f"Q: {question}")

    retriever = Retriever()
    hits = retriever.retrieve(question, k=DEFAULT_TOP_K, min_score=DEFAULT_MIN_SCORE)
    print(f"RAG: {len(hits)} hit(s) above {DEFAULT_MIN_SCORE}")
    for h in hits:
        print(f"  {h.score:.3f}  {h.chunk['source']} > {h.chunk['h2']}")
    print()

    if not hits:
        print("A: (refused — no in-domain chunks)")
        retriever.close()
        return

    cjk = sum(1 for c in question if "一" <= c <= "鿿")
    lang = "zh" if cjk >= max(1, len(question) // 5) else "en"
    label = "出處" if lang == "zh" else "Source"
    context = "\n\n".join(
        f"【{label} {h.chunk['source']} > {h.chunk['h2']}】\n{h.text}" for h in hits
    )
    if lang == "zh":
        user_msg = (
            "依以下【出處】段落回答。只准用段落內事實。\n\n"
            f"---\n{context}\n---\n\n問題: {question}"
        )
    else:
        user_msg = (
            "Answer using ONLY the Source excerpts below. Do not invent facts.\n\n"
            f"---\n{context}\n---\n\nQuestion: {question}"
        )

    lang_directive = (
        "\n\n# THIS REPLY MUST BE IN TRADITIONAL CHINESE (繁體中文) — NOT SIMPLIFIED, NOT ENGLISH."
        if lang == "zh"
        else "\n\n# THIS REPLY MUST BE IN ENGLISH ONLY — NO CHINESE CHARACTERS."
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + lang_directive},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": 400,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{BASE_URL}/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
    retriever.close()

    raw = data["choices"][0]["message"]["content"]
    cleaned = clean_reply(raw)
    finish = data["choices"][0].get("finish_reason")
    usage = data.get("usage", {})

    print(f"A ({finish}, tokens={usage.get('completion_tokens')}):")
    print(cleaned)
    print()
    print(f"bytes on LoRa (after chunk header reserve): {len(cleaned.encode('utf-8'))}")

    think_match = re.search(r"<think>(.*?)</think>", raw, re.DOTALL)
    if think_match and think_match.group(1).strip():
        print("⚠️  non-empty <think> block leaked in raw output — model is still reasoning out loud.")
    if likely_simplified(cleaned):
        print("ℹ️  simplified-Chinese characters detected. Tighten the zh-TW instruction in system_prompt.txt.")


if __name__ == "__main__":
    main()
