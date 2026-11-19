"""Curated, sourced knowledge base. The assistant may only state facts found here or from tools."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

KB_DIR = Path(settings.BASE_DIR) / "knowledge"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set(
    "the a an and or of to in on for is are you your with at be can by it this that "
    "what how do i my me we".split()
)


@dataclass(frozen=True)
class Doc:
    slug: str
    title: str
    text: str
    sources: tuple[str, ...]


def _parse(path: Path) -> Doc:
    raw = path.read_text()
    _, front, body = raw.split("---", 2)
    title = re.search(r"title:\s*(.+)", front).group(1).strip()  # type: ignore[union-attr]
    sources = tuple(re.findall(r"-\s*(https?://\S+)", front))
    return Doc(path.stem, title, body.strip(), sources)


@lru_cache(maxsize=1)
def docs() -> tuple[Doc, ...]:
    return tuple(_parse(p) for p in sorted(KB_DIR.glob("*.md")))


def _terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def search(query: str, k: int = 2) -> list[dict]:
    q = _terms(query)
    if not q:
        return []
    corpus = docs()
    n = len(corpus)
    scored = []
    for d in corpus:
        words = _terms(d.title + " " + d.text)
        score = 0.0
        for t in set(q):
            tf = words.count(t)
            if tf:
                df = sum(1 for o in corpus if t in _terms(o.title + " " + o.text))
                score += (1 + math.log(tf)) * math.log(1 + n / df)
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [{"title": d.title, "text": d.text, "sources": list(d.sources)} for _, d in scored[:k]]
