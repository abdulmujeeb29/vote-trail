"""Hausa is a full language on the channels basic-phone voters use: USSD, SMS and verdicts."""

import pytest

from apps.alerts.models import Alert, Subscription
from apps.alerts.services import VOICE_LANGS, ingest
from apps.channels import messages, ussd
from apps.channels.models import OutboxMessage
from apps.claims import verdicts
from apps.core.models import Participant
from apps.geo.models import PollingUnit
from apps.jobs.queue import run_pending

from .test_alerts_channels_voice import NOTICE, OLD, fakes  # noqa: F401

PHONE = "+2348031239999"


def test_every_template_has_hausa_and_stays_in_gsm7():
    gsm7 = set(
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà{}[]~|^\\€"
    )
    tables = [*messages.MESSAGES.values(), *ussd.T.values(), *verdicts.REASON.values()]
    tables += [*verdicts.HEADLINE.values(), verdicts.UNKNOWN]
    for table in tables:
        assert "ha" in table
        assert set(table["ha"]) <= gsm7 | {"…"}, table["ha"]
    text, lang = messages.render("otp.code", "ha", app="VT", code="123456")
    assert lang == "ha" and "Lambar VT: 123456" in text


@pytest.mark.django_db
def test_ussd_switch_to_hausa_then_everything_is_hausa(seeded):
    assert "3 Hausa" in ussd.handle("s", PHONE, "5")
    assert "An ajiye harshe: Hausa" in ussd.handle("s", PHONE, "5*3")
    assert Participant.objects.get().language == "ha"
    menu = ussd.handle("s", PHONE, "")
    assert menu.startswith("CON ") and "Rumfar zabe ta" in menu
    moved = ussd.handle("s", PHONE, "1*370602002")
    assert "AN MAYAR DA ITA" in moved and "37/06/02/004" in moved and len(moved) <= ussd.MAX
    assert "Zabin bai dace ba" in ussd.handle("s", PHONE, "9")


@pytest.mark.django_db(transaction=True)
def test_hausa_voter_gets_hausa_sms_and_no_voice_note(fakes):  # noqa: F811
    p = Participant(language="ha")
    p.set_phone("08031110777")
    p.save()
    Subscription.objects.create(
        participant=p, polling_unit=PollingUnit.objects.get(code=OLD), language="ha", voice=True
    )
    ingest(source_url="https://www.inecnigeria.org/notice/relocation", text=NOTICE, is_mock=True)
    run_pending()
    assert Alert.objects.count() == 1
    msgs = OutboxMessage.objects.filter(participant=p)
    assert [m.channel for m in msgs] == ["sms"]  # no Hausa TTS voice yet: SMS only
    assert "An mayar da rumfar zabenku" in msgs[0].body and msgs[0].language == "ha"
    assert "ha" not in VOICE_LANGS


@pytest.mark.django_db(transaction=True)
def test_hausa_leader_who_wanted_voice_gets_sms_instead(fakes):  # noqa: F811
    p = Participant(language="ha", role="community_leader")
    p.set_phone("08031110778")
    p.save()
    Subscription.objects.create(
        participant=p, polling_unit=PollingUnit.objects.get(code=OLD), language="ha", sms=False
    )
    ingest(source_url="https://www.inecnigeria.org/notice/relocation", text=NOTICE, is_mock=True)
    run_pending()
    assert [m.channel for m in OutboxMessage.objects.filter(participant=p)] == ["sms"]


def test_hausa_verdict():
    v = verdicts.render(None, "ha")
    assert v["headline"] == "Muna dubawa…"
