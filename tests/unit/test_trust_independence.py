import datetime as dt

from hypothesis import given
from hypothesis import strategies as st

from apps.trust.hashing import hex_distance, normalize_text, simhash
from apps.trust.independence import eligible, independent_origins, is_cross_party
from apps.trust.types import Origin, Submission


def sub(i, **kw):
    return Submission(id=str(i), **kw)


def test_distinct_people_are_distinct_origins():
    origins = independent_origins([sub(1, participant_key="a"), sub(2, participant_key="b")])
    assert len(origins) == 2


def test_same_person_is_one_origin():
    origins = independent_origins([sub(1, participant_key="a"), sub(2, participant_key="a")])
    assert len(origins) == 1
    assert origins[0].member_ids == ("1", "2")


def test_same_device_is_one_origin():
    items = [sub(1, participant_key="a", device_id="d"), sub(2, participant_key="b", device_id="d")]
    assert len(independent_origins(items)) == 1


def test_same_exact_image_is_one_origin():
    items = [
        sub(1, participant_key="a", image_sha256="x"),
        sub(2, participant_key="b", image_sha256="x"),
    ]
    assert len(independent_origins(items)) == 1


def test_near_identical_image_is_one_origin():
    items = [
        sub(1, participant_key="a", image_phash="ffffffffffffffff"),
        sub(2, participant_key="b", image_phash="fffffffffffffff0"),
    ]
    assert len(independent_origins(items)) == 1


def test_different_images_stay_separate():
    items = [
        sub(1, participant_key="a", image_phash="ffffffffffffffff"),
        sub(2, participant_key="b", image_phash="0000000000000000"),
    ]
    assert len(independent_origins(items)) == 2


def test_near_duplicate_text_is_one_origin():
    text = "Vote buying happening now at Garki Village polling unit, they are sharing money"
    items = [sub(1, participant_key="a", text=text), sub(2, participant_key="b", text=text + "!!")]
    assert len(independent_origins(items)) == 1


def test_known_forward_joins_its_original():
    items = [
        sub(1, participant_key="a", text="Officials have not arrived at Bwari Central"),
        sub(
            2,
            participant_key="b",
            text="completely different words here",
            is_forward=True,
            forward_of="1",
        ),
    ]
    origins = independent_origins(items)
    assert len(origins) == 1
    assert not origins[0].forwards_only


def test_unknown_forwards_of_similar_text_collapse():
    base = "BREAKING they are buying votes with 5000 naira at ward 5 share this"
    items = [
        sub(i, participant_key=f"p{i}", text=base + " " * i, is_forward=True) for i in range(40)
    ]
    origins = independent_origins(items)
    assert len(origins) == 1
    assert origins[0].forwards_only


def test_unrelated_texts_from_different_people_are_separate():
    items = [
        sub(1, participant_key="a", text="Long queue at the polling unit, officials just arrived"),
        sub(2, participant_key="b", text="BVAS machine is working well and voting is orderly"),
    ]
    assert len(independent_origins(items)) == 2


def test_empty_attributes_never_merge():
    items = [sub(1), sub(2)]
    assert len(independent_origins(items)) == 2


def test_unknown_forward_of_id_is_ignored():
    items = [sub(1, participant_key="a", forward_of="missing", text="aaa bbb ccc")]
    assert len(independent_origins(items)) == 1


def test_cross_party_requires_two_parties():
    a = Origin("1", ("1",), frozenset({"agent"}), frozenset({"PA"}), False)
    b = Origin("2", ("2",), frozenset({"agent"}), frozenset({"PB"}), False)
    c = Origin("3", ("3",), frozenset({"agent"}), frozenset({"PA"}), False)
    v = Origin("4", ("4",), frozenset({"voter"}), frozenset(), False)
    assert is_cross_party([a, b])
    assert not is_cross_party([a, c])
    assert not is_cross_party([a, v])


def test_eligibility_threshold():
    assert eligible(sub(1, reputation=-3), -3)
    assert not eligible(sub(1, reputation=-4), -3)


def test_hashing_helpers():
    assert normalize_text("Héllo, WORLD!") == "hello world"
    assert simhash("") == 0
    assert hex_distance("", "ff") is None
    assert hex_distance("ff", "fff") is None
    assert hex_distance("zz", "zz") is None
    assert hex_distance("f0", "ff") == 4


_ids = st.integers(min_value=0, max_value=30)
_keys = st.sampled_from(["", "a", "b", "c", "d"])


@st.composite
def submissions(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    return [
        Submission(
            id=f"s{i}",
            participant_key=draw(_keys),
            device_id=draw(_keys),
            text=draw(st.sampled_from(["", "polling unit opened late", "money sharing at ward 5"])),
        )
        for i in range(n)
    ]


@given(submissions(), st.randoms())
def test_order_never_changes_origin_count(items, rnd):
    shuffled = items[:]
    rnd.shuffle(shuffled)
    assert len(independent_origins(items)) == len(independent_origins(shuffled))


@given(submissions(), st.integers(min_value=0, max_value=7))
def test_adding_a_known_forward_never_increases_origins(items, k):
    if not items:
        return
    original = items[k % len(items)]
    fwd = Submission(
        id="fwd",
        participant_key="zz",
        text="different",
        is_forward=True,
        forward_of=original.id,
        observed_at=dt.datetime(2027, 1, 16),
    )
    assert len(independent_origins([*items, fwd])) == len(independent_origins(items))


def test_lightly_edited_forwards_collapse_but_edited_originals_do_not():
    base = "they are buying votes with 5000 naira at ward 5 polling unit share this message now"
    edited = "they 10000 buying votes with 5000 naira at ward 5 polling unit share this message now"
    fwd = [
        sub(1, participant_key="a", text=base, is_forward=True),
        sub(2, participant_key="b", text=edited, is_forward=True),
    ]
    assert len(independent_origins(fwd)) == 1
    originals = [sub(1, participant_key="a", text=base), sub(2, participant_key="b", text=edited)]
    assert len(independent_origins(originals)) == 2
