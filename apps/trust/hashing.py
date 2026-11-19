"""Text simhash and hex-hash distances (pure Python)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WORD = re.compile(r"[a-z0-9]+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(_WORD.findall(text.lower()))


def simhash(text: str, bits: int = 64) -> int:
    tokens = normalize_text(text).split()
    if not tokens:
        return 0
    shingles = (
        tokens if len(tokens) < 3 else [" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
    )
    weights = [0] * bits
    for sh in shingles:
        h = int.from_bytes(hashlib.blake2b(sh.encode(), digest_size=8).digest(), "big")
        for i in range(bits):
            weights[i] += 1 if (h >> i) & 1 else -1
    return sum(1 << i for i in range(bits) if weights[i] > 0)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def hex_distance(a: str, b: str) -> int | None:
    if not a or not b or len(a) != len(b):
        return None
    try:
        return hamming(int(a, 16), int(b, 16))
    except ValueError:
        return None
