"""Parse English number words as written on result sheets ("two hundred and fourteen")."""

from __future__ import annotations

import re

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_UNITS = {w: i for i, w in enumerate(_ONES)}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fourty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_NIL = {"nil", "none", "nill"}


def words_to_int(text: str | None) -> int | None:
    if not text:
        return None
    tokens = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    tokens = [t for t in tokens if t not in {"and", "only", "votes", "vote"}]
    if not tokens:
        return None
    if len(tokens) == 1 and tokens[0] in _NIL:
        return 0
    total = current = 0
    for t in tokens:
        if t in _UNITS:
            current += _UNITS[t]
        elif t in _TENS:
            current += _TENS[t]
        elif t == "hundred":
            current = max(current, 1) * 100
        elif t in _SCALES:
            total += max(current, 1) * _SCALES[t]
            current = 0
        else:
            return None
    return total + current


def int_to_words(n: int) -> str:
    if n == 0:
        return "nil"
    ones = _ONES
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    def below_thousand(x: int) -> str:
        parts = []
        if x >= 100:
            parts.append(f"{ones[x // 100]} hundred")
            x %= 100
            if x:
                parts.append("and")
        if x >= 20:
            parts.append(tens[x // 10] + (f"-{ones[x % 10]}" if x % 10 else ""))
        elif x:
            parts.append(ones[x])
        return " ".join(parts)

    if n >= 1000:
        head, rest = divmod(n, 1000)
        tail = below_thousand(rest)
        joiner = " and " if 0 < rest < 100 else " "
        return f"{below_thousand(head)} thousand" + (joiner + tail if rest else "")
    return below_thousand(n)
