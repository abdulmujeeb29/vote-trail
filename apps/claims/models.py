from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import Participant


class Category(models.TextChoices):
    VOTE_BUYING = "vote_buying", _("Vote buying")
    VIOLENCE = "violence", _("Violence")
    LATE_OFFICIALS = "late_officials", _("Officials late")
    MISSING_MATERIALS = "missing_materials", _("Missing materials")
    BVAS_FAILURE = "bvas_failure", _("BVAS failure")
    PU_RELOCATION = "pu_relocation", _("Polling unit moved")
    RESULTS = "results", _("Results")
    OTHER = "other", _("Other")


class Claim(models.Model):
    """A rumour or incident. Many reports can point to one claim."""

    text = models.TextField(help_text="First report's text, as written.")
    simhash = models.CharField(max_length=20, db_index=True)
    category = models.CharField(max_length=24, choices=Category.choices, default=Category.OTHER)
    location_code = models.CharField(max_length=12, blank=True, help_text="PU/ward/LGA code")
    location_label = models.CharField(max_length=160, blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.text[:60]

    @property
    def latest(self) -> ClaimAssessment | None:
        return self.assessments.order_by("-revision").first()


class Report(models.Model):
    class Source(models.TextChoices):
        APP = "app", "App"
        SMS = "sms", "SMS"
        VOICE = "voice", "Voice note"
        USSD = "ussd", "USSD"
        VERIFIER = "verifier", "Verifier"

    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="reports")
    text = models.TextField()
    simhash = models.CharField(max_length=20)
    participant = models.ForeignKey(Participant, null=True, blank=True, on_delete=models.SET_NULL)
    visitor_id = models.CharField(max_length=64, blank=True)
    device_id = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.APP)
    is_forward = models.BooleanField(default=False)
    forward_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    observed_at = models.DateTimeField(null=True, blank=True, help_text="Never defaulted to now.")
    language = models.CharField(max_length=4, default="en")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"Report {self.pk} on claim {self.claim_id}"


class EvidenceItem(models.Model):
    class Kind(models.TextChoices):
        REPORT = "report", "Citizen report"
        VERIFIER = "verifier", "Verifier"
        WEB = "web", "Public source"

    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="evidence")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    report = models.OneToOneField(Report, null=True, blank=True, on_delete=models.CASCADE)
    participant = models.ForeignKey(Participant, null=True, blank=True, on_delete=models.SET_NULL)
    url = models.URLField(max_length=500, blank=True)
    domain = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=300, blank=True)
    excerpt = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    # Filled from validated AI analysis:
    stance = models.CharField(max_length=12, blank=True)
    quote = models.TextField(blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    explicit = models.BooleanField(default=False)
    analysis_valid = models.BooleanField(default=False)
    analysed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        unique_together = [("claim", "content_hash")]

    def __str__(self) -> str:
        return f"{self.kind} evidence {self.pk}"


class ClaimAssessment(models.Model):
    """Immutable revision of a claim's public status."""

    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="assessments")
    revision = models.PositiveIntegerField()
    status = models.CharField(max_length=24)
    reasons = models.JSONField(default=list)
    origin_count = models.PositiveIntegerField(default=0)
    forward_count = models.PositiveIntegerField(default=0)
    authority = models.CharField(max_length=120, blank=True)
    evidence_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("claim", "revision")]
        ordering = ["-revision"]

    def __str__(self) -> str:
        return f"Claim {self.claim_id} r{self.revision} {self.status}"

    def save(self, *args, **kwargs) -> None:
        if self.pk is not None:
            raise RuntimeError("Assessments are immutable.")
        super().save(*args, **kwargs)


class WebSearchCache(models.Model):
    query_hash = models.CharField(max_length=64)
    day = models.DateField()
    query = models.CharField(max_length=300)
    results = models.JSONField()

    class Meta:
        unique_together = [("query_hash", "day")]

    def __str__(self) -> str:
        return self.query
