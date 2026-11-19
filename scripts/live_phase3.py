"""Live checks for Phase 3 against real services. Run: uv run python scripts/live_phase3.py"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "votetrail.settings.dev")
TMP = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/live.sqlite3"
os.environ["MEDIA_ROOT"] = str(TMP / "media")

import django

django.setup()
from django.core.management import call_command

call_command("migrate", verbosity=0)
call_command("seed", verbosity=0)

from apps.alerts.models import Announcement
from apps.alerts.services import ingest
from apps.claims.models import Claim
from apps.claims.services import submit_report
from apps.claims.verdicts import render
from apps.jobs.queue import run_pending
from apps.voice import realtime, tts

report = {}


def timed(name, fn):
    t = time.time()
    try:
        out = fn()
        report[name] = {"ok": True, "seconds": round(time.time() - t, 1), "out": out}
    except Exception as exc:
        report[name] = {"ok": False, "seconds": round(time.time() - t, 1), "error": repr(exc)[:300]}


def claims_forwards():
    text = (
        "BREAKING: they are buying votes with 5000 naira at Garki ward polling units in Abuja,"
        " pls share before they delete"
    )
    for i in range(12):
        submit_report(
            text=text, category="vote_buying", visitor_id=f"v{i}", location_code="37/06/02"
        )
    run_pending()
    c = Claim.objects.get()
    v = render(c.latest, "pcm")
    return {
        "status": c.latest.status,
        "forwards": c.latest.forward_count,
        "origins": c.latest.origin_count,
        "evidence": c.evidence.count(),
        "web": c.evidence.filter(kind="web").count(),
        "valid": c.evidence.filter(analysis_valid=True).count(),
        "verdict_pcm": v,
    }


def announcement():
    text = (
        "INDEPENDENT NATIONAL ELECTORAL COMMISSION. PRESS RELEASE (DEMO). Relocation of "
        "polling unit: the Commission wishes to inform voters that polling unit 37/06/02/002 "
        "(Garki Village/Near Da'a Social Club) has been relocated to 37/06/02/004 (Garki "
        "Village II/New Pri. Sch.) to improve access. Voters should vote at the new location."
    )
    ingest(source_url="https://www.inecnigeria.org/demo-relocation-notice", text=text, is_mock=True)
    run_pending()
    a = Announcement.objects.get()
    return {"state": a.state, "kind": a.kind, "affected": a.extracted, "errors": a.errors}


def session():
    s = realtime.mint_session("pcm")
    return {
        "token_prefix": s["token"][:3],
        "rtc_url": s["rtc_url"].split("/openai")[1],
        "has_key": "api-key" in json.dumps(s),
    }


def speech():
    clip = tts.speak(
        "Dem dey share money for Garki ward five polling unit. Make una check am.", "pcm"
    )
    return {
        "bytes": clip.audio.size,
        "cached_again": tts.speak(
            "Dem dey share money for Garki ward five polling unit. Make una check am.", "pcm"
        ).pk
        == clip.pk,
        "path": clip.audio.path,
    }


def voice_note():
    mp3 = report["tts"]["out"]["path"]
    wav = TMP / "note.wav"
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", mp3, str(wav)], check=True
    )
    pcm = realtime.wav_to_pcm16(wav.read_bytes())
    return realtime.get_understander().understand(pcm)


timed("claims_forwards", claims_forwards)
timed("announcement", announcement)
timed("realtime_session", session)
timed("tts", speech)
if report["tts"]["ok"]:
    timed("voice_note", voice_note)
out = Path(__file__).resolve().parent.parent / "docs/reviews/eval/phase3_live.json"
out.write_text(json.dumps(report, indent=1, default=str))
print(json.dumps({k: (v["ok"], v["seconds"]) for k, v in report.items()}))
