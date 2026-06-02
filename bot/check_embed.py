"""Quick sanity check: does qvac serve openai's /v1/embeddings actually work?

Usage:
    python bot/check_embed.py
    python bot/check_embed.py "any custom text here"

Prints embedding dimension and first/last few values. Run from inside venv.
"""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv
from pathlib import Path

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

BASE_URL = os.getenv("QVAC_BASE_URL", "http://127.0.0.1:11434/v1")
EMBED_MODEL = os.getenv("QVAC_EMBED_MODEL", "embed-mlm")


def main() -> None:
    text = " ".join(sys.argv[1:]).strip() or "被毒蛇咬了"
    print(f"Embedding model: {EMBED_MODEL}")
    print(f"Input text:      {text}")

    payload = {"model": EMBED_MODEL, "input": text}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{BASE_URL}/embeddings", json=payload)
        r.raise_for_status()
        data = r.json()

    vec = data["data"][0]["embedding"]
    print(f"Dim:             {len(vec)}")
    print(f"First 5:         {[round(x, 4) for x in vec[:5]]}")
    print(f"Last 5:          {[round(x, 4) for x in vec[-5:]]}")

    norm = sum(x * x for x in vec) ** 0.5
    print(f"L2 norm:         {norm:.4f}")
    if abs(norm - 1.0) > 0.01:
        print("  (note: vector is not L2-normalized; remember to normalize before cosine sim)")
    else:
        print("  (already L2-normalized — cosine = dot product)")


if __name__ == "__main__":
    main()
