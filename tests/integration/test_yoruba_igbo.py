"""Yoruba and Igbo are full languages on USSD, SMS and verdicts, like Hausa."""

import pytest

from apps.channels import messages, ussd
from apps.claims import verdicts
from apps.core.models import Participant

PHONE = "+2348031238888"


@pytest.mark.parametrize("lang", ["pcm", "ha", "yo", "ig"])
def test_every_table_has_the_language_in_plain_sms_letters(lang):
    tables = [*messages.MESSAGES.values(), *ussd.T.values(), *verdicts.REASON.values()]
    tables += [*verdicts.HEADLINE.values(), verdicts.UNKNOWN]
    for table in tables:
        assert lang in table
        assert table[lang].replace("…", "").isascii(), table[lang]
    assert messages.render("otp.code", lang, app="VT", code="1")[1] == lang
    assert verdicts.render(None, lang)["language"] == lang


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("key", "lang", "saved", "menu", "moved"),
    [
        ("4", "yo", "Yoruba", "Ibudo idibo mi", "WON TI GBE E KURO"),
        ("5", "ig", "Igbo", "Ebe ntuli aka m", "EBUGHARILA YA"),
    ],
)
def test_ussd_language_switch(seeded, key, lang, saved, menu, moved):
    assert "4 Yoruba\n5 Igbo" in ussd.handle("s", PHONE, "5")
    assert saved in ussd.handle("s", PHONE, f"5*{key}")
    assert Participant.objects.get().language == lang
    assert menu in ussd.handle("s", PHONE, "")
    reply = ussd.handle("s", PHONE, "1*370602002")
    assert moved in reply and "37/06/02/004" in reply and len(reply) <= ussd.MAX
