"""Mock IReV sheets for the demo scenario. Always labelled mock; images say SPECIMEN."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile

from apps.elections.models import Election
from apps.geo.models import PollingUnit
from apps.jobs.queue import enqueue

from .imaging import clean_image, sha256_hex
from .models import IrevSheet
from .synth import SheetSpec, render

LAGOS = ZoneInfo("Africa/Lagos")
WALL = {"PA": 214, "PB": 187, "PC": 43, "PD": 12}

# (pu_code, parties on IReV, cancelled). Amaka's new PU shows PB 287 on IReV vs 187 on the wall.
SCENARIO = [
    ("37/06/02/004", {**WALL, "PB": 287}, False),
    ("37/06/01/001", {"PA": 301, "PB": 122, "PC": 66, "PD": 9}, False),
    ("37/06/01/003", {"PA": 150, "PB": 140, "PC": 20, "PD": 4}, True),
]


def seed_irev(election: Election) -> list[IrevSheet]:
    out = []
    for i, (code, parties, cancelled) in enumerate(SCENARIO):
        pu = PollingUnit.objects.select_related("ward__lga").get(code=code)
        spec = SheetSpec(
            pu_code=code,
            pu_name=pu.name,
            ward=pu.ward.name,
            lga=pu.ward.lga.name,
            parties=parties,
            registered=pu.registered_voters or 900,
            cancelled=cancelled,
            seed=500 + i,
            damage="light",
        )
        spec.registered = max(spec.registered, sum(parties.values()) + 120)
        img = clean_image(render(spec))
        sheet, _ = IrevSheet.objects.get_or_create(election=election, polling_unit=pu)
        sheet.sha256 = sha256_hex(img)
        sheet.is_mock = True
        sheet.uploaded_at = dt.datetime(2027, 1, 16, 21, 40, tzinfo=LAGOS)
        sheet.source_url = ""
        sheet.extraction = None
        sheet.image.save(f"{pu.url_code}.jpg", ContentFile(img), save=False)
        sheet.save()
        enqueue("results.extract_irev", {"irev_id": sheet.pk})
        out.append(sheet)
    return out
