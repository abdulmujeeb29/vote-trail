import datetime as dt

import pytest

from apps.trust.status import claim_status, compare_figures, is_material_change, result_status
from apps.trust.types import (
    CitizenSheet,
    ClaimStatus,
    Decision,
    Evidence,
    Flag,
    Reason,
    ResultStatus,
    Severity,
    SheetFigures,
    Stance,
    Submission,
)

WALL = SheetFigures(
    party_votes={"PA": 214, "PB": 187, "PC": 43},
    rejected=9,
    total_valid=444,
    total_used=453,
    accredited=470,
    registered=900,
)
IREV_SAME = WALL
IREV_DIFF = SheetFigures(
    party_votes={"PA": 214, "PB": 287, "PC": 43},
    rejected=9,
    total_valid=544,
    total_used=553,
    accredited=600,
    registered=900,
)


def sheet(i, figures=WALL, flags=(), **kw):
    defaults = {"participant_key": f"p{i}", "device_id": f"d{i}", "image_sha256": f"h{i}"}
    defaults.update(kw)
    return CitizenSheet(Submission(id=str(i), **defaults), figures, tuple(flags))


def codes(decision):
    return decision.reason_codes


class TestResultStatus:
    def test_no_uploads_is_pending(self):
        d = result_status([], IREV_SAME)
        assert d.status == ResultStatus.PENDING
        assert "no_citizen_uploads" in codes(d)

    def test_no_irev_is_pending(self):
        d = result_status([sheet(1)], None)
        assert d.status == ResultStatus.PENDING
        assert "irev_not_uploaded" in codes(d)
        assert d.origin_count == 1

    def test_one_origin_matching_irev(self):
        d = result_status([sheet(1)], IREV_SAME)
        assert d.status == ResultStatus.MATCHES
        assert d.origin_count == 1

    def test_two_origins_differ_from_irev_is_mismatch(self):
        d = result_status(
            [sheet(1, role="agent", party="PA"), sheet(2, role="agent", party="PB")], IREV_DIFF
        )
        assert d.status == ResultStatus.MISMATCH
        assert d.origin_count == 2
        assert d.cross_party
        assert d.diffs["party:PB"] == (187, 287)

    def test_one_origin_differing_needs_review_not_mismatch(self):
        d = result_status([sheet(1)], IREV_DIFF)
        assert d.status == ResultStatus.NEEDS_REVIEW
        assert "single_origin_disagrees_with_irev" in codes(d)

    def test_same_person_twice_is_still_one_origin(self):
        d = result_status([sheet(1), sheet(2, participant_key="p1")], IREV_DIFF)
        assert d.status == ResultStatus.NEEDS_REVIEW
        assert d.origin_count == 1

    def test_reused_image_excluded(self):
        bad = sheet(2, flags=[Flag("reused_image", Severity.REJECT)])
        d = result_status([sheet(1), bad], IREV_DIFF)
        assert d.status == ResultStatus.NEEDS_REVIEW
        assert "excluded_reused_image" in codes(d)
        assert d.origin_count == 1

    def test_low_reputation_excluded(self):
        d = result_status([sheet(1, reputation=-10)], IREV_SAME)
        assert d.status == ResultStatus.PENDING
        assert "excluded_low_reputation" in codes(d)

    def test_review_flag(self):
        d = result_status([sheet(1, flags=[Flag("too_far", Severity.REVIEW)])], IREV_SAME)
        assert d.status == ResultStatus.NEEDS_REVIEW
        assert "flag_too_far" in codes(d)

    def test_info_flag_has_no_effect(self):
        d = result_status([sheet(1, flags=[Flag("no_location", Severity.INFO)])], IREV_SAME)
        assert d.status == ResultStatus.MATCHES

    def test_arithmetic_error_needs_review(self):
        broken = SheetFigures(party_votes={"PA": 1, "PB": 1}, total_valid=5)
        d = result_status([sheet(1, figures=broken)], IREV_SAME)
        assert d.status == ResultStatus.NEEDS_REVIEW
        assert "arithmetic_sum_mismatch" in codes(d)

    def test_irev_arithmetic_error_needs_review(self):
        broken = SheetFigures(party_votes={"PA": 1}, total_valid=2)
        d = result_status([sheet(1)], broken)
        assert "irev_arithmetic_sum_mismatch" in codes(d)

    def test_low_confidence_needs_review(self):
        unsure = SheetFigures(party_votes=WALL.party_votes, low_confidence_fields=("party:PB",))
        d = result_status([sheet(1, figures=unsure)], IREV_SAME)
        assert d.status == ResultStatus.NEEDS_REVIEW
        assert "low_confidence" in codes(d)

    def test_irev_low_confidence_needs_review(self):
        unsure = SheetFigures(party_votes=WALL.party_votes, low_confidence_fields=("party:PA",))
        assert "irev_low_confidence" in codes(result_status([sheet(1)], unsure))

    def test_citizen_origins_disagree(self):
        other = SheetFigures(party_votes={"PA": 1, "PB": 2, "PC": 3})
        d = result_status([sheet(1), sheet(2, figures=other)], IREV_SAME)
        assert d.status == ResultStatus.NEEDS_REVIEW
        assert "citizen_origins_disagree" in codes(d)

    def test_inconsistent_uploads_within_one_origin(self):
        other = SheetFigures(party_votes={"PA": 1, "PB": 2, "PC": 3})
        d = result_status([sheet(1), sheet(2, figures=other, participant_key="p1")], IREV_SAME)
        assert "origin_inconsistent" in codes(d)

    @pytest.mark.parametrize("where", ["citizen", "irev"])
    def test_cancelled(self, where):
        cancelled = SheetFigures(party_votes={}, cancelled=True)
        if where == "citizen":
            d = result_status([sheet(1, figures=cancelled)], IREV_SAME)
        else:
            d = result_status([sheet(1)], cancelled)
        assert d.status == ResultStatus.CANCELLED

    def test_totals_compared_only_when_both_present(self):
        partial = SheetFigures(party_votes=WALL.party_votes)
        assert compare_figures(WALL, partial) == {}
        assert result_status([sheet(1, figures=partial)], IREV_SAME).status == ResultStatus.MATCHES

    def test_two_people_photographing_the_same_sheet_stay_independent(self):
        a = sheet(1, image_phash="ffffffffffffffff")
        b = sheet(2, image_phash="fffffffffffffffe")
        assert result_status([a, b], IREV_DIFF).status == ResultStatus.MISMATCH

    def test_order_independent(self):
        a = [sheet(1, role="agent", party="PA"), sheet(2, role="agent", party="PB")]
        assert result_status(a, IREV_DIFF) == result_status(list(reversed(a)), IREV_DIFF)


T0 = dt.datetime(2027, 1, 16, 10, 0, tzinfo=dt.UTC)


def ev(i, stance=Stance.SUPPORTS, observed=T0, explicit=False, **kw):
    defaults = {"participant_key": f"p{i}"}
    defaults.update(kw)
    return Evidence(
        str(i), Submission(id=str(i), observed_at=observed, **defaults), stance, explicit
    )


AUTH = ["inecnigeria.org", "npf.gov.ng"]


class TestClaimStatus:
    def test_no_evidence(self):
        d = claim_status([], AUTH)
        assert d.status == ClaimStatus.UNCONFIRMED
        assert "no_supporting_evidence" in codes(d)

    def test_single_origin(self):
        d = claim_status([ev(1)], AUTH)
        assert d.status == ClaimStatus.UNCONFIRMED
        assert "single_origin" in codes(d)

    def test_two_independent_in_window_corroborated(self):
        d = claim_status([ev(1), ev(2, observed=T0 + dt.timedelta(hours=1))], AUTH)
        assert d.status == ClaimStatus.CORROBORATED
        assert d.origin_count == 2

    def test_outside_window(self):
        d = claim_status([ev(1), ev(2, observed=T0 + dt.timedelta(hours=5))], AUTH)
        assert "outside_time_window" in codes(d)

    def test_missing_observation_time(self):
        d = claim_status([ev(1, observed=None), ev(2, observed=None)], AUTH)
        assert d.status == ClaimStatus.UNCONFIRMED
        assert "missing_observation_time" in codes(d)

    def test_forty_forwards_stay_unconfirmed(self):
        text = "They are buying votes with 5000 naira at ward 5, share before they delete"
        items = [ev(i, text=text, is_forward=True) for i in range(40)]
        d = claim_status(items, AUTH)
        assert d.status == ClaimStatus.UNCONFIRMED
        assert d.forward_count == 40
        assert d.origin_count == 1
        assert "forwards_only" in codes(d)

    def test_conflicting_evidence(self):
        d = claim_status([ev(1), ev(2), ev(3, stance=Stance.OPPOSES)], AUTH)
        assert d.status == ClaimStatus.UNCONFIRMED
        assert "conflicting_evidence" in codes(d)

    def test_irrelevant_ignored(self):
        d = claim_status([ev(1), ev(2), ev(3, stance=Stance.IRRELEVANT)], AUTH)
        assert d.status == ClaimStatus.CORROBORATED

    def test_authority_confirms(self):
        d = claim_status([ev(1, explicit=True, source_domain="inecnigeria.org")], AUTH)
        assert d.status == ClaimStatus.CONFIRMED_BY_SOURCE
        assert d.authority == "inecnigeria.org"

    def test_authority_refutes(self):
        d = claim_status(
            [ev(1), ev(2), ev(3, stance=Stance.OPPOSES, explicit=True, source_domain="npf.gov.ng")],
            AUTH,
        )
        assert d.status == ClaimStatus.REFUTED_BY_SOURCE

    def test_authority_needs_explicit_statement(self):
        d = claim_status([ev(1, source_domain="inecnigeria.org")], AUTH)
        assert d.status == ClaimStatus.UNCONFIRMED

    def test_unlisted_domain_is_not_authority(self):
        d = claim_status([ev(1, explicit=True, source_domain="fake-inec.ng")], AUTH)
        assert d.status == ClaimStatus.UNCONFIRMED

    def test_authorities_conflict(self):
        d = claim_status(
            [
                ev(1, explicit=True, source_domain="inecnigeria.org"),
                ev(2, stance=Stance.OPPOSES, explicit=True, source_domain="npf.gov.ng"),
            ],
            AUTH,
        )
        assert "authorities_conflict" in codes(d)

    def test_low_reputation_ignored(self):
        d = claim_status([ev(1), ev(2, reputation=-9)], AUTH)
        assert "single_origin" in codes(d)

    def test_location_kept(self):
        assert claim_status([ev(1)], AUTH, location="37/06/02").location == "37/06/02"


class TestMaterialChange:
    base = Decision("unconfirmed", (Reason("single_origin"),), origin_count=1)

    def test_first_is_material(self):
        assert is_material_change(None, self.base)

    def test_identical_is_not(self):
        assert not is_material_change(
            self.base, Decision("unconfirmed", (Reason("single_origin"),), origin_count=1)
        )

    def test_wording_only_is_not(self):
        same = Decision("unconfirmed", (Reason("single_origin", {"note": "x"}),), origin_count=1)
        assert not is_material_change(self.base, same)

    @pytest.mark.parametrize(
        "new",
        [
            Decision("corroborated", origin_count=1),
            Decision("unconfirmed", (Reason("single_origin"),), origin_count=2),
            Decision("unconfirmed", (Reason("single_origin"),), origin_count=1, location="x"),
            Decision("unconfirmed", (Reason("conflicting_evidence"),), origin_count=1),
            Decision(
                "unconfirmed", (Reason("single_origin"),), origin_count=1, diffs={"a": (1, 2)}
            ),
        ],
    )
    def test_material(self, new):
        assert is_material_change(self.base, new)
