"""Build the Amaka demo pack by running the REAL pipeline once (live AI), then saving outputs.

Runs in a throwaway database so the working DB is untouched. Playback (/demo/) reads only the
saved pack: no AI, search or SMS calls during the demo.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

LAGOS = ZoneInfo("Africa/Lagos")
OUT = Path(settings.BASE_DIR) / "static" / "demo"
AMAKA = "+2348031234567"
OLD, NEW = "37/06/02/002", "37/06/02/004"
WALL = {"PA": 214, "PB": 187, "PC": 43, "PD": 12}
RUMOUR = (
    "BREAKING!! They are buying votes with 5000 naira at Garki ward polling units in "
    "Abuja right now. Pls share before they delete it"
)
NOTICE = (
    "INDEPENDENT NATIONAL ELECTORAL COMMISSION. NOTICE (DEMO). Relocation of polling unit: "
    "voters registered at polling unit 37/06/02/002 (Garki Village/Near Da'a Social Club) "
    "will vote at 37/06/02/004 (Garki Village II/New Pri. Sch.) to improve access."
)


def _display_copy(data: bytes, dest: Path, width: int = 720) -> None:
    """Small, fast copy for the replay page (the evidence pack keeps the originals)."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((width, width * 2))
    img.save(dest, format="JPEG", quality=72, optimize=True, progressive=True)


def build(log=print) -> dict:
    from apps.alerts.models import Subscription
    from apps.alerts.services import ingest
    from apps.channels import ussd
    from apps.channels.models import OutboxMessage
    from apps.claims.models import Claim
    from apps.claims.services import submit_report
    from apps.claims.verdicts import render as verdict
    from apps.core.models import Participant
    from apps.elections.models import Election
    from apps.geo.models import PollingUnit
    from apps.jobs.queue import run_pending
    from apps.journey.models import CheckIn
    from apps.journey.status import day_status
    from apps.results import presenters
    from apps.results.demo_irev import seed_irev
    from apps.results.evidence import build_pack
    from apps.results.imaging import clean_image
    from apps.results.models import IrevSheet, ResultCheck, ResultUpload
    from apps.results.services import accept_upload
    from apps.results.synth import SheetSpec, render

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    pack: dict = {
        "version": 1,
        "built_at": timezone.now().isoformat(),
        "model": settings.AZURE_OPENAI_DEPLOYMENT,
        "steps": {},
    }

    # Amaka subscribes to her (old) polling unit in Pidgin, with voice notes.
    amaka = Participant(display_name="Amaka", language="pcm")
    amaka.set_phone(AMAKA)
    amaka.save()
    old = PollingUnit.objects.get(code=OLD)
    new = PollingUnit.objects.get(code=NEW)
    old.status, old.relocated_to = PollingUnit.Status.ACTIVE, None  # the notice will move it
    old.save()
    Subscription.objects.create(participant=amaka, polling_unit=old, language="pcm", voice=True)

    # 1. Official notice → AI extraction → allowlist → alert (SMS + voice note).
    log("1/5 relocation notice")
    ingest(source_url="https://www.inecnigeria.org/demo-notice", text=NOTICE, is_mock=True)
    run_pending()
    sms = OutboxMessage.objects.filter(participant=amaka, channel="sms").first()
    voice = OutboxMessage.objects.filter(participant=amaka, channel="voice").first()
    audio_name = ""
    if voice and voice.audio_url:
        src = Path(settings.MEDIA_ROOT) / voice.audio_url.replace(settings.MEDIA_URL, "", 1)
        audio_name = "relocation-pcm.mp3"
        shutil.copy(src, OUT / audio_name)
    pack["steps"]["alert"] = {
        "notice": NOTICE,
        "sms": sms.body if sms else "",
        "audio": f"/static/demo/{audio_name}" if audio_name else "",
        "old": OLD,
        "new": NEW,
        "new_name": new.name,
        "landmark": new.landmark,
        "access": new.accessibility_notes,
    }

    # 2. USSD in Pidgin: language, then "my polling unit".
    log("2/5 ussd")
    screens = []
    for text in ["", "5", "5*2", "", "1", "1*370602002"]:
        screens.append(
            {
                "input": text.split("*")[-1] if text else "*384*2027#",
                "screen": ussd.handle("demo", AMAKA, text),
            }
        )
    pack["steps"]["ussd"] = screens

    # 3. Election morning: official check-ins.
    log("3/5 morning")
    official = Participant(role="official", verified_at=timezone.now())
    official.set_phone("+2348030000040")
    official.save()
    morning = dt.datetime(2027, 1, 16, 9, 40, tzinfo=LAGOS)
    for kind, minutes in (("materials", -25), ("opened", 0), ("bvas_ok", 2)):
        CheckIn.objects.create(
            polling_unit=new,
            participant=official,
            kind=kind,
            official=True,
            at=morning + dt.timedelta(minutes=minutes),
            is_demo=True,
        )
    status = day_status(new, now=morning + dt.timedelta(minutes=30))
    pack["steps"]["morning"] = {"headline": status.headline, "lines": status.lines}

    # 4. Results: mock IReV (PB 287) vs two agents photographing the wall sheet (PB 187).
    log("4/5 results (live extraction)")
    election = Election.objects.get(slug="presidential-2027-demo")
    seed_irev(election)
    run_pending()
    spec = SheetSpec(
        pu_code=NEW,
        pu_name=new.name,
        ward=new.ward.name,
        lga=new.ward.lga.name,
        parties=WALL,
        registered=max(new.registered_voters or 900, 560),
        seed=77,
        damage="light",
    )
    wall = clean_image(render(spec))
    _display_copy(wall, OUT / "wall-ec8a.jpg")
    irev = IrevSheet.objects.get(election=election, polling_unit=new)
    _display_copy(Path(irev.image.path).read_bytes(), OUT / "irev-ec8a.jpg")
    captured = dt.datetime(2027, 1, 16, 17, 5, tzinfo=LAGOS)
    for party, phone, seed in (("PA", "+2348030000011", 78), ("PB", "+2348030000012", 79)):
        agent = Participant(role="agent", party=party, verified_at=timezone.now())
        agent.set_phone(phone)
        agent.save()
        photo = clean_image(render(SheetSpec(**{**spec.__dict__, "seed": seed, "damage": "none"})))
        accept_upload(
            election=election,
            pu=new,
            idempotency_key=uuid.uuid4().hex,
            image_bytes=photo,
            in_app_capture=True,
            captured_at=captured.isoformat(),
            lat=str(new.lat),
            lng=str(new.lng),
            device_id=f"demo-{party}",
            visitor_id=f"demo-{party}",
            participant=agent,
            is_demo=True,
        )
    run_pending()
    check = ResultCheck.objects.filter(election=election, polling_unit=new).first()
    uploads = ResultUpload.objects.filter(polling_unit=new).select_related("extraction")
    zip_bytes = build_pack(election, new)
    (OUT / "evidence-37-06-02-004.zip").write_bytes(zip_bytes)
    pack["steps"]["results"] = {
        "status": check.status,
        "label": presenters.STATUS_LABEL[check.status],
        "explain": presenters.explain(check),
        "origins": check.origin_count,
        "cross_party": check.cross_party,
        "diffs": check.diffs,
        "citizen": check.citizen_figures,
        "irev": check.irev_figures,
        "extracted": [u.extraction.figures["party_votes"] for u in uploads if u.extraction],
        "low_confidence": [u.extraction.low_confidence_fields for u in uploads if u.extraction],
        "wall_image": "/static/demo/wall-ec8a.jpg",
        "irev_image": "/static/demo/irev-ec8a.jpg",
        "evidence_zip": "/static/demo/evidence-37-06-02-004.zip",
        "evidence_bytes": len(zip_bytes),
    }

    # 5. Rumour: 40 forwards + public sources → verdict.
    log("5/5 rumour (live analysis + search)")
    for i in range(40):
        submit_report(
            text=RUMOUR,
            category="vote_buying",
            location_code="37/06/02",
            visitor_id=f"fwd{i}",
            device_id=f"dev{i}",
            is_demo=True,
        )
    run_pending()
    claim = Claim.objects.get()
    a = claim.latest
    sources = [
        {"title": e.title, "domain": e.domain, "stance": e.stance, "quote": e.quote[:220]}
        for e in claim.evidence.filter(kind="web", analysis_valid=True).exclude(
            stance="irrelevant"
        )[:3]
    ]
    pack["steps"]["rumour"] = {
        "text": RUMOUR,
        "status": a.status,
        "forwards": a.forward_count,
        "origins": a.origin_count,
        "en": verdict(a, "en"),
        "pcm": verdict(a, "pcm"),
        "sources": sources,
    }
    pack["build_seconds"] = round(time.time() - t0, 1)
    (OUT / "pack.json").write_text(json.dumps(pack, indent=1, ensure_ascii=False, default=str))
    return pack


def run_isolated(log=print) -> dict:
    """Run build() against a fresh temporary SQLite DB and media dir."""
    import tempfile

    from django.core.management import call_command
    from django.db import connections

    tmp = Path(tempfile.mkdtemp(prefix="vt-demo-"))
    db = connections.databases["default"]
    saved = dict(db)
    saved_media = settings.MEDIA_ROOT
    connections["default"].close()
    db.update({"ENGINE": "django.db.backends.sqlite3", "NAME": str(tmp / "demo.sqlite3")})
    settings.MEDIA_ROOT = tmp / "media"
    try:
        call_command("migrate", verbosity=0)
        call_command("seed", verbosity=0)
        return build(log)
    finally:
        connections["default"].close()
        db.clear()
        db.update(saved)
        settings.MEDIA_ROOT = saved_media
        shutil.rmtree(tmp, ignore_errors=True)
