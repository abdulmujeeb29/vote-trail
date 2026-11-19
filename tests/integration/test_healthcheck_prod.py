"""Platform health probes come over plain HTTP, by IP: no HTTPS redirect, no host rejection."""

import pytest
from django.test import Client


@pytest.mark.django_db
def test_healthz_skips_https_redirect_and_host_check(settings):
    settings.SECURE_SSL_REDIRECT = True
    settings.ALLOWED_HOSTS = ["vote-trail.apps.thalesops.com"]
    c = Client()
    r = c.get("/healthz", HTTP_HOST="10.0.0.5:8000")
    assert r.status_code in (200, 503)  # answered directly, never 301/400
    assert r.json()["checks"]["db"] == "ok"
    # Every other page still enforces HTTPS and the host list.
    assert c.get("/", HTTP_HOST="vote-trail.apps.thalesops.com").status_code == 301
    assert c.get("/", HTTP_HOST="10.0.0.5:8000", secure=True).status_code == 400
