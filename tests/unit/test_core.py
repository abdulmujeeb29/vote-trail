import logging

import pytest
from django.test import Client

from apps.core.logging import JsonFormatter, RedactFilter, redact
from apps.core.models import AppendOnlyError, AuditLog, Participant
from apps.core.privacy import InvalidPhoneNumber, mask_phone, normalize_ng_phone, phone_hmac
from apps.core.services import delete_my_data


@pytest.mark.parametrize("raw", ["08031234567", "+2348031234567", "234 803 123 4567", "8031234567"])
def test_phone_normalisation(raw):
    assert normalize_ng_phone(raw) == "+2348031234567"


@pytest.mark.parametrize("raw", ["", "12345", "05031234567", "+23412345"])
def test_invalid_phone(raw):
    with pytest.raises(InvalidPhoneNumber):
        normalize_ng_phone(raw)


def test_hmac_is_stable_and_not_the_number():
    h = phone_hmac("+2348031234567")
    assert h == phone_hmac("+2348031234567")
    assert "8031234567" not in h
    assert mask_phone("+2348031234567") == "+234803***67"
    assert mask_phone("123") == "***"


@pytest.mark.django_db
def test_participant_phone_roundtrip_and_lookup():
    p = Participant(role="agent", party="PA")
    p.set_phone("0803 123 4567")
    p.save()
    assert p.phone == "+2348031234567"
    assert "8031234567" not in p.phone_encrypted
    assert Participant.objects.by_phone("+2348031234567") == p
    assert not p.is_verified
    assert str(p).startswith("Party agent")
    assert Participant(role="voter").phone is None


@pytest.mark.django_db
def test_audit_log_is_append_only():
    entry = AuditLog.record(
        actor="system", action="test", object_type="x", object_id="1", after={"a": 1}
    )
    assert entry.after_digest and not entry.before_digest
    assert str(entry) == "test x:1"
    entry.action = "changed"
    with pytest.raises(AppendOnlyError):
        entry.save()
    with pytest.raises(AppendOnlyError):
        entry.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().update(action="x")
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()


@pytest.mark.django_db
def test_delete_my_data():
    p = Participant(display_name="Amaka", visitor_id="v1")
    p.set_phone("08031234567")
    p.save()
    delete_my_data(p)
    p.refresh_from_db()
    assert p.phone_hmac is None and p.phone_encrypted == "" and p.display_name == ""
    assert p.anonymised_at is not None
    assert AuditLog.objects.filter(action="privacy.delete_my_data", object_id=str(p.pk)).exists()


def test_redaction():
    fake_key = "sk-" + "ABCDEFGHIJ" * 2
    text = redact(f"call +2348031234567 or 08031234567 api_key=abc123 token: xyz {fake_key}")
    assert "8031234567" not in text
    assert "abc123" not in text and "xyz" not in text and "ABCDEFGHIJ" not in text


def test_redact_filter_and_json_formatter():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "phone %s", ("08031234567",), None)
    RedactFilter().filter(record)
    out = JsonFormatter().format(record)
    assert "[phone]" in out and "0803" not in out


@pytest.mark.django_db
def test_visitor_cookie_and_request_id(settings, tmp_path):
    settings.WORKER_HEARTBEAT_FILE = tmp_path / "hb"
    c = Client()
    r = c.get("/healthz")
    assert r.status_code == 503  # worker heartbeat missing
    assert r.json()["checks"] == {"db": "ok", "worker": "stale"}
    assert "X-Request-ID" in r
    assert settings.VISITOR_COOKIE_NAME in r.cookies
    (tmp_path / "hb").touch()
    r2 = c.get("/healthz")
    assert r2.status_code == 200
    assert settings.VISITOR_COOKIE_NAME not in r2.cookies  # existing visitor kept


@pytest.mark.django_db
def test_tampered_visitor_cookie_is_replaced(settings):
    c = Client()
    c.cookies[settings.VISITOR_COOKIE_NAME] = "tampered"
    r = c.get("/healthz")
    assert settings.VISITOR_COOKIE_NAME in r.cookies


@pytest.mark.django_db
def test_security_headers():
    r = Client().get("/healthz")
    csp = r["Content-Security-Policy"]
    assert (
        "script-src 'self'" in csp
        and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    )
    assert "frame-ancestors 'none'" in csp
    assert "camera=(self)" in r["Permissions-Policy"]


def test_client_ip_ignores_spoofed_forwarded_for(settings, rf):
    from apps.core.ratelimit import client_ip

    req = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 10.0.0.9", REMOTE_ADDR="10.0.0.1")
    settings.TRUSTED_PROXY_COUNT = 0
    assert client_ip(req) == "10.0.0.1"
    settings.TRUSTED_PROXY_COUNT = 1
    assert client_ip(req) == "10.0.0.9"  # the address our proxy saw, not the spoofed one
    settings.TRUSTED_PROXY_COUNT = 3
    assert client_ip(req) == "10.0.0.1"
