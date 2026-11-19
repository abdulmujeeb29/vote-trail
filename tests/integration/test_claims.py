import datetime as dt
from unittest import mock

import pytest
from django.utils import timezone

from apps.claims import analysis, search
from apps.claims.models import Claim, ClaimAssessment, EvidenceItem, Report
from apps.claims.services import add_verifier_evidence, assess, looks_forwarded, submit_report
from apps.claims.verdicts import render, sms_text
from apps.core.models import Participant
from apps.jobs.queue import run_pending

T0 = dt.datetime(2027, 1, 16, 10, 0, tzinfo=dt.UTC)
RUMOUR = "They are buying votes with 5000 naira at Garki ward 5, share this before they delete it"


class FakeAnalyzer:
    """Supports every item, quoting its first 20 chars; observed time from a marker."""

    model = "fake"

    def __init__(self, stance="supports", explicit=False, bad_quote=False, hours=None):
        self.stance, self.explicit, self.bad_quote, self.hours = stance, explicit, bad_quote, hours
        self.calls = 0

    def analyse(self, claim, items):
        self.calls += 1
        out = []
        for i, it in enumerate(items):
            text = it["text"]
            stance = self.stance(text) if callable(self.stance) else self.stance
            observed = None
            if self.hours is not None:
                observed = (T0 + dt.timedelta(hours=self.hours * i)).isoformat()
            out.append(
                {
                    "id": it["id"],
                    "stance": stance,
                    "quote": "invented quote" if self.bad_quote else text[:20],
                    "observed_at": observed,
                    "explicit": self.explicit(text) if callable(self.explicit) else self.explicit,
                }
            )
        return {"items": out}


class FakeSearch:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = 0

    def search(self, query):
        self.calls += 1
        return self.results


@pytest.fixture
def fakes():
    a, s = FakeAnalyzer(), FakeSearch()
    analysis.set_analyzer(a)
    search.set_searcher(s)
    yield a, s
    analysis.set_analyzer(None)
    search.set_searcher(None)


def person(i, **kw):
    p = Participant(**kw)
    p.set_phone(f"0803000{i:04d}")
    p.save()
    return p


def latest(claim):
    return ClaimAssessment.objects.filter(claim=claim).order_by("-revision").first()


@pytest.mark.django_db(transaction=True)
def test_forty_forwards_stay_unconfirmed(fakes):
    for i in range(40):
        submit_report(text=RUMOUR, category="vote_buying", visitor_id=f"v{i}", device_id=f"d{i}")
    run_pending()
    claim = Claim.objects.get()
    a = latest(claim)
    assert a.status == "unconfirmed"
    assert a.forward_count == 40 and a.origin_count == 1
    assert {r["code"] for r in a.reasons} >= {"single_origin", "forwards_only"}
    text = sms_text(a, "pcm")
    assert "forward" in text and "40" in text


@pytest.mark.django_db(transaction=True)
def test_two_independent_eyewitnesses_in_window_corroborated(fakes):
    fakes[0].hours = 1
    submit_report(
        text="I saw men sharing envelopes of cash near the Garki ward 5 polling unit",
        category="vote_buying",
        visitor_id="a",
        device_id="da",
        is_forward=False,
        location_code="37/06/02/004",
    )
    submit_report(
        text="Party agents handing out money at the queue in Garki ward five right now",
        category="vote_buying",
        visitor_id="b",
        device_id="db",
        is_forward=False,
        location_code="37/06/02/004",
    )
    run_pending()
    claims = Claim.objects.all()
    assert claims.count() == 1, "similar reports should cluster"
    assert latest(claims[0]).status == "corroborated"


@pytest.mark.django_db(transaction=True)
def test_eyewitnesses_far_apart_in_time_stay_unconfirmed(fakes):
    fakes[0].hours = 6
    submit_report(
        text="I saw men sharing envelopes of cash near the Garki ward 5 polling unit",
        category="vote_buying",
        visitor_id="a",
        is_forward=False,
        location_code="37/06/02/004",
    )
    submit_report(
        text="Party agents handing out money at the queue in Garki ward five right now",
        category="vote_buying",
        visitor_id="b",
        is_forward=False,
        location_code="37/06/02/004",
    )
    run_pending()
    a = latest(Claim.objects.get())
    assert a.status == "unconfirmed"
    assert "outside_time_window" in {r["code"] for r in a.reasons}


@pytest.mark.django_db(transaction=True)
def test_hallucinated_quotes_are_dropped(fakes):
    fakes[0].bad_quote = True
    submit_report(text=RUMOUR, visitor_id="a")
    run_pending()
    claim = Claim.objects.get()
    assert not EvidenceItem.objects.filter(analysis_valid=True).exists()
    assert latest(claim).status == "unconfirmed"


@pytest.mark.django_db(transaction=True)
def test_authority_refutes_via_public_source(settings, fakes):
    a, s = fakes
    s.results = [
        {
            "url": "https://www.inecnigeria.org/press/statement",
            "title": "INEC statement",
            "content": "INEC: reports of vote buying at Garki ward"
            " 5 are false. Our officials and security agents found no such activity.",
        }
    ]
    a.stance = lambda text: "opposes" if text.startswith("INEC") else "supports"
    a.explicit = lambda text: text.startswith("INEC")
    submit_report(text=RUMOUR, visitor_id="a")
    run_pending()
    result = latest(Claim.objects.get())
    assert result.status == "refuted_by_source"
    assert result.authority == "inecnigeria.org"
    assert render(result, "en")["headline"] == "Denied by inecnigeria.org"


@pytest.mark.django_db(transaction=True)
def test_web_search_is_cached_per_day(fakes):
    _, s = fakes
    s.results = [{"url": "https://news.example/a", "title": "t", "content": "something about it"}]
    submit_report(text=RUMOUR, visitor_id="a")
    run_pending()
    claim = Claim.objects.get()
    assess(claim)
    assert s.calls == 1
    assert EvidenceItem.objects.filter(kind="web").count() == 1


@pytest.mark.django_db(transaction=True)
def test_verifier_evidence_counts_as_independent(fakes):
    fakes[0].hours = 0
    submit_report(
        text="I saw men sharing cash near the Garki ward 5 polling unit at 10am",
        visitor_id="a",
        is_forward=False,
        observed_at=T0,
    )
    run_pending()
    claim = Claim.objects.get()
    v = person(9, role="verifier", verified_at=timezone.now())
    add_verifier_evidence(
        claim,
        v,
        note="Our observer at Garki ward 5 confirms cash sharing",
        stance="supports",
        observed_at=T0 + dt.timedelta(minutes=30),
    )
    run_pending()
    assert latest(claim).status == "corroborated"


@pytest.mark.django_db(transaction=True)
def test_no_new_revision_without_material_change(fakes):
    submit_report(text=RUMOUR, visitor_id="a")
    run_pending()
    claim = Claim.objects.get()
    assert assess(claim) is None
    assert ClaimAssessment.objects.count() == 1
    with pytest.raises(RuntimeError):
        ClaimAssessment.objects.get().save()


@pytest.mark.django_db
def test_intake_validation_and_forward_detection():
    with pytest.raises(ValueError):
        submit_report(text="hi")
    assert looks_forwarded("Pls share this message to all")
    assert looks_forwarded("FORWARDED: they are rigging")
    assert not looks_forwarded("I saw officials arrive at 9:40")
    r = submit_report(text="Officials arrived at 9:40 and voting started", category="nonsense")
    assert r.claim.category == "other" and r.observed_at is None


def test_validate_rejects_bad_rows():
    items = {"e1": "The officials arrived late at nine forty.", "e2": "Unrelated text"}
    raw = {
        "items": [
            {
                "id": "e1",
                "stance": "supports",
                "quote": "arrived  LATE at nine",
                "observed_at": "2027-01-16T09:40:00+01:00",
                "explicit": False,
            },
            {
                "id": "e1",
                "stance": "supports",
                "quote": "dup",
                "observed_at": None,
                "explicit": False,
            },
            {
                "id": "e9",
                "stance": "supports",
                "quote": "x",
                "observed_at": None,
                "explicit": False,
            },
            {"id": "e2", "stance": "maybe", "quote": "", "observed_at": None, "explicit": False},
        ]
    }
    valid, dropped = analysis.validate(raw, items)
    assert [v.id for v in valid] == ["e1"] and valid[0].observed_at is not None
    assert len(dropped) == 3
    naive = {
        "items": [
            {
                "id": "e2",
                "stance": "irrelevant",
                "quote": "",
                "observed_at": "2027-01-16T09:40:00",
                "explicit": False,
            }
        ]
    }
    v2, _ = analysis.validate(naive, items)
    assert v2[0].observed_at is None


def test_analysis_schema_and_azure_call(settings):
    s = analysis.schema()
    assert s["additionalProperties"] is False
    settings.AZURE_OPENAI_DEPLOYMENT = "dep"
    with mock.patch.object(analysis.ai, "structured", return_value='{"items": []}') as call:
        assert analysis.AzureClaimAnalyzer().analyse("c", [{"id": "e1", "text": "t"}]) == {
            "items": []
        }
    assert call.call_args.kwargs["name"] == "claim_analysis"
    assert analysis.AzureClaimAnalyzer().model == "dep"


def test_tavily_request_shape(settings):
    settings.TAVILY_API_KEY = "test-key"
    resp = mock.Mock()
    resp.json.return_value = {"results": [{"url": "u", "title": "t", "content": "c" * 9000}]}
    with mock.patch.object(search.httpx, "post", return_value=resp) as post:
        out = search.TavilySearcher().search("q")
    assert out[0]["content"] == "c" * 6000
    assert post.call_args.kwargs["json"]["max_results"] == 4


def test_verdict_rendering_fallbacks():
    v = render(None, "fr")  # unsupported language falls back to English
    assert v["status"] == "checking" and v["language"] == "en"
    a = ClaimAssessment(
        status="corroborated",
        reasons=[{"code": "independent_sources_agree", "detail": {"origins": 2}}],
        origin_count=2,
    )
    assert "2 independent sources" in render(a)["reasons"][0]
    assert "different sources" in render(a, "pcm")["reasons"][0]
    assert str(Report(pk=1, claim_id=2)) == "Report 1 on claim 2"


def test_ward_of():
    from apps.claims.services import ward_of

    assert ward_of("37/06/02/004") == "37/06/02"
    assert ward_of("37-6-2") == "37/06/02"
    assert ward_of("37/06") == "37/06"
    assert ward_of("") == ""


@pytest.mark.django_db(transaction=True)
def test_each_item_analysed_once_and_jobs_coalesce(fakes):
    from apps.jobs.models import Job

    for i in range(10):
        submit_report(
            text=RUMOUR, category="vote_buying", visitor_id=f"v{i}", location_code="37/06/02"
        )
    assert Job.objects.filter(kind="claims.assess", status="queued").count() == 1
    run_pending()
    assert fakes[0].calls == 1
    submit_report(text=RUMOUR, category="vote_buying", visitor_id="late", location_code="37/06/02")
    run_pending()
    assert fakes[0].calls == 2
    assert EvidenceItem.objects.filter(analysed_at__isnull=True).count() == 0
