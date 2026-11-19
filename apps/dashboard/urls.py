from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="/"), name="logout"),
    path("verify/", views.verify, name="verify"),
    path("", views.overview, name="overview"),
    path("results/<str:code>/", views.result_review, name="result"),
    path("uploads/<int:pk>/decision", views.upload_decision, name="upload_decision"),
    path("claims/", views.claims, name="claims"),
    path("claims/<int:pk>/evidence", views.claim_evidence, name="claim_evidence"),
    path("announcements/", views.announcements, name="announcements"),
    path(
        "announcements/<int:pk>/decision", views.announcement_decision, name="announcement_decision"
    ),
]
