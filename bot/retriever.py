"""Embedding-backed retriever for knowledge/index.json.

Loads the pre-built index, embeds incoming queries via the local QVAC server,
returns top-k chunks by cosine similarity (computed as dot product since
EmbeddingGemma already returns L2-normalized vectors).

Run as a script for a smoketest:

    python bot/retriever.py
    python bot/retriever.py "在山上失溫了"

Loaded once at bot startup; the entire index lives in memory (≪1 MB for the
seed corpus).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
INDEX_PATH = ROOT / "knowledge" / "index.json"

load_dotenv(ROOT / "bot" / ".env")
BASE_URL = os.getenv("QVAC_BASE_URL", "http://127.0.0.1:11434/v1")
EMBED_MODEL = os.getenv("QVAC_EMBED_MODEL", "embed-mlm")

DEFAULT_TOP_K = 3
# Tuned 2026-06-02: in-domain queries scored 0.46-0.77, off-topic 0.30-0.34.
# 0.40 gives ~0.06 buffer on both sides; revisit if false-refuse becomes common.
DEFAULT_MIN_SCORE = 0.40

log = logging.getLogger("retriever")


@dataclass
class Hit:
    score: float
    chunk: dict[str, Any]

    @property
    def text(self) -> str:
        return self.chunk["text"]

    @property
    def source(self) -> str:
        return f"{self.chunk['source']} > {self.chunk['h2']}"


class Retriever:
    def __init__(
        self,
        index_path: Path = INDEX_PATH,
        base_url: str = BASE_URL,
        embed_model: str = EMBED_MODEL,
    ) -> None:
        if not index_path.exists():
            raise FileNotFoundError(
                f"{index_path} not found — run `python bot/build_index.py` first."
            )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        self.model = data["model"]
        self.dim = data["dim"]
        self.chunks: list[dict[str, Any]] = data["chunks"]
        self.matrix = np.array([c["vec"] for c in self.chunks], dtype=np.float32)
        self.base_url = base_url
        self.embed_model = embed_model
        self._client = httpx.Client(timeout=60.0)
        log.info(
            "retriever ready: %d chunks, dim=%d, model=%s",
            len(self.chunks), self.dim, self.model,
        )

    def _embed(self, text: str) -> np.ndarray:
        r = self._client.post(
            f"{self.base_url}/embeddings",
            json={"model": self.embed_model, "input": text},
        )
        r.raise_for_status()
        vec = np.array(r.json()["data"][0]["embedding"], dtype=np.float32)
        return vec

    def retrieve(
        self,
        query: str,
        k: int = DEFAULT_TOP_K,
        min_score: float = 0.0,
    ) -> list[Hit]:
        qvec = self._embed(query)
        scores = self.matrix @ qvec
        order = np.argsort(-scores)
        hits = [Hit(score=float(scores[i]), chunk=self.chunks[i]) for i in order[:k]]
        return [h for h in hits if h.score >= min_score]

    def close(self) -> None:
        self._client.close()


def _smoketest() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    queries = sys.argv[1:] or [
        "被毒蛇咬了怎麼辦",
        "在山上失溫了",
        "我迷路了天快黑",
        "snake bite first aid",
        "I am lost in the mountains",
        "hypothermia treatment",
        "Google的URL是什麼",
        "幫我寫 hello world",
    ]

    r = Retriever()
    try:
        for q in queries:
            print(f"\nQ: {q}")
            hits = r.retrieve(q, k=3)
            top = hits[0].score if hits else 0.0
            verdict = "REFUSE" if top < DEFAULT_MIN_SCORE else "PASS"
            print(f"   top score: {top:.3f}  → {verdict} (threshold {DEFAULT_MIN_SCORE})")
            for h in hits:
                print(f"     {h.score:.3f}  {h.source}")
    finally:
        r.close()


if __name__ == "__main__":
    _smoketest()
