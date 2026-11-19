"""Rumour/incident intake and assessment."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditLog, Participant
from apps.jobs.queue import compute_digest, enqueue_once
from apps.trust.hashing import hamming, normalize_text, simhash
from apps.trust.status import claim_status, is_material_change
from apps.trust.types import Decision, Evidence, Reason, Stance, Submission

from . import analysis, search
from .models import Category, Claim, ClaimAssessment, EvidenceItem, Report

CLUSTER_DISTANCE = 12
CLUSTER_WINDOW = dt.timedelta(hours=48)
_FORWARD_MARKERS = re.compile(
    r"\b(forwarded|forward this|pls share|please share|share (this|before|am|it)|broadcast|"
    r"send to all|copied|received this)\b",
    re.I,
)
MAX_TEXT = 2000


def looks_forwarded(text: str) -> bool:
    return bool(_FORWARD_MARKERS.search(text or ""))


def _sh(text: str) -> str:
    return format(simhash(text), "x")


def ward_of(code: str) -> str:
    """Normalise a PU/ward code to its ward (SS/LL/WW) for grouping."""
    parts = (code or "").replace("-", "/").split("/")
    return "/".join(p.zfill(2) for p in parts[:3]) if len(parts) >= 3 else (code or "")


def find_claim(text: str, category: str, location_code: str = "") -> Claim | None:
    """Same incident type in the same ward → same claim; otherwise near-identical text."""
    since = timezone.now() - CLUSTER_WINDOW
    ward = ward_of(location_code)
    if category != Category.OTHER and ward:
        for claim in Claim.objects.filter(created_at__gte=since, category=category):
            if ward_of(claim.location_code) == ward:
                return claim
    h = simhash(text)
    for claim in Claim.objects.filter(created_at__gte=since).only("id", "simhash", "category"):
        if category not in (claim.category, Category.OTHER) and claim.category != Category.OTHER:
            continue
        if hamming(h, int(claim.simhash, 16)) <= CLUSTER_DISTANCE:
            return claim
    return None


@transaction.atomic
def submit_report(
    *,
    text: str,
    category: str = Category.OTHER,
    location_code: str = "",
    location_label: str = "",
    observed_at: dt.datetime | None = None,
    source: str = Report.Source.APP,
    is_forward: bool | None = None,
    participant: Participant | None = None,
    visitor_id: str = "",
    device_id: str = "",
    language: str = "en",
    is_demo: bool = False,
) -> Report:
    text = (text or "").strip()[:MAX_TEXT]
    if len(normalize_text(text)) < 8:
        raise ValueError("Tell us a bit more about what you saw or heard.")
    if category not in Category.values:
        category = Category.OTHER
    forward = looks_forwarded(text) if is_forward is None else is_forward
    claim = find_claim(text, category, location_code)
    if claim is None:
        claim = Claim.objects.create(
            text=text,
            simhash=_sh(text),
            category=category,
            location_code=location_code,
            location_label=location_label,
            is_demo=is_demo,
        )
    original = None
    if forward:
        original = claim.reports.filter(is_forward=False).order_by("created_at").first()
    report = Report.objects.create(
        claim=claim,
        text=text,
        simhash=_sh(text),
        participant=participant,
        visitor_id=visitor_id,
        device_id=device_id[:64],
        source=source,
        is_forward=forward,
        forward_of=original,
        observed_at=observed_at,
        language=language,
    )
    EvidenceItem.objects.create(
        claim=claim,
        kind=EvidenceItem.Kind.REPORT,
        report=report,
        participant=participant,
        excerpt=text,
        content_hash=f"report:{report.pk}",
    )
    AuditLog.record(
        actor=f"visitor:{visitor_id[:12]}" if visitor_id else "system",
        action="claims.report_received",
        obj=report,
        after={"claim": claim.pk, "forward": forward},
    )
    transaction.on_commit(lambda: enqueue_once("claims.assess", {"claim_id": claim.pk}))
    return report


def add_verifier_evidence(
    claim: Claim,
    verifier: Participant,
    *,
    note: str,
    stance: str,
    observed_at: dt.datetime | None = None,
) -> EvidenceItem:
    item = EvidenceItem.objects.create(
        claim=claim,
        kind=EvidenceItem.Kind.VERIFIER,
        participant=verifier,
        excerpt=note[:MAX_TEXT],
        content_hash=hashlib.sha256(f"verifier:{verifier.pk}:{note}".encode()).hexdigest(),
        stance=stance,
        quote=note[:300],
        observed_at=observed_at,
        analysis_valid=True,
    )
    AuditLog.record(
        actor=f"participant:{verifier.pk}",
        action="claims.verifier_evidence",
        obj=item,
        after={"stance": stance},
    )
    enqueue_once("claims.assess", {"claim_id": claim.pk})
    return item


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def gather_web(claim: Claim) -> int:
    if not getattr(settings, "CLAIMS_WEB_SEARCH", True):
        return 0
    query = f"{claim.text[:200]} {claim.location_label} Nigeria election".strip()
    added = 0
    for r in search.cached_search(query):
        content = (r.get("content") or "").strip()
        if not r.get("url") or not content:
            continue
        digest = hashlib.sha256(f"{r['url']}|{normalize_text(content)}".encode()).hexdigest()
        _, created = EvidenceItem.objects.get_or_create(
            claim=claim,
            content_hash=digest,
            defaults={
                "kind": EvidenceItem.Kind.WEB,
                "url": r["url"][:500],
                "domain": _domain(r["url"]),
                "title": r.get("title", "")[:300],
                "excerpt": content[: search.MAX_EXCERPT],
            },
        )
        added += created
    return added


def _submission(item: EvidenceItem) -> Submission:
    if item.kind == EvidenceItem.Kind.REPORT and item.report is not None:
        r, p = item.report, item.report.participant
        return Submission(
            id=f"r{r.pk}",
            participant_key=(p.phone_hmac if p and p.phone_hmac else r.visitor_id),
            device_id=r.device_id,
            role=p.role if p else "voter",
            party=p.party if p else "",
            reputation=p.reputation if p else 0,
            text=r.text,
            is_forward=r.is_forward,
            forward_of=f"r{r.forward_of_id}" if r.forward_of_id else "",
            observed_at=item.observed_at or r.observed_at,
        )
    if item.kind == EvidenceItem.Kind.VERIFIER:
        p = item.participant
        return Submission(
            id=f"v{item.pk}",
            participant_key=(p.phone_hmac or f"p{p.pk}") if p else f"v{item.pk}",
            role="verifier",
            reputation=p.reputation if p else 0,
            observed_at=item.observed_at,
        )
    return Submission(
        id=f"w{item.pk}",
        participant_key=f"domain:{item.domain}",
        source_domain=item.domain,
        text=item.excerpt[:500],
        observed_at=item.observed_at,
    )


def _decision_from(a: ClaimAssessment | None) -> Decision | None:
    if a is None:
        return None
    return Decision(
        status=a.status,
        origin_count=a.origin_count,
        reasons=tuple(Reason(r["code"], r.get("detail", {})) for r in a.reasons),
        location=a.claim.location_code,
    )


def assess(claim: Claim) -> ClaimAssessment | None:
    gather_web(claim)
    items = list(claim.evidence.select_related("report__participant", "participant"))
    # Each item is analysed once; later assessments only analyse new evidence.
    pending = {
        f"e{i.pk}": i.excerpt
        for i in items
        if i.kind != EvidenceItem.Kind.VERIFIER and i.analysed_at is None
    }
    if pending:
        raw = analysis.get_analyzer().analyse(
            claim.text, [{"id": k, "text": v} for k, v in pending.items()]
        )
        valid, dropped = analysis.validate(raw, pending)
        by_id = {v.id: v for v in valid}
        for item in items:
            key = f"e{item.pk}"
            if key not in pending:
                continue
            v = by_id.get(key)
            item.analysed_at = timezone.now()
            item.analysis_valid = v is not None
            item.stance = v.stance if v else ""
            item.quote = v.quote if v else ""
            item.explicit = v.explicit if v else False
            if v and v.observed_at:
                item.observed_at = v.observed_at
            item.save(
                update_fields=[
                    "analysed_at",
                    "analysis_valid",
                    "stance",
                    "quote",
                    "explicit",
                    "observed_at",
                ]
            )
        if dropped:
            AuditLog.record(
                actor="worker",
                action="claims.analysis_items_dropped",
                obj=claim,
                detail={"dropped": dropped},
            )

    evidence = []
    for item in items:
        if not item.analysis_valid or item.stance not in ("supports", "opposes"):
            continue
        evidence.append(
            Evidence(f"e{item.pk}", _submission(item), Stance(item.stance), explicit=item.explicit)
        )
    forwards = claim.reports.filter(is_forward=True).count()
    decision = claim_status(
        evidence,
        settings.TRUSTED_AUTHORITIES,
        window=dt.timedelta(hours=settings.CLAIM_WINDOW_HOURS),
        min_reputation=settings.MIN_REPUTATION,
        location=claim.location_code,
    )
    latest = claim.latest
    if not is_material_change(_decision_from(latest), decision) and latest is not None:
        return None
    reasons = [{"code": r.code, "detail": dict(r.detail)} for r in decision.reasons]
    for r in reasons:
        if r["code"] == "forwards_only":
            r["detail"]["forwards"] = forwards
    assessment = ClaimAssessment.objects.create(
        claim=claim,
        revision=(latest.revision + 1) if latest else 1,
        status=str(decision.status),
        reasons=reasons,
        origin_count=decision.origin_count,
        forward_count=forwards,
        authority=decision.authority,
        evidence_ids=[e.id for e in evidence],
    )
    AuditLog.record(
        actor="worker",
        action="claims.status_published",
        obj=assessment,
        after={"status": assessment.status, "revision": assessment.revision},
    )
    return assessment


def assess_digest(claim: Claim) -> str:
    parts = list(claim.evidence.order_by("id").values_list("content_hash", "stance"))
    return compute_digest(
        "claims.assess", {"claim": claim.pk, "e": parts}, analysis.ANALYSIS_VERSION
    )
