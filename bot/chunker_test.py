"""Sanity tests for chunker.py. Run with:  python -m unittest bot/chunker_test.py"""

from __future__ import annotations

import re
import unittest

from chunker import byte_length, chunk_for_mesh


HEADER_RE = re.compile(r"^\[\d+/\d+]\s")


def strip(chunk: str) -> str:
    return HEADER_RE.sub("", chunk, count=1)


class ChunkerTests(unittest.TestCase):
    def test_short_ascii(self) -> None:
        self.assertEqual(chunk_for_mesh("hello world"), ["[1/1] hello world"])

    def test_empty(self) -> None:
        self.assertEqual(chunk_for_mesh(""), ["[1/1] "])

    def test_long_ascii_under_budget(self) -> None:
        long = "a" * 1000
        chunks = chunk_for_mesh(long)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(byte_length(c), 200)
        self.assertEqual("".join(strip(c) for c in chunks), long)

    def test_custom_budget(self) -> None:
        for c in chunk_for_mesh("a" * 120, max_bytes=50):
            self.assertLessEqual(byte_length(c), 50)

    def test_zh_never_splits_codepoint(self) -> None:
        zh = "野外求生" * 40
        chunks = chunk_for_mesh(zh, max_bytes=60)
        for c in chunks:
            self.assertLessEqual(byte_length(c), 60)
            self.assertNotIn("�", c)
        self.assertEqual("".join(strip(c) for c in chunks), zh)

    def test_emoji_never_splits_codepoint(self) -> None:
        emoji = "🏕️🐍🍄🩹" * 30
        chunks = chunk_for_mesh(emoji, max_bytes=40)
        for c in chunks:
            self.assertLessEqual(byte_length(c), 40)
            self.assertNotIn("�", c)
        self.assertEqual("".join(strip(c) for c in chunks), emoji)


if __name__ == "__main__":
    unittest.main()
