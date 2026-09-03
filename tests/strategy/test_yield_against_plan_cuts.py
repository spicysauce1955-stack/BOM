"""`yield_threshold` against the packer it is a claim about.

`yield_threshold` is arithmetic derived from `plan_cuts`' kerf model. Testing it
against its own formula proves nothing — the formula is the thing in doubt. So
this asks the real packer: at the threshold, do `n` pieces fit on one board, and
at one millimetre over, do they stop fitting?

That cliff is the whole justification for a snap-to-yield tick, and it is the one
number in this design a person cannot judge by eye.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.model import DivisibleLinear
from fenceai.fulfillment.cutplan import CutPiece, plan_cuts
from fenceai.strategy.layout import yield_threshold


def _boards(piece_mm: int, *, stock_mm: int, kerf_mm: int, count: int) -> int:
    plan = plan_cuts(
        "yield-probe",
        DivisibleLinear(purchase_length_mm=stock_mm, kerf_mm=kerf_mm),
        [CutPiece(length_mm=piece_mm, requirement_id=f"p{i}")
         for i in range(count)],
    )
    return plan.new_bar_count


@pytest.mark.parametrize("stock_mm,kerf_mm", [
    (2000, 3), (2000, 0), (2438, 3), (3000, 3), (6000, 5),
])
@pytest.mark.parametrize("pieces", [2, 3])
def test_the_threshold_is_exactly_where_the_packer_changes_its_mind(
    stock_mm, kerf_mm, pieces,
):
    """At the threshold, `pieces` share a board. One millimetre longer and they
    do not — so the same order needs more boards. `count` is a multiple of
    `pieces` so the arithmetic is a clean division either way."""
    threshold = yield_threshold(stock_mm, kerf_mm, pieces)
    count = pieces * 4

    assert _boards(threshold, stock_mm=stock_mm, kerf_mm=kerf_mm,
                   count=count) == count // pieces
    assert _boards(threshold + 1, stock_mm=stock_mm, kerf_mm=kerf_mm,
                   count=count) > count // pieces


def test_the_cliff_this_design_quotes():
    """The measured example the panel argues from: ten infill pieces out of 2 m
    stock with a 3 mm blade. Two millimetres of piece length halves the boards.

    Stated as PIECE lengths, not bay widths — the correction that mattered most,
    because a bay is one post face wider than the piece it holds."""
    assert yield_threshold(2000, 3, 2) == 998
    assert _boards(1000, stock_mm=2000, kerf_mm=3, count=10) == 10
    assert _boards(998, stock_mm=2000, kerf_mm=3, count=10) == 5


def test_a_piece_longer_than_its_stock_is_refused_by_the_packer():
    """Why nothing is measured speculatively. A candidate laying out 2439 mm bays
    against 2 m stock does not return a bad number — it raises, and a probe is a
    full generation, so it would fail a run over a published table."""
    with pytest.raises(ValueError, match="exceeds stock length"):
        _boards(2439, stock_mm=2000, kerf_mm=3, count=1)
