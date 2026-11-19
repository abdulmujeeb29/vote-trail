"""Announcements → affected PUs → alerts to exactly the subscribed voters."""

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.channels.messages import render
from apps.channels.models import OutboxMessage
from apps.channels.outbox import queue_message
from apps.core.models import AuditLog, Role
from apps.geo.codes import InvalidPUCode, normalize_pu_code
from apps.geo.models import PollingUnit
from apps.jobs.queue import enqueue

from .extract import get_reader, squash
from .models import Alert, Announcement, Subscription

# Languages with a text-to-speech voice. Hausa has none yet (ElevenLabs), so it gets SMS only.
VOICE_LANGS = {"en", "pcm"}


def is_official(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    full = f"{host}{parsed.path}".lower()
    for src in settings.OFFICIAL_ANNOUNCEMENT_SOURCES:
        src = src.lower().removeprefix("www.")
        if "/" in src:
            if full.startswith(src):
                return True
        elif host == src or host.endswith("." + src):
            return True
    return False


def ingest(*, source_url: str, text: str, is_mock: bool = False) -> Announcement:
    if not source_url:
        raise ValueError("A source link is required.")
    ann = Announcement.objects.create(
        source_url=source_url, text=text[:20000], is_mock=is_mock, official=is_official(source_url)
    )
    AuditLog.record(
        actor="system",
        action="alerts.announcement_received",
        obj=ann,
        after={"official": ann.official},
    )
    enqueue("alerts.process", {"announcement_id": ann.pk})
    return ann


def process(ann: Announcement) -> Announcement:
    raw = get_reader().read(ann.text)
    errors, affected = [], []
    body = squash(ann.text)
    for row in raw.get("affected") or []:
        quote = row.get("quote") or ""
        if not quote or squash(quote) not in body:
            errors.append(f"quote_not_found:{row.get('pu_code')}")
            continue
        try:
            code = normalize_pu_code(row["pu_code"])
            new = normalize_pu_code(row["new_pu_code"]) if row.get("new_pu_code") else None
        except InvalidPUCode:
            errors.append(f"bad_code:{row.get('pu_code')}")
            continue
        if not PollingUnit.objects.filter(code=code).exists():
            errors.append(f"unknown_pu:{code}")
            continue
        if new and not PollingUnit.objects.filter(code=new).exists():
            errors.append(f"unknown_new_pu:{new}")
            continue
        affected.append({"pu_code": code, "new_pu_code": new, "quote": quote})
    ann.kind = raw.get("kind", "other")
    ann.extracted = {"affected": affected}
    ann.errors = errors
    ann.state = (
        Announcement.State.APPLIED
        if ann.official and affected
        else Announcement.State.PENDING_APPROVAL
    )
    ann.save()
    if ann.state == Announcement.State.APPLIED:
        apply(ann, actor="system:allowlist")
    return ann


@transaction.atomic
def apply(ann: Announcement, *, actor: str) -> list[Alert]:
    alerts = []
    for row in (ann.extracted or {}).get("affected", []):
        pu = PollingUnit.objects.get(code=row["pu_code"])
        new = (
            PollingUnit.objects.filter(code=row["new_pu_code"]).first()
            if row["new_pu_code"]
            else None
        )
        if ann.kind == "pu_relocation" and new is not None:
            before = {"status": pu.status, "relocated_to": pu.relocated_to_id}
            pu.status, pu.relocated_to, pu.relocated_at = (
                PollingUnit.Status.RELOCATED,
                new,
                timezone.now(),
            )
            pu.save(update_fields=["status", "relocated_to", "relocated_at"])
            AuditLog.record(
                actor=actor,
                action="geo.pu_relocated",
                obj=pu,
                before=before,
                after={"relocated_to": new.code, "announcement": ann.pk},
            )
        alert, _ = Alert.objects.get_or_create(
            announcement=ann, polling_unit=pu, defaults={"kind": ann.kind, "new_polling_unit": new}
        )
        alerts.append(alert)
    if ann.state != Announcement.State.APPLIED:
        ann.state = Announcement.State.APPLIED
        ann.approved_by = actor
        ann.save(update_fields=["state", "approved_by"])
    for alert in alerts:
        transaction.on_commit(lambda a=alert: enqueue("alerts.deliver", {"alert_id": a.pk}))
    return alerts


def deliver(alert: Alert) -> int:
    """Send to exactly the voters subscribed to the affected PU. Re-runs never duplicate."""
    if alert.kind != "pu_relocation" or alert.new_polling_unit is None:
        return 0
    new = alert.new_polling_unit
    sent = 0
    subs = Subscription.objects.filter(polling_unit=alert.polling_unit, active=True)
    for sub in subs.select_related("participant"):
        phone = sub.participant.phone
        if not phone:
            continue
        body, lang = render(
            "pu.relocated",
            sub.language,
            app=settings.APP_NAME,
            old=alert.polling_unit.code,
            new=new.code,
            new_name=new.name,
            landmark=new.landmark or new.ward.name,
            source=urlparse(alert.announcement.source_url).netloc,
        )
        channels = []
        if sub.sms:
            channels.append(OutboxMessage.Channel.SMS)
        wants_voice = sub.voice or sub.participant.role == Role.COMMUNITY_LEADER
        if wants_voice and lang in VOICE_LANGS:
            channels.append(OutboxMessage.Channel.VOICE)
        elif wants_voice and not channels:
            channels.append(OutboxMessage.Channel.SMS)  # no voice in this language: text instead
        for ch in channels:
            msg = queue_message(
                to_phone=phone,
                body=body,
                language=lang,
                channel=ch,
                participant=sub.participant,
                dedupe_key=f"alert:{alert.pk}:{sub.participant_id}:{ch}",
            )
            if msg is not None:
                sent += 1
                if ch == OutboxMessage.Channel.VOICE:
                    enqueue("voice.tts_for_message", {"message_id": msg.pk})
    return sent
