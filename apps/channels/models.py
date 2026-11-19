from django.db import models
from django.utils import timezone

from apps.core.models import Participant


class OutboxMessage(models.Model):
    """Every SMS/voice message we send. In demo mode this IS the delivery (simulator reads it)."""

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        VOICE = "voice", "Voice call"

    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    participant = models.ForeignKey(Participant, null=True, blank=True, on_delete=models.SET_NULL)
    to_hmac = models.CharField(max_length=64, db_index=True)
    to_encrypted = models.TextField()
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.SMS)
    language = models.CharField(max_length=4, default="en")
    body = models.TextField()
    audio_url = models.CharField(max_length=300, blank=True)
    dedupe_key = models.CharField(max_length=120, unique=True)
    backend = models.CharField(max_length=20, default="outbox")
    state = models.CharField(max_length=8, choices=State.choices, default=State.QUEUED)
    provider_ref = models.CharField(max_length=120, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.channel} → {self.to_hmac[:8]} ({self.state})"


from .otp import OtpCode  # noqa: E402,F401  (model registration)
