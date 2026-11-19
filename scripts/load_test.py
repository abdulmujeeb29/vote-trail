"""Load sanity: N concurrent result-sheet uploads against a local production-like server.

Starts Gunicorn + 2 workers on a temp SQLite DB with the deterministic demo extractor
(no AI cost), fires N uploads from N different visitors, and measures errors, latency and
how long the job queue takes to drain. Usage: uv run python scripts/load_test.py [N]
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
PORT = 8079
BASE = f"http://127.0.0.1:{PORT}"


def env(tmp: Path) -> dict:
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "votetrail.settings.prod",
        "SECURE_SSL_REDIRECT": "false",
        "DATABASE_URL": f"sqlite:///{tmp}/load.sqlite3",
        "MEDIA_ROOT": str(tmp / "media"),
        "WORKER_HEARTBEAT_FILE": str(tmp / "hb"),
        "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "EXTRACTOR_BACKEND": "demo",
        "UPLOAD_LIMIT_PER_IP": "100000",
        "SECURE_COOKIES": "false",
        "TRUSTED_PROXY_COUNT": "0",
    }


def photo(i: int) -> bytes:
    img = Image.new("RGB", (1200, 1600), (240 - i % 40, 238, 230))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


async def one(i: int, image: bytes) -> tuple[int, float]:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        page = await c.get("/capture/37-06-02-004/")
        token = page.cookies.get("csrftoken")
        t = time.perf_counter()
        r = await c.post(
            "/api/results/uploads",
            headers={"X-CSRFToken": token},
            data={
                "pu_code": "37/06/02/004",
                "election": "presidential-2027-demo",
                "idempotency_key": uuid.uuid4().hex,
                "in_app": "1",
                "captured_at": "2027-01-16T17:05:00+01:00",
                "lat": "9.0279",
                "lng": "7.4881",
                "device_id": f"load-{i}",
            },
            files={"image": ("s.jpg", image, "image/jpeg")},
        )
        return r.status_code, time.perf_counter() - t


async def main() -> dict:
    image = photo(1)
    t0 = time.perf_counter()
    results = await asyncio.gather(*(one(i, image) for i in range(N)))
    wall = time.perf_counter() - t0
    codes: dict[int, int] = {}
    for code, _ in results:
        codes[code] = codes.get(code, 0) + 1
    lat = sorted(t for _, t in results)
    return {
        "uploads": N,
        "status_codes": codes,
        "wall_seconds": round(wall, 1),
        "p50_ms": round(statistics.median(lat) * 1000),
        "p95_ms": round(lat[int(len(lat) * 0.95) - 1] * 1000),
    }


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    e = env(tmp)

    def run(*a):
        return subprocess.run(
            ["uv", "run", "python", "manage.py", *a],
            env=e,
            cwd=ROOT,
            check=True,
            capture_output=True,
        )

    run("migrate", "--noinput")
    run("seed")
    run("collectstatic", "--noinput")
    web = subprocess.Popen(
        [
            "uv",
            "run",
            "gunicorn",
            "votetrail.wsgi:application",
            "--bind",
            f"127.0.0.1:{PORT}",
            "--workers",
            "4",
            "--log-level",
            "error",
        ],
        env=e,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    workers = [
        subprocess.Popen(
            ["uv", "run", "python", "manage.py", "run_worker", "--poll", "0.2"],
            env=e,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(2)
    ]
    try:
        for _ in range(40):
            try:
                httpx.get(f"{BASE}/healthz", timeout=2)
                break
            except httpx.HTTPError:
                time.sleep(0.5)
        report = asyncio.run(main())
        t = time.perf_counter()
        import sqlite3

        while True:
            con = sqlite3.connect(tmp / "load.sqlite3")
            left = con.execute(
                "select count(*) from jobs_job where status in ('queued','running','failed')"
            ).fetchone()[0]
            dead = con.execute("select count(*) from jobs_job where status='dead'").fetchone()[0]
            errors = con.execute(
                "select kind, substr(error,1,160), count(*) from jobs_job where "
                "status='dead' group by 1,2"
            ).fetchall()
            con.close()
            if left == 0 or time.perf_counter() - t > 300:
                break
            time.sleep(1)
        report["queue_drain_seconds"] = round(time.perf_counter() - t, 1)
        report["jobs_left"], report["jobs_dead"] = left, dead
        report["dead_errors"] = errors
        print(json.dumps(report))
        (ROOT / "docs/reviews/eval/load_test.json").write_text(json.dumps(report, indent=1))
    finally:
        web.terminate()
        for w in workers:
            w.terminate()
        shutil.rmtree(tmp, ignore_errors=True)
