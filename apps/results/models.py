from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.models import Participant
from apps.elections.models import Election
from apps.geo.models import PollingUnit


def upload_path(instance: ResultUpload, filename: str) -> str:
    return f"ec8a/{instance.election_id}/{instance.sha256[:2]}/{instance.sha256}.jpg"


def irev_path(instance: IrevSheet, filename: str) -> str:
    return f"irev/{instance.election_id}/{instance.polling_unit_id}.jpg"


class Extraction(models.Model):
    """One AI reading of one sheet image. Reused when image, model and prompt match."""

    image_sha256 = models.CharField(max_length=64, db_index=True)
    schema_version = models.CharField(max_length=20)
    prompt_version = models.CharField(max_length=30)
    model = models.CharField(max_length=80)
    raw = models.JSONField(help_text="Validated model output (per-field value/confidence).")
    figures = models.JSONField(help_text="Normalised figures used by the trust rules.")
    low_confidence_fields = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("image_sha256", "schema_version", "prompt_version", "model")]

    def __str__(self) -> str:
        return f"Extraction {self.image_sha256[:10]} ({self.model})"


class ResultUpload(models.Model):
    class Source(models.TextChoices):
        APP = "app", "In-app camera"
        SMS = "sms", "SMS figures"

    class State(models.TextChoices):
        RECEIVED = "received", "Received"
        CHECKING = "checking", "Checking"
        CHECKED = "checked", "Checked"
        REJECTED = "rejected", "Rejected"

    election = models.ForeignKey(Election, on_delete=models.PROTECT)
    polling_unit = models.ForeignKey(PollingUnit, on_delete=models.PROTECT, related_name="uploads")
    participant = models.ForeignKey(Participant, null=True, blank=True, on_delete=models.SET_NULL)
    visitor_id = models.CharField(max_length=64, blank=True)
    device_id = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.APP)
    image = models.ImageField(upload_to=upload_path, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    phash = models.CharField(max_length=32, blank=True)
    in_app_capture = models.BooleanField(default=False)
    captured_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    sms_figures = models.JSONField(null=True, blank=True)
    extraction = models.ForeignKey(Extraction, null=True, blank=True, on_delete=models.SET_NULL)
    flags = models.JSONField(default=list)
    state = models.CharField(max_length=10, choices=State.choices, default=State.RECEIVED)
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["received_at", "id"]

    def __str__(self) -> str:
        return f"Upload {self.pk} for {self.polling_unit.code}"

    @property
    def participant_key(self) -> str:
        if self.participant and self.participant.phone_hmac:
            return self.participant.phone_hmac
        return self.visitor_id


class IrevSheet(models.Model):
    """INEC's IReV upload for a PU. Read through the same extractor as citizen photos."""

    election = models.ForeignKey(Election, on_delete=models.PROTECT)
    polling_unit = models.ForeignKey(PollingUnit, on_delete=models.PROTECT, related_name="irev")
    image = models.ImageField(upload_to=irev_path, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    extraction = models.ForeignKey(Extraction, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(blank=True)
    is_mock = models.BooleanField(default=True)

    class Meta:
        unique_together = [("election", "polling_unit")]

    def __str__(self) -> str:
        return f"IReV {self.polling_unit.code}"


class ResultCheck(models.Model):
    """Immutable revision of the public result status for one PU."""

    election = models.ForeignKey(Election, on_delete=models.PROTECT)
    polling_unit = models.ForeignKey(PollingUnit, on_delete=models.PROTECT, related_name="checks")
    revision = models.PositiveIntegerField()
    status = models.CharField(max_length=16)
    reasons = models.JSONField(default=list)
    origin_count = models.PositiveIntegerField(default=0)
    cross_party = models.BooleanField(default=False)
    diffs = models.JSONField(default=dict)
    citizen_figures = models.JSONField(null=True, blank=True)
    irev_figures = models.JSONField(null=True, blank=True)
    upload_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("election", "polling_unit", "revision")]
        ordering = ["-revision"]

    def __str__(self) -> str:
        return f"{self.polling_unit.code} r{self.revision} {self.status}"

    def save(self, *args, **kwargs) -> None:
        if self.pk is not None:
            raise RuntimeError("ResultCheck revisions are immutable.")
        super().save(*args, **kwargs)
