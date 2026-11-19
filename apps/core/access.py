from __future__ import annotations

from .models import Participant, Role

EVIDENCE_ROLES = {Role.OBSERVER, Role.VERIFIER}


def current_participant(request) -> Participant | None:
    visitor = getattr(request, "visitor_id", "")
    if not visitor:
        return None
    return Participant.objects.filter(visitor_id=visitor, anonymised_at__isnull=True).first()


def can_export_evidence(request) -> bool:
    if request.user.is_authenticated and request.user.is_staff:
        return True
    p = current_participant(request)
    return bool(p and p.is_verified and p.role in EVIDENCE_ROLES)
