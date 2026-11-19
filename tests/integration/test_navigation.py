"""New information architecture: setup → profile → My vote / Verify / Ask / Activity."""

import pytest
from django.test import Client

from apps.alerts.models import Subscription
from apps.channels.models import OutboxMessage
from apps.geo.models import PollingUnit
from apps.journey import profile as prof
from apps.journey.models import VoterProfile

MOVED, NEW = "37/06/02/002", "37/06/02/004"


def set_up(client, *, lang="pcm", pu="370602002", phone=""):
    client.post("/setup/", {"step": "1", "language": lang})
    client.post("/setup/", {"step": "2", "pu_code": pu})
    return client.post("/setup/", {"step": "3", "phone": phone})


@pytest.mark.django_db
def test_first_visit_sees_landing_then_get_started(seeded):
    c = Client()
    html = c.get("/").content.decode()
    assert "every voice." in html and "Get started" in html
    assert 'href="/setup/"' in html and "Watch the full replay" in html
    assert 'class="tabbar"' not in html
    assert c.get("/vote/")["Location"] == "/"  # My vote before setup → landing
    assert c.get("/vote/?skip=1").status_code == 200
    assert "Do this next" in c.get("/vote/").content.decode()
    # The landing page is always at /, even after setup; it now offers "Open my vote".
    again = c.get("/").content.decode()
    assert "every voice." in again and "Open my vote" in again
    assert c.get("/welcome/")["Location"] == "/"


@pytest.mark.django_db
def test_setup_saves_one_profile_used_everywhere(seeded):
    c = Client()
    assert set_up(c, phone="0803 555 0001")["Location"] == "/setup/?step=done"
    p = VoterProfile.objects.get()
    assert p.language == "pcm" and p.polling_unit.code == MOVED and p.unit.code == NEW
    assert p.moved and p.phone_on_file and p.setup_done_at
    assert Subscription.objects.get().polling_unit.code == MOVED
    assert OutboxMessage.objects.count() == 1
    home = c.get("/vote/").content.decode()
    # The voter chose Pidgin, so the screens are in Pidgin.
    assert 'class="tag warn">Don move' in home and "Do this one next" in home and NEW in home
    assert 'lang="pcm"' in home and ">Check am<" in home
    verify = c.get("/verify/").content.decode()
    assert NEW in verify and "from your profile" in verify


@pytest.mark.django_db
def test_setup_validation(seeded):
    c = Client()
    c.post("/setup/", {"step": "2", "pu_code": "99/99/99/999"})
    assert VoterProfile.objects.get().polling_unit is None
    r = c.post("/setup/", {"step": "3", "phone": "123"})
    assert r["Location"] == "/setup/?step=3"
    c.post("/setup/", {"step": "1", "language": "xx"})
    assert VoterProfile.objects.get().language == "en"
    for step in ("1", "2", "3", "done"):
        assert c.get(f"/setup/?step={step}").status_code == 200


@pytest.mark.django_db
def test_next_action_follows_the_voter(seeded, settings):
    c = Client()
    c.get("/vote/?skip=1")
    p = VoterProfile.objects.get()
    assert prof.next_action(p).kind == "find_pu"
    set_up(c, pu="370602002")
    p.refresh_from_db()
    assert prof.next_action(p).kind == "visit_new"
    c.post("/me/mark/seen_move")
    p.refresh_from_db()
    assert prof.next_action(p).kind == "register"
    c.post("/me/mark/registered")
    c.post("/me/mark/pvc_collected")
    p.refresh_from_db()
    assert prof.next_action(p).kind == "alerts"
    c.post("/pu/37-06-02-002/subscribe", {"phone": "08035550002"})
    p.refresh_from_db()
    assert prof.next_action(p).kind == "rumour"
    c.post("/me/mark/pvc_collected", {"value": "0"})
    p.refresh_from_db()
    assert not p.pvc_collected
    c.post("/me/mark/nonsense")  # ignored


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("now", "kind", "phase"),
    [
        ("2027-01-16T10:00:00+01:00", "is_open", "election_day"),
        ("2027-01-16T17:00:00+01:00", "photo", "counting"),
        ("2027-01-20T10:00:00+01:00", "result", "after"),
    ],
)
def test_election_phases(seeded, settings, now, kind, phase):
    settings.DEMO_NOW = now
    c = Client()
    set_up(c, pu="370602004")
    p = VoterProfile.objects.get()
    assert prof.phase(prof.election(), prof.now()) == phase
    assert prof.next_action(p).kind == kind
    assert prof.countdown() is None
    assert c.get("/vote/").status_code == 200


def test_phase_without_election():
    assert prof.phase(None, None) == "before"


@pytest.mark.django_db
def test_journey_tags_and_countdown(seeded):
    c = Client()
    set_up(c)
    steps = prof.journey(VoterProfile.objects.get())
    assert [s["tag"][0] for s in steps[:3]] == ["TO DO", "TO DO", "MOVED"]
    assert prof.countdown()["days"] >= 0


@pytest.mark.django_db
def test_make_this_my_polling_unit(seeded):
    c = Client()
    c.get("/vote/?skip=1")
    page = c.get("/pu/37-06-02-004/").content.decode()
    assert "Make this my polling unit" in page
    c.post("/me/unit/37-06-02-004")
    assert VoterProfile.objects.get().polling_unit.code == NEW
    assert "YOUR POLLING UNIT" in c.get("/pu/37-06-02-004/").content.decode()


@pytest.mark.django_db
def test_language_switch_updates_profile_and_participant(seeded):
    c = Client()
    set_up(c, lang="en", phone="08035550003")
    c.post("/me/language", {"language": "pcm"})
    p = VoterProfile.objects.get()
    assert p.language == "pcm" and p.participant.language == "pcm"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url", "back"),
    [
        ("/register/", "MY VOTE"),
        ("/pvc/", "MY VOTE"),
        ("/accessibility/", "MY VOTE"),
        ("/find/", "MY VOTE"),
        ("/pu/37-06-02-002/", "MY VOTE"),
        ("/pu/37-06-02-004/today/", "POLLING UNIT"),
        ("/pu/37-06-02-004/result/", "VERIFY"),
        ("/capture/", "VERIFY"),
    ],
)
def test_detail_pages_have_a_back_bar(seeded, url, back):
    html = Client().get(url).content.decode()
    assert 'class="backbar"' in html and back in html


@pytest.mark.django_db
def test_four_tabs_everywhere_except_setup(seeded):
    c = Client()
    for url in ("/vote/?skip=1", "/verify/", "/ask/", "/activity/"):
        html = c.get(url).content.decode()
        for tab in (">My vote<", ">Verify<", ">Ask<", ">Activity<"):
            assert tab in html
        assert 'class="appnav"' in html
        assert 'class="sync"' in html
    assert 'class="appnav"' not in c.get("/setup/").content.decode()


@pytest.mark.django_db
def test_mark_steps_from_detail_pages(seeded):
    c = Client()
    assert (
        "I&#x27;m registered" in c.get("/register/").content.decode()
        or "I'm registered" in c.get("/register/").content.decode()
    )
    c.post("/me/mark/registered", {"next": "/register/"})
    assert "Registered · undo" in c.get("/register/").content.decode()


@pytest.mark.django_db(transaction=True)
def test_activity_feed_and_sync(seeded, settings, tmp_path):
    from apps.claims import analysis, search

    settings.MEDIA_ROOT = tmp_path
    analysis.set_analyzer(type("A", (), {"model": "f", "analyse": lambda s, c, i: {"items": []}})())
    search.set_searcher(type("S", (), {"search": lambda s, q: []})())
    try:
        c = Client()
        set_up(c, phone="08035550004")
        c.post(
            "/rumours/new",
            {
                "text": "Officials have not arrived at Garki ward 5 polling unit",
                "category": "late_officials",
            },
        )
        assert c.get("/api/me/sync").json()["processing"] == 1
        from apps.jobs.queue import run_pending

        run_pending()
        assert c.get("/api/me/sync").json()["processing"] == 0
        c.post("/pu/37-06-02-004/checkin", {"kind": "queue_long"})
        html = c.get("/activity/").content.decode()
        # set_up() picked Pidgin, so the feed is in Pidgin.
        assert "Rumour wey you check" in html and "We don send alert to your phone" in html
        assert "You report: Line long well well" in html
    finally:
        analysis.set_analyzer(None)
        search.set_searcher(None)


@pytest.mark.django_db
def test_activity_upload_pipeline(seeded, settings, tmp_path):
    from apps.elections.models import Election
    from apps.results.models import ResultUpload

    settings.MEDIA_ROOT = tmp_path
    c = Client()
    c.get("/vote/?skip=1")
    visitor = VoterProfile.objects.get().visitor_id
    pu = PollingUnit.objects.get(code=NEW)
    e = Election.objects.get()
    for state in ("received", "checking", "rejected", "checked"):
        ResultUpload.objects.create(
            election=e,
            polling_unit=pu,
            visitor_id=visitor,
            idempotency_key=f"key-{state}-000",
            state=state,
            source="sms",
        )
    html = c.get("/activity/").content.decode()
    assert html.count("Your upload · EC8A") == 4 and "Not accepted" in html


@pytest.mark.django_db
def test_nearest_polling_units(seeded):
    pu = PollingUnit.objects.get(code=NEW)
    r = Client().get("/api/pu/nearest", {"lat": pu.lat, "lng": pu.lng}).json()["results"]
    assert r[0]["code"] == NEW and r[0]["distance_m"] == 0 and len(r) == 5
    c = Client()
    assert c.get("/api/pu/nearest").status_code == 400
    assert c.get("/api/pu/nearest", {"lat": "200", "lng": "1"}).status_code == 400


@pytest.mark.django_db
def test_live_endpoints(seeded):
    c = Client()
    assert c.get("/api/pu/37-06-02-004/today").json()["updated"] == ""
    c.post("/pu/37-06-02-004/checkin", {"kind": "queue_long"})
    assert c.get("/api/pu/37-06-02-004/today").json()["updated"]
    assert c.get("/api/rumours/999").status_code == 404


@pytest.mark.django_db
def test_skipping_setup_sticks(seeded):
    c = Client()
    c.get("/vote/?skip=1")
    assert c.get("/vote/").status_code == 200
