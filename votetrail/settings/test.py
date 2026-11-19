from .base import *  # noqa: F403
from .base import BASE_DIR

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = BASE_DIR / ".test-media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
NOTIFY_BACKEND = "outbox"
TRUSTED_AUTHORITIES = ["inecnigeria.org", "npf.gov.ng"]
WORKER_HEARTBEAT_FILE = BASE_DIR / ".test-worker-heartbeat"
STATIC_ROOT = None
WHITENOISE_USE_FINDERS = True
DATABASES["default"].setdefault("TEST", {})["NAME"] = BASE_DIR / ".test-db.sqlite3"  # noqa: F405
