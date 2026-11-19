"""Show every app screen in the language the voter chose at setup."""

from __future__ import annotations

from django.utils import translation

from .models import VoterProfile

APP_LANGS = {"en", "pcm", "ha", "yo", "ig"}


class ProfileLanguageMiddleware:
    """Activate the voter's saved language (read-only lookup; no profile is created here)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = "en"
        visitor = getattr(request, "visitor_id", None)
        if visitor:
            saved = (
                VoterProfile.objects.filter(visitor_id=visitor)
                .values_list("language", flat=True)
                .first()
            )
            if saved in APP_LANGS:
                lang = saved
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", lang)
        translation.deactivate()
        return response


# Labels passed into templates as variables ({% translate back_label %}), listed here so
# makemessages extracts them.
from django.utils.translation import gettext_noop  # noqa: E402

TEMPLATE_LABELS = [
    gettext_noop("MY VOTE"),
    gettext_noop("VERIFY"),
    gettext_noop("POLLING UNIT"),
    gettext_noop("BACK"),
    gettext_noop("I'm registered"),
    gettext_noop("Registered"),
    gettext_noop("I have my PVC"),
    gettext_noop("PVC collected"),
]
