from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.alerts.models import Subscription
from apps.channels.models import OutboxMessage
from apps.channels.outbox import queue_message
from apps.claims.models import Category, Claim, Report
from apps.claims.services import submit_report
from apps.claims.verdicts import render as render_verdict
from apps.core import privacy
from apps.core.models import Participant
from apps.core.ratelimit import client_ip, hit
from apps.geo.codes import InvalidPUCode, normalize_pu_code
from apps.geo.models import PollingUnit, haversine_m
from apps.results import presenters
from apps.results.models import ResultCheck, ResultUpload

from . import profile as prof
from .models import CheckIn, VoterProfile
from .status import day_status

LANGS = prof.LANGS


def _pu(code: str) -> PollingUnit:
    try:
        return get_object_or_404(
            PollingUnit.objects.select_related("ward__lga"), code=normalize_pu_code(code)
        )
    except InvalidPUCode as exc:
        raise Http404 from exc


def _lang(request) -> str:
    return prof.get_profile(request).language


# ---------------- My vote ----------------


@require_GET
@ensure_csrf_cookie
def home(request):
    p = prof.get_profile(request)
    if p.setup_done_at is None:
        if "skip" not in request.GET:
            return redirect("journey:landing")
        p.setup_done_at = timezone.now()  # "just look around" counts as set up
        p.save(update_fields=["setup_done_at", "updated_at"])
    unit = p.unit
    latest_alert = None
    if p.participant_id:
        latest_alert = (
            OutboxMessage.objects.filter(participant=p.participant)
            .exclude(dedupe_key__startswith="otp:")
            .first()
        )
    steps = prof.journey(p)
    done = [i for i, s in enumerate(steps) if s["tag"][1] == "ok"]
    hour = timezone.localtime(prof.now()).hour
    greeting = (
        _("Good morning") if hour < 12 else _("Good afternoon") if hour < 17 else _("Good evening")
    )
    return render(
        request,
        "journey/home.html",
        {
            "p": p,
            "unit": unit,
            "action": prof.next_action(p),
            "steps": steps,
            "done_count": len(done),
            "progress_pct": round(max(done, default=0) / len(steps) * 100) if done else 0,
            "greeting": greeting,
            "countdown": prof.countdown(),
            "latest_alert": latest_alert,
            "day": day_status(unit) if unit else None,
            "phase": prof.phase(prof.election(), prof.now()),
        },
    )


@require_GET
@ensure_csrf_cookie
def landing(request):
    """What VoteTrail is, how it works, and one clear way in."""
    import json
    from pathlib import Path

    from django.conf import settings

    pack_path = Path(settings.BASE_DIR) / "static" / "demo" / "pack.json"
    demo = json.loads(pack_path.read_text())["steps"] if pack_path.exists() else None
    rows = []
    if demo:
        wall = demo["results"]["citizen"]["party_votes"]
        irev = demo["results"]["irev"]["party_votes"]
        rows = [
            {"party": k, "wall": v, "irev": irev.get(k), "differs": v != irev.get(k)}
            for k, v in wall.items()
        ]
    return render(
        request,
        "journey/landing.html",
        {
            "demo": demo,
            "rows": rows,
            "countdown": prof.countdown(),
            "returning": prof.get_profile(request).setup_done_at is not None,
        },
    )


# ---------------- Setup (3 steps) ----------------


@ensure_csrf_cookie
def setup(request):
    p = prof.get_profile(request)
    step = request.GET.get("step", "1")
    if request.method == "POST":
        step = request.POST.get("step", "1")
        if step == "1":
            lang = request.POST.get("language", "en")
            p.language = lang if lang in dict(LANGS) else "en"
            p.save(update_fields=["language", "updated_at"])
            return redirect(reverse("journey:setup") + "?step=2")
        if step == "2":
            code = request.POST.get("pu_code", "").strip()
            if code:
                try:
                    p.polling_unit = PollingUnit.objects.get(
                        code=normalize_pu_code(_nine_digits(code))
                    )
                    p.save(update_fields=["polling_unit", "updated_at"])
                except (InvalidPUCode, PollingUnit.DoesNotExist):
                    messages.error(
                        request, _("We couldn't find that code. Check your voter's card.")
                    )
                    return redirect(reverse("journey:setup") + "?step=2")
            return redirect(reverse("journey:setup") + "?step=3")
        if step == "3":
            raw = request.POST.get("phone", "").strip()
            if raw:
                try:
                    _subscribe(request, p, raw, voice=request.POST.get("voice") == "on")
                except privacy.InvalidPhoneNumber as exc:
                    messages.error(request, str(exc))
                    return redirect(reverse("journey:setup") + "?step=3")
            p.setup_done_at = p.setup_done_at or timezone.now()
            p.save(update_fields=["setup_done_at", "updated_at"])
            return redirect(reverse("journey:setup") + "?step=done")
    return render(
        request, "journey/setup.html", {"p": p, "step": step, "langs": LANGS, "beta": prof.BETA}
    )


def _nine_digits(code: str) -> str:
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) == 9 and code.isdigit():
        return f"{digits[:2]}/{digits[2:4]}/{digits[4:6]}/{digits[6:]}"
    return code


def _subscribe(request, p: VoterProfile, raw_phone: str, voice: bool = False) -> None:
    if not hit(f"sub:{client_ip(request)}", 10, 600):
        raise privacy.InvalidPhoneNumber("Too many requests. Try again in a few minutes.")
    e164 = privacy.normalize_ng_phone(raw_phone)
    part = Participant.objects.filter(phone_hmac=privacy.phone_hmac(e164)).first() or Participant()
    if part.pk is None:
        part.set_phone(e164)
    part.language = p.language
    part.visitor_id = part.visitor_id or request.visitor_id
    part.save()
    p.participant = part
    p.save(update_fields=["participant", "updated_at"])
    if p.polling_unit:
        Subscription.objects.update_or_create(
            participant=part,
            polling_unit=p.polling_unit,
            defaults={"sms": True, "voice": voice, "active": True, "language": p.language},
        )
        queue_message(
            to_phone=e164,
            participant=part,
            language=p.language,
            body=f"VoteTrail: alerts on for PU {p.polling_unit.code}. Send STOP to end.",
            dedupe_key=f"subscribed:{part.pk}:{p.polling_unit_id}",
        )


@require_POST
def mark(request, flag: str):
    p = prof.get_profile(request)
    if flag in ("seen_move", "registered", "pvc_collected"):
        setattr(p, flag, request.POST.get("value", "1") == "1")
        p.save(update_fields=[flag, "updated_at"])
    return redirect(request.POST.get("next") or "journey:home")


@require_POST
def set_language(request):
    p = prof.get_profile(request)
    lang = request.POST.get("language", "en")
    if lang in dict(LANGS):
        p.language = lang
        p.save(update_fields=["language", "updated_at"])
        if p.participant:
            p.participant.language = lang
            p.participant.save(update_fields=["language"])
    return HttpResponseRedirect(request.POST.get("next") or reverse("journey:home"))


@require_POST
def set_unit(request, code: str):
    p = prof.get_profile(request)
    p.polling_unit = _pu(code)
    p.seen_move = False
    p.save(update_fields=["polling_unit", "seen_move", "updated_at"])
    messages.success(
        request, _("Saved. %(code)s is now your polling unit.") % {"code": p.polling_unit.code}
    )
    return redirect("journey:home")


# ---------------- Verify ----------------


@require_GET
@ensure_csrf_cookie
def verify(request):
    p = prof.get_profile(request)
    tab = request.GET.get("tab", "result")
    unit = p.unit
    check = None
    if unit:
        check = ResultCheck.objects.filter(election=prof.election(), polling_unit=unit).first()
    claims = Claim.objects.order_by("-created_at")[:8]
    lang = p.language
    recent = [{"claim": c, "verdict": render_verdict(c.latest, lang)} for c in claims]
    rows = []
    if check and (check.citizen_figures or check.irev_figures):
        cit = (check.citizen_figures or {}).get("party_votes", {})
        irv = (check.irev_figures or {}).get("party_votes", {})
        for party in sorted(set(cit) | set(irv)):
            rows.append(
                {
                    "party": party,
                    "citizen": cit.get(party),
                    "irev": irv.get(party),
                    "differs": f"party:{party}" in check.diffs,
                }
            )
    return render(
        request,
        "journey/verify.html",
        {
            "p": p,
            "unit": unit,
            "tab": tab,
            "check": check,
            "rows": rows,
            "label": presenters.STATUS_LABEL[check.status] if check else None,
            "tone": presenters.STATUS_TONE[check.status] if check else "info",
            "explain": presenters.explain(check),
            "recent": recent,
            "categories": Category.choices,
            "election": prof.election(),
        },
    )


@require_POST
def rumour_submit(request):
    if not hit(f"rumour:{request.visitor_id}", 10, 600):
        messages.error(request, _("Too many reports. Try again in a few minutes."))
        return redirect(reverse("journey:verify") + "?tab=rumour")
    p = prof.get_profile(request)
    try:
        report = submit_report(
            text=request.POST.get("text", ""),
            category=request.POST.get("category", "other"),
            location_code=request.POST.get("location") or (p.unit.ward.code if p.unit else ""),
            is_forward=request.POST.get("forwarded") == "on",
            visitor_id=request.visitor_id,
            participant=p.participant,
            device_id=request.POST.get("device_id", ""),
            language=p.language,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(reverse("journey:verify") + "?tab=rumour")
    return redirect("journey:rumour", report.claim_id)


@require_GET
def rumour_detail(request, pk: int):
    claim = get_object_or_404(Claim, pk=pk)
    lang = _lang(request)
    sources = claim.evidence.filter(kind="web", analysis_valid=True).exclude(stance="irrelevant")
    return render(
        request,
        "journey/rumour.html",
        {
            "claim": claim,
            "verdict": render_verdict(claim.latest, lang),
            "sources": sources,
            "assessment": claim.latest,
            "reports": claim.reports.count(),
        },
    )


@require_GET
def rumours(request):
    return redirect(reverse("journey:verify") + "?tab=rumour")


# ---------------- Activity ----------------

PIPE = [
    gettext_noop("SAVED"),
    gettext_noop("SENT"),
    gettext_noop("READING"),
    gettext_noop("COMPARED"),
    gettext_noop("RESULT"),
]


def _upload_stage(u: ResultUpload) -> int:
    if u.state == ResultUpload.State.RECEIVED:
        return 1
    if u.state == ResultUpload.State.CHECKING or (
        u.state == ResultUpload.State.CHECKED and u.extraction_id is None and u.source == "app"
    ):
        return 2
    if u.state == ResultUpload.State.REJECTED:
        return 4
    return (
        4
        if ResultCheck.objects.filter(
            polling_unit=u.polling_unit, created_at__gte=u.received_at
        ).exists()
        else 3
    )


@require_GET
@ensure_csrf_cookie
def activity(request):
    p = prof.get_profile(request)
    items = []
    uploads = (
        ResultUpload.objects.filter(visitor_id=request.visitor_id)
        .select_related("polling_unit")
        .order_by("-received_at")[:10]
    )
    pipes = []
    for u in uploads:
        stage = _upload_stage(u)
        check = ResultCheck.objects.filter(polling_unit=u.polling_unit).first()
        pipes.append(
            {
                "u": u,
                "stage": stage,
                "steps": [_(x) for x in PIPE],
                "label": presenters.STATUS_LABEL[check.status] if check and stage == 4 else None,
                "tone": presenters.STATUS_TONE[check.status] if check else "info",
                "rejected": u.state == ResultUpload.State.REJECTED,
            }
        )
    for r in Report.objects.filter(visitor_id=request.visitor_id).select_related("claim")[:20]:
        v = render_verdict(r.claim.latest, p.language)
        items.append(
            {
                "at": r.created_at,
                "tag": v["status"].replace("_", " ").upper(),
                "tone": "info",
                "title": _("Rumour you checked"),
                "text": r.text[:90],
                "url": reverse("journey:rumour", args=[r.claim_id]),
            }
        )
    if p.participant_id:
        for m in OutboxMessage.objects.filter(participant=p.participant).exclude(
            dedupe_key__startswith="otp:"
        )[:20]:
            items.append(
                {
                    "at": m.created_at,
                    "tag": m.channel.upper(),
                    "tone": "warn"
                    if "move" in m.body.lower() or "not match" in m.body.lower()
                    else "ok",
                    "title": _("Alert sent to your phone"),
                    "text": m.body,
                    "audio": m.audio_url,
                }
            )
    for c in CheckIn.objects.filter(visitor_id=request.visitor_id).select_related("polling_unit")[
        :10
    ]:
        items.append(
            {
                "at": c.at,
                "tag": _("REPORTED"),
                "tone": "ok",
                "title": _("You reported: %(what)s") % {"what": c.get_kind_display()},
                "text": f"PU {c.polling_unit.code}",
            }
        )
    items.sort(key=lambda i: i["at"], reverse=True)
    return render(request, "journey/activity.html", {"p": p, "pipes": pipes, "items": items})


@require_GET
def sync_api(request):
    """What's still being processed on the server for this visitor."""
    uploads = ResultUpload.objects.filter(
        visitor_id=request.visitor_id,
        state__in=[ResultUpload.State.RECEIVED, ResultUpload.State.CHECKING],
    ).count()
    reports = (
        Report.objects.filter(visitor_id=request.visitor_id, claim__assessments__isnull=True)
        .values("claim")
        .distinct()
    )
    return JsonResponse({"processing": uploads + reports.count()})


# ---------------- Detail pages ----------------


@require_GET
def register(request):
    return render(request, "journey/register.html", {"p": prof.get_profile(request)})


@require_GET
def pvc(request):
    return render(request, "journey/pvc.html", {"p": prof.get_profile(request)})


@require_GET
def accessibility(request):
    p = prof.get_profile(request)
    return render(request, "journey/accessibility.html", {"p": p, "unit": p.unit})


@require_GET
def find(request):
    q = (request.GET.get("q") or "").strip()
    results = []
    if q:
        try:
            results = list(PollingUnit.objects.filter(code=normalize_pu_code(_nine_digits(q))))
        except InvalidPUCode:
            terms = [t for t in q.split() if len(t) > 1][:4]
            qs = PollingUnit.objects.select_related("ward__lga")
            for t in terms:
                qs = qs.filter(
                    Q(name__icontains=t)
                    | Q(ward__name__icontains=t)
                    | Q(ward__lga__name__icontains=t)
                )
            results = list(qs[:20])
        if len(results) == 1:
            return redirect("journey:pu", results[0].url_code)
    return render(request, "journey/find.html", {"q": q, "results": results})


@require_GET
@ensure_csrf_cookie
def pu_detail(request, code: str):
    pu = _pu(code)
    cur = pu.current
    p = prof.get_profile(request)
    result = ResultCheck.objects.filter(election=prof.election(), polling_unit=cur).first()
    return render(
        request,
        "journey/pu.html",
        {
            "pu": pu,
            "cur": cur,
            "moved": cur.pk != pu.pk,
            "day": day_status(cur),
            "result": result,
            "result_label": presenters.STATUS_LABEL[result.status] if result else None,
            "p": p,
            "is_mine": p.polling_unit_id == pu.pk,
        },
    )


@require_POST
def subscribe(request, code: str):
    pu = _pu(code)
    p = prof.get_profile(request)
    if p.polling_unit_id is None:
        p.polling_unit = pu
        p.save(update_fields=["polling_unit", "updated_at"])
    try:
        _subscribe(
            request, p, request.POST.get("phone", ""), voice=request.POST.get("voice") == "on"
        )
        messages.success(
            request, _("Alerts on for PU %(code)s. We sent a confirmation SMS.") % {"code": pu.code}
        )
    except privacy.InvalidPhoneNumber as exc:
        messages.error(request, str(exc))
    return redirect("journey:pu", pu.url_code)


@require_GET
@ensure_csrf_cookie
def today(request, code: str):
    pu = _pu(code)
    return render(
        request,
        "journey/today.html",
        {"pu": pu, "day": day_status(pu), "kinds": CheckIn.Kind.choices},
    )


@require_POST
def checkin(request, code: str):
    pu = _pu(code)
    kind = request.POST.get("kind", "")
    if kind in CheckIn.Kind.values and hit(f"checkin:{request.visitor_id}:{pu.pk}", 6, 3600):
        CheckIn.objects.create(polling_unit=pu, kind=kind, visitor_id=request.visitor_id)
        messages.success(request, _("Thanks. Your report helps other voters."))
    return redirect("journey:today", pu.url_code)


@require_GET
def nearest_api(request):
    try:
        lat, lng = float(request.GET["lat"]), float(request.GET["lng"])
    except (KeyError, ValueError):
        return JsonResponse({"error": "Location needed."}, status=400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return JsonResponse({"error": "Location out of range."}, status=400)
    units = PollingUnit.objects.exclude(lat=None).select_related("ward__lga")
    ranked = sorted(units, key=lambda u: haversine_m(lat, lng, u.lat, u.lng))[:5]
    return JsonResponse(
        {
            "results": [
                {
                    "code": u.code,
                    "url_code": u.url_code,
                    "name": u.name,
                    "ward": u.ward.name,
                    "distance_m": round(haversine_m(lat, lng, u.lat, u.lng)),
                    "moved": u.current.pk != u.pk,
                    "url": reverse("journey:pu", args=[u.url_code]),
                }
                for u in ranked
            ]
        }
    )


@require_GET
def rumour_status_api(request, pk: int):
    claim = get_object_or_404(Claim, pk=pk)
    latest = claim.latest
    return JsonResponse(
        {
            "status": latest.status if latest else "checking",
            "revision": latest.revision if latest else 0,
        }
    )


@require_GET
def today_api(request, code: str):
    pu = _pu(code)
    day = day_status(pu)
    return JsonResponse(
        {
            "headline": day.headline,
            "lines": day.lines,
            "updated": day.updated.isoformat() if day.updated else "",
        }
    )
