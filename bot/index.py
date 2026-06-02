"""Build knowledge/index.json from markdown files in knowledge/{zh,en}/.

Walks every .md file under knowledge/<lang>/, splits by `## ` headings, calls
the local QVAC embeddings endpoint for each chunk, writes index.json atomically.

Run from project root inside venv, **after** `qvac serve openai` is up:

    python bot/index.py

Re-run whenever you edit / add markdown in knowledge/. Index is overwritten in
place.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
INDEX_PATH = KNOWLEDGE_DIR / "index.json"

load_dotenv(ROOT / "bot" / ".env")
BASE_URL = os.getenv("QVAC_BASE_URL", "http://127.0.0.1:11434/v1")
EMBED_MODEL = os.getenv("QVAC_EMBED_MODEL", "embed-mlm")

MIN_CHUNK_CHARS = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("index")


@dataclass
class Chunk:
    id: str
    lang: str
    source: str
    h1: str
    h2: str
    text: str
    vec: list[float]


def parse_markdown(path: Path) -> list[tuple[str, str, str]]:
    """Return list of (h1, h2, body) tuples for each ## section."""
    raw = path.read_text(encoding="utf-8")

    h1_match = re.search(r"^#\s+(.+)$", raw, flags=re.MULTILINE)
    h1 = h1_match.group(1).strip() if h1_match else path.stem

    parts = re.split(r"^##\s+(.+)$", raw, flags=re.MULTILINE)
    sections: list[tuple[str, str, str]] = []
    for i in range(1, len(parts), 2):
        h2 = parts[i].strip()
        body = parts[i + 1].strip()
        body = re.sub(r"\n\s*>\s+Source:.*$", "", body, flags=re.DOTALL).strip()
        if len(body) >= MIN_CHUNK_CHARS:
            sections.append((h1, h2, body))
    return sections


def embed(client: httpx.Client, text: str) -> list[float]:
    r = client.post(f"{BASE_URL}/embeddings", json={"model": EMBED_MODEL, "input": text})
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def main() -> None:
    files = sorted(p for p in KNOWLEDGE_DIR.rglob("*.md") if p.parent != KNOWLEDGE_DIR)
    log.info("scanning %s — %d markdown file(s)", KNOWLEDGE_DIR, len(files))

    chunks: list[Chunk] = []
    with httpx.Client(timeout=60.0) as client:
        for path in files:
            rel = path.relative_to(KNOWLEDGE_DIR).as_posix()
            lang = path.parent.name
            sections = parse_markdown(path)
            log.info("  %s (lang=%s): %d section(s)", rel, lang, len(sections))
            for i, (h1, h2, body) in enumerate(sections):
                payload_text = f"{h1} > {h2}\n\n{body}"
                vec = embed(client, payload_text)
                chunks.append(Chunk(
                    id=f"{rel}#{i + 1}",
                    lang=lang,
                    source=rel,
                    h1=h1,
                    h2=h2,
                    text=body,
                    vec=vec,
                ))

    if not chunks:
        log.error("no chunks produced — nothing to write")
        return

    dim = len(chunks[0].vec)
    bad_norm = sum(1 for c in chunks if abs(sum(x * x for x in c.vec) ** 0.5 - 1.0) > 0.01)
    if bad_norm:
        log.warning("%d / %d vectors are not L2-normalized — retriever must normalize", bad_norm, len(chunks))

    index = {
        "model": EMBED_MODEL,
        "dim": dim,
        "chunks": [asdict(c) for c in chunks],
    }

    tmp = INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(INDEX_PATH)
    log.info("wrote %d chunks (dim=%d) → %s", len(chunks), dim, INDEX_PATH)


if __name__ == "__main__":
    main()
