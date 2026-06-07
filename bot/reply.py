"""Post-processing for LLM replies before they hit the LoRa wire."""

from __future__ import annotations

import re

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

# Meshtastic renders plain text, so markdown markers are just noise (and wasted
# bytes on LoRa). Strip the ones Qwen tends to emit.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC_RE = re.compile(r"\*(.+?)\*|(?<![A-Za-z0-9_])_(.+?)_(?![A-Za-z0-9_])", re.DOTALL)
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HEADER_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]*", re.MULTILINE)
_BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+", re.MULTILINE)
_BLANKS_RE = re.compile(r"\n{3,}")
_TRAIL_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Flatten markdown to clean plain text for a no-markdown chat client."""
    text = _LINK_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _CODE_RE.sub(r"\1", text)
    text = _HEADER_RE.sub("", text)
    text = _BULLET_RE.sub(r"\1• ", text)  # nicer than a bare hyphen
    text = _BLANKS_RE.sub("\n\n", text)
    text = _TRAIL_WS_RE.sub("", text)
    return text


def clean_reply(text: str) -> str:
    """Normalize a model reply for the LoRa wire: drop Qwen3 <think>…</think>
    blocks (including the empty one from /no_think), flatten markdown, and trim.
    Run on every model reply before chunking.
    """
    return strip_markdown(_THINK_RE.sub("", text)).strip()


# Common simplified-Chinese chars that should be traditional in zh-TW.
# Not exhaustive — picks high-frequency offenders so we notice prompt drift.
SIMPLIFIED_HINTS = "并与后对们时会学长发当国书车东马门见来这那这么么该这"


def likely_simplified(text: str) -> bool:
    return any(c in SIMPLIFIED_HINTS for c in text)
