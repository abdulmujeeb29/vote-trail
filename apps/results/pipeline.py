"""Results pipeline jobs: integrity → extract → rules → compare with IReV → status → notify."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from apps.alerts.models import Subscription
from apps.channels.messages import render
from apps.channels.outbox import queue_message
from apps.core.models import AuditLog
from apps.elections.models import Election
from apps.geo.models import PollingUnit
from apps.jobs.queue import enqueue_once, handler
from apps.trust.integrity import PriorImage, PUFacts, UploadFacts, check_integrity
from apps.trust.status import is_material_change, result_status
from apps.trust.types import CitizenSheet, Decision, Reason, ResultStatus, Severity, Submission

from .extract import extract, figures_from_json
from .irev import get_source
from .models import IrevSheet, ResultCheck, ResultUpload

log = logging.getLogger(__name__)
NOTIFY_STATUSES = {ResultStatus.MATCHES, ResultStatus.MISMATCH, ResultStatus.CANCELLED}


def _parties(election: Election) -> list[str]:
    return list(
        election.parties.order_by("electionparty__ballot_order").values_list("acronym", flat=True)
    )


def _flags_to_json(flags) -> list[dict]:
    return [{"code": f.code, "severity": str(f.severity), "detail": dict(f.detail)} for f in flags]


def _flags_from_json(items):
    from apps.trust.types import Flag

    return tuple(Flag(i["code"], Severity(i["severity"]), i.get("detail", {})) for i in items)


@handler("results.check_upload")
def check_upload(payload: dict) -> dict:
    upload = ResultUpload.objects.select_related("polling_unit", "election").get(
        pk=payload["upload_id"]
    )
    pu, election = upload.polling_unit, upload.election
    window = None
    if election.polls_open and election.window_end:
        window = (election.polls_open, election.window_end)
    priors = [
        PriorImage(u["polling_unit__code"], u["sha256"], u["phash"])
        for u in ResultUpload.objects.filter(election=election)
        .exclude(pk=upload.pk)
        .exclude(sha256="")
        .values("polling_unit__code", "sha256", "phash")
    ]
    flags = []
    if upload.source == ResultUpload.Source.APP:
        flags = check_integrity(
            UploadFacts(
                pu.code,
                upload.in_app_capture,
                upload.captured_at,
                upload.lat,
                upload.lng,
                upload.sha256,
                upload.phash,
            ),
            PUFacts(pu.code, pu.lat, pu.lng),
            window,
            priors,
            radius_m=settings.PU_RADIUS_M,
            phash_max=settings.PHASH_MAX_DISTANCE,
        )
    upload.flags = _flags_to_json(flags)
    rejected = any(f.severity is Severity.REJECT for f in flags)
    if not rejected and upload.source == ResultUpload.Source.APP and upload.extraction_id is None:
        with upload.image.open("rb") as fh:
            data = fh.read()
        upload.extraction = extract(
            data, upload.sha256, pu_code=pu.code, parties=_parties(election)
        )
    upload.state = ResultUpload.State.REJECTED if rejected else ResultUpload.State.CHECKED
    upload.save(update_fields=["flags", "extraction", "state"])
    AuditLog.record(
        actor="worker",
        action="results.upload_checked",
        obj=upload,
        after={"state": upload.state, "flags": upload.flags},
    )
    enqueue_once("results.recompute", {"election_id": election.pk, "pu_id": pu.pk})
    return {"state": upload.state, "flags": [f["code"] for f in upload.flags]}


@handler("results.extract_irev")
def extract_irev(payload: dict) -> dict:
    sheet = IrevSheet.objects.select_related("polling_unit", "election").get(pk=payload["irev_id"])
    if sheet.extraction_id is None and sheet.image:
        with sheet.image.open("rb") as fh:
            data = fh.read()
        sheet.extraction = extract(
            data, sheet.sha256, pu_code=sheet.polling_unit.code, parties=_parties(sheet.election)
        )
        sheet.save(update_fields=["extraction"])
    enqueue_once(
        "results.recompute", {"election_id": sheet.election_id, "pu_id": sheet.polling_unit_id}
    )
    return {"extracted": sheet.extraction_id is not None}


def _citizen_sheets(election: Election, pu: PollingUnit) -> list[CitizenSheet]:
    sheets = []
    uploads = (
        ResultUpload.objects.filter(election=election, polling_unit=pu)
        .exclude(state__in=[ResultUpload.State.RECEIVED, ResultUpload.State.CHECKING])
        .select_related("participant", "extraction")
    )
    for u in uploads:
        if u.source == ResultUpload.Source.SMS:
            figures = figures_from_json(u.sms_figures)
        elif u.extraction is not None:
            figures = figures_from_json(u.extraction.figures, u.extraction.low_confidence_fields)
        else:
            figures = figures_from_json({})
        p = u.participant
        sub = Submission(
            id=f"u{u.pk}",
            participant_key=u.participant_key,
            device_id=u.device_id,
            role=p.role if p else "voter",
            party=p.party if p else "",
            reputation=p.reputation if p else 0,
            image_sha256=u.sha256,
            image_phash=u.phash,
            observed_at=u.captured_at,
        )
        sheets.append(CitizenSheet(sub, figures, _flags_from_json(u.flags)))
    return sheets


def _decision_from_check(check: ResultCheck | None) -> Decision | None:
    if check is None:
        return None
    return Decision(
        status=check.status,
        reasons=tuple(Reason(r["code"], r.get("detail", {})) for r in check.reasons),
        origin_count=check.origin_count,
        cross_party=check.cross_party,
        diffs={k: tuple(v) for k, v in check.diffs.items()},
    )


def _figures_json(fig) -> dict | None:
    if fig is None:
        return None
    return {
        "party_votes": dict(fig.party_votes),
        "registered": fig.registered,
        "accredited": fig.accredited,
        "rejected": fig.rejected,
        "total_valid": fig.total_valid,
        "total_used": fig.total_used,
        "cancelled": fig.cancelled,
    }


@handler("results.recompute")
def recompute(payload: dict) -> dict:
    election = Election.objects.get(pk=payload["election_id"])
    pu = PollingUnit.objects.get(pk=payload["pu_id"])
    citizen = _citizen_sheets(election, pu)
    irev_sheet = get_source().get_sheet(election, pu)
    irev = None
    if irev_sheet is not None and irev_sheet.extraction is not None:
        irev = figures_from_json(
            irev_sheet.extraction.figures, irev_sheet.extraction.low_confidence_fields
        )
    decision = result_status(
        citizen, irev, min_reputation=settings.MIN_REPUTATION, phash_max=settings.PHASH_MAX_DISTANCE
    )
    with transaction.atomic():
        latest = ResultCheck.objects.filter(election=election, polling_unit=pu).first()
        if not is_material_change(_decision_from_check(latest), decision):
            return {"status": str(decision.status), "revision": latest.revision, "changed": False}
        usable = [s for s in citizen if not any(f.severity is Severity.REJECT for f in s.flags)]
        check = ResultCheck.objects.create(
            election=election,
            polling_unit=pu,
            revision=(latest.revision + 1) if latest else 1,
            status=str(decision.status),
            reasons=[{"code": r.code, "detail": dict(r.detail)} for r in decision.reasons],
            origin_count=decision.origin_count,
            cross_party=decision.cross_party,
            diffs={k: list(v) for k, v in decision.diffs.items()},
            citizen_figures=_figures_json(usable[0].figures) if usable else None,
            irev_figures=_figures_json(irev),
            upload_ids=[s.submission.id for s in citizen],
        )
        AuditLog.record(
            actor="worker",
            action="results.status_published",
            obj=check,
            after={"status": check.status, "revision": check.revision},
        )
    if decision.status in NOTIFY_STATUSES:
        _notify(check)
    return {"status": check.status, "revision": check.revision, "changed": True}


def _notify(check: ResultCheck) -> int:
    key = f"result.{check.status}"
    url = reverse("results:pu_result", args=[check.polling_unit.url_code])
    sent = 0
    subs = Subscription.objects.filter(polling_unit=check.polling_unit, active=True, sms=True)
    for sub in subs.select_related("participant"):
        phone = sub.participant.phone
        if not phone:
            continue
        body, lang = render(
            key,
            sub.language,
            app=settings.APP_NAME,
            code=check.polling_unit.code,
            n=check.origin_count,
            url=url,
        )
        msg = queue_message(
            to_phone=phone,
            body=body,
            language=lang,
            participant=sub.participant,
            dedupe_key=f"result:{check.pk}:{sub.participant_id}",
        )
        sent += msg is not None
    return sent
