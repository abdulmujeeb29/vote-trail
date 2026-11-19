"""Inbound SMS commands: PU <code> · CHECK <text> · RESULT <code> · STOP · R (agent figures)."""

from __future__ import annotations

import re
import uuid

from django.conf import settings

from apps.alerts.models import Subscription
from apps.claims.services import submit_report
from apps.claims.verdicts import sms_text
from apps.core.models import Participant, Role
from apps.elections.models import Election
from apps.jobs.queue import enqueue_once
from apps.results import presenters
from apps.results.models import ResultCheck, ResultUpload

from .outbox import queue_message
from .ussd import _participant, _pu

HELP = (
    "{app}: send PU <code>, CHECK <message>, RESULT <code>, or STOP. "
    "Agents: R <code> PA 120 PB 98 REJ 4"
)
_R = re.compile(r"^R\s+(?P<code>[\d/\-]+)\s+(?P<body>.+)$", re.I)
_PAIR = re.compile(r"([A-Z]{1,8})\s+(\d{1,6})")


def parse_agent_result(body: str) -> dict:
    pairs = _PAIR.findall(body.upper())
    if not pairs:
        raise ValueError("No figures found.")
    figures: dict = {"party_votes": {}, "words": {}, "cancelled": False}
    for name, value in pairs:
        if name in ("REJ", "REJECTED"):
            figures["rejected"] = int(value)
        elif name in ("ACC", "ACCREDITED"):
            figures["accredited"] = int(value)
        elif name in ("REG", "REGISTERED"):
            figures["registered"] = int(value)
        else:
            figures["party_votes"][name] = int(value)
    if figures.get("rejected") is not None:
        figures["total_valid"] = sum(figures["party_votes"].values())
        figures["total_used"] = figures["total_valid"] + figures["rejected"]
    return figures


def handle_inbound(phone: str, text: str, message_id: str = "") -> str:
    p = _participant(phone)
    lang = p.language
    text = (text or "").strip()
    cmd, _, rest = text.partition(" ")
    cmd = cmd.upper()
    reply: str
    if cmd == "PU":
        pu = _pu(rest)
        if pu is None:
            reply = "Unknown PU code."
        else:
            cur = pu.current
            reply = f"PU {pu.code}: {pu.name}."
            if cur.pk != pu.pk:
                reply += f" MOVED: vote at {cur.name} ({cur.code})."
    elif cmd == "CHECK":
        try:
            report = submit_report(
                text=rest, source="sms", is_forward=True, participant=p, language=lang
            )
            reply = f"Thanks. {sms_text(report.claim.latest, lang)}"
        except ValueError as exc:
            reply = str(exc)
    elif cmd == "RESULT":
        pu = _pu(rest)
        election = Election.objects.order_by("-date").first()
        check = (
            ResultCheck.objects.filter(election=election, polling_unit=pu).first() if pu else None
        )
        status = check.status if check else "pending"
        reply = f"PU {pu.code}: {presenters.STATUS_LABEL[status]}." if pu else "Unknown PU code."
    elif cmd == "STOP":
        n = Subscription.objects.filter(participant=p, active=True).update(active=False)
        reply = f"Stopped {n} alert subscription(s)."
    elif _R.match(text):
        reply = _agent_result(p, _R.match(text))
    else:
        reply = HELP.format(app=settings.APP_NAME)
    queue_message(
        to_phone=p.phone,
        body=reply,
        language=lang,
        participant=p,
        dedupe_key=f"reply:{message_id or uuid.uuid4().hex}",
    )
    return reply


def _agent_result(p: Participant, m: re.Match) -> str:
    if p.role not in (Role.AGENT, Role.OBSERVER) or not p.is_verified:
        return "Only verified party agents and observers can send results by SMS."
    pu = _pu(m.group("code"))
    if pu is None:
        return "Unknown PU code."
    try:
        figures = parse_agent_result(m.group("body"))
    except ValueError:
        return "Format: R <code> PA 120 PB 98 REJ 4"
    election = Election.objects.order_by("-date").first()
    upload = ResultUpload.objects.create(
        election=election,
        polling_unit=pu,
        participant=p,
        idempotency_key=uuid.uuid4().hex,
        source=ResultUpload.Source.SMS,
        sms_figures=figures,
        state=ResultUpload.State.CHECKED,
    )
    enqueue_once("results.recompute", {"election_id": election.pk, "pu_id": pu.pk})
    return f"Received figures for PU {pu.code} (upload {upload.pk})."
