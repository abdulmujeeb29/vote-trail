import json
from pathlib import Path

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

PACK = Path(settings.BASE_DIR) / "static" / "demo" / "pack.json"


@require_GET
def replay(request):
    pack = json.loads(PACK.read_text()) if PACK.exists() else None
    return render(request, "demo/replay.html", {"pack": pack})
