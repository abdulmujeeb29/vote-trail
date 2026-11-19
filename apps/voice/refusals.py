"""Guardrails: no partisan opinions, no voting advice, no winner predictions."""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\bwho (won|will win|is winning|go win|don win)\b", re.I),
    re.compile(r"\bwho (should|do|must|can|shall) (i|we) vote\b", re.I),
    re.compile(r"\bwho (i|we) (go|fit|suppose) vote\b", re.I),
    re.compile(r"\bwho make (i|we) vote\b", re.I),
    re.compile(r"\b(which|what) party (is|dey) (best|better|good)\b", re.I),
    re.compile(r"\bvote for (who|which)\b", re.I),
]

REFUSAL = (
    "I can't tell you who to vote for or who won. Only INEC declares results. "
    "I can help you find your polling unit, check a result sheet, or check a rumour."
)


def refusal_for(text: str) -> str:
    return REFUSAL if any(p.search(text or "") for p in _PATTERNS) else ""
