from .base import *  # noqa: F403

DEBUG = True
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
# Let WhiteNoise (not runserver) serve static files, so the header below applies.
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]  # noqa: F405


def _revalidate(headers, path, url):
    # Local only: always revalidate static files so design changes show up on reload.
    headers["Cache-Control"] = "no-cache"


WHITENOISE_ADD_HEADERS_FUNCTION = _revalidate
