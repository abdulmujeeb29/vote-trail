"""Participants (people who interact with the platform) and the append-only audit log."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import models
from django.utils import timezone

from . import privacy


class Role(models.TextChoices):
    VOTER = "voter", "Voter"
    AGENT = "agent", "Party agent"
    OBSERVER = "observer", "Observer"
    OFFICIAL = "official", "Polling official"
    VERIFIER = "verifier", "CSO verifier"
    COMMUNITY_LEADER = "community_leader", "Community leader"


class Language(models.TextChoices):
    EN = "en", "English"
    PCM = "pcm", "Pidgin"
    YO = "yo", "Yoruba"
    HA = "ha", "Hausa"
    IG = "ig", "Igbo"


class ParticipantQuerySet(models.QuerySet):
    def by_phone(self, raw_phone: str) -> Participant | None:
        e164 = privacy.normalize_ng_phone(raw_phone)
        return self.filter(phone_hmac=privacy.phone_hmac(e164)).first()


class Participant(models.Model):
    """A person known to the platform. Anonymous voters have only a visitor_id."""

    user = models.OneToOneField(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="participant"
    )
    visitor_id = models.CharField(max_length=64, blank=True, db_index=True)
    phone_hmac = models.CharField(max_length=64, unique=True, null=True, blank=True)
    phone_encrypted = models.TextField(blank=True)
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.VOTER)
    party = models.CharField(max_length=16, blank=True, help_text="Party acronym, for agents.")
    display_name = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=4, choices=Language.choices, default=Language.EN)
    verified_at = models.DateTimeField(null=True, blank=True)
    reputation = models.IntegerField(default=0)
    anonymised_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ParticipantQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.get_role_display()} #{self.pk}"

    def set_phone(self, raw_phone: str) -> None:
        e164 = privacy.normalize_ng_phone(raw_phone)
        self.phone_hmac = privacy.phone_hmac(e164)
        self.phone_encrypted = privacy.encrypt(e164)

    @property
    def phone(self) -> str | None:
        return privacy.decrypt(self.phone_encrypted) if self.phone_encrypted else None

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


class AppendOnlyError(RuntimeError):
    pass


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> int:
        raise AppendOnlyError("Audit log is append-only.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Audit log is append-only.")


def digest(value: Any) -> str:
    if value is None:
        return ""
    raw = json.dumps(value, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class AuditLog(models.Model):
    actor = models.CharField(max_length=80, help_text="participant:<id>, system, worker, user:<id>")
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=60)
    object_id = models.CharField(max_length=64)
    before_digest = models.CharField(max_length=64, blank=True)
    after_digest = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise AppendOnlyError("Audit log is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any):
        raise AppendOnlyError("Audit log is append-only.")

    @classmethod
    def record(
        cls,
        *,
        actor: str,
        action: str,
        obj: models.Model | None = None,
        object_type: str = "",
        object_id: str = "",
        before: Any = None,
        after: Any = None,
        detail: dict | None = None,
    ) -> AuditLog:
        if obj is not None:
            object_type = object_type or obj._meta.label_lower
            object_id = object_id or str(obj.pk)
        return cls.objects.create(
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before_digest=digest(before),
            after_digest=digest(after),
            detail=detail or {},
        )
