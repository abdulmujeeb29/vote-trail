"""Status decisions. These are the only functions allowed to set a public status."""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection, Mapping, Sequence
from itertools import pairwise

from .arithmetic import check_arithmetic
from .confidence import settle
from .independence import eligible, independent_origins, is_cross_party
from .types import (
    CitizenSheet,
    ClaimStatus,
    Decision,
    Evidence,
    Origin,
    Reason,
    ResultStatus,
    Severity,
    SheetFigures,
    Stance,
)

_TOTALS = ("total_valid", "rejected", "total_used", "accredited")


def compare_figures(a: SheetFigures, b: SheetFigures) -> dict[str, tuple[int | None, int | None]]:
    """Fields that differ. Totals are compared only when both sides have them."""
    diffs: dict[str, tuple[int | None, int | None]] = {}
    for party in sorted(set(a.party_votes) | set(b.party_votes)):
        x, y = a.party_votes.get(party), b.party_votes.get(party)
        if x != y:
            diffs[f"party:{party}"] = (x, y)
    for name in _TOTALS:
        x, y = getattr(a, name), getattr(b, name)
        if x is not None and y is not None and x != y:
            diffs[name] = (x, y)
    return diffs


def result_status(
    citizen: Sequence[CitizenSheet],
    irev: SheetFigures | None,
    *,
    min_reputation: int = -3,
    phash_max: int = 6,
) -> Decision:
    reasons: list[Reason] = []

    usable: list[CitizenSheet] = []
    for sheet in citizen:
        rejects = [f for f in sheet.flags if f.severity is Severity.REJECT]
        if rejects:
            reasons.extend(
                Reason(f"excluded_{f.code}", {"upload": sheet.submission.id}) for f in rejects
            )
        elif not eligible(sheet.submission, min_reputation):
            reasons.append(Reason("excluded_low_reputation", {"upload": sheet.submission.id}))
        else:
            usable.append(sheet)

    # Settle low-confidence readings using the sheet's own words and arithmetic.
    settled = []
    for s in usable:
        fig, _, dropped = settle(s.figures)
        if dropped:
            reasons.append(
                Reason("not_compared", {"upload": s.submission.id, "fields": list(dropped)})
            )
        settled.append(CitizenSheet(s.submission, fig, s.flags))
    usable = settled
    if irev is not None:
        irev, _, irev_dropped = settle(irev)
        if irev_dropped:
            reasons.append(Reason("irev_not_compared", {"fields": list(irev_dropped)}))

    if any(s.figures.cancelled for s in usable) or (irev is not None and irev.cancelled):
        return Decision(ResultStatus.CANCELLED, (*reasons, Reason("sheet_endorsed_cancelled")))

    by_id = {s.submission.id: s for s in usable}
    origins = independent_origins(
        [s.submission for s in usable], phash_max=phash_max, merge_similar_images=False
    )

    review: list[Reason] = []
    for s in usable:
        for f in s.flags:
            if f.severity is Severity.REVIEW:
                review.append(Reason(f"flag_{f.code}", {"upload": s.submission.id, **f.detail}))
        for viol in check_arithmetic(s.figures):
            review.append(
                Reason(f"arithmetic_{viol.code}", {"upload": s.submission.id, **viol.detail})
            )
        if s.figures.low_confidence_fields:
            review.append(
                Reason(
                    "low_confidence",
                    {"upload": s.submission.id, "fields": list(s.figures.low_confidence_fields)},
                )
            )
    if irev is not None:
        for viol in check_arithmetic(irev):
            review.append(Reason(f"irev_arithmetic_{viol.code}", dict(viol.detail)))
        if irev.low_confidence_fields:
            review.append(
                Reason("irev_low_confidence", {"fields": list(irev.low_confidence_fields)})
            )

    representative: list[tuple[Origin, SheetFigures]] = []
    for origin in origins:
        sheets = [by_id[i].figures for i in origin.member_ids]
        if any(compare_figures(sheets[0], other) for other in sheets[1:]):
            review.append(Reason("origin_inconsistent", {"origin": origin.key}))
        representative.append((origin, sheets[0]))

    if len(representative) > 1:
        base = representative[0][1]
        if any(compare_figures(base, fig) for _, fig in representative[1:]):
            review.append(Reason("citizen_origins_disagree"))

    count = len(origins)
    cross = is_cross_party(origins)
    if review:
        return Decision(
            ResultStatus.NEEDS_REVIEW, (*reasons, *review), origin_count=count, cross_party=cross
        )
    if count == 0:
        return Decision(ResultStatus.PENDING, (*reasons, Reason("no_citizen_uploads")))
    if irev is None:
        return Decision(
            ResultStatus.PENDING,
            (*reasons, Reason("irev_not_uploaded")),
            origin_count=count,
            cross_party=cross,
        )

    diffs = compare_figures(representative[0][1], irev)
    if not diffs:
        return Decision(
            ResultStatus.MATCHES,
            (*reasons, Reason("matches_irev", {"origins": count})),
            origin_count=count,
            cross_party=cross,
        )
    if count >= 2:
        return Decision(
            ResultStatus.MISMATCH,
            (*reasons, Reason("differs_from_irev", {"origins": count})),
            origin_count=count,
            cross_party=cross,
            diffs=diffs,
        )
    return Decision(
        ResultStatus.NEEDS_REVIEW,
        (*reasons, Reason("single_origin_disagrees_with_irev")),
        origin_count=count,
        cross_party=cross,
        diffs=diffs,
    )


def _within_window(times: Sequence[dt.datetime], window: dt.timedelta) -> bool:
    ordered = sorted(times)
    return any(b - a <= window for a, b in pairwise(ordered))


def _origin_times(origins: Sequence[Origin], subs: Mapping[str, Evidence]) -> list[dt.datetime]:
    times = []
    for o in origins:
        observed = [subs[i].submission.observed_at for i in o.member_ids]
        known = [t for t in observed if t is not None]
        if known:
            times.append(min(known))
    return times


def claim_status(
    evidence: Sequence[Evidence],
    authorities: Collection[str],
    *,
    window: dt.timedelta = dt.timedelta(hours=3),
    min_reputation: int = -3,
    location: str = "",
) -> Decision:
    authorities = {a.lower() for a in authorities}
    relevant = [e for e in evidence if e.stance is not Stance.IRRELEVANT]
    forwards = sum(1 for e in relevant if e.submission.is_forward)

    official = [
        e for e in relevant if e.explicit and e.submission.source_domain.lower() in authorities
    ]
    if official:
        stances = {e.stance for e in official}
        if len(stances) == 1:
            e = official[0]
            status = (
                ClaimStatus.CONFIRMED_BY_SOURCE
                if e.stance is Stance.SUPPORTS
                else ClaimStatus.REFUTED_BY_SOURCE
            )
            return Decision(
                status,
                (Reason("authority_statement", {"source": e.submission.source_domain}),),
                authority=e.submission.source_domain,
                forward_count=forwards,
                location=location,
            )
        return Decision(
            ClaimStatus.UNCONFIRMED,
            (Reason("authorities_conflict"),),
            forward_count=forwards,
            location=location,
        )

    usable = [e for e in relevant if eligible(e.submission, min_reputation)]
    by_id = {e.submission.id: e for e in usable}
    sup = [e.submission for e in usable if e.stance is Stance.SUPPORTS]
    opp = [e.submission for e in usable if e.stance is Stance.OPPOSES]
    sup_origins = independent_origins(sup)
    opp_origins = independent_origins(opp)
    count = len(sup_origins)

    reasons: list[Reason] = []
    if not sup_origins:
        reasons.append(Reason("no_supporting_evidence"))
    elif count == 1:
        reasons.append(Reason("single_origin"))
    if sup_origins and all(o.forwards_only for o in sup_origins):
        reasons.append(Reason("forwards_only", {"forwards": forwards}))
    if opp_origins:
        reasons.append(Reason("conflicting_evidence", {"opposing_origins": len(opp_origins)}))

    sup_times = _origin_times(sup_origins, by_id)
    if count >= 2 and len(sup_times) < 2:
        reasons.append(Reason("missing_observation_time"))
    elif count >= 2 and not _within_window(sup_times, window):
        reasons.append(Reason("outside_time_window", {"hours": window.total_seconds() / 3600}))

    if not reasons:
        return Decision(
            ClaimStatus.CORROBORATED,
            (Reason("independent_sources_agree", {"origins": count}),),
            origin_count=count,
            forward_count=forwards,
            location=location,
        )
    return Decision(
        ClaimStatus.UNCONFIRMED,
        tuple(reasons),
        origin_count=count,
        forward_count=forwards,
        location=location,
    )


def is_material_change(prev: Decision | None, new: Decision) -> bool:
    """Only status, source count, contradictions or location changes count as material."""
    if prev is None:
        return True
    return (
        prev.status != new.status
        or prev.origin_count != new.origin_count
        or prev.location != new.location
        or ("conflicting_evidence" in prev.reason_codes)
        != ("conflicting_evidence" in new.reason_codes)
        or prev.diffs != new.diffs
    )
