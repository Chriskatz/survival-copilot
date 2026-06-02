from __future__ import annotations

DEFAULT_MAX_BYTES = 200
HEADER_RESERVE = 8


def byte_length(s: str) -> int:
    return len(s.encode("utf-8"))


def chunk_for_mesh(text: str, max_bytes: int = DEFAULT_MAX_BYTES) -> list[str]:
    if max_bytes <= HEADER_RESERVE:
        raise ValueError(f"max_bytes must exceed header reserve ({HEADER_RESERVE})")
    body_max = max_bytes - HEADER_RESERVE
    bodies = _pack_by_byte_budget(text, body_max)
    total = len(bodies) or 1
    return [f"[{i + 1}/{total}] {body}" for i, body in enumerate(bodies)]


def _pack_by_byte_budget(text: str, max_bytes: int) -> list[str]:
    data = text.encode("utf-8")
    if not data:
        return [""]
    chunks: list[str] = []
    offset = 0
    while offset < len(data):
        end = min(offset + max_bytes, len(data))
        while end > offset and end < len(data) and (data[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(data[offset:end].decode("utf-8"))
        offset = end
    return chunks
