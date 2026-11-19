import datetime as dt
import threading

import pytest
from django.db import connection
from django.utils import timezone

from apps.jobs import queue
from apps.jobs.models import Job
from apps.jobs.queue import (
    claim_next,
    compute_digest,
    enqueue,
    handler,
    registered_kinds,
    run_job,
    run_pending,
)
from apps.jobs.worker import Worker

CALLS: list[int] = []


@handler("test.echo")
def _echo(payload):
    CALLS.append(payload["n"])
    return {"n": payload["n"]}


@handler("test.fail")
def _fail(payload):
    raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _reset():
    CALLS.clear()


@pytest.mark.django_db
def test_enqueue_and_run():
    job = enqueue("test.echo", {"n": 1})
    assert run_pending() == 1
    job.refresh_from_db()
    assert job.status == Job.Status.SUCCEEDED and job.result == {"n": 1}
    assert "test.echo" in registered_kinds()
    assert str(job).startswith("test.echo#")


@pytest.mark.django_db
def test_digest_reuse_returns_same_job():
    d = compute_digest("test.echo", {"n": 2}, "v1")
    assert d == compute_digest("test.echo", {"n": 2}, "v1")
    assert d != compute_digest("test.echo", {"n": 2}, "v2")
    a = enqueue("test.echo", {"n": 2}, digest=d)
    run_pending()
    b = enqueue("test.echo", {"n": 2}, digest=d)
    assert a.pk == b.pk
    assert CALLS == [2]


@pytest.mark.django_db
def test_dead_job_is_not_reused():
    d = compute_digest("test.fail", {})
    a = enqueue("test.fail", {}, digest=d, max_attempts=1)
    run_pending()
    a.refresh_from_db()
    assert a.status == Job.Status.DEAD
    assert enqueue("test.fail", {}, digest=d).pk != a.pk


@pytest.mark.django_db
def test_retry_with_backoff_then_dead():
    job = enqueue("test.fail", {}, max_attempts=2)
    run_pending()
    job.refresh_from_db()
    assert job.status == Job.Status.FAILED and "boom" in job.error
    assert job.run_after > timezone.now()
    assert claim_next() is None  # backing off
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
    run_pending()
    job.refresh_from_db()
    assert job.status == Job.Status.DEAD and job.attempts == 2


@pytest.mark.django_db
def test_unknown_kind_goes_dead_immediately():
    job = enqueue("nope.unknown", {})
    run_pending()
    job.refresh_from_db()
    assert job.status == Job.Status.DEAD


@pytest.mark.django_db
def test_expired_lease_is_recovered():
    job = enqueue("test.echo", {"n": 3})
    claimed = claim_next()
    assert claimed.pk == job.pk and claimed.status == Job.Status.RUNNING
    assert claim_next() is None  # lease still valid
    Job.objects.filter(pk=job.pk).update(lease_until=timezone.now() - dt.timedelta(seconds=1))
    again = claim_next()
    assert again.pk == job.pk and again.attempts == 2
    run_job(again)
    # The first holder's late result must be discarded (it lost the claim).
    run_job(claimed)
    job.refresh_from_db()
    assert job.status == Job.Status.SUCCEEDED
    assert CALLS == [3, 3]


@pytest.mark.django_db
def test_expired_lease_on_final_attempt_goes_dead():
    job = enqueue("test.echo", {"n": 4}, max_attempts=1)
    claim_next()
    Job.objects.filter(pk=job.pk).update(lease_until=timezone.now() - dt.timedelta(seconds=1))
    assert claim_next() is None
    job.refresh_from_db()
    assert job.status == Job.Status.DEAD


@pytest.mark.django_db
def test_kind_filter():
    enqueue("test.echo", {"n": 5})
    assert claim_next(kinds=["other"]) is None
    assert claim_next(kinds=["test.echo"]) is not None


@pytest.mark.django_db(transaction=True)
def test_concurrent_workers_never_run_the_same_job():
    for n in range(30):
        enqueue("test.echo", {"n": n})
    claimed: list[int] = []
    lock = threading.Lock()
    errors: list[BaseException] = []

    def work():
        try:
            while True:
                job = claim_next()
                if job is None:
                    break
                with lock:
                    claimed.append(job.pk)
                run_job(job)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(claimed) == len(set(claimed)) == 30
    assert sorted(CALLS) == list(range(30))
    assert Job.objects.filter(status=Job.Status.SUCCEEDED).count() == 30


@pytest.mark.django_db(transaction=True)
def test_worker_loop_heartbeat_and_stop(tmp_path):
    enqueue("test.echo", {"n": 9})
    w = Worker(poll_interval=0, heartbeat=tmp_path / "hb")
    w.run(max_iterations=2)
    assert (tmp_path / "hb").exists()
    assert CALLS == [9]
    w.stop()
    assert w._stop


def test_backoff_caps():
    assert queue._backoff(1) == dt.timedelta(seconds=10)
    assert queue._backoff(20) == dt.timedelta(seconds=300)


LOCKS = {"n": 0}


@handler("test.locked")
def _locked(payload):
    from django.db import OperationalError

    LOCKS["n"] += 1
    if LOCKS["n"] <= payload["fails"]:
        raise OperationalError("database is locked")
    return {"ok": True}


@pytest.mark.django_db
def test_lock_errors_retry_without_using_attempts():
    LOCKS["n"] = 0
    job = enqueue("test.locked", {"fails": 5}, max_attempts=2)
    for _ in range(10):
        Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
        run_pending()
    job.refresh_from_db()
    assert job.status == Job.Status.SUCCEEDED and job.lock_retries == 5 and job.attempts == 1


@pytest.mark.django_db
def test_lock_retries_are_capped(monkeypatch):
    monkeypatch.setattr(queue, "MAX_LOCK_RETRIES", 2)
    LOCKS["n"] = 0
    job = enqueue("test.locked", {"fails": 99}, max_attempts=1)
    for _ in range(5):
        Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
        run_pending()
    job.refresh_from_db()
    assert job.status == Job.Status.DEAD


@pytest.mark.django_db
def test_enqueue_once_coalesces_waiting_jobs():
    from apps.jobs.queue import enqueue_once

    a = enqueue_once("test.echo", {"n": 1})
    b = enqueue_once("test.echo", {"n": 1})
    c = enqueue_once("test.echo", {"n": 2})
    assert a.pk == b.pk != c.pk
