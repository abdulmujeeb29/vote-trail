"""Idempotent seed: a real FCT sample from INEC's locator, plus labelled demo data."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction

from apps.core.models import AuditLog
from apps.elections.models import Election, ElectionParty, Party

from .models import LGA, PollingUnit, State, Ward

FIXTURE = Path(settings.BASE_DIR) / "fixtures" / "geo" / "fct_sample.json"
LAGOS_TZ = ZoneInfo("Africa/Lagos")

# Approximate ward centroids (labelled approximate in the UI).
_WARD_CENTRES = {
    "37/06/01": (9.0579, 7.4951),  # City Centre, AMAC
    "37/06/02": (9.0279, 7.4881),  # Garki
    "37/02/01": (9.2827, 7.3811),  # Bwari Central
    "37/02/02": (9.2936, 7.3929),  # Kuduru
}

# Amaka's polling unit moves (demo scenario, labelled as such).
DEMO_RELOCATION = ("37/06/02/002", "37/06/02/004")

DEMO_PARTIES = [
    ("PA", "Party A (demo)"),
    ("PB", "Party B (demo)"),
    ("PC", "Party C (demo)"),
    ("PD", "Party D (demo)"),
]


_ROMAN = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)$", re.I)
_KEEP_UPPER = {"FCT", "LEA", "FGGC", "GSS", "CDS", "FSP", "JAMB", "UBE", "LGEA", "NYSC"}


def smart_title(text: str) -> str:
    """Title-case INEC's UPPERCASE names without mangling roman numerals or acronyms."""

    def word(w: str) -> str:
        core = w.strip(".,/()")
        if _ROMAN.match(core) or core.upper().replace(".", "") in _KEEP_UPPER:
            return w.upper()
        if "'" in w:
            head, _, tail = w.partition("'")
            return head.capitalize() + "'" + tail.lower()
        return w.capitalize()

    text = re.sub(r"\s+", " ", text).strip()
    return "/".join(" ".join(word(w) for w in part.split(" ")) for part in text.split("/"))


def _split(label: str) -> tuple[str, str]:
    code, _, name = label.partition(" - ")
    return code.strip(), smart_title(name)


def _offset(code: str) -> tuple[float, float]:
    h = hashlib.sha256(code.encode()).digest()
    return (h[0] - 128) / 128 * 0.004, (h[1] - 128) / 128 * 0.004


def _registered(code: str) -> int:
    return 600 + int(hashlib.sha256(code.encode()).hexdigest()[:4], 16) % 700


@transaction.atomic
def seed() -> dict[str, int]:
    data = json.loads(FIXTURE.read_text())
    source = "https://cvr.inecnigeria.org/pu"
    state, _ = State.objects.update_or_create(
        code=data["state"]["code"], defaults={"name": data["state"]["name"]}
    )
    counts = {"lgas": 0, "wards": 0, "pus": 0}
    for lga_d in data["lgas"]:
        lcode, lname = _split(lga_d["label"])
        lga, _ = LGA.objects.update_or_create(
            code=f"{state.code}/{lcode}", defaults={"state": state, "name": lname}
        )
        counts["lgas"] += 1
        for ward_d in lga_d["wards"]:
            wcode, wname = _split(ward_d["label"])
            ward, _ = Ward.objects.update_or_create(
                code=f"{lga.code}/{wcode}", defaults={"lga": lga, "name": wname}
            )
            counts["wards"] += 1
            clat, clng = _WARD_CENTRES.get(ward.code, (9.06, 7.49))
            for pu_d in ward_d["pus"]:
                pcode, pname = _split(pu_d["label"])
                code = f"{ward.code}/{pcode}"
                dlat, dlng = _offset(code)
                PollingUnit.objects.update_or_create(
                    code=code,
                    defaults={
                        "ward": ward,
                        "name": pname,
                        "lat": round(clat + dlat, 6),
                        "lng": round(clng + dlng, 6),
                        "coordinates_approximate": True,
                        "registered_voters": _registered(code),
                        "source_url": source,
                        "is_mock": False,
                    },
                )
                counts["pus"] += 1

    old_code, new_code = DEMO_RELOCATION
    old = PollingUnit.objects.get(code=old_code)
    new = PollingUnit.objects.get(code=new_code)
    if old.status != PollingUnit.Status.RELOCATED:
        old.status = PollingUnit.Status.RELOCATED
        old.relocated_to = new
        old.relocated_at = dt.datetime(2027, 1, 10, 9, 0, tzinfo=LAGOS_TZ)
        old.save()
        AuditLog.record(
            actor="system:seed",
            action="geo.pu_relocated",
            obj=old,
            after={"relocated_to": new.code},
            detail={"demo_scenario": True},
        )
    new.accessibility_notes = "Ramp at the main gate. Ask for the assisted-voting desk."
    new.landmark = "Opposite the old dispensary, Garki Village"
    new.save()

    election, _ = Election.objects.update_or_create(
        slug="presidential-2027-demo",
        defaults={
            "name": "Presidential election 2027 (demo)",
            "kind": Election.Kind.PRESIDENTIAL,
            "date": dt.date(2027, 1, 16),
            "polls_open": dt.datetime(2027, 1, 16, 8, 30, tzinfo=LAGOS_TZ),
            "window_end": dt.datetime(2027, 1, 17, 23, 59, tzinfo=LAGOS_TZ),
            "status": Election.Status.UPCOMING,
            "is_mock": True,
        },
    )
    for order, (acr, name) in enumerate(DEMO_PARTIES, start=1):
        party, _ = Party.objects.update_or_create(
            acronym=acr, defaults={"name": name, "is_mock": True}
        )
        ElectionParty.objects.update_or_create(
            election=election, party=party, defaults={"ballot_order": order}
        )
    return counts
