"""Plain-language wording for result statuses. Never says who won."""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import ResultCheck

STATUS_LABEL = {
    "pending": _("Pending"),
    "matches": _("Matches IReV"),
    "mismatch": _("Mismatch with IReV"),
    "needs_review": _("Needs review"),
    "cancelled": _("Result cancelled"),
}
STATUS_ICON = {
    "pending": "clock",
    "matches": "check",
    "mismatch": "alert",
    "needs_review": "eye",
    "cancelled": "x",
}
STATUS_TONE = {
    "pending": "info",
    "matches": "ok",
    "mismatch": "warn",
    "needs_review": "warn",
    "cancelled": "bad",
}


def explain(check: ResultCheck | None) -> str:
    if check is None:
        return _("No result-sheet photos yet. Results appear after counting at the polling unit.")
    n = check.origin_count
    who = ngettext("%(n)d independent upload", "%(n)d independent uploads", n) % {"n": n}
    if check.cross_party:
        who += _(", including agents from different parties")
    codes = {r["code"] for r in check.reasons}
    if check.status == "matches":
        return _("%(who)s match the sheet on IReV.") % {"who": who}
    if check.status == "mismatch":
        return _(
            "%(who)s agree with each other but differ from the sheet on IReV. "
            "Observers have been alerted."
        ) % {"who": who}
    if check.status == "cancelled":
        return _("The result sheet is endorsed 'Result Cancelled'.")
    if check.status == "pending":
        if "irev_not_uploaded" in codes:
            return _("%(who)s received. Waiting for INEC's IReV upload to compare.") % {"who": who}
        return _("Waiting for result-sheet photos from this polling unit.")
    if "single_origin_disagrees_with_irev" in codes:
        return _(
            "One upload differs from IReV. We need a second independent upload before "
            "flagging a mismatch."
        )
    if "low_confidence" in codes or "irev_low_confidence" in codes:
        return _("Part of the sheet was hard to read. A verifier will check it.")
    if any(c.startswith("arithmetic") or c.startswith("irev_arithmetic") for c in codes):
        return _("The numbers on a sheet don't add up. A verifier will check it.")
    if "citizen_origins_disagree" in codes:
        return _("Uploads from different people don't agree. A verifier will check them.")
    return _("A verifier needs to check this before we show a result status.")
