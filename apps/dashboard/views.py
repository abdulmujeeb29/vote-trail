from __future__ import annotations

from collections import Counter

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.alerts.models import Announcement
from apps.alerts.services import apply as apply_announcement
from apps.channels.otp import OtpError, request_otp, verify_otp
from apps.claims.models import Claim
from apps.claims.services import add_verifier_evidence
from apps.claims.verdicts import render as render_verdict
from apps.core.models import AuditLog
from apps.elections.models import Election
from apps.geo.models import LGA, PollingUnit
from apps.jobs.queue import enqueue
from apps.results import presenters
from apps.results.models import IrevSheet, ResultCheck, ResultUpload

from .auth import OTP_SESSION_KEY, is_dashboard_user, verifier_required


class LoginView(auth_views.LoginView):
    template_name = "dashboard/login.html"

    def form_valid(self, form):
        super().form_valid(form)  # logs the user in
        self.request.session[OTP_SESSION_KEY] = False
        user = form.get_user()
        if is_dashboard_user(user):
            try:
                request_otp(user.participant.phone, user.participant.language)
            except OtpError as exc:
                messages.error(self.request, str(exc))
        return redirect("/dashboard/verify/")


def verify(request):
    if not request.user.is_authenticated or not is_dashboard_user(request.user):
        return redirect("/dashboard/login/?denied=1")
    if request.method == "POST":
        if verify_otp(request.user.participant.phone, request.POST.get("code", "")):
            request.session[OTP_SESSION_KEY] = True
            request.session.cycle_key()
            AuditLog.record(
                actor=f"user:{request.user.pk}",
                action="dashboard.login",
                object_type="auth.user",
                object_id=str(request.user.pk),
            )
            return redirect("/dashboard/")
        messages.error(request, "That code is wrong or expired.")
    return render(request, "dashboard/verify.html", {})


def _latest_checks(election):
    latest: dict[int, ResultCheck] = {}
    for c in (
        ResultCheck.objects.filter(election=election)
        .select_related("polling_unit__ward__lga")
        .order_by("polling_unit_id", "-revision")
    ):
        latest.setdefault(c.polling_unit_id, c)
    return latest


@verifier_required
def overview(request):
    election = Election.objects.order_by("-date").first()
    latest = _latest_checks(election)
    lga = request.GET.get("lga", "")
    status = request.GET.get("status", "")
    pus = PollingUnit.objects.select_related("ward__lga").order_by("code")
    if lga:
        pus = pus.filter(ward__lga__code=lga)
    rows = []
    for pu in pus:
        c = latest.get(pu.pk)
        st = c.status if c else "pending"
        if status and st != status:
            continue
        rows.append(
            {
                "pu": pu,
                "status": st,
                "label": presenters.STATUS_LABEL[st],
                "tone": presenters.STATUS_TONE[st],
                "check": c,
            }
        )
    counts = Counter(c.status for c in latest.values())
    counts["pending"] += PollingUnit.objects.count() - len(latest)
    return render(
        request,
        "dashboard/overview.html",
        {
            "rows": rows,
            "counts": counts,
            "lgas": LGA.objects.all(),
            "lga": lga,
            "status": status,
            "labels": presenters.STATUS_LABEL,
            "election": election,
            "claims_open": Claim.objects.count(),
            "announcements_pending": Announcement.objects.filter(state="pending_approval").count(),
            "audit": AuditLog.objects.order_by("-created_at", "-id")[:12],
        },
    )


@verifier_required
def result_review(request, code):
    election = Election.objects.order_by("-date").first()
    pu = get_object_or_404(PollingUnit, code=code.replace("-", "/"))
    uploads = ResultUpload.objects.filter(election=election, polling_unit=pu).select_related(
        "extraction", "participant"
    )
    check = ResultCheck.objects.filter(election=election, polling_unit=pu).first()
    irev = (
        IrevSheet.objects.filter(election=election, polling_unit=pu)
        .select_related("extraction")
        .first()
    )
    return render(
        request,
        "dashboard/result.html",
        {
            "pu": pu,
            "uploads": uploads,
            "check": check,
            "irev": irev,
            "election": election,
            "explain": presenters.explain(check),
        },
    )


@require_POST
@verifier_required
@transaction.atomic
def upload_decision(request, pk):
    upload = get_object_or_404(ResultUpload, pk=pk)
    decision = request.POST.get("decision")
    actor = f"user:{request.user.pk}"
    if decision == "wrong":
        upload.state = ResultUpload.State.REJECTED
        upload.flags = [
            *upload.flags,
            {"code": "verifier_rejected", "severity": "reject", "detail": {"by": actor}},
        ]
        upload.save(update_fields=["state", "flags"])
        if upload.participant:
            upload.participant.reputation -= 2
            upload.participant.save(update_fields=["reputation"])
    elif decision == "correct" and upload.participant:
        upload.participant.reputation += 1
        upload.participant.save(update_fields=["reputation"])
    else:
        messages.error(request, "Unknown decision.")
        return redirect("dashboard:result", upload.polling_unit.url_code)
    AuditLog.record(
        actor=actor,
        action=f"dashboard.upload_{decision}",
        obj=upload,
        after={"state": upload.state},
    )
    enqueue(
        "results.recompute", {"election_id": upload.election_id, "pu_id": upload.polling_unit_id}
    )
    messages.success(request, "Decision recorded. The status will update shortly.")
    return redirect("dashboard:result", upload.polling_unit.url_code)


@verifier_required
def claims(request):
    items = [
        {"claim": c, "verdict": render_verdict(c.latest), "reports": c.reports.count()}
        for c in Claim.objects.order_by("-created_at")[:50]
    ]
    return render(request, "dashboard/claims.html", {"items": items})


@require_POST
@verifier_required
def claim_evidence(request, pk):
    claim = get_object_or_404(Claim, pk=pk)
    stance = request.POST.get("stance")
    note = (request.POST.get("note") or "").strip()
    if stance not in ("supports", "opposes") or len(note) < 10:
        messages.error(request, "Choose supports or opposes and write what you verified.")
    else:
        add_verifier_evidence(claim, request.user.participant, note=note, stance=stance)
        messages.success(request, "Verifier evidence added. The claim is being re-checked.")
    return redirect("dashboard:claims")


@verifier_required
def announcements(request):
    return render(
        request,
        "dashboard/announcements.html",
        {"items": Announcement.objects.order_by("-created_at")[:30]},
    )


@require_POST
@verifier_required
def announcement_decision(request, pk):
    ann = get_object_or_404(Announcement, pk=pk, state=Announcement.State.PENDING_APPROVAL)
    actor = f"user:{request.user.pk}"
    if request.POST.get("decision") == "approve" and (ann.extracted or {}).get("affected"):
        apply_announcement(ann, actor=actor)
        messages.success(request, "Announcement applied. Affected voters are being alerted.")
    else:
        ann.state = Announcement.State.REJECTED
        ann.approved_by = actor
        ann.save(update_fields=["state", "approved_by"])
        AuditLog.record(actor=actor, action="alerts.announcement_rejected", obj=ann)
        messages.success(request, "Announcement rejected.")
    return redirect("dashboard:announcements")
