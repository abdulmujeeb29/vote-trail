from django.urls import path

from . import views

app_name = "voice"

urlpatterns = [
    path("ask/", views.voice_page, name="ask"),
    path("voice/", views.voice_page, name="assistant"),
    path("api/voice/session", views.session_api, name="session"),
    path("api/voice/tool", views.tool_api, name="tool"),
    path("api/voice/note", views.voice_note_api, name="note"),
]
