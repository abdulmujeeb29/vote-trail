"""App screens follow the voter's language: Pidgin, Hausa, Yoruba and Igbo are complete."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

LANGS = ["pcm", "ha", "yo", "ig"]
PLACEHOLDER = re.compile(r"%\(\w+\)[sd]")


def _entries(lang):
    """Minimal .po reader: yields (msgid, [msgstr, ...]) with continuation lines joined."""
    path = Path(settings.BASE_DIR) / "locale" / lang / "LC_MESSAGES" / "django.po"
    entries, cur, key = [], None, None
    for line in path.read_text().splitlines():
        m = re.match(r'^(msgid|msgid_plural|msgstr(?:\[\d\])?) "(.*)"$', line)
        if m:
            key = m.group(1)
            if key == "msgid":
                cur = {"msgid": "", "strs": {}}
                entries.append(cur)
            if key.startswith("msgstr"):
                cur["strs"][key] = m.group(2)
            else:
                cur[key] = m.group(2)
        elif line.startswith('"') and cur is not None:
            part = line[1:-1]
            if key.startswith("msgstr"):
                cur["strs"][key] += part
            else:
                cur[key] += part
    for e in entries:
        if e["msgid"]:  # skip the header
            yield e["msgid"], list(e["strs"].values())


@pytest.mark.parametrize("lang", LANGS)
def test_every_screen_string_is_translated_with_placeholders_intact(lang):
    count = 0
    for msgid, strs in _entries(lang):
        count += 1
        assert strs and all(strs), f"{lang}: untranslated {msgid!r}"
        for s in strs:
            assert sorted(PLACEHOLDER.findall(s)) == sorted(PLACEHOLDER.findall(msgid)), (
                lang,
                msgid,
            )
    assert count > 250


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("lang", "nav", "next_title"),
    [
        ("en", ">Verify<", "Visit your new polling unit before election day"),
        ("pcm", ">Check am<", "Go see your new polling unit before election day"),
        ("ha", ">Tantance<", "Ziyarci sabuwar rumfar zabenka kafin ranar zabe"),
        ("yo", ">Ye e wo<", "Lo wo ibudo idibo tuntun re ki ojo idibo to de"),
        ("ig", ">Nyochaa<", "Gaa leta ebe ntuli aka ohuru gi tupu ubochi ntuli aka"),
    ],
)
def test_my_vote_renders_in_the_chosen_language(seeded, lang, nav, next_title):
    c = Client()
    c.post("/setup/", {"step": "1", "language": lang})
    c.post("/setup/", {"step": "2", "pu_code": "370602002"})
    c.post("/setup/", {"step": "3", "phone": ""})
    r = c.get("/vote/")
    html = r.content.decode()
    assert f'lang="{lang}"' in html and r["Content-Language"] == lang
    assert nav in html and next_title in html


@pytest.mark.django_db
def test_landing_stays_english_and_new_visitors_get_english(seeded):
    html = Client().get("/").content.decode()
    assert 'lang="en"' in html and "every voice." in html
