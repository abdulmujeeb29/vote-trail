"""Privacy services (NDPA 2023): delete-my-data."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import AuditLog, Participant


@transaction.atomic
def delete_my_data(participant: Participant) -> None:
    """Anonymise a participant. Audit digests remain; personal data is removed."""
    before = {"phone_hmac": participant.phone_hmac, "name": participant.display_name}
    participant.phone_hmac = None
    participant.phone_encrypted = ""
    participant.display_name = ""
    participant.visitor_id = ""
    participant.anonymised_at = timezone.now()
    participant.save()
    AuditLog.record(
        actor=f"participant:{participant.pk}",
        action="privacy.delete_my_data",
        obj=participant,
        before=before,
        after={"anonymised": True},
    )
