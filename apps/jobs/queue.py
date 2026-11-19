"""DB-backed job queue that works on SQLite and Postgres.

Claiming is a single atomic conditional UPDATE: only one worker can move a given
row from queued to running, so two workers never run the same job.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import random
import secrets
import traceback
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.db import OperationalError
from django.db.models import Q
from django.utils import timezone

from .models import Job

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], dict[str, Any] | None]
_HANDLERS: dict[str, Handler] = {}


class UnknownJobKind(LookupError):
    pass


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return register


def registered_kinds() -> list[str]:
    return sorted(_HANDLERS)


def compute_digest(kind: str, payload: dict[str, Any], version: str = "") -> str:
    raw = json.dumps({"k": kind, "p": payload, "v": version}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def enqueue(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    digest: str | None = None,
    run_after: dt.datetime | None = None,
    max_attempts: int | None = None,
) -> Job:
    """Queue a job. With a digest, an identical job that already succeeded is reused."""
    payload = payload or {}
    if digest:
        existing = (
            Job.objects.filter(kind=kind, input_digest=digest)
            .exclude(status=Job.Status.DEAD)
            .order_by("-id")
            .first()
        )
        if existing is not None:
            return existing
    return Job.objects.create(
        kind=kind,
        payload=payload,
        input_digest=digest or "",
        run_after=run_after or timezone.now(),
        max_attempts=max_attempts or settings.JOB_MAX_ATTEMPTS,
    )


def enqueue_once(kind: str, payload: dict[str, Any]) -> Job:
    """Coalesce: if the same job is already waiting, don't queue another."""
    waiting = Job.objects.filter(kind=kind, payload=payload, status=Job.Status.QUEUED).first()
    return waiting or enqueue(kind, payload)


def _claimable(now: dt.datetime) -> Q:
    ready = Q(status__in=[Job.Status.QUEUED, Job.Status.FAILED], run_after__lte=now)
    expired = Q(status=Job.Status.RUNNING, lease_until__lt=now)
    return ready | expired


def claim_next(kinds: list[str] | None = None) -> Job | None:
    """Atomically claim the oldest ready job (or one whose lease expired)."""
    now = timezone.now()
    lease = now + dt.timedelta(seconds=settings.JOB_LEASE_SECONDS)
    for _ in range(5):
        qs = Job.objects.filter(_claimable(now))
        if kinds:
            qs = qs.filter(kind__in=kinds)
        candidate = qs.order_by("id").values("id", "status", "attempts", "max_attempts").first()
        if candidate is None:
            return None
        if candidate["attempts"] >= candidate["max_attempts"]:
            Job.objects.filter(id=candidate["id"], status=candidate["status"]).update(
                status=Job.Status.DEAD, error="Lease expired after final attempt.", updated_at=now
            )
            continue
        token = secrets.token_hex(16)
        updated = (
            Job.objects.filter(id=candidate["id"])
            .filter(_claimable(now))
            .update(
                status=Job.Status.RUNNING,
                claim_token=token,
                lease_until=lease,
                attempts=candidate["attempts"] + 1,
                updated_at=now,
            )
        )
        if updated == 1:
            return Job.objects.get(id=candidate["id"], claim_token=token)
    return None


def _backoff(attempts: int) -> dt.timedelta:
    return dt.timedelta(seconds=min(300, 2**attempts * 5))


MAX_LOCK_RETRIES = 30


def _is_lock_error(exc: BaseException) -> bool:
    return isinstance(exc, OperationalError) and "locked" in str(exc).lower()


def run_job(job: Job) -> Job:
    """Run a claimed job. Status is only written if we still hold the claim.

    Handlers run WITHOUT an outer transaction: slow work (AI, network) must never hold a
    database write lock. Handlers keep their own writes short and are idempotent (digest
    reuse, material-change checks, dedupe keys), so a rare double run after a lost lease is
    harmless.
    """
    fn = _HANDLERS.get(job.kind)
    now = timezone.now()
    try:
        if fn is None:
            raise UnknownJobKind(job.kind)
        result = fn(job.payload) or {}
        written = Job.objects.filter(id=job.id, claim_token=job.claim_token).update(
            status=Job.Status.SUCCEEDED,
            result=result,
            error="",
            lease_until=None,
            updated_at=timezone.now(),
        )
        if written != 1:
            log.warning("Lost claim on job %s; another worker owns it now", job.id)
    except Exception as exc:
        if _is_lock_error(exc) and job.lock_retries < MAX_LOCK_RETRIES:
            # Contention is not the job's fault: retry soon without using an attempt.
            Job.objects.filter(id=job.id, claim_token=job.claim_token).update(
                status=Job.Status.FAILED,
                attempts=max(job.attempts - 1, 0),
                lock_retries=job.lock_retries + 1,
                run_after=now + dt.timedelta(milliseconds=random.randint(200, 1500)),
                lease_until=None,
                updated_at=now,
            )
            job.refresh_from_db()
            return job
        dead = job.attempts >= job.max_attempts or isinstance(exc, UnknownJobKind)
        Job.objects.filter(id=job.id, claim_token=job.claim_token).update(
            status=Job.Status.DEAD if dead else Job.Status.FAILED,
            error="".join(traceback.format_exception_only(type(exc), exc)).strip()[:2000],
            run_after=now + _backoff(job.attempts),
            lease_until=None,
            updated_at=now,
        )
        log.exception("Job %s (%s) failed", job.id, job.kind)
    job.refresh_from_db()
    return job


def run_pending(limit: int = 100, kinds: list[str] | None = None) -> int:
    """Drain ready jobs synchronously (used by tests, management commands, and demo builds)."""
    done = 0
    while done < limit:
        job = claim_next(kinds)
        if job is None:
            break
        run_job(job)
        done += 1
    return done
