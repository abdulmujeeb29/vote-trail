from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz, service_worker

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("sw.js", service_worker, name="sw"),
    path("admin/", admin.site.urls),
    path("dashboard/", include("apps.dashboard.urls")),
    path("", include("apps.journey.urls")),
    path("", include("apps.demo.urls")),
    path("", include("apps.results.urls")),
    path("", include("apps.channels.urls")),
    path("", include("apps.voice.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
