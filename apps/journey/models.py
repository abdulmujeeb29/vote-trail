from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import Participant
from apps.geo.models import PollingUnit


class CheckIn(models.Model):
    """Election-day status for a polling unit, from officials (verified) or the crowd."""

    class Kind(models.TextChoices):
        OPENED = "opened", _("Polling unit opened")
        MATERIALS = "materials", _("Materials arrived")
        BVAS_OK = "bvas_ok", _("BVAS working")
        BVAS_FAIL = "bvas_fail", _("BVAS not working")
        QUEUE_LONG = "queue_long", _("Long queue")
        NOT_OPEN = "not_open", _("Not open yet")

    polling_unit = models.ForeignKey(PollingUnit, on_delete=models.CASCADE, related_name="checkins")
    participant = models.ForeignKey(Participant, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    official = models.BooleanField(default=False)
    visitor_id = models.CharField(max_length=64, blank=True)
    is_demo = models.BooleanField(default=False)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.polling_unit.code} {self.kind}"


class VoterProfile(models.Model):
    """One profile per browser. Every screen reads from here, so everything stays in sync."""

    visitor_id = models.CharField(max_length=64, unique=True)
    participant = models.ForeignKey(Participant, null=True, blank=True, on_delete=models.SET_NULL)
    language = models.CharField(max_length=4, default="en")
    polling_unit = models.ForeignKey(
        PollingUnit, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    registered = models.BooleanField(default=False)
    pvc_collected = models.BooleanField(default=False)
    seen_move = models.BooleanField(default=False, help_text="User acknowledged the relocation.")
    setup_done_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile {self.visitor_id[:8]}"

    @property
    def unit(self) -> PollingUnit | None:
        """Where the voter actually votes (follows relocations)."""
        return self.polling_unit.current if self.polling_unit else None

    @property
    def moved(self) -> bool:
        return bool(self.polling_unit and self.unit and self.unit.pk != self.polling_unit.pk)

    @property
    def phone_on_file(self) -> bool:
        return bool(self.participant and self.participant.phone_hmac)
