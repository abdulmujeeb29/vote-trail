from django.urls import path

from . import views

app_name = "demo"
urlpatterns = [path("demo/", views.replay, name="replay")]
