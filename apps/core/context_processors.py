from django.conf import settings


def app_meta(request):
    return {
        "APP_NAME": settings.APP_NAME,
        "BETA_LANGUAGES": settings.BETA_LANGUAGES,
        "MAPBOX_PUBLIC_TOKEN": settings.MAPBOX_PUBLIC_TOKEN,
    }
