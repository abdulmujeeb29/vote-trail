from apps.trust.confidence import settle
from apps.trust.status import result_status
from apps.trust.types import CitizenSheet, ResultStatus, SheetFigures, Submission

BASE = dict(
    party_votes={"PA": 214, "PB": 187},
    total_valid=401,
    rejected=9,
    total_used=410,
    ballots_issued=900,
    unused=489,
    spoilt=1,
    accredited=420,
    registered=900,
)


def fig(low=(), **over):
    return SheetFigures(**{**BASE, **over, "low_confidence_fields": tuple(low)})


def test_unsure_total_confirmed_by_balancing_equation():
    out, blocking, dropped = settle(fig(["total_valid"]))
    assert blocking == () and dropped == () and out.total_valid == 401


def test_chain_of_confirmations():
    _, blocking, dropped = settle(fig(["total_valid", "total_used"]))
    assert blocking == () and dropped == ()


def test_unbalanced_unsure_total_is_dropped_not_blocking():
    out, blocking, dropped = settle(fig(["total_valid"], total_valid=499))
    assert blocking == () and dropped == ("total_valid",) and out.total_valid is None


def test_accredited_cannot_be_confirmed_so_it_is_dropped():
    out, blocking, dropped = settle(fig(["accredited"]))
    assert dropped == ("accredited",) and out.accredited is None and blocking == ()


def test_unsure_party_blocks_unless_words_agree():
    _, blocking, _ = settle(fig(["party:PB"]))
    # total_valid equation holds and PB is the only unsure member -> confirmed
    assert blocking == ()
    # Chains confirm too: E2 confirms total_valid, then E1 confirms PB.
    _, blocking, _ = settle(fig(["party:PB", "total_valid"]))
    assert blocking == ()
    # With no total to check against, only the words can confirm a party score.
    _, blocking, _ = settle(fig(["party:PB"], total_valid=None))
    assert blocking == ("party:PB",)
    _, blocking, _ = settle(fig(["party:PB"], total_valid=None, words={"PB": 187}))
    assert blocking == ()


def test_other_unknown_low_fields_block():
    _, blocking, _ = settle(fig(["pu_code"]))
    assert blocking == ("pu_code",)


def test_status_uses_settled_figures():
    irev = SheetFigures(
        **{
            **BASE,
            "party_votes": {"PA": 214, "PB": 287},
            "total_valid": 501,
            "accredited": 520,
            "total_used": 510,
            "unused": 389,
        }
    )
    sheets = [
        CitizenSheet(Submission("1", participant_key="a"), fig()),
        CitizenSheet(
            Submission("2", participant_key="b"),
            fig(["accredited", "total_valid", "total_used", "unused"]),
        ),
    ]
    d = result_status(sheets, irev)
    assert d.status == ResultStatus.MISMATCH
    assert "not_compared" in d.reason_codes


def test_unsure_irev_totals_are_not_compared():
    irev = SheetFigures(**{**BASE, "low_confidence_fields": ("accredited",)})
    d = result_status([CitizenSheet(Submission("1", participant_key="a"), fig())], irev)
    assert d.status == ResultStatus.MATCHES and "irev_not_compared" in d.reason_codes
