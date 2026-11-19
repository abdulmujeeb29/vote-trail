from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.core.access import can_export_evidence, current_participant
from apps.core.ratelimit import client_ip, hit
from apps.elections.models import Election
from apps.geo.codes import InvalidPUCode, normalize_pu_code
from apps.geo.models import PollingUnit

from . import presenters
from .evidence import build_pack
from .imaging import InvalidImage
from .models import IrevSheet, ResultUpload
from .services import UploadError, accept_upload, latest_check


def _election(slug: str | None = None) -> Election:
    qs = Election.objects.all()
    election = qs.filter(slug=slug).first() if slug else qs.order_by("-date").first()
    if election is None:
        raise Http404("No election")
    return election


def _pu(code: str) -> PollingUnit:
    try:
        return get_object_or_404(PollingUnit, code=normalize_pu_code(code))
    except InvalidPUCode as exc:
        raise Http404(str(exc)) from exc


def _check_json(check) -> dict:
    if check is None:
        return {
            "status": "pending",
            "label": presenters.STATUS_LABEL["pending"],
            "explain": presenters.explain(None),
            "revision": 0,
        }
    return {
        "status": check.status,
        "label": presenters.STATUS_LABEL[check.status],
        "icon": presenters.STATUS_ICON[check.status],
        "explain": presenters.explain(check),
        "revision": check.revision,
        "origin_count": check.origin_count,
        "cross_party": check.cross_party,
        "diffs": check.diffs,
        "citizen": check.citizen_figures,
        "irev": check.irev_figures,
    }


@require_POST
def upload_api(request):
    if not hit(f"upload:{request.visitor_id}", 30, 600) or not hit(
        f"upload-ip:{client_ip(request)}", settings.UPLOAD_LIMIT_PER_IP, 600
    ):
        return JsonResponse({"error": "Too many uploads. Try again in a few minutes."}, status=429)
    image = request.FILES.get("image")
    if image is None:
        return JsonResponse({"error": "Add a photo of the result sheet."}, status=400)
    try:
        election = _election(request.POST.get("election"))
        pu = _pu(request.POST.get("pu_code", ""))
        upload, created = accept_upload(
            election=election,
            pu=pu,
            idempotency_key=request.POST.get("idempotency_key", ""),
            image_bytes=image.read(),
            in_app_capture=request.POST.get("in_app") == "1",
            captured_at=request.POST.get("captured_at"),
            lat=request.POST.get("lat"),
            lng=request.POST.get("lng"),
            device_id=request.POST.get("device_id", ""),
            visitor_id=request.visitor_id,
            participant=current_participant(request),
        )
    except (UploadError, InvalidImage) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Http404 as exc:
        return JsonResponse({"error": str(exc) or "Unknown polling unit."}, status=404)
    return JsonResponse(
        {
            "id": upload.pk,
            "state": upload.state,
            "key": upload.idempotency_key,
            "status_url": f"/api/results/uploads/{upload.idempotency_key}",
        },
        status=201 if created else 200,
    )


@require_GET
def upload_status_api(request, key: str):
    upload = get_object_or_404(ResultUpload, idempotency_key=key)
    check = latest_check(upload.election, upload.polling_unit)
    return JsonResponse(
        {
            "state": upload.state,
            "flags": [f["code"] for f in upload.flags],
            "pu": upload.polling_unit.code,
            "result": _check_json(check),
        }
    )


@require_GET
def pu_result_api(request, code: str):
    pu = _pu(code)
    election = _election(request.GET.get("election"))
    return JsonResponse(
        {"pu": pu.code, "name": pu.name, "result": _check_json(latest_check(election, pu))}
    )


@require_GET
def pu_result(request, code: str):
    pu = _pu(code)
    election = _election(request.GET.get("election"))
    check = latest_check(election, pu)
    irev = IrevSheet.objects.filter(election=election, polling_unit=pu).first()
    history = list(pu.checks.filter(election=election).order_by("-revision")[:10])
    parties = list(election.parties.order_by("electionparty__ballot_order"))
    rows = []
    if check and (check.citizen_figures or check.irev_figures):
        cit = (check.citizen_figures or {}).get("party_votes", {})
        irv = (check.irev_figures or {}).get("party_votes", {})
        for p in parties:
            rows.append(
                {
                    "party": p.acronym,
                    "citizen": cit.get(p.acronym),
                    "irev": irv.get(p.acronym),
                    "differs": f"party:{p.acronym}" in check.diffs,
                }
            )
    return render(
        request,
        "results/pu_result.html",
        {
            "pu": pu,
            "election": election,
            "check": check,
            "result": _check_json(check),
            "irev": irev,
            "history": history,
            "rows": rows,
            "can_export": can_export_evidence(request),
        },
    )


@require_GET
@ensure_csrf_cookie
def capture(request, code: str | None = None):
    pu = _pu(code) if code else None
    return render(request, "results/capture.html", {"pu": pu, "election": _election()})


@require_GET
def evidence_pack(request, code: str):
    if not can_export_evidence(request):
        return JsonResponse(
            {"error": "Evidence packs are for verified observers and verifiers."}, status=403
        )
    pu = _pu(code)
    election = _election(request.GET.get("election"))
    data = build_pack(election, pu)
    resp = HttpResponse(data, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="evidence-{pu.code.replace("/", "-")}.zip"'
    return resp
