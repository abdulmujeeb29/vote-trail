from apps.jobs.queue import handler

from .models import Claim
from .services import assess


@handler("claims.assess")
def assess_job(payload: dict) -> dict:
    claim = Claim.objects.get(pk=payload["claim_id"])
    result = assess(claim)
    latest = claim.latest
    return {"status": latest.status if latest else "unconfirmed", "changed": result is not None}
