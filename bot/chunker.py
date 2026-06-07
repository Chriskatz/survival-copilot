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


_CJK_END = "。！？"
_ASCII_END = ".!?"


def _best_break(window: str) -> int | None:
    """Index to cut ``window`` at for the most readable segment, or None to
    hard-cut at the byte budget. Prefer a sentence end, else any whitespace.
    Only break past the halfway point so segments don't come out tiny."""
    half = len(window) // 2
    for k in range(len(window) - 1, half - 1, -1):
        ch = window[k]
        if ch in _CJK_END or ch == "\n":
            return k + 1
        if ch in _ASCII_END:  # require ". " and skip list numbers like "1."
            prev = window[k - 1] if k else ""
            nxt = window[k + 1] if k + 1 < len(window) else " "
            if not prev.isdigit() and nxt in " \n":
                return k + 1
    for k in range(len(window) - 1, half - 1, -1):
        if window[k] in " \t\n":
            return k + 1
    return None


def _pack_by_byte_budget(text: str, max_bytes: int) -> list[str]:
    if not text:
        return [""]
    chunks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        # Grow char by char (never splitting a codepoint) up to the byte budget.
        j, used = i, 0
        while j < n:
            cb = len(text[j].encode("utf-8"))
            if used + cb > max_bytes:
                break
            used += cb
            j += 1
        if j >= n:
            piece, i = text[i:n], n
        else:
            cut = _best_break(text[i:j])
            if cut is None:  # no good break point — hard cut at the budget
                piece, i = text[i:j], j
            else:
                piece, i = text[i:i + cut], i + cut
        piece = piece.strip()
        if piece:
            chunks.append(piece)
    return chunks or [""]
