import datetime as dt

import pytest

from apps.trust.arithmetic import check_arithmetic
from apps.trust.integrity import PriorImage, PUFacts, UploadFacts, check_integrity, worst
from apps.trust.types import Severity, SheetFigures

GOOD = SheetFigures(
    party_votes={"PA": 214, "PB": 187, "PC": 43},
    registered=900,
    accredited=470,
    rejected=9,
    total_valid=444,
    total_used=453,
    words={"PA": 214},
)


def codes(sheet):
    return [v.code for v in check_arithmetic(sheet)]


def test_consistent_sheet_has_no_violations():
    assert codes(GOOD) == []


def test_missing_fields_are_skipped():
    assert codes(SheetFigures(party_votes={"PA": 1})) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"total_valid": 445, "total_used": 454}, "sum_mismatch"),
        ({"rejected": 10}, "valid_plus_rejected"),
        ({"accredited": 400}, "used_exceeds_accredited"),
        ({"registered": 400}, "accredited_exceeds_registered"),
        ({"words": {"PA": 241}}, "figures_words_mismatch"),
        ({"rejected": -1}, "negative_value"),
        ({"rejected": 1.5}, "not_integer"),
        ({"rejected": True}, "not_integer"),
        ({"ballots_issued": 1000, "unused": 500, "spoilt": 2}, "issued_balance"),
    ],
)
def test_each_violation(change, expected):
    data = {
        "party_votes": GOOD.party_votes,
        "registered": GOOD.registered,
        "accredited": GOOD.accredited,
        "rejected": GOOD.rejected,
        "total_valid": GOOD.total_valid,
        "total_used": GOOD.total_used,
        "words": GOOD.words,
        **change,
    }
    assert expected in codes(SheetFigures(**data))


def test_words_none_is_ignored():
    sheet = SheetFigures(party_votes={"PA": 3}, words={"PA": None, "PZ": 4})
    assert codes(sheet) == []


START = dt.datetime(2027, 1, 16, 8, 30, tzinfo=dt.UTC)
END = dt.datetime(2027, 1, 17, 23, 59, tzinfo=dt.UTC)
PU = PUFacts("37/06/02/004", 9.0279, 7.4881)


def upload(**kw):
    base = dict(
        pu_code="37/06/02/004",
        in_app_capture=True,
        captured_at=dt.datetime(2027, 1, 16, 17, 0, tzinfo=dt.UTC),
        lat=9.0280,
        lng=7.4882,
        image_sha256="aa",
        image_phash="ffffffffffffffff",
    )
    base.update(kw)
    return UploadFacts(**base)


def flag_codes(flags):
    return {f.code for f in flags}


def test_clean_upload_has_no_flags():
    assert check_integrity(upload(), PU, (START, END)) == []


def test_gallery_upload_rejected():
    flags = check_integrity(upload(in_app_capture=False), PU, (START, END))
    assert "untrusted_source" in flag_codes(flags)
    assert worst(flags) is Severity.REJECT


def test_outside_window_needs_review():
    early = upload(captured_at=dt.datetime(2027, 1, 15, tzinfo=dt.UTC))
    assert worst(check_integrity(early, PU, (START, END))) is Severity.REVIEW
    assert "outside_window" in flag_codes(
        check_integrity(upload(captured_at=None), PU, (START, END))
    )


def test_no_window_skips_time_check():
    assert check_integrity(upload(captured_at=None), PU, None) == []


def test_too_far_needs_review():
    flags = check_integrity(upload(lat=9.10, lng=7.40), PU, (START, END))
    assert "too_far" in flag_codes(flags)


def test_missing_location_info_only():
    flags = check_integrity(upload(lat=None, lng=None), PU, (START, END))
    assert flag_codes(flags) == {"no_location"}
    assert worst(flags) is Severity.INFO


def test_unknown_pu_location_not_penalised():
    flags = check_integrity(upload(), PUFacts("x", None, None), (START, END))
    assert flag_codes(flags) == {"location_unverifiable"}


def test_reused_image_across_pus_rejected():
    priors = [
        PriorImage("37/06/02/004", "aa", "ffffffffffffffff"),
        PriorImage("37/06/01/001", "bb", "fffffffffffffff0"),
    ]
    flags = check_integrity(upload(), PU, (START, END), priors)
    assert "reused_image" in flag_codes(flags)


def test_reuse_by_exact_hash():
    flags = check_integrity(upload(), PU, (START, END), [PriorImage("37/02/01/001", "aa", "")])
    assert "reused_image" in flag_codes(flags)


def test_worst_of_nothing_is_none():
    assert worst([]) is None


def test_prior_image_on_same_pu_is_fine():
    flags = check_integrity(upload(), PU, (START, END), [PriorImage("37/06/02/004", "aa", "")])
    assert flags == []


def test_unrelated_prior_image_elsewhere_is_fine():
    priors = [PriorImage("37/02/01/001", "zz", "0000000000000000")]
    assert check_integrity(upload(), PU, (START, END), priors) == []
