"""Accept result-sheet uploads (idempotent) and expose status for a PU."""

from __future__ import annotations

import datetime as dt

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from apps.core.models import AuditLog, Participant
from apps.elections.models import Election
from apps.geo.models import PollingUnit
from apps.jobs.queue import enqueue

from . import imaging
from .models import ResultCheck, ResultUpload


class UploadError(ValueError):
    pass


def _parse_time(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    value = parse_datetime(raw)
    if value is None or value.tzinfo is None:
        raise UploadError("captured_at must be an ISO time with a timezone.")
    return value


def _parse_coord(raw: str | None, lo: float, hi: float) -> float | None:
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise UploadError("Location must be numbers.") from exc
    if not lo <= value <= hi:
        raise UploadError("Location is out of range.")
    return value


def accept_upload(
    *,
    election: Election,
    pu: PollingUnit,
    idempotency_key: str,
    image_bytes: bytes,
    in_app_capture: bool,
    captured_at: str | None,
    lat: str | None,
    lng: str | None,
    device_id: str,
    visitor_id: str,
    participant: Participant | None = None,
    is_demo: bool = False,
) -> tuple[ResultUpload, bool]:
    """Store an upload once per idempotency key. Returns (upload, created)."""
    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 64:
        raise UploadError("Missing upload key.")
    existing = ResultUpload.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return existing, False
    clean = imaging.clean_image(image_bytes)
    sha = imaging.sha256_hex(clean)
    upload = ResultUpload(
        election=election,
        polling_unit=pu,
        participant=participant,
        visitor_id=visitor_id,
        device_id=device_id[:64],
        idempotency_key=key,
        source=ResultUpload.Source.APP,
        sha256=sha,
        phash=imaging.phash_hex(clean),
        in_app_capture=in_app_capture,
        captured_at=_parse_time(captured_at),
        lat=_parse_coord(lat, -90, 90),
        lng=_parse_coord(lng, -180, 180),
        is_demo=is_demo,
    )
    upload.image.save(f"{sha}.jpg", ContentFile(clean), save=False)
    try:
        with transaction.atomic():
            upload.save()
    except IntegrityError:
        return ResultUpload.objects.get(idempotency_key=key), False
    AuditLog.record(
        actor=f"visitor:{visitor_id[:12]}",
        action="results.upload_received",
        obj=upload,
        after={"sha256": sha, "pu": pu.code},
    )
    enqueue("results.check_upload", {"upload_id": upload.pk})
    return upload, True


def latest_check(election: Election, pu: PollingUnit) -> ResultCheck | None:
    return ResultCheck.objects.filter(election=election, polling_unit=pu).first()
