from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "journey"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("welcome/", RedirectView.as_view(url="/", permanent=False)),
    path("vote/", views.home, name="home"),
    path("setup/", views.setup, name="setup"),
    path("me/mark/<str:flag>", views.mark, name="mark"),
    path("me/language", views.set_language, name="language"),
    path("me/unit/<str:code>", views.set_unit, name="set_unit"),
    path("verify/", views.verify, name="verify"),
    path("activity/", views.activity, name="activity"),
    path("journey/", RedirectView.as_view(pattern_name="journey:home"), name="journey"),
    path("register/", views.register, name="register"),
    path("pvc/", views.pvc, name="pvc"),
    path("accessibility/", views.accessibility, name="access"),
    path("find/", views.find, name="find"),
    path("pu/<str:code>/", views.pu_detail, name="pu"),
    path("pu/<str:code>/subscribe", views.subscribe, name="subscribe"),
    path("pu/<str:code>/today/", views.today, name="today"),
    path("pu/<str:code>/checkin", views.checkin, name="checkin"),
    path("api/pu/nearest", views.nearest_api, name="nearest"),
    path("api/me/sync", views.sync_api, name="sync"),
    path("rumours/", views.rumours, name="rumours"),
    path("rumours/new", views.rumour_submit, name="rumour_submit"),
    path("rumours/<int:pk>/", views.rumour_detail, name="rumour"),
    path("api/rumours/<int:pk>", views.rumour_status_api, name="rumour_api"),
    path("api/pu/<str:code>/today", views.today_api, name="today_api"),
]
