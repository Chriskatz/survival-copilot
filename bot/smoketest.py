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

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

BASE_URL = os.getenv("QVAC_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL = os.getenv("QVAC_MODEL", "co-pilot")
SYSTEM_PROMPT = (HERE / "system_prompt.txt").read_text(encoding="utf-8").strip()


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or "被毒蛇咬到了怎麼辦,三步驟"
    print(f"--- model={MODEL} url={BASE_URL} ---")
    print(f"Q: {question}\n")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{BASE_URL}/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()

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
