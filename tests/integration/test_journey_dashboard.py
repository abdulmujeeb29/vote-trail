import datetime as dt
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.alerts.models import Announcement, Subscription
from apps.channels import ussd
from apps.claims.models import Claim
from apps.core.models import AuditLog, Participant
from apps.geo.models import PollingUnit
from apps.journey.models import CheckIn
from apps.journey.status import day_status
from apps.results.models import ResultUpload

MOVED = "37-06-02-002"
NEW = "37-06-02-004"


@pytest.fixture(autouse=True)
def _cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "/",
        "/vote/?skip=1",
        "/setup/",
        "/verify/",
        "/verify/?tab=rumour",
        "/activity/",
        "/ask/",
        "/register/",
        "/pvc/",
        "/accessibility/",
        "/find/",
        "/find/?q=garki",
        "/find/?q=zzzz",
        f"/pu/{MOVED}/",
        f"/pu/{NEW}/today/",
        "/dashboard/login/",
    ],
)
def test_pages(seeded, url):
    assert Client().get(url).status_code == 200


@pytest.mark.django_db
def test_find_redirects_on_exact_code(seeded):
    assert Client().get("/find/?q=370602002")["Location"] == f"/pu/{MOVED}/"
    assert Client().get("/find/?q=37/06/02/002")["Location"] == f"/pu/{MOVED}/"


@pytest.mark.django_db
def test_crowd_checkins_need_two_people(seeded):
    pu = PollingUnit.objects.get(code="37/06/02/004")
    a, b = Client(), Client()
    a.post(f"/pu/{NEW}/checkin", {"kind": "not_open"})
    a.post(f"/pu/{NEW}/checkin", {"kind": "not_open"})
    assert day_status(pu).headline == "No updates yet"
    b.post(f"/pu/{NEW}/checkin", {"kind": "not_open"})
    assert day_status(pu).headline.startswith("Not open yet")
    a.post(f"/pu/{NEW}/checkin", {"kind": "nonsense"})
    assert CheckIn.objects.count() == 3


@pytest.mark.django_db
def test_official_checkin_via_ussd(seeded):
    phone = "+2348036660000"
    assert "Only verified" in ussd.handle("s", phone, "6")
    p = Participant.objects.by_phone(phone)
    p.role, p.verified_at = "official", timezone.now()
    p.save()
    assert ussd.handle("s", phone, "6").startswith("CON")
    assert "PU code" in ussd.handle("s", phone, "6")
    assert ussd.handle("s", phone, "6*370602004").startswith("CON")
    assert "Recorded" in ussd.handle("s", phone, "6*370602004*1")
    assert ussd.handle("s", phone, "6*370602004*9").startswith("END")
    assert ussd.handle("s", phone, "6*1").startswith("END")
    status = day_status(PollingUnit.objects.get(code="37/06/02/004"))
    assert status.headline.startswith("Open since") and status.tone == "ok"
    CheckIn.objects.create(
        polling_unit_id=status and PollingUnit.objects.get(code="37/06/02/004").pk,
        kind="bvas_fail",
        official=True,
    )
    assert day_status(PollingUnit.objects.get(code="37/06/02/004")).tone == "warn"


@pytest.mark.django_db(transaction=True)
def test_rumour_form(seeded):
    from apps.claims import analysis, search

    analysis.set_analyzer(type("A", (), {"model": "f", "analyse": lambda s, c, i: {"items": []}})())
    search.set_searcher(type("S", (), {"search": lambda s, q: []})())
    try:
        c = Client()
        r = c.post(
            "/rumours/new",
            {
                "text": "Officials have not arrived at Garki ward 5",
                "category": "late_officials",
                "location": "37/06/02",
                "forwarded": "on",
            },
        )
        claim = Claim.objects.get()
        assert r["Location"] == f"/rumours/{claim.pk}/"
        assert c.get(r["Location"]).status_code == 200
        assert c.post("/rumours/new", {"text": "hi"}).status_code == 302
        assert Claim.objects.count() == 1
    finally:
        analysis.set_analyzer(None)
        search.set_searcher(None)


# ---- Dashboard ----


def make_verifier(role="verifier", phone="08034440000"):
    user = User.objects.create_user("ver", password="correct-horse-battery")
    p = Participant(user=user, role=role, verified_at=timezone.now())
    p.set_phone(phone)
    p.save()
    return user, p


def logged_in(code="123456"):
    c = Client()
    with mock.patch("apps.channels.otp.secrets.randbelow", return_value=int(code)):
        r = c.post("/dashboard/login/", {"username": "ver", "password": "correct-horse-battery"})
    assert r["Location"] == "/dashboard/verify/"
    return c


@pytest.mark.django_db
def test_dashboard_requires_login_role_and_otp(seeded):
    assert Client().get("/dashboard/")["Location"].startswith("/dashboard/login/")
    make_verifier()
    c = logged_in()
    assert c.get("/dashboard/")["Location"] == "/dashboard/verify/"
    c.post("/dashboard/verify/", {"code": "000000"})
    assert c.get("/dashboard/")["Location"] == "/dashboard/verify/"
    assert c.post("/dashboard/verify/", {"code": "123456"})["Location"] == "/dashboard/"
    page = c.get("/dashboard/")
    assert page.status_code == 200 and b"Verifier dashboard" in page.content
    assert c.get("/dashboard/?lga=37/06&status=pending").status_code == 200
    assert AuditLog.objects.filter(action="dashboard.login").exists()


@pytest.mark.django_db
def test_voter_account_cannot_use_dashboard(seeded):
    user = User.objects.create_user("ver", password="correct-horse-battery")
    p = Participant(user=user, role="voter")
    p.set_phone("08034440001")
    p.save()
    c = Client()
    c.post("/dashboard/login/", {"username": "ver", "password": "correct-horse-battery"})
    assert "denied" in c.get("/dashboard/verify/")["Location"]
    assert "denied" in c.get("/dashboard/")["Location"]


@pytest.mark.django_db(transaction=True)
def test_dashboard_actions(seeded, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    from apps.claims import analysis, search
    from apps.elections.models import Election

    analysis.set_analyzer(type("A", (), {"model": "f", "analyse": lambda s, c, i: {"items": []}})())
    search.set_searcher(type("S", (), {"search": lambda s, q: []})())
    try:
        make_verifier()
        c = logged_in()
        c.post("/dashboard/verify/", {"code": "123456"})
        agent = Participant(role="agent", party="PA")
        agent.set_phone("08031119999")
        agent.save()
        pu = PollingUnit.objects.get(code="37/06/02/004")
        upload = ResultUpload.objects.create(
            election=Election.objects.get(),
            polling_unit=pu,
            participant=agent,
            idempotency_key="k" * 12,
            source="sms",
            state="checked",
            sms_figures={"party_votes": {"PA": 1}},
        )
        assert c.get(f"/dashboard/results/{NEW}/").status_code == 200
        c.post(f"/dashboard/uploads/{upload.pk}/decision", {"decision": "wrong"})
        upload.refresh_from_db()
        agent.refresh_from_db()
        assert upload.state == "rejected" and agent.reputation == -2
        c.post(f"/dashboard/uploads/{upload.pk}/decision", {"decision": "correct"})
        agent.refresh_from_db()
        assert agent.reputation == -1
        c.post(f"/dashboard/uploads/{upload.pk}/decision", {"decision": "?"})

        from apps.claims.services import submit_report

        claim = submit_report(
            text="Officials are late at Garki ward 5 polling unit", visitor_id="x"
        ).claim
        assert c.get("/dashboard/claims/").status_code == 200
        c.post(f"/dashboard/claims/{claim.pk}/evidence", {"stance": "supports", "note": "short"})
        c.post(
            f"/dashboard/claims/{claim.pk}/evidence",
            {"stance": "supports", "note": "Our observer confirms officials arrived at 11am"},
        )
        assert claim.evidence.filter(kind="verifier").count() == 1

        ann = Announcement.objects.create(
            source_url="https://blog.example/notice",
            text="x",
            kind="pu_relocation",
            state="pending_approval",
            extracted={
                "affected": [
                    {"pu_code": "37/06/01/001", "new_pu_code": "37/06/01/002", "quote": "x"}
                ]
            },
        )
        assert c.get("/dashboard/announcements/").status_code == 200
        c.post(f"/dashboard/announcements/{ann.pk}/decision", {"decision": "approve"})
        ann.refresh_from_db()
        assert ann.state == "applied" and ann.approved_by.startswith("user:")
        assert PollingUnit.objects.get(code="37/06/01/001").current.code == "37/06/01/002"
        ann2 = Announcement.objects.create(
            source_url="https://x.example", text="y", state="pending_approval"
        )
        c.post(f"/dashboard/announcements/{ann2.pk}/decision", {"decision": "reject"})
        ann2.refresh_from_db()
        assert ann2.state == "rejected"
    finally:
        analysis.set_analyzer(None)
        search.set_searcher(None)


@pytest.mark.django_db
def test_create_verifier_command(seeded, capsys):
    call_command(
        "create_verifier", "--username", "obs", "--phone", "08030001111", "--role", "observer"
    )
    out = capsys.readouterr().out
    assert "Password:" in out
    p = User.objects.get(username="obs").participant
    assert p.role == "observer" and p.is_verified


def test_checkin_str():
    assert "opened" in str(
        CheckIn(
            polling_unit=PollingUnit(code="1/1/1/1"),
            kind="opened",
            at=dt.datetime(2027, 1, 16, tzinfo=dt.UTC),
        )
    )


@pytest.mark.django_db
def test_redirects(seeded):
    c = Client()
    assert c.get("/journey/")["Location"] == "/vote/"
    assert c.get("/rumours/")["Location"] == "/verify/?tab=rumour"


@pytest.mark.django_db
def test_subscribe_from_pu_page(seeded):
    c = Client()
    r = c.post(f"/pu/{MOVED}/subscribe", {"phone": "0803 777 0000", "voice": "on"})
    assert r.status_code == 302
    sub = Subscription.objects.get()
    assert sub.voice and sub.polling_unit.code == "37/06/02/002"
    c.post(f"/pu/{MOVED}/subscribe", {"phone": "bad"})
    assert Subscription.objects.count() == 1
