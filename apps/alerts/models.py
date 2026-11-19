from django.db import models

from apps.core.models import Participant
from apps.geo.models import PollingUnit


class Subscription(models.Model):
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="subscriptions"
    )
    polling_unit = models.ForeignKey(
        PollingUnit, on_delete=models.CASCADE, related_name="subscriptions"
    )
    sms = models.BooleanField(default=True)
    voice = models.BooleanField(default=False)
    app = models.BooleanField(default=True)
    language = models.CharField(max_length=4, default="en")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("participant", "polling_unit")]

    def __str__(self) -> str:
        return f"{self.participant_id} → {self.polling_unit.code}"


class Announcement(models.Model):
    class State(models.TextChoices):
        RECEIVED = "received", "Received"
        PENDING_APPROVAL = "pending_approval", "Awaiting verifier approval"
        APPLIED = "applied", "Applied"
        REJECTED = "rejected", "Rejected"

    source_url = models.URLField(max_length=500)
    text = models.TextField()
    kind = models.CharField(max_length=24, blank=True)
    extracted = models.JSONField(null=True, blank=True)
    errors = models.JSONField(default=list)
    state = models.CharField(max_length=20, choices=State.choices, default=State.RECEIVED)
    official = models.BooleanField(default=False)
    is_mock = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Announcement {self.pk} ({self.state})"


class Alert(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="alerts")
    polling_unit = models.ForeignKey(PollingUnit, on_delete=models.CASCADE, related_name="alerts")
    new_polling_unit = models.ForeignKey(
        PollingUnit, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("announcement", "polling_unit")]

    def __str__(self) -> str:
        return f"{self.kind} {self.polling_unit.code}"
