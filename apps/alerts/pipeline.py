from apps.jobs.queue import handler

from .models import Alert, Announcement
from .services import deliver, process


@handler("alerts.process")
def process_job(payload: dict) -> dict:
    ann = process(Announcement.objects.get(pk=payload["announcement_id"]))
    return {"state": ann.state, "affected": len((ann.extracted or {}).get("affected", []))}


@handler("alerts.deliver")
def deliver_job(payload: dict) -> dict:
    return {"sent": deliver(Alert.objects.get(pk=payload["alert_id"]))}
