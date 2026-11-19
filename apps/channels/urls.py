from django.urls import path

from . import views

app_name = "channels"

urlpatterns = [
    path("ussd", views.ussd_webhook, name="ussd"),
    path("sms/inbound", views.sms_webhook, name="sms_inbound"),
    path("simulator/", views.simulator, name="simulator"),
    path("api/simulator/ussd", views.simulator_ussd, name="sim_ussd"),
    path("api/simulator/sms", views.simulator_sms, name="sim_sms"),
    path("api/simulator/inbox", views.simulator_inbox, name="sim_inbox"),
]
