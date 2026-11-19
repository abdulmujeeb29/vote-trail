"""Profile access + the single 'do this next' decision used by every screen."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.elections.models import Election

from .models import VoterProfile

LANGS = [
    ("en", "English"),
    ("pcm", "Naijá (Pidgin)"),
    ("yo", "Yorùbá"),
    ("ha", "Hausa"),
    ("ig", "Igbo"),
]
BETA: set[str] = set()


def get_profile(request) -> VoterProfile:
    cached = getattr(request, "_vt_profile", None)
    if cached is not None:
        return cached
    profile, _ = VoterProfile.objects.select_related(
        "polling_unit__relocated_to", "polling_unit__ward__lga", "participant"
    ).get_or_create(visitor_id=request.visitor_id)
    request._vt_profile = profile
    return profile


def now() -> dt.datetime:
    """Current time; DEMO_NOW lets a demo pretend it's election day."""
    fake = getattr(settings, "DEMO_NOW", "")
    if fake:
        from django.utils.dateparse import parse_datetime

        parsed = parse_datetime(fake)
        if parsed:
            return parsed
    return timezone.now()


def election() -> Election | None:
    return Election.objects.order_by("-date").first()


def phase(e: Election | None, at: dt.datetime) -> str:
    """before | election_day | counting | after"""
    if e is None or e.polls_open is None:
        return "before"
    if at < e.polls_open:
        return "before"
    close = e.polls_open + dt.timedelta(hours=6)
    if at < close:
        return "election_day"
    if e.window_end and at <= e.window_end:
        return "counting"
    return "after"


@dataclass
class Action:
    kind: str
    title: str
    detail: str
    url: str
    cta: str
    done_post: str = ""  # optional: POST here to mark done


def next_action(p: VoterProfile, at: dt.datetime | None = None) -> Action:
    at = at or now()
    ph = phase(election(), at)
    unit = p.unit
    if unit is None:
        return Action(
            "find_pu",
            _("Find your polling unit"),
            _("Use your location or the code on your voter's card."),
            reverse("journey:setup") + "?step=2",
            _("Find it"),
        )
    if p.moved and not p.seen_move:
        return Action(
            "visit_new",
            _("Visit your new polling unit before election day"),
            _("So you know the way on the morning."),
            f"https://www.google.com/maps/dir/?api=1&destination={unit.lat},{unit.lng}",
            _("Directions"),
            done_post=reverse("journey:mark", args=["seen_move"]),
        )
    if ph == "election_day":
        return Action(
            "is_open",
            _("Is your polling unit open?"),
            _("See live check-ins from officials and voters."),
            reverse("journey:today", args=[unit.url_code]),
            _("Check now"),
        )
    if ph == "counting":
        return Action(
            "photo",
            _("Photograph the result sheet on the wall"),
            _("We compare it with IReV. Two independent photos are needed to flag a mismatch."),
            reverse("journey:verify"),
            _("Open camera"),
        )
    if ph == "after":
        return Action(
            "result",
            _("See your polling unit's result check"),
            _("Wall sheet vs IReV, with reasons."),
            reverse("results:pu_result", args=[unit.url_code]),
            _("View"),
        )
    if not p.registered:
        return Action(
            "register",
            _("Make sure you're registered"),
            _("Pre-register online, then finish in person. Only on cvr.inecnigeria.org."),
            reverse("journey:register"),
            _("How to register"),
            done_post=reverse("journey:mark", args=["registered"]),
        )
    if not p.pvc_collected:
        return Action(
            "pvc",
            _("Collect your PVC"),
            _("In person only. Only voters with a PVC can vote."),
            reverse("journey:pvc"),
            _("Where and how"),
            done_post=reverse("journey:mark", args=["pvc_collected"]),
        )
    if not p.phone_on_file:
        return Action(
            "alerts",
            _("Turn on alerts"),
            _("Get an SMS if your unit moves or a result is checked."),
            reverse("journey:setup") + "?step=3",
            _("Turn on"),
        )
    return Action(
        "rumour",
        _("Heard something? Check it before you forward it"),
        _("Forwards are not confirmation."),
        reverse("journey:verify") + "?tab=rumour",
        _("Check a rumour"),
    )


def journey(p: VoterProfile, at: dt.datetime | None = None) -> list[dict]:
    at = at or now()
    ph = phase(election(), at)
    e = election()
    day = e.date.strftime("%-d %b").upper() if e else "TBA"
    unit_state = (
        (_("MOVED"), "warn")
        if p.moved and not p.seen_move
        else ((_("SET"), "ok") if p.unit else (_("TO DO"), "info"))
    )
    return [
        {
            "title": _("Registered"),
            "tag": (_("DONE"), "ok") if p.registered else (_("TO DO"), "info"),
            "url": reverse("journey:register"),
        },
        {
            "title": _("PVC collected"),
            "tag": (_("DONE"), "ok") if p.pvc_collected else (_("TO DO"), "info"),
            "url": reverse("journey:pvc"),
        },
        {
            "title": _("Know your unit"),
            "tag": unit_state,
            "url": reverse("journey:pu", args=[p.unit.url_code])
            if p.unit
            else reverse("journey:setup") + "?step=2",
        },
        {
            "title": _("Election day"),
            "tag": (_("TODAY"), "warn")
            if ph == "election_day"
            else ((_("DONE"), "ok") if ph in ("counting", "after") else (day, "info")),
            "url": reverse("journey:today", args=[p.unit.url_code])
            if p.unit
            else reverse("journey:setup") + "?step=2",
        },
        {
            "title": _("Check the result"),
            "tag": (_("NOW"), "warn")
            if ph == "counting"
            else ((_("OPEN"), "ok") if ph == "after" else (_("AFTER COUNT"), "info")),
            "url": reverse("results:pu_result", args=[p.unit.url_code])
            if p.unit
            else reverse("journey:verify"),
        },
        {
            "title": _("Accessibility help"),
            "tag": (_("INFO"), "info"),
            "url": reverse("journey:access"),
        },
    ]


def countdown(at: dt.datetime | None = None) -> dict | None:
    e = election()
    if e is None or e.polls_open is None:
        return None
    at = at or now()
    left = e.polls_open - at
    if left.total_seconds() <= 0:
        return None
    return {
        "days": left.days,
        "hours": left.seconds // 3600,
        "minutes": (left.seconds % 3600) // 60,
        "iso": e.polls_open.isoformat(),
        "label": f"{e.date:%-d %b %Y} · {e.get_kind_display()}",
    }
