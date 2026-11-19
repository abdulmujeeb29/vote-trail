import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.geo.codes import InvalidPUCode, normalize_pu_code, parse_pu_code
from apps.geo.models import PollingUnit, haversine_m


@pytest.mark.parametrize("raw", ["37/06/01/001", "37-06-01-001", " 37 / 6 / 1 / 1 "])
def test_codes_normalise(raw):
    assert normalize_pu_code(raw) == "37/06/01/001"


@pytest.mark.parametrize(
    "raw", ["", "37/06/01", "abc", "38/01/01/001", "00/01/01/001", "37/00/01/001"]
)
def test_bad_codes(raw):
    with pytest.raises(InvalidPUCode):
        parse_pu_code(raw)


@given(
    st.integers(1, 37),
    st.integers(1, 99),
    st.integers(1, 99),
    st.integers(1, 999),
    st.sampled_from(["/", "-"]),
)
def test_roundtrip(s, lga, w, u, sep):
    code = parse_pu_code(sep.join(str(x) for x in (s, lga, w, u)))
    assert parse_pu_code(str(code)) == code
    assert str(code).startswith(code.ward_code)


def test_haversine():
    assert haversine_m(9.0, 7.0, 9.0, 7.0) == 0
    assert 1100 < haversine_m(9.0, 7.0, 9.01, 7.0) < 1120


@pytest.mark.django_db
def test_seed_is_idempotent_and_real(seeded):
    from apps.elections.models import Election
    from apps.geo.seed import seed

    seed()
    assert PollingUnit.objects.count() == 24
    assert Election.objects.count() == 1
    pu = PollingUnit.objects.get(code="37/06/01/001")
    assert pu.source_url.startswith("https://cvr.inecnigeria.org")
    assert "Area I" in pu.name
    assert str(pu).startswith("37/06/01/001")
    moved = PollingUnit.objects.get(code="37/06/02/002")
    assert moved.status == PollingUnit.Status.RELOCATED
    assert moved.current.code == "37/06/02/004"
    assert moved.distance_m(moved.lat, moved.lng) == 0
    assert PollingUnit(code="1/1/1/1", lat=None).distance_m(1, 1) is None
    assert str(pu.ward) and str(pu.ward.lga) and str(pu.ward.lga.state)


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("GARKI VILLAGE II/NEW PRI. SCH.", "Garki Village II/New Pri. Sch."),
        ("GARKI VILLAGE/NEAR DA'A SOCIAL CLUB", "Garki Village/Near Da'a Social Club"),
        ("BWARI STAFF QTRS  /  SECURITY POST FGGC.", "Bwari Staff Qtrs / Security Post FGGC."),
    ],
)
def test_smart_title(raw, want):
    from apps.geo.seed import smart_title

    assert smart_title(raw) == want
