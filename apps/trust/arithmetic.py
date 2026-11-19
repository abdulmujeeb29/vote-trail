"""Arithmetic consistency of an EC8A sheet. Field names follow docs/ec8a-schema.md."""

from __future__ import annotations

from .types import SheetFigures, Violation


def check_arithmetic(sheet: SheetFigures) -> list[Violation]:
    v: list[Violation] = []
    numbers = {
        **{f"party:{k}": n for k, n in sheet.party_votes.items()},
        "registered": sheet.registered,
        "accredited": sheet.accredited,
        "rejected": sheet.rejected,
        "total_valid": sheet.total_valid,
        "total_used": sheet.total_used,
        "ballots_issued": sheet.ballots_issued,
        "unused": sheet.unused,
        "spoilt": sheet.spoilt,
    }
    for name, value in numbers.items():
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            v.append(Violation("not_integer", {"field": name}))
        elif value < 0:
            v.append(Violation("negative_value", {"field": name, "value": value}))
    if v:
        return v

    party_sum = sum(sheet.party_votes.values())
    if sheet.total_valid is not None and party_sum != sheet.total_valid:
        v.append(
            Violation("sum_mismatch", {"party_sum": party_sum, "total_valid": sheet.total_valid})
        )
    has_totals = None not in (sheet.total_valid, sheet.rejected, sheet.total_used)
    if has_totals and sheet.total_valid + sheet.rejected != sheet.total_used:  # type: ignore[operator]
        v.append(
            Violation(
                "valid_plus_rejected",
                {
                    "total_valid": sheet.total_valid,
                    "rejected": sheet.rejected,
                    "total_used": sheet.total_used,
                },
            )
        )
    if None not in (sheet.total_used, sheet.accredited) and sheet.total_used > sheet.accredited:  # type: ignore[operator]
        v.append(
            Violation(
                "used_exceeds_accredited",
                {"total_used": sheet.total_used, "accredited": sheet.accredited},
            )
        )
    if None not in (sheet.accredited, sheet.registered) and sheet.accredited > sheet.registered:  # type: ignore[operator]
        v.append(
            Violation(
                "accredited_exceeds_registered",
                {"accredited": sheet.accredited, "registered": sheet.registered},
            )
        )
    issued_parts = (sheet.ballots_issued, sheet.total_used, sheet.unused, sheet.spoilt)
    if None not in issued_parts:
        issued, used, unused, spoilt = issued_parts
        if issued != used + unused + spoilt:  # type: ignore[operator]
            v.append(
                Violation(
                    "issued_balance",
                    {"ballots_issued": issued, "used": used, "unused": unused, "spoilt": spoilt},
                )
            )
    for party, in_words in sheet.words.items():
        in_figures = sheet.party_votes.get(party)
        if in_words is not None and in_figures is not None and in_words != in_figures:
            v.append(
                Violation(
                    "figures_words_mismatch",
                    {"party": party, "figures": in_figures, "words": in_words},
                )
            )
    return v
