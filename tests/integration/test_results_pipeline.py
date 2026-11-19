import datetime as dt
import io
import uuid
import zipfile

import pytest
from django.core.files.base import ContentFile
from django.test import Client
from django.utils import timezone

from apps.alerts.models import Subscription
from apps.channels.models import OutboxMessage
from apps.core.models import AuditLog, Participant
from apps.elections.models import Election
from apps.geo.models import PollingUnit
from apps.jobs.queue import run_pending
from apps.results.extract import extract, set_extractor
from apps.results.imaging import clean_image, sha256_hex
from apps.results.models import IrevSheet, ResultCheck, ResultUpload
from apps.results.synth import SheetSpec, render, truth
from tests.fakes import FakeExtractor

PARTIES = {"PA": 214, "PB": 187, "PC": 43, "PD": 12}
CODE = "37/06/02/004"
URL_CODE = "37-06-02-004"


@pytest.fixture
def fake(seeded):
    f = FakeExtractor()
    set_extractor(f)
    yield f
    set_extractor(None)


@pytest.fixture
def election(seeded):
    return Election.objects.get(slug="presidential-2027-demo")


def sheet_image(fake, *, seed, parties=PARTIES, **kw):
    spec = SheetSpec(
        pu_code=CODE,
        pu_name="Garki Village Ii/New Pri. Sch.",
        ward="Garki",
        lga="Municipal",
        parties=dict(parties),
        seed=seed,
        damage="none",
        **kw,
    )
    img = render(spec)
    fake.register(img, truth(spec))
    return img


def add_irev(fake, election, *, parties=PARTIES, seed=999, **kw):
    img = sheet_image(fake, seed=seed, parties=parties, **kw)
    clean = clean_image(img)
    sheet = IrevSheet(
        election=election,
        polling_unit=PollingUnit.objects.get(code=CODE),
        sha256=sha256_hex(clean),
        is_mock=True,
        uploaded_at=timezone.now(),
        source_url="https://example.invalid/mock-irev",
    )
    sheet.image.save("irev.jpg", ContentFile(clean), save=False)
    sheet.save()
    from apps.jobs.queue import enqueue

    enqueue("results.extract_irev", {"irev_id": sheet.pk})
    return sheet


CAPTURED = "2027-01-16T17:05:00+01:00"


def post(
    client,
    img,
    *,
    key=None,
    pu=CODE,
    in_app="1",
    captured=CAPTURED,
    lat=None,
    lng=None,
    device="dev-1",
):
    if lat is None:
        unit = PollingUnit.objects.get(code=pu)
        lat, lng = str(unit.lat), str(unit.lng)
    return client.post(
        "/api/results/uploads",
        {
            "pu_code": pu,
            "election": "presidential-2027-demo",
            "idempotency_key": key or uuid.uuid4().hex,
            "in_app": in_app,
            "captured_at": captured,
            "lat": lat,
            "lng": lng,
            "device_id": device,
            "image": ContentFile(img, name="x.jpg"),
        },
    )


def agent_client(party, phone):
    c = Client()
    c.get("/healthz")
    from django.core import signing

    visitor = signing.loads(c.cookies["vt_visitor"].value, salt="votetrail.visitor")
    p = Participant(visitor_id=visitor, role="agent", party=party, verified_at=timezone.now())
    p.set_phone(phone)
    p.save()
    return c


def latest(election):
    return (
        ResultCheck.objects.filter(election=election, polling_unit__code=CODE)
        .order_by("-revision")
        .first()
    )


@pytest.mark.django_db
def test_two_cross_party_agents_vs_different_irev_is_mismatch(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    voter = Participant(role="voter")
    voter.set_phone("08030000001")
    voter.save()
    Subscription.objects.create(
        participant=voter, polling_unit=PollingUnit.objects.get(code=CODE), language="pcm"
    )
    add_irev(fake, election, parties={**PARTIES, "PB": 287})
    a = agent_client("PA", "08030000010")
    b = agent_client("PB", "08030000011")
    r1 = post(a, sheet_image(fake, seed=1), device="dev-a")
    r2 = post(b, sheet_image(fake, seed=2), device="dev-b")
    assert r1.status_code == 201 and r2.status_code == 201
    run_pending()
    check = latest(election)
    assert check.status == "mismatch", check.reasons
    assert check.origin_count == 2 and check.cross_party
    assert check.diffs["party:PB"] == [187, 287]
    msg = OutboxMessage.objects.get()
    assert "no match IReV" in msg.body and msg.language == "pcm"
    assert msg.state == "sent"
    page = a.get(f"/pu/{URL_CODE}/result/")
    assert page.status_code == 200 and b"Mismatch with IReV" in page.content
    assert b"Demo data" in page.content
    status = a.get(r1.json()["status_url"]).json()
    assert status["state"] == "checked" and status["result"]["status"] == "mismatch"


@pytest.mark.django_db
def test_one_upload_matching_irev(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election)
    post(Client(), sheet_image(fake, seed=1))
    run_pending()
    assert latest(election).status == "matches"


@pytest.mark.django_db
def test_single_disagreeing_upload_needs_review(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election, parties={**PARTIES, "PB": 287})
    post(Client(), sheet_image(fake, seed=1))
    run_pending()
    check = latest(election)
    assert check.status == "needs_review"
    assert any(r["code"] == "single_origin_disagrees_with_irev" for r in check.reasons)


@pytest.mark.django_db
def test_no_irev_yet_is_pending(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    post(Client(), sheet_image(fake, seed=1))
    run_pending()
    assert latest(election).status == "pending"


@pytest.mark.django_db
def test_cancelled_sheet(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election)
    post(Client(), sheet_image(fake, seed=1, cancelled=True))
    run_pending()
    assert latest(election).status == "cancelled"


@pytest.mark.django_db
def test_smudged_field_goes_to_review(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election)
    post(Client(), sheet_image(fake, seed=1, smudge="party:PB"))
    run_pending()
    check = latest(election)
    assert check.status == "needs_review"
    assert any(r["code"] == "low_confidence" for r in check.reasons)


@pytest.mark.django_db
def test_arithmetic_error_goes_to_review(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election)
    post(Client(), sheet_image(fake, seed=1, override_total_valid=500))
    run_pending()
    assert latest(election).status == "needs_review"


@pytest.mark.django_db
def test_reused_image_across_pus_is_rejected(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    img = sheet_image(fake, seed=1)
    post(Client(), img, pu="37/06/01/001")
    run_pending()
    r = post(Client(), img)
    run_pending()
    upload = ResultUpload.objects.get(idempotency_key=r.json()["key"])
    assert upload.state == "rejected"
    assert {f["code"] for f in upload.flags} >= {"reused_image"}


@pytest.mark.django_db
def test_gallery_upload_rejected(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    r = post(Client(), sheet_image(fake, seed=1), in_app="0")
    run_pending()
    assert ResultUpload.objects.get(idempotency_key=r.json()["key"]).state == "rejected"


@pytest.mark.django_db
def test_delayed_offline_upload_still_valid(fake, election, settings, tmp_path):
    """Captured during the count, uploaded hours later when signal returned."""
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election)
    r = post(Client(), sheet_image(fake, seed=1), captured="2027-01-16T17:05:00+01:00")
    ResultUpload.objects.filter(idempotency_key=r.json()["key"]).update(
        received_at=dt.datetime(2027, 1, 17, 6, 0, tzinfo=dt.UTC)
    )
    run_pending()
    assert latest(election).status == "matches"


@pytest.mark.django_db
def test_too_far_goes_to_review(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election)
    post(Client(), sheet_image(fake, seed=1), lat="9.3", lng="7.2")
    run_pending()
    assert latest(election).status == "needs_review"


@pytest.mark.django_db
def test_upload_is_idempotent(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    img = sheet_image(fake, seed=1)
    key = uuid.uuid4().hex
    c = Client()
    assert post(c, img, key=key).status_code == 201
    assert post(c, img, key=key).status_code == 200
    assert ResultUpload.objects.count() == 1


@pytest.mark.django_db
def test_exif_is_stripped(fake, election, settings, tmp_path):
    from PIL import Image

    settings.MEDIA_ROOT = tmp_path
    img = Image.new("RGB", (40, 40), "white")
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    assert b"SecretCam" in buf.getvalue()
    r = post(Client(), buf.getvalue())
    upload = ResultUpload.objects.get(idempotency_key=r.json()["key"])
    assert b"SecretCam" not in upload.image.read()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("pu_code", "nonsense", 404),
        ("captured_at", "2027-01-16T17:05:00", 400),
        ("lat", "abc", 400),
        ("lat", "123", 400),
        ("idempotency_key", "short", 400),
    ],
)
def test_upload_validation(fake, election, settings, tmp_path, field, value, error):
    settings.MEDIA_ROOT = tmp_path
    data = {
        "pu": CODE,
        "key": uuid.uuid4().hex,
        "captured": CAPTURED,
        "lat": "9.0279",
        "lng": "7.4881",
    }
    mapping = {"pu_code": "pu", "captured_at": "captured", "lat": "lat", "idempotency_key": "key"}
    data[mapping[field]] = value
    r = post(Client(), sheet_image(fake, seed=1), **data)
    assert r.status_code == error


@pytest.mark.django_db
def test_upload_requires_image_and_valid_photo(election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    c = Client()
    assert c.post("/api/results/uploads", {"pu_code": CODE}).status_code == 400
    r = c.post(
        "/api/results/uploads",
        {
            "pu_code": CODE,
            "idempotency_key": uuid.uuid4().hex,
            "image": ContentFile(b"not an image", name="x.jpg"),
        },
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_rate_limit(fake, election, settings, tmp_path):
    from django.core.cache import cache

    cache.clear()
    settings.MEDIA_ROOT = tmp_path
    c = Client()
    img = sheet_image(fake, seed=1)
    codes = [post(c, img).status_code for _ in range(31)]
    assert codes[-1] == 429
    cache.clear()


@pytest.mark.django_db
def test_no_new_revision_without_material_change(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election)
    post(Client(), sheet_image(fake, seed=1))
    run_pending()
    from apps.jobs.queue import enqueue

    enqueue(
        "results.recompute",
        {"election_id": election.pk, "pu_id": PollingUnit.objects.get(code=CODE).pk},
    )
    run_pending()
    assert ResultCheck.objects.count() == 1
    with pytest.raises(RuntimeError):
        ResultCheck.objects.get().save()


@pytest.mark.django_db
def test_extraction_reused_for_same_image(fake, election):
    img = clean_image(sheet_image(fake, seed=1))
    sha = sha256_hex(img)
    a = extract(img, sha, pu_code=CODE, parties=list(PARTIES))
    b = extract(img, sha, pu_code=CODE, parties=list(PARTIES))
    assert a.pk == b.pk and fake.calls == 1


@pytest.mark.django_db
def test_evidence_pack_gated_and_deterministic(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    add_irev(fake, election, parties={**PARTIES, "PB": 287})
    a = agent_client("PA", "08030000010")
    post(a, sheet_image(fake, seed=1), device="dev-a")
    run_pending()
    assert Client().get(f"/pu/{URL_CODE}/evidence.zip").status_code == 403
    obs = agent_client("", "08030000020")
    Participant.objects.filter(party="", role="agent").update(role="observer")
    r1 = obs.get(f"/pu/{URL_CODE}/evidence.zip")
    r2 = obs.get(f"/pu/{URL_CODE}/evidence.zip")
    assert r1.status_code == 200 and r1.content == r2.content
    names = zipfile.ZipFile(io.BytesIO(r1.content)).namelist()
    assert {
        "manifest.json",
        "summary.html",
        "history.json",
        "audit.json",
        "irev/irev.jpg",
        "irev/irev.json",
    } <= set(names)
    assert any(n.endswith(".jpg") and n.startswith("uploads/") for n in names)
    assert AuditLog.objects.filter(action="results.status_published").exists()


@pytest.mark.django_db
def test_pages_render(fake, election):
    c = Client()
    assert c.get("/capture/").status_code == 200
    assert c.get(f"/capture/{URL_CODE}/").status_code == 200
    assert c.get(f"/pu/{URL_CODE}/result/").status_code == 200
    assert c.get("/pu/99-99-99-999/result/").status_code == 404
    api = c.get(f"/api/pu/{URL_CODE}/result").json()
    assert api["result"]["status"] == "pending"
    sw = c.get("/sw.js")
    assert sw["Service-Worker-Allowed"] == "/"


@pytest.mark.django_db
def test_seed_demo_irev_with_demo_extractor(seeded, settings, tmp_path):
    from django.core.management import call_command

    settings.MEDIA_ROOT = tmp_path
    settings.EXTRACTOR_BACKEND = "demo"
    call_command("seed_demo_irev")
    call_command("seed_demo_irev", "--no-run")
    assert IrevSheet.objects.count() == 3
    assert all(s.is_mock for s in IrevSheet.objects.all())
    run_pending()
    assert IrevSheet.objects.filter(extraction__isnull=False).count() == 3


@pytest.mark.django_db
def test_capture_page_sets_csrf_cookie_and_upload_needs_it(fake, election, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    c = Client(enforce_csrf_checks=True)
    page = c.get(f"/capture/{URL_CODE}/")
    assert "csrftoken" in page.cookies
    img = sheet_image(fake, seed=1)
    unit = PollingUnit.objects.get(code=CODE)
    data = {
        "pu_code": CODE,
        "election": "presidential-2027-demo",
        "idempotency_key": uuid.uuid4().hex,
        "in_app": "1",
        "captured_at": CAPTURED,
        "lat": unit.lat,
        "lng": unit.lng,
        "image": ContentFile(img, name="x.jpg"),
    }
    assert c.post("/api/results/uploads", data).status_code == 403
    data["image"] = ContentFile(img, name="x.jpg")
    token = c.cookies["csrftoken"].value
    assert c.post("/api/results/uploads", data, HTTP_X_CSRFTOKEN=token).status_code == 201
