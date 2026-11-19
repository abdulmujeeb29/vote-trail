from __future__ import annotations

import uuid

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.core import privacy
from apps.core.ratelimit import client_ip, hit

from . import sms, ussd
from .models import OutboxMessage


def _webhook_allowed(request) -> bool:
    token = settings.CHANNEL_WEBHOOK_TOKEN
    return not token or request.GET.get("token") == token


@csrf_exempt
@require_POST
def ussd_webhook(request):
    if not _webhook_allowed(request) or not hit(f"ussd:{client_ip(request)}", 600, 60):
        return HttpResponse("END Service unavailable", content_type="text/plain", status=403)
    body = ussd.handle(
        request.POST.get("sessionId", ""),
        request.POST.get("phoneNumber", ""),
        request.POST.get("text", ""),
    )
    return HttpResponse(body, content_type="text/plain")


@csrf_exempt
@require_POST
def sms_webhook(request):
    if not _webhook_allowed(request):
        return HttpResponse(status=403)
    try:
        sms.handle_inbound(
            request.POST.get("from", ""), request.POST.get("text", ""), request.POST.get("id", "")
        )
    except privacy.InvalidPhoneNumber:
        return HttpResponse(status=400)
    return HttpResponse("ok", content_type="text/plain")


def _simulator_on():
    if not settings.SIMULATOR_ENABLED:
        raise Http404


@require_GET
@ensure_csrf_cookie
def simulator(request):
    _simulator_on()
    return render(request, "channels/simulator.html", {"service_code": settings.USSD_SERVICE_CODE})


@require_POST
def simulator_ussd(request):
    _simulator_on()
    body = ussd.handle(
        request.POST.get("sessionId") or uuid.uuid4().hex,
        request.POST.get("phoneNumber", ""),
        request.POST.get("text", ""),
    )
    return JsonResponse({"reply": body})


@require_POST
def simulator_sms(request):
    _simulator_on()
    try:
        reply = sms.handle_inbound(
            request.POST.get("phoneNumber", ""), request.POST.get("text", "")
        )
    except privacy.InvalidPhoneNumber as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"reply": reply})


@require_GET
def simulator_inbox(request):
    _simulator_on()
    try:
        e164 = privacy.normalize_ng_phone(request.GET.get("phone", ""))
    except privacy.InvalidPhoneNumber as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    msgs = OutboxMessage.objects.filter(to_hmac=privacy.phone_hmac(e164))[:20]
    return JsonResponse(
        {
            "messages": [
                {
                    "id": m.pk,
                    "channel": m.channel,
                    "body": m.body,
                    "audio_url": m.audio_url,
                    "at": m.created_at.isoformat(),
                    "state": m.state,
                }
                for m in msgs
            ]
        }
    )
