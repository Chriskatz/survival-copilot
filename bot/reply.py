"""Post-processing for LLM replies before they hit the LoRa wire."""

from __future__ import annotations

import re

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def clean_reply(text: str) -> str:
    """Strip Qwen3 <think>…</think> blocks (including empty ones from /no_think)
    and trim trailing whitespace. Run on every model reply before chunking.
    """
    return _THINK_RE.sub("", text).strip()


# Common simplified-Chinese chars that should be traditional in zh-TW.
# Not exhaustive — picks high-frequency offenders so we notice prompt drift.
SIMPLIFIED_HINTS = "并与后对们时会学长发当国书车东马门见来这那这么么该这"


def likely_simplified(text: str) -> bool:
    return any(c in SIMPLIFIED_HINTS for c in text)
