"""Browser-test settings: real server, deterministic fake AI (no network, no tokens)."""

from .base import BASE_DIR
from .prod import *  # noqa: F403

DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / ".e2e-db.sqlite3",
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
MEDIA_ROOT = BASE_DIR / ".e2e-media"
WORKER_HEARTBEAT_FILE = BASE_DIR / ".e2e-heartbeat"
EXTRACTOR_BACKEND = "demo"
