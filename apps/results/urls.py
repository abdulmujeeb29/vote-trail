from django.urls import path

from . import views

app_name = "results"

urlpatterns = [
    path("capture/", views.capture, name="capture"),
    path("capture/<str:code>/", views.capture, name="capture_pu"),
    path("pu/<str:code>/result/", views.pu_result, name="pu_result"),
    path("pu/<str:code>/evidence.zip", views.evidence_pack, name="evidence"),
    path("api/results/uploads", views.upload_api, name="upload_api"),
    path("api/results/uploads/<str:key>", views.upload_status_api, name="upload_status"),
    path("api/pu/<str:code>/result", views.pu_result_api, name="pu_result_api"),
]
