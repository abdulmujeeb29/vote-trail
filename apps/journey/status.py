"""Election-day status per polling unit: official check-ins first, crowd reports as support."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.geo.models import PollingUnit

from .models import CheckIn

CROWD_MIN = 2  # independent crowd reports needed before we show a crowd signal
WINDOW = dt.timedelta(hours=3)


@dataclass
class DayStatus:
    headline: str
    tone: str
    lines: list[str]
    updated: dt.datetime | None


def day_status(pu: PollingUnit, now: dt.datetime | None = None) -> DayStatus:
    now = now or timezone.now()
    recent = list(pu.checkins.filter(at__gte=now - dt.timedelta(hours=14)).order_by("-at"))
    official = {}
    for c in recent:
        if c.official and c.kind not in official:
            official[c.kind] = c
    lines = []
    for kind in ("opened", "materials", "bvas_ok", "bvas_fail", "not_open"):
        c = official.get(kind)
        if c:
            lines.append(
                _("%(what)s at %(time)s (polling official)")
                % {"what": CheckIn.Kind(kind).label, "time": f"{timezone.localtime(c.at):%H:%M}"}
            )
    crowd: dict[str, set[str]] = {}
    for c in recent:
        if not c.official and c.at >= now - WINDOW:
            who = c.visitor_id or (f"p{c.participant_id}" if c.participant_id else str(c.pk))
            crowd.setdefault(c.kind, set()).add(who)
    for kind, people in crowd.items():
        if len(people) >= CROWD_MIN:
            lines.append(
                _("%(what)s: reported by %(n)d people")
                % {"what": CheckIn.Kind(kind).label, "n": len(people)}
            )
    updated = recent[0].at if recent else None
    if "bvas_fail" in official:
        return DayStatus(_("BVAS problem reported"), "warn", lines, updated)
    if "opened" in official:
        return DayStatus(
            _("Open since %(time)s")
            % {"time": f"{timezone.localtime(official['opened'].at):%H:%M}"},
            "ok",
            lines,
            updated,
        )
    if len(crowd.get("not_open", set())) >= CROWD_MIN:
        return DayStatus(_("Not open yet (crowd reports)"), "warn", lines, updated)
    return DayStatus(_("No updates yet"), "info", lines, updated)
