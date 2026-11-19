"""Shared settings. Environment-specific modules import from here."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

APP_NAME = env.str("APP_NAME", default="VoteTrail")
SECRET_KEY = env.str("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.geo",
    "apps.elections",
    "apps.jobs",
    "apps.trust",
    "apps.results",
    "apps.claims",
    "apps.alerts",
    "apps.channels",
    "apps.voice",
    "apps.journey",
    "apps.dashboard",
    "apps.demo",
]

MIDDLEWARE = [
    "apps.core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.VisitorIdentityMiddleware",
    "apps.journey.middleware.ProfileLanguageMiddleware",
]

ROOT_URLCONF = "votetrail.urls"
WSGI_APPLICATION = "votetrail.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_meta",
                "apps.journey.context.profile",
            ],
        },
    }
]

# SQLite locally (default), Postgres in production via DATABASE_URL.
_db_url = env.str("DATABASE_URL", default="")
if _db_url:
    DATABASES = {"default": env.db_url_config(_db_url)}
    DATABASES["default"]["CONN_MAX_AGE"] = 60
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                "timeout": 20,
                "transaction_mode": "IMMEDIATE",
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("pcm", "Naijá (Pidgin)"),
    ("yo", "Yorùbá"),
    ("ha", "Hausa"),
    ("ig", "Igbo"),
]
BETA_LANGUAGES: set[str] = set()
LOCALE_PATHS = [BASE_DIR / "locale"]

# Django has no built-in locale data for these; register them so i18n helpers work.
from django.conf.locale import LANG_INFO  # noqa: E402

for _code, _name, _local in (
    ("pcm", "Nigerian Pidgin", "Naijá"),
    ("ha", "Hausa", "Hausa"),
    ("yo", "Yoruba", "Yorùbá"),
    ("ig", "Igbo", "Igbo"),
):
    LANG_INFO.setdefault(_code, {"bidi": False, "code": _code, "name": _name, "name_local": _local})
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env.str("MEDIA_ROOT", default=str(BASE_DIR / "media")))

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

LOGIN_URL = "/dashboard/login/"
# Pretend "now" for demos (ISO datetime), e.g. 2027-01-16T10:00:00+01:00. Empty = real time.
DEMO_NOW = env.str("DEMO_NOW", default="")
# Number of reverse proxies in front of the app (ThalesOps: 1). 0 = ignore X-Forwarded-For.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)
UPLOAD_LIMIT_PER_IP = env.int("UPLOAD_LIMIT_PER_IP", default=120)

# --- Privacy ---
PHONE_HMAC_KEY = env.str("PHONE_HMAC_KEY")
FIELD_ENCRYPTION_KEY = env.str("FIELD_ENCRYPTION_KEY")
VISITOR_COOKIE_NAME = "vt_visitor"
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 180
DATA_RETENTION_DAYS = env.int("DATA_RETENTION_DAYS", default=180)

# --- Trust engine ---
PU_RADIUS_M = env.int("PU_RADIUS_M", default=300)
CLAIM_WINDOW_HOURS = env.int("CLAIM_WINDOW_HOURS", default=3)
PHASH_MAX_DISTANCE = env.int("PHASH_MAX_DISTANCE", default=6)
SIMHASH_MAX_DISTANCE = env.int("SIMHASH_MAX_DISTANCE", default=3)
MIN_REPUTATION = env.int("MIN_REPUTATION", default=-3)
EXTRACTION_MIN_CONFIDENCE = env.float("EXTRACTION_MIN_CONFIDENCE", default=0.85)
# Authorities whose primary evidence can confirm/refute a claim. Empty by default;
# configured by operators only. The model can never add to this list.
TRUSTED_AUTHORITIES = env.list("TRUSTED_AUTHORITIES", default=[])
OFFICIAL_ANNOUNCEMENT_SOURCES = env.list(
    "OFFICIAL_ANNOUNCEMENT_SOURCES", default=["inecnigeria.org", "x.com/inecnigeria"]
)

# --- AI / external services (read lazily by clients; fail loudly when used unset) ---
AZURE_OPENAI_BASE_URL = env.str("AZURE_OPENAI_BASE_URL", default="")
AZURE_OPENAI_DEPLOYMENT = env.str("AZURE_OPENAI_DEPLOYMENT", default="")
AZURE_OPENAI_API_KEY = env.str("AZURE_OPENAI_API_KEY", default="")
AZURE_REALTIME_ENDPOINT = env.str("AZURE_REALTIME_ENDPOINT", default="")
AZURE_REALTIME_DEPLOYMENT = env.str("AZURE_REALTIME_DEPLOYMENT", default="")
AZURE_REALTIME_API_KEY = env.str("AZURE_REALTIME_API_KEY", default="")
ELEVENLABS_API_KEY = env.str("ELEVENLABS_API_KEY", default="")
ELEVENLABS_VOICE_ID_EN = env.str("ELEVENLABS_VOICE_ID_EN", default="")
ELEVENLABS_VOICE_ID_PCM = env.str("ELEVENLABS_VOICE_ID_PCM", default="")
TAVILY_API_KEY = env.str("TAVILY_API_KEY", default="")
MAPBOX_PUBLIC_TOKEN = env.str("MAPBOX_PUBLIC_TOKEN", default="")
NOTIFY_BACKEND = env.str("NOTIFY_BACKEND", default="outbox")
AT_USERNAME = env.str("AT_USERNAME", default="sandbox")
AT_API_KEY = env.str("AT_API_KEY", default="")

# "azure" (real) or "demo" (deterministic, for browser tests and offline demos only)
EXTRACTOR_BACKEND = env.str("EXTRACTOR_BACKEND", default="azure")

# Basic-phone channels
CHANNEL_WEBHOOK_TOKEN = env.str("CHANNEL_WEBHOOK_TOKEN", default="")
USSD_SERVICE_CODE = env.str("USSD_SERVICE_CODE", default="*384*2027#")
# The phone simulator shows any number's outbox. Demo/hackathon only: turn off with real users.
SIMULATOR_ENABLED = env.bool("SIMULATOR_ENABLED", default=True)
CLAIMS_WEB_SEARCH = env.bool("CLAIMS_WEB_SEARCH", default=True)

# --- Jobs ---
JOB_LEASE_SECONDS = env.int("JOB_LEASE_SECONDS", default=120)
JOB_MAX_ATTEMPTS = env.int("JOB_MAX_ATTEMPTS", default=3)
WORKER_HEARTBEAT_FILE = Path(
    env.str("WORKER_HEARTBEAT_FILE", default=str(BASE_DIR / ".worker-heartbeat"))
)
WORKER_HEARTBEAT_MAX_AGE = env.int("WORKER_HEARTBEAT_MAX_AGE", default=60)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact": {"()": "apps.core.logging.RedactFilter"},
        "request_id": {"()": "apps.core.logging.RequestIdFilter"},
    },
    "formatters": {"json": {"()": "apps.core.logging.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["redact", "request_id"],
        }
    },
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO")},
}
