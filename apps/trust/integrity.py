"""Photo integrity checks for result-sheet uploads."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .hashing import hex_distance
from .types import Flag, Severity


@dataclass(frozen=True, slots=True)
class UploadFacts:
    pu_code: str
    in_app_capture: bool
    captured_at: dt.datetime | None
    lat: float | None
    lng: float | None
    image_sha256: str
    image_phash: str


@dataclass(frozen=True, slots=True)
class PUFacts:
    code: str
    lat: float | None
    lng: float | None


@dataclass(frozen=True, slots=True)
class PriorImage:
    pu_code: str
    image_sha256: str
    image_phash: str


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def check_integrity(
    upload: UploadFacts,
    pu: PUFacts,
    window: tuple[dt.datetime, dt.datetime] | None,
    prior_images: Iterable[PriorImage] = (),
    *,
    radius_m: int = 300,
    phash_max: int = 6,
) -> list[Flag]:
    flags: list[Flag] = []
    if not upload.in_app_capture:
        flags.append(Flag("untrusted_source", Severity.REJECT))

    for prior in prior_images:
        if prior.pu_code == upload.pu_code:
            continue
        same = prior.image_sha256 and prior.image_sha256 == upload.image_sha256
        d = hex_distance(prior.image_phash, upload.image_phash)
        if same or (d is not None and d <= phash_max):
            flags.append(Flag("reused_image", Severity.REJECT, {"other_pu": prior.pu_code}))
            break

    if window is not None:
        start, end = window
        if upload.captured_at is None or not (start <= upload.captured_at <= end):
            flags.append(
                Flag("outside_window", Severity.REVIEW, {"captured_at": str(upload.captured_at)})
            )

    if upload.lat is None or upload.lng is None:
        flags.append(Flag("no_location", Severity.INFO))
    elif pu.lat is None or pu.lng is None:
        flags.append(Flag("location_unverifiable", Severity.INFO))
    else:
        dist = _distance_m(pu.lat, pu.lng, upload.lat, upload.lng)
        if dist > radius_m:
            flags.append(Flag("too_far", Severity.REVIEW, {"distance_m": round(dist)}))
    return flags


def worst(flags: Iterable[Flag]) -> Severity | None:
    order: Mapping[Severity, int] = {Severity.REJECT: 2, Severity.REVIEW: 1, Severity.INFO: 0}
    found = [f.severity for f in flags]
    return max(found, key=order.__getitem__) if found else None
