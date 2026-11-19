"""Settle low-confidence readings using the sheet's own redundancy.

- A party score is confirmed when the written words equal the figure.
- A total is confirmed when an equation containing it balances and every other value in that
  equation is confident (iterated to a fixed point). A misread digit almost never still balances.
- Party scores that stay unconfirmed BLOCK publication (they decide the comparison).
- Totals that stay unconfirmed are DROPPED from the comparison (shown as not compared).
"""

from __future__ import annotations

from dataclasses import replace

from .types import SheetFigures

_TOTALS = (
    "registered",
    "accredited",
    "ballots_issued",
    "unused",
    "spoilt",
    "rejected",
    "total_valid",
    "total_used",
)


def _equations(f: SheetFigures) -> list[tuple[set[str], bool | None]]:
    parties = {f"party:{p}" for p in f.party_votes}
    eqs: list[tuple[set[str], bool | None]] = []
    if f.total_valid is not None and f.party_votes:
        eqs.append((parties | {"total_valid"}, sum(f.party_votes.values()) == f.total_valid))
    if None not in (f.total_valid, f.rejected, f.total_used):
        eqs.append(
            ({"total_valid", "rejected", "total_used"}, f.total_valid + f.rejected == f.total_used)
        )  # type: ignore[operator]
    if None not in (f.ballots_issued, f.total_used, f.unused, f.spoilt):
        eqs.append(
            (
                {"ballots_issued", "total_used", "unused", "spoilt"},
                f.ballots_issued == f.total_used + f.unused + f.spoilt,
            )
        )  # type: ignore[operator]
    return eqs


def settle(f: SheetFigures) -> tuple[SheetFigures, tuple[str, ...], tuple[str, ...]]:
    """Return (figures for comparison, blocking fields, dropped totals)."""
    low = set(f.low_confidence_fields)
    for party, value in f.party_votes.items():
        key = f"party:{party}"
        if key in low and f.words.get(party) is not None and f.words.get(party) == value:
            low.discard(key)
    changed = True
    while changed:
        changed = False
        for members, holds in _equations(f):
            if not holds:
                continue
            unsure = members & low
            if len(unsure) == 1:
                low -= unsure
                changed = True
    blocking = tuple(sorted(k for k in low if k.startswith("party:") or k not in _TOTALS))
    dropped = tuple(sorted(k for k in low if k in _TOTALS))
    cleaned = replace(f, low_confidence_fields=blocking, **{k: None for k in dropped})
    return cleaned, blocking, dropped
