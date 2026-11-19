import io
import json
import struct
import wave
from unittest import mock

import pytest
from django.core.files.base import ContentFile
from django.test import Client
from django.utils import timezone

from apps.alerts import extract as alert_extract
from apps.alerts.models import Alert, Announcement, Subscription
from apps.alerts.services import deliver, ingest, is_official
from apps.channels import ussd
from apps.channels.messages import render as render_msg
from apps.channels.models import OutboxMessage
from apps.channels.otp import OtpError, request_otp, verify_otp
from apps.channels.sms import handle_inbound, parse_agent_result
from apps.claims import analysis, search
from apps.core.models import Participant
from apps.geo.models import PollingUnit
from apps.jobs.queue import run_pending
from apps.voice import realtime, tools, tts
from apps.voice.refusals import refusal_for

OLD, NEW = "37/06/02/002", "37/06/02/004"
NOTICE = (
    "INEC notice: Polling unit 37/06/02/002 (Garki Village/Near Da'a Social Club) has been "
    "relocated to 37/06/02/004 (Garki Village II/New Pri. Sch.) for the 2027 elections."
)


class FakeReader:
    def __init__(self, quote=NOTICE[:60]):
        self.quote = quote

    def read(self, text):
        return {
            "kind": "pu_relocation",
            "affected": [
                {"pu_code": OLD, "new_pu_code": NEW, "quote": self.quote},
                {"pu_code": "37/99/99/999", "new_pu_code": None, "quote": "x"},
            ],
        }


class FakeSynth:
    calls = 0

    def synth(self, text, voice_id):
        FakeSynth.calls += 1
        return b"ID3fake-mp3"


@pytest.fixture
def fakes(seeded, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.ELEVENLABS_VOICE_ID_EN = "voice-en"
    settings.ELEVENLABS_VOICE_ID_PCM = ""
    alert_extract.set_reader(FakeReader())
    tts.set_synth(FakeSynth())

    class A:
        model = "fake"

        def analyse(self, claim, items):
            return {
                "items": [
                    {
                        "id": i["id"],
                        "stance": "supports",
                        "quote": i["text"][:15],
                        "observed_at": None,
                        "explicit": False,
                    }
                    for i in items
                ]
            }

    analysis.set_analyzer(A())
    search.set_searcher(type("S", (), {"search": lambda self, q: []})())
    yield
    alert_extract.set_reader(None)
    tts.set_synth(None)
    analysis.set_analyzer(None)
    search.set_searcher(None)


def voter(i, pu_code, lang="en", role="voter", voice=False, sms=True):
    p = Participant(role=role, language=lang)
    p.set_phone(f"0803111{i:04d}")
    p.save()
    Subscription.objects.create(
        participant=p,
        polling_unit=PollingUnit.objects.get(code=pu_code),
        language=lang,
        voice=voice,
        sms=sms,
    )
    return p


def test_official_source_matching(settings):
    settings.OFFICIAL_ANNOUNCEMENT_SOURCES = ["inecnigeria.org", "x.com/inecnigeria"]
    assert is_official("https://www.inecnigeria.org/news/x")
    assert is_official("https://inecnigeria.org/x")
    assert is_official("https://x.com/inecnigeria/status/1")
    assert not is_official("https://x.com/fakeinec/status/1")
    assert not is_official("https://inecnigeria.org.fake.ng/x")


@pytest.mark.django_db(transaction=True)
def test_official_relocation_alerts_exactly_the_affected_voters(fakes):
    a = voter(1, OLD, "pcm")
    b = voter(2, OLD, "en", voice=True)
    leader = voter(3, OLD, role="community_leader", sms=False)
    voter(4, NEW)  # subscribed to the new PU: not affected
    voter(5, "37/06/01/001")  # elsewhere: not affected
    ingest(source_url="https://www.inecnigeria.org/notice/relocation", text=NOTICE, is_mock=True)
    run_pending()
    ann = Announcement.objects.get()
    assert ann.state == "applied" and ann.official
    assert "quote_not_found:37/99/99/999" in ann.errors
    msgs = OutboxMessage.objects.all()
    recipients = {(m.participant_id, m.channel) for m in msgs}
    assert recipients == {(a.pk, "sms"), (b.pk, "sms"), (b.pk, "voice"), (leader.pk, "voice")}
    pidgin = msgs.get(participant=a)
    assert "don move" in pidgin.body and pidgin.language == "pcm"
    assert all(m.audio_url for m in msgs.filter(channel="voice"))
    # re-delivery never duplicates
    deliver(Alert.objects.get())
    assert OutboxMessage.objects.count() == 4
    assert PollingUnit.objects.get(code=OLD).current.code == NEW


@pytest.mark.django_db(transaction=True)
def test_unofficial_source_waits_for_approval(fakes):
    voter(1, OLD)
    ingest(source_url="https://random-blog.ng/inec-news", text=NOTICE)
    run_pending()
    assert Announcement.objects.get().state == "pending_approval"
    assert not OutboxMessage.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_hallucinated_quote_is_dropped(fakes):
    alert_extract.set_reader(FakeReader(quote="This sentence is not in the notice"))
    ingest(source_url="https://inecnigeria.org/x", text=NOTICE)
    run_pending()
    ann = Announcement.objects.get()
    assert ann.state == "pending_approval"
    assert any(e.startswith("quote_not_found") for e in ann.errors)


@pytest.mark.django_db
def test_ingest_requires_source():
    with pytest.raises(ValueError):
        ingest(source_url="", text="x")


def test_message_templates_cover_en_and_pcm():
    from apps.channels.messages import MESSAGES

    for key, langs in MESSAGES.items():
        assert {"en", "pcm"} <= set(langs), key
    text, lang = render_msg("otp.code", "fr", app="VT", code="123456")
    assert lang == "en" and "123456" in text


@pytest.mark.django_db
class TestUssd:
    phone = "+2348031234567"

    def run(self, text):
        return ussd.handle("s1", self.phone, text)

    def test_menu(self, seeded):
        r = self.run("")
        assert r.startswith("CON ") and "1 My polling unit" in r

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "1",
            "1*370602002",
            "1*370602004",
            "1*123",
            "2",
            "2*They are buying votes at ward 5 share this",
            "2*hi",
            "3",
            "3*370602004",
            "4*370602004",
            "5",
            "5*2",
            "5*9",
            "9",
        ],
    )
    def test_every_path_is_valid_and_short(self, seeded, text):
        r = self.run(text)
        assert r[:4] in ("CON ", "END ")
        assert len(r) <= 182

    def test_moved_pu(self, seeded):
        r = self.run("1*370602002")
        assert r.startswith("END") and "MOVED" in r and "37/06/02/004" in r

    def test_pidgin(self, seeded):
        self.run("5*2")
        assert "E DON MOVE" in self.run("1*370602002")

    def test_subscribe(self, seeded):
        self.run("4*37/06/02/004")
        assert Subscription.objects.filter(polling_unit__code=NEW).count() == 1

    def test_bad_phone(self, seeded):
        assert ussd.handle("s", "123", "").startswith("END")

    def test_webhook(self, seeded, settings):
        c = Client()
        r = c.post(
            "/ussd",
            {"sessionId": "x", "serviceCode": "*384*2027#", "phoneNumber": self.phone, "text": ""},
        )
        assert r.status_code == 200 and r.content.startswith(b"CON")
        settings.CHANNEL_WEBHOOK_TOKEN = "t0ken"
        assert c.post("/ussd", {"phoneNumber": self.phone}).status_code == 403
        assert c.post("/ussd?token=t0ken", {"phoneNumber": self.phone}).status_code == 200


def test_ussd_truncation():
    long = ussd._reply("END", "x " * 200)
    assert len(long) <= 182 and long.endswith("…")


@pytest.mark.django_db(transaction=True)
def test_sms_commands(fakes):
    phone = "08031230000"
    assert "MOVED" in handle_inbound(phone, "PU 370602002")
    assert "Unknown" in handle_inbound(phone, "PU 1")
    assert "Thanks" in handle_inbound(phone, "CHECK they are sharing money at Garki ward 5")
    assert "Pending" in handle_inbound(phone, "RESULT 37/06/02/004")
    assert "Unknown" in handle_inbound(phone, "RESULT 99")
    assert "send PU" in handle_inbound(phone, "hello")
    assert "Stopped 0" in handle_inbound(phone, "STOP")
    assert "Only verified" in handle_inbound(phone, "R 370602004 PA 1 PB 2 REJ 0")
    assert OutboxMessage.objects.count() == 8


@pytest.mark.django_db(transaction=True)
def test_agent_sms_results_create_an_origin(fakes):
    p = Participant(role="agent", party="PA", verified_at=timezone.now())
    p.set_phone("08039990000")
    p.save()
    assert "Received figures" in handle_inbound("08039990000", "R 370602004 PA 214 PB 187 REJ 9")
    assert "Format" in handle_inbound("08039990000", "R 370602004 nothing")
    assert "Unknown" in handle_inbound("08039990000", "R 99 PA 1")
    run_pending()
    from apps.results.models import ResultCheck

    assert ResultCheck.objects.filter(polling_unit__code=NEW).exists()


def test_parse_agent_result():
    f = parse_agent_result("PA 214 PB 187 REJ 9 ACC 420 REG 900")
    assert f["party_votes"] == {"PA": 214, "PB": 187}
    assert f["total_valid"] == 401 and f["total_used"] == 410
    assert f["accredited"] == 420 and f["registered"] == 900
    with pytest.raises(ValueError):
        parse_agent_result("nothing")


@pytest.mark.django_db
def test_otp_flow(settings):
    from django.core.cache import cache

    cache.clear()
    with mock.patch("apps.channels.otp.secrets.randbelow", return_value=123456):
        request_otp("08035550000")
    msg = OutboxMessage.objects.get()
    assert "123456" in msg.body
    assert not verify_otp("08035550000", "000000")
    assert verify_otp("08035550000", "123456")
    assert not verify_otp("08035550000", "123456")  # single use
    request_otp("08035550000")
    request_otp("08035550000")
    with pytest.raises(OtpError):
        request_otp("08035550000")
    cache.clear()


@pytest.mark.django_db
def test_otp_lockout_and_expiry():
    from datetime import timedelta

    from django.core.cache import cache

    from apps.channels.otp import OtpCode

    cache.clear()
    with mock.patch("apps.channels.otp.secrets.randbelow", return_value=111111):
        request_otp("08035550001")
    for _ in range(5):
        verify_otp("08035550001", "999999")
    assert not verify_otp("08035550001", "111111")  # locked out
    OtpCode.objects.update(attempts=0, expires_at=timezone.now() - timedelta(seconds=1))
    assert not verify_otp("08035550001", "111111")  # expired
    cache.clear()


@pytest.mark.django_db
def test_simulator(seeded, settings):
    c = Client()
    assert c.get("/simulator/").status_code == 200
    r = c.post("/api/simulator/ussd", {"phoneNumber": "08031234567", "text": "1*370602002"})
    assert "MOVED" in r.json()["reply"]
    c.post("/api/simulator/sms", {"phoneNumber": "08031234567", "text": "PU 370602004"})
    inbox = c.get("/api/simulator/inbox", {"phone": "08031234567"}).json()
    assert inbox["messages"][0]["body"].startswith("PU 37/06/02/004")
    assert c.get("/api/simulator/inbox", {"phone": "1"}).status_code == 400
    assert c.post("/api/simulator/sms", {"phoneNumber": "1", "text": "x"}).status_code == 400
    settings.SIMULATOR_ENABLED = False
    assert c.get("/simulator/").status_code == 404


@pytest.mark.django_db
def test_sms_webhook(seeded):
    c = Client()
    assert (
        c.post("/sms/inbound", {"from": "+2348031234567", "text": "PU 370602004"}).status_code
        == 200
    )
    assert c.post("/sms/inbound", {"from": "1", "text": "PU"}).status_code == 400


# ---- Voice ----


@pytest.mark.django_db
def test_tools(seeded):
    moved = tools.call("lookup_pu", {"query": "370602002"})
    assert moved["moved_to"]["code"] == NEW
    assert tools.call("lookup_pu", {"query": "Garki Dispensary"})["found"]
    assert not tools.call("lookup_pu", {"query": "zz"})["found"]
    assert tools.call("get_result_status", {"pu_code": NEW})["status"] == "Pending"
    assert not tools.call("get_result_status", {"pu_code": "1"})["found"]
    assert not tools.call("check_claim", {"text": "nothing known about this topic"})["known"]
    kb = tools.call("kb_search", {"query": "how do I collect my PVC"})
    assert kb["found"] and kb["results"][0]["sources"]
    assert not tools.call("kb_search", {"query": "zzzz"})["found"]
    assert "error" in tools.call("nope", {})
    assert tools.call("kb_search", {"query": "who will win the election"})["refuse"]


@pytest.mark.django_db(transaction=True)
def test_check_claim_tool_knows_existing_claims(fakes):
    from apps.claims.services import submit_report

    submit_report(text="They are buying votes at Garki ward 5 share this", visitor_id="a")
    run_pending()
    out = tools.call(
        "check_claim", {"text": "They are buying votes at Garki ward 5 share this"}, "pcm"
    )
    assert out["known"] and out["headline"] == "We never confirm am"


@pytest.mark.parametrize(
    ("text", "refused"),
    [
        ("who will win the election", True),
        ("Who should I vote for", True),
        ("which party is best", True),
        ("where is my polling unit", False),
    ],
)
def test_refusals(text, refused):
    assert bool(refusal_for(text)) is refused


def test_instructions_rules():
    text = realtime.instructions("pcm")
    assert "Nigerian Pidgin" in text and "Never say who won" in text and "read it back" in text


def test_mint_session_never_returns_key(settings):
    settings.AZURE_REALTIME_ENDPOINT = "wss://res.openai.azure.com/openai/v1/realtime?model=m"
    settings.AZURE_REALTIME_DEPLOYMENT = "dep"
    settings.AZURE_REALTIME_API_KEY = "server-secret-key"
    resp = mock.Mock()
    resp.json.return_value = {"value": "ek_short", "expires_at": 123}
    with mock.patch.object(realtime.httpx, "post", return_value=resp) as post:
        out = realtime.mint_session("en")
    assert out["token"] == "ek_short" and "server-secret-key" not in json.dumps(out)
    assert post.call_args.kwargs["headers"]["api-key"] == "server-secret-key"
    sent = post.call_args.kwargs["json"]["session"]
    assert {t["name"] for t in sent["tools"]} == {
        "lookup_pu",
        "get_result_status",
        "check_claim",
        "kb_search",
    }


@pytest.mark.django_db
def test_session_api_hides_errors_and_key(settings):
    c = Client()
    c.get("/voice/")
    with mock.patch.object(realtime, "mint_session", side_effect=RuntimeError("boom")):
        r = c.post("/api/voice/session")
    assert r.status_code == 503 and "boom" not in r.content.decode()
    with mock.patch.object(realtime, "mint_session", return_value={"token": "ek_1"}):
        assert c.post("/api/voice/session").json()["token"] == "ek_1"


@pytest.mark.django_db
def test_tool_api(seeded):
    c = Client()
    r = c.post(
        "/api/voice/tool",
        json.dumps({"name": "lookup_pu", "arguments": json.dumps({"query": "370602002"})}),
        content_type="application/json",
    )
    assert r.json()["moved_to"]["code"] == NEW
    assert c.post("/api/voice/tool", "not json", content_type="application/json").status_code == 400


def wav(seconds=0.2, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))
    return buf.getvalue()


def test_wav_parsing():
    assert len(realtime.wav_to_pcm16(wav(0.1))) == 4800
    with pytest.raises(ValueError):
        realtime.wav_to_pcm16(b"not a wav file at all")
    with pytest.raises(ValueError):
        realtime.wav_to_pcm16(wav(rate=16000))


class FakeUnderstander:
    def __init__(self, result):
        self.result = result

    def understand(self, pcm16):
        return self.result


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("intent", ["rumour", "question", "other"])
def test_voice_note_routes_by_intent(fakes, intent):
    realtime.set_understander(
        FakeUnderstander(
            {
                "transcript": "Dem dey share money for Garki ward 5",
                "language": "pcm",
                "intent": intent,
                "english": "They are sharing money at Garki ward 5 polling unit",
            }
        )
    )
    c = Client()
    r = c.post("/api/voice/note", {"audio": ContentFile(wav(), name="n.wav")}).json()
    realtime.set_understander(None)
    assert r["language"] == "pcm"
    if intent == "rumour":
        assert r["claim_id"] and r["verdict"]["headline"]
    elif intent == "question":
        assert "answer" in r
    else:
        assert "claim_id" not in r


@pytest.mark.django_db
def test_voice_note_errors(seeded):
    c = Client()
    assert c.post("/api/voice/note").status_code == 400
    assert (
        c.post("/api/voice/note", {"audio": ContentFile(b"junk", name="n.wav")}).status_code == 400
    )
    realtime.set_understander(type("U", (), {"understand": lambda s, p: 1 / 0})())
    r = c.post("/api/voice/note", {"audio": ContentFile(wav(), name="n.wav")})
    realtime.set_understander(None)
    assert r.status_code == 503


@pytest.mark.django_db
def test_tts_cache(fakes):
    FakeSynth.calls = 0
    a = tts.speak("Your polling unit has moved", "en")
    b = tts.speak("Your polling unit has moved", "en")
    assert a.pk == b.pk and FakeSynth.calls == 1
    assert tts.voice_for("pcm") == "voice-en"


def test_tts_requires_voice(settings):
    from django.core.exceptions import ImproperlyConfigured

    settings.ELEVENLABS_VOICE_ID_EN = ""
    settings.ELEVENLABS_VOICE_ID_PCM = ""
    with pytest.raises(ImproperlyConfigured):
        tts.voice_for("en")


def test_elevenlabs_request_shape(settings):
    settings.ELEVENLABS_API_KEY = "k"
    resp = mock.Mock(content=b"mp3")
    with mock.patch.object(tts.httpx, "post", return_value=resp) as post:
        assert tts.ElevenLabsSynth().synth("hi", "v1") == b"mp3"
    assert post.call_args.args[0].endswith("/v1/text-to-speech/v1")
    assert post.call_args.kwargs["headers"]["xi-api-key"] == "k"
