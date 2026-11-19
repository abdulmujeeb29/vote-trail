"""USSD menu per the Africa's Talking spec: POST sessionId, serviceCode, phoneNumber, text.

Replies start with "CON " (continue) or "END " (finish). Plain text, max 182 characters.
State lives in `text` (choices joined by '*'), so the handler is stateless.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.db import transaction

from apps.alerts.models import Subscription
from apps.claims.services import submit_report
from apps.claims.verdicts import sms_text
from apps.core import privacy
from apps.core.models import Participant
from apps.elections.models import Election
from apps.geo.codes import InvalidPUCode, normalize_pu_code
from apps.geo.models import PollingUnit
from apps.results import presenters
from apps.results.models import ResultCheck

MAX = 182
USSD_LANGS_BY_KEY = {"1": "en", "2": "pcm", "3": "ha", "4": "yo", "5": "ig"}
USSD_LANGS = set(USSD_LANGS_BY_KEY.values())

T = {
    "menu": {
        "en": "{app}\n1 My polling unit\n2 Check a rumour\n3 Result for my PU\n4 Get alerts\n"
        "5 Language",
        "pcm": "{app}\n1 My polling unit\n2 Check rumour\n3 Result for my PU\n4 Collect alert\n"
        "5 Language",
        "ha": "{app}\n1 Rumfar zabe ta\n2 Duba jita-jita\n3 Sakamakon rumfata\n4 Karbi sanarwa\n"
        "5 Harshe",
        "yo": "{app}\n1 Ibudo idibo mi\n2 Ye agbaso oro wo\n3 Esi ibudo mi\n4 Gba itaniji\n5 Ede",
        "ig": "{app}\n1 Ebe ntuli aka m\n2 Nyochaa akuko\n3 Nsonaazu PU m\n4 Nata ozi\n5 Asusu",
    },
    "ask_pu": {
        "en": "Enter your PU code, 9 digits (e.g. 370602004)",
        "pcm": "Type your PU code, 9 numbers (e.g. 370602004)",
        "ha": "Shigar da lambar PU, lambobi 9 (misali 370602004)",
        "yo": "Te koodu PU re, nomba 9 (apeere 370602004)",
        "ig": "Tinye koodu PU gi, onu ogugu 9 (dika 370602004)",
    },
    "bad_pu": {
        "en": "We couldn't find that PU code. Check your voter's card and try again.",
        "pcm": "We no see that PU code. Check your voter card try again.",
        "ha": "Ba mu sami wannan lambar PU ba. Duba katin zabenka ka sake gwadawa.",
        "yo": "A ko ri koodu PU yii. Wo kaadi idibo re ki o tun gbiyanju.",
        "ig": "Anyi ahughi koodu PU a. Lelee kaadi ntuli aka gi wee nwaa ozo.",
    },
    "pu": {
        "en": "PU {code}: {name}.{moved}",
        "pcm": "PU {code}: {name}.{moved}",
        "ha": "PU {code}: {name}.{moved}",
        "yo": "PU {code}: {name}.{moved}",
        "ig": "PU {code}: {name}.{moved}",
    },
    "moved": {
        "en": " MOVED: vote at {name} ({code}).",
        "pcm": " E DON MOVE: go vote for {name} ({code}).",
        "ha": " AN MAYAR DA ITA: ka je ka yi zabe a {name} ({code}).",
        "yo": " WON TI GBE E KURO: lo dibo ni {name} ({code}).",
        "ig": " EBUGHARILA YA: gaa tuo vootu na {name} ({code}).",
    },
    "ask_rumour": {
        "en": "Type the message you received:",
        "pcm": "Type the message wey you receive:",
        "ha": "Rubuta sakon da ka karba:",
        "yo": "Te oro ti won fi ranse si o:",
        "ig": "Dee ozi e zitere gi:",
    },
    "rumour_ack": {
        "en": "Thanks. {verdict} We'll SMS you if this changes.",
        "pcm": "Thank you. {verdict} We go SMS you if e change.",
        "ha": "Na gode. {verdict} Za mu tura maka SMS idan wani abu ya canza.",
        "yo": "E se. {verdict} A o fi SMS ranse si o ti eyi ba yipada.",
        "ig": "Daalu. {verdict} Anyi ga-ezitere gi SMS ma o gbanwee.",
    },
    "result": {
        "en": "PU {code}: {label}. {explain}",
        "pcm": "PU {code}: {label}. {explain}",
        "ha": "PU {code}: {label}. {explain}",
        "yo": "PU {code}: {label}. {explain}",
        "ig": "PU {code}: {label}. {explain}",
    },
    "subscribed": {
        "en": "Done. You'll get SMS alerts for PU {code}. Reply STOP to end.",
        "pcm": "Done. You go dey get SMS alert for PU {code}. Send STOP to stop.",
        "ha": "An gama. Za ka rika samun sanarwar SMS na PU {code}. Tura STOP don dainawa.",
        "yo": "O ti pari. Iwo yoo maa gba itaniji SMS fun PU {code}. Fi STOP ranse lati duro.",
        "ig": "O zuola. I ga-anata ozi SMS maka PU {code}. Zite STOP ka o kwusi.",
    },
    "lang_menu": {
        "en": "1 English\n2 Pidgin\n3 Hausa\n4 Yoruba\n5 Igbo",
        "pcm": "1 English\n2 Pidgin\n3 Hausa\n4 Yoruba\n5 Igbo",
        "ha": "1 English\n2 Pidgin\n3 Hausa\n4 Yoruba\n5 Igbo",
        "yo": "1 English\n2 Pidgin\n3 Hausa\n4 Yoruba\n5 Igbo",
        "ig": "1 English\n2 Pidgin\n3 Hausa\n4 Yoruba\n5 Igbo",
    },
    "lang_set": {
        "en": "Language saved: English.",
        "pcm": "We don set am: Pidgin.",
        "ha": "An ajiye harshe: Hausa.",
        "yo": "A ti fi ede pamo: Yoruba.",
        "ig": "Echekwala asusu: Igbo.",
    },
    "checkin_menu": {
        "en": "Official check-in\n1 PU opened\n2 Materials arrived\n3 BVAS working\n"
        "4 BVAS not working",
        "pcm": "Official check-in\n1 PU don open\n2 Materials "
        "don land\n3 BVAS dey work\n4 BVAS no dey work",
        "ha": "Shigar jami'i\n1 An bude rumfa\n2 Kayan zabe sun iso\n3 BVAS na aiki\n"
        "4 BVAS baya aiki",
        "yo": "Iforukosile osise\n1 Ibudo ti si\n2 Awon ohun elo ti de\n3 BVAS n sise\n4 BVAS "
        "ko sise",
        "ig": "Ndebanye onye oru\n1 Emeghere PU\n2 Ihe ntuli aka eruola\n3 BVAS na-aru oru\n4 "
        "BVAS anaghi aru oru",
    },
    "checkin_done": {
        "en": "Recorded for PU {code}. Thank you.",
        "pcm": "We don record am for PU {code}. Thank you.",
        "ha": "An rubuta wa PU {code}. Na gode.",
        "yo": "A ti ko o sile fun PU {code}. E se.",
        "ig": "Edeela ya maka PU {code}. Daalu.",
    },
    "not_official": {
        "en": "Only verified polling officials can check in.",
        "pcm": "Na only verified polling officials fit check in.",
        "ha": "Jami'an zabe da aka tabbatar ne kadai za su iya shiga.",
        "yo": "Awon osise idibo ti a fowosi nikan lo le forukosile.",
        "ig": "O bu naani ndi oru ntuli aka akwadoro nwere ike idebanye aha.",
    },
    "invalid": {
        "en": "Invalid choice. Dial again.",
        "pcm": "That choice no correct. Dial again.",
        "ha": "Zabin bai dace ba. Sake kira.",
        "yo": "Asayan ko to. Tun pe.",
        "ig": "Nhoro ezighi ezi. Kpoo ozo.",
    },
}


def _t(key: str, lang: str, **kw: object) -> str:
    return T[key].get(lang, T[key]["en"]).format(**kw)


def _reply(kind: str, body: str) -> str:
    body = re.sub(r"[ \t]+", " ", body).strip()
    room = MAX - 4
    if len(body) > room:
        body = body[: room - 1].rstrip() + "…"
    return f"{kind} {body}"


def parse_ussd_pu(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        return normalize_pu_code(f"{digits[:2]}/{digits[2:4]}/{digits[4:6]}/{digits[6:]}")
    return normalize_pu_code(raw)


def _participant(phone: str) -> Participant:
    e164 = privacy.normalize_ng_phone(phone)
    p = Participant.objects.filter(phone_hmac=privacy.phone_hmac(e164)).first()
    if p is None:
        p = Participant()
        p.set_phone(e164)
        p.save()
    return p


def _pu(raw: str) -> PollingUnit | None:
    try:
        return PollingUnit.objects.filter(code=parse_ussd_pu(raw)).first()
    except InvalidPUCode:
        return None


@transaction.atomic
def handle(session_id: str, phone: str, text: str) -> str:
    try:
        p = _participant(phone)
    except privacy.InvalidPhoneNumber:
        return _reply("END", "Unsupported phone number.")
    lang = p.language if p.language in USSD_LANGS else "en"
    parts = [x.strip() for x in (text or "").split("*")] if text else []
    if not parts:
        return _reply("CON", _t("menu", lang, app=settings.APP_NAME))
    choice, rest = parts[0], parts[1:]

    if choice in ("1", "3", "4"):
        if not rest:
            return _reply("CON", _t("ask_pu", lang))
        pu = _pu("".join(rest))
        if pu is None:
            return _reply("END", _t("bad_pu", lang))
        if choice == "1":
            cur = pu.current
            moved = _t("moved", lang, name=cur.name, code=cur.code) if cur.pk != pu.pk else ""
            return _reply("END", _t("pu", lang, code=pu.code, name=pu.name, moved=moved))
        if choice == "3":
            election = Election.objects.order_by("-date").first()
            check = ResultCheck.objects.filter(election=election, polling_unit=pu).first()
            status = check.status if check else "pending"
            return _reply(
                "END",
                _t(
                    "result",
                    lang,
                    code=pu.code,
                    label=presenters.STATUS_LABEL[status],
                    explain=presenters.explain(check),
                ),
            )
        Subscription.objects.update_or_create(
            participant=p, polling_unit=pu, defaults={"sms": True, "active": True, "language": lang}
        )
        return _reply("END", _t("subscribed", lang, code=pu.code))

    if choice == "2":
        if not rest:
            return _reply("CON", _t("ask_rumour", lang))
        message = "*".join(rest)
        try:
            report = submit_report(
                text=message, source="ussd", is_forward=True, participant=p, language=lang
            )
        except ValueError as exc:
            return _reply("END", str(exc))
        return _reply("END", _t("rumour_ack", lang, verdict=sms_text(report.claim.latest, lang)))

    if choice == "6":
        return _official_checkin(p, lang, rest)

    if choice == "5":
        if not rest:
            return _reply("CON", _t("lang_menu", lang))
        if rest[0] in USSD_LANGS_BY_KEY:
            p.language = USSD_LANGS_BY_KEY[rest[0]]
            p.save(update_fields=["language"])
            return _reply("END", _t("lang_set", p.language))
    return _reply("END", _t("invalid", lang))


CHECKIN_KINDS = {"1": "opened", "2": "materials", "3": "bvas_ok", "4": "bvas_fail"}


def _official_checkin(p: Participant, lang: str, rest: list[str]) -> str:
    from apps.core.models import Role
    from apps.journey.models import CheckIn

    if p.role != Role.OFFICIAL or not p.is_verified:
        return _reply("END", _t("not_official", lang))
    if not rest:
        return _reply("CON", _t("ask_pu", lang))
    pu = _pu(rest[0])
    if pu is None:
        return _reply("END", _t("bad_pu", lang))
    if len(rest) < 2:
        return _reply("CON", _t("checkin_menu", lang))
    kind = CHECKIN_KINDS.get(rest[1])
    if kind is None:
        return _reply("END", _t("invalid", lang))
    CheckIn.objects.create(polling_unit=pu, participant=p, kind=kind, official=True)
    return _reply("END", _t("checkin_done", lang, code=pu.code))
