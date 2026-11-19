"""Notification gateway: outbox (default, simulated) or Africa's Talking (real)."""

from __future__ import annotations

import logging
from typing import Protocol

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import privacy
from apps.core.models import Participant
from apps.jobs.queue import enqueue, handler

from .models import OutboxMessage

log = logging.getLogger(__name__)
SMS_MAX = 459  # 3 concatenated GSM segments


class Gateway(Protocol):
    name: str

    def send(self, msg: OutboxMessage, to: str) -> str: ...


class OutboxGateway:
    """Delivery is the outbox row itself; the phone simulator reads it."""

    name = "outbox"

    def send(self, msg: OutboxMessage, to: str) -> str:
        return f"outbox-{msg.pk}"


class AfricasTalkingGateway:  # pragma: no cover - requires a live account
    name = "africastalking"

    def send(self, msg: OutboxMessage, to: str) -> str:
        import httpx

        if not settings.AT_API_KEY:
            raise RuntimeError("AT_API_KEY is not set")
        base = (
            "https://api.sandbox.africastalking.com"
            if settings.AT_USERNAME == "sandbox"
            else "https://api.africastalking.com"
        )
        resp = httpx.post(
            f"{base}/version1/messaging",
            data={"username": settings.AT_USERNAME, "to": to, "message": msg.body},
            headers={"apiKey": settings.AT_API_KEY, "Accept": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        return str(resp.json()["SMSMessageData"]["Recipients"][0].get("messageId", ""))


def gateway() -> Gateway:
    return (
        AfricasTalkingGateway() if settings.NOTIFY_BACKEND == "africastalking" else OutboxGateway()
    )


def queue_message(
    *,
    to_phone: str,
    body: str,
    dedupe_key: str,
    participant: Participant | None = None,
    channel: str = OutboxMessage.Channel.SMS,
    language: str = "en",
    audio_url: str = "",
) -> OutboxMessage | None:
    """Queue one message. The same dedupe_key never sends twice. Returns None if duplicate."""
    e164 = privacy.normalize_ng_phone(to_phone)
    try:
        with transaction.atomic():
            msg = OutboxMessage.objects.create(
                participant=participant,
                to_hmac=privacy.phone_hmac(e164),
                to_encrypted=privacy.encrypt(e164),
                channel=channel,
                language=language,
                body=body[:SMS_MAX],
                audio_url=audio_url,
                dedupe_key=dedupe_key[:120],
                backend=gateway().name,
            )
    except IntegrityError:
        return None
    enqueue("channels.send", {"message_id": msg.pk})
    return msg


@handler("channels.send")
def send_message(payload: dict) -> dict:
    msg = OutboxMessage.objects.get(pk=payload["message_id"])
    if msg.state == OutboxMessage.State.SENT:
        return {"state": "already_sent"}
    ref = gateway().send(msg, privacy.decrypt(msg.to_encrypted))
    msg.state = OutboxMessage.State.SENT
    msg.provider_ref = ref
    msg.sent_at = timezone.now()
    msg.save(update_fields=["state", "provider_ref", "sent_at"])
    return {"state": "sent", "ref": ref}
