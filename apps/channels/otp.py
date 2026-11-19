"""Phone OTP for participants who upload evidence (agents, observers, verifiers)."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core import privacy
from apps.core.ratelimit import hit

from .messages import render
from .outbox import queue_message

TTL = dt.timedelta(minutes=5)
MAX_ATTEMPTS = 5


class OtpCode(models.Model):
    phone_hmac = models.CharField(max_length=64, db_index=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "channels"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"OTP {self.phone_hmac[:8]}"


class OtpError(ValueError):
    pass


def _hash(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def request_otp(raw_phone: str, language: str = "en") -> None:
    e164 = privacy.normalize_ng_phone(raw_phone)
    key = privacy.phone_hmac(e164)
    if not hit(f"otp:{key}", 3, 600):
        raise OtpError("Too many codes requested. Try again in 10 minutes.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpCode.objects.create(
        phone_hmac=key, code_hash=_hash(code), expires_at=timezone.now() + TTL
    )
    body, lang = render("otp.code", language, app=settings.APP_NAME, code=code)
    queue_message(to_phone=e164, body=body, language=lang, dedupe_key=f"otp:{otp.pk}")


def verify_otp(raw_phone: str, code: str) -> bool:
    key = privacy.phone_hmac(privacy.normalize_ng_phone(raw_phone))
    otp = OtpCode.objects.filter(phone_hmac=key, used_at__isnull=True).first()
    if otp is None or otp.expires_at < timezone.now() or otp.attempts >= MAX_ATTEMPTS:
        return False
    otp.attempts += 1
    ok = hmac.compare_digest(otp.code_hash, _hash((code or "").strip()))
    if ok:
        otp.used_at = timezone.now()
    otp.save(update_fields=["attempts", "used_at"])
    return ok
