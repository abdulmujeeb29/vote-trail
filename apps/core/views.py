from __future__ import annotations

import time

from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def healthz(request):
    checks: dict[str, str] = {}
    ok = True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        checks["db"] = "ok"
    except Exception:  # pragma: no cover - exercised in ops
        checks["db"] = "fail"
        ok = False
    hb = settings.WORKER_HEARTBEAT_FILE
    try:
        age = time.time() - hb.stat().st_mtime
        worker_ok = age <= settings.WORKER_HEARTBEAT_MAX_AGE
    except FileNotFoundError:
        worker_ok = False
    checks["worker"] = "ok" if worker_ok else "stale"
    ok = ok and worker_ok
    return JsonResponse(
        {"status": "ok" if ok else "degraded", "checks": checks}, status=200 if ok else 503
    )


def service_worker(request):
    from django.contrib.staticfiles import finders
    from django.http import HttpResponse

    path = finders.find("sw.js")
    with open(path, "rb") as fh:
        body = fh.read()
    resp = HttpResponse(body, content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp
