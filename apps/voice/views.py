from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.claims.services import submit_report
from apps.claims.verdicts import render as render_verdict
from apps.core.access import current_participant
from apps.core.ratelimit import client_ip, hit

from . import realtime, tools

MAX_NOTE_BYTES = 24000 * 2 * 60 + 1024  # 60 s of 24 kHz mono PCM16


def _lang(request) -> str:
    lang = request.POST.get("language") or request.GET.get("language") or "en"
    return lang if lang in realtime.LANG_NAME else "en"


@require_GET
@ensure_csrf_cookie
def voice_page(request):
    return render(request, "voice/assistant.html", {})


@require_POST
def session_api(request):
    if not hit(f"voice-session:{request.visitor_id}", 10, 600) or not hit(
        f"voice-session-ip:{client_ip(request)}", 40, 600
    ):
        return JsonResponse({"error": "Too many voice sessions. Try again soon."}, status=429)
    try:
        return JsonResponse(realtime.mint_session(_lang(request)))
    except Exception:
        return JsonResponse(
            {"error": "Voice is unavailable right now. Use the text options."}, status=503
        )


@require_POST
def tool_api(request):
    if not hit(f"voice-tool:{request.visitor_id}", 120, 600):
        return JsonResponse({"error": "Too many requests."}, status=429)
    try:
        payload = json.loads(request.body or b"{}")
        args = json.loads(payload.get("arguments") or "{}")
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Bad tool call."}, status=400)
    return JsonResponse(tools.call(str(payload.get("name", "")), args, _lang(request)))


@require_POST
def voice_note_api(request):
    if not hit(f"voice-note:{request.visitor_id}", 10, 600):
        return JsonResponse({"error": "Too many voice notes. Try again soon."}, status=429)
    audio = request.FILES.get("audio")
    if audio is None or audio.size > MAX_NOTE_BYTES:
        return JsonResponse({"error": "Record up to 60 seconds."}, status=400)
    try:
        pcm = realtime.wav_to_pcm16(audio.read())
        understood = realtime.get_understander().understand(pcm)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception:
        return JsonResponse(
            {"error": "We couldn't process the voice note. Try typing it."}, status=503
        )
    lang = understood.get("language", "en")
    out: dict = {
        "transcript": understood.get("transcript", ""),
        "language": lang,
        "intent": understood["intent"],
    }
    if understood["intent"] == "rumour":
        text = understood.get("english") or understood.get("transcript", "")
        try:
            report = submit_report(
                text=text,
                source="voice",
                language=lang,
                participant=current_participant(request),
                visitor_id=request.visitor_id,
            )
            out["claim_id"] = report.claim_id
            out["verdict"] = render_verdict(report.claim.latest, lang)
        except ValueError as exc:
            out["error"] = str(exc)
    elif understood["intent"] == "question":
        out["answer"] = tools.kb_search(understood.get("english") or out["transcript"])
    return JsonResponse(out)
