import json
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.core import ai
from apps.results import extract, presenters
from apps.results.imaging import InvalidImage, clean_image, phash_hex
from apps.results.models import ResultCheck
from apps.results.schema import json_schema
from apps.results.words import int_to_words, words_to_int


@pytest.mark.parametrize(
    ("text", "n"),
    [
        ("two hundred and fourteen", 214),
        ("forty-three", 43),
        ("Nil", 0),
        ("twelve votes only", 12),
        ("one thousand two hundred and five", 1205),
        ("hundred", 100),
        ("fourty", 40),
        ("one thousand", 1000),
        ("", None),
        (None, None),
        ("and", None),
        ("banana", None),
    ],
)
def test_words_to_int(text, n):
    assert words_to_int(text) == n


@pytest.mark.parametrize("n", [0, 7, 19, 20, 43, 100, 187, 214, 999, 1000, 1005, 1205, 2330])
def test_int_to_words_roundtrip(n):
    assert words_to_int(int_to_words(n)) == n


def field(value, conf=0.99, unreadable=False):
    return {"value": value, "confidence": conf, "unreadable": unreadable}


def raw(**over):
    data = {
        k: field(None)
        for k in (
            "registered",
            "accredited",
            "ballots_issued",
            "unused",
            "spoilt",
            "rejected",
            "total_valid",
            "total_used",
        )
    }
    data |= {
        "pu_code": field("37/06/02/004"),
        "cancelled": field(False),
        "signed_by_agents": field(True),
        "parties": [
            {"party": "PA", "figures": field(10), "words": field("ten")},
            {"party": "pb", "figures": field(5), "words": field("five")},
        ],
    }
    data.update(over)
    return data


def test_normalise_clean():
    n = extract.normalise(
        raw(total_valid=field(15)),
        expected_pu="37-06-02-004",
        parties=["PA", "PB"],
        min_confidence=0.85,
    )
    assert n.low_confidence == [] and n.errors == []
    assert n.figures["party_votes"] == {"PA": 10, "PB": 5}
    assert n.figures["words"] == {"PA": 10, "PB": 5}
    assert n.figures["total_valid"] == 15


def test_normalise_flags_problems():
    r = raw(
        pu_code=field("37/06/01/001"),
        rejected=field(None, unreadable=True),
        total_valid=field(15, conf=0.4),
        total_used=field("16"),
        parties=[
            {"party": "PA", "figures": field(10, conf=0.3), "words": field("ten")},
            {"party": "PZ", "figures": field(1), "words": field("one")},
            {"party": "", "figures": field(1), "words": field("one")},
        ],
    )
    n = extract.normalise(
        r, expected_pu="37/06/02/004", parties=["PA", "PB", "PC"], min_confidence=0.85
    )
    assert {
        "party:PA",
        "party:PZ",
        "party:PB",
        "party:PC",
        "rejected",
        "total_valid",
        "total_used",
        "pu_code",
    } <= set(n.low_confidence)
    assert {
        "pu_code_mismatch",
        "unknown_party:PZ",
        "missing_party:PB",
        "not_integer:total_used",
    } <= set(n.errors)


def test_normalise_party_without_number_and_bad_code():
    r = raw(
        pu_code=field("garbage"),
        parties=[{"party": "PA", "figures": field(None, unreadable=True), "words": field(None)}],
    )
    n = extract.normalise(r, expected_pu="37/06/02/004", parties=["PA"])
    assert "party:PA" in n.low_confidence and "pu_code_unreadable" in n.errors


def test_schema_is_strict():
    s = json_schema()
    assert s["additionalProperties"] is False
    assert set(s["required"]) == set(s["properties"])


def test_azure_extractor_builds_strict_request(settings):
    settings.AZURE_OPENAI_DEPLOYMENT = "dep"
    with mock.patch.object(ai, "structured", return_value=json.dumps({"ok": 1})) as call:
        out = extract.AzureExtractor().read(b"img", {"pu_code": "37/06/02/004", "parties": ["PA"]})
    assert out == {"ok": 1}
    kwargs = call.call_args.kwargs
    assert kwargs["name"] == "ec8a" and kwargs["schema"]["additionalProperties"] is False
    assert kwargs["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
    assert extract.AzureExtractor().model == "dep"


def test_ai_fails_loudly_without_config(settings):
    settings.AZURE_OPENAI_API_KEY = ""
    ai.azure_client.cache_clear()
    with pytest.raises(ImproperlyConfigured):
        ai.azure_client()
    ai.azure_client.cache_clear()


def test_ai_structured_returns_text(settings):
    fake_client = mock.Mock()
    fake_client.responses.create.return_value = mock.Mock(output_text='{"a": 1}')
    with mock.patch.object(ai, "azure_client", return_value=fake_client):
        assert ai.structured(system="s", content=[], schema={}, name="n") == '{"a": 1}'
        fake_client.responses.create.return_value = mock.Mock(output_text="")
        with pytest.raises(ai.AIUnavailable):
            ai.structured(system="s", content=[], schema={}, name="n")


def test_images():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (3000, 1000), "white").save(buf, format="PNG")
    out = clean_image(buf.getvalue())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and max(img.size) == 2000
    assert len(phash_hex(out)) == 16
    with pytest.raises(InvalidImage):
        clean_image(b"x" * (9 * 1024 * 1024))
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    with pytest.raises(InvalidImage):
        clean_image(gif.getvalue())


def check(status, reasons=(), n=1, cross=False):
    return ResultCheck(
        status=status, reasons=[{"code": c} for c in reasons], origin_count=n, cross_party=cross
    )


@pytest.mark.parametrize(
    ("c", "needle"),
    [
        (None, "No result-sheet photos"),
        (check("matches", n=2, cross=True), "different parties"),
        (check("mismatch", n=2), "Observers have been alerted"),
        (check("cancelled"), "Result Cancelled"),
        (check("pending", ["irev_not_uploaded"]), "Waiting for INEC"),
        (check("pending", ["no_citizen_uploads"], n=0), "Waiting for result-sheet photos"),
        (check("needs_review", ["single_origin_disagrees_with_irev"]), "second independent"),
        (check("needs_review", ["low_confidence"]), "hard to read"),
        (check("needs_review", ["arithmetic_sum_mismatch"]), "don't add up"),
        (check("needs_review", ["citizen_origins_disagree"]), "don't agree"),
        (check("needs_review", ["flag_too_far"]), "verifier needs to check"),
    ],
)
def test_explanations_never_name_a_winner(c, needle):
    text = presenters.explain(c)
    assert needle in text
    assert "won" not in text.lower() and "winner" not in text.lower()
