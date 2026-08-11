"""Cut planner boundary tests (test-review findings 3-4)."""

from __future__ import annotations

import pytest

from fenceai.catalog.model import DivisibleLinear
from fenceai.fulfillment.cutplan import CutPiece, RemnantStock, plan_cuts

SEM = DivisibleLinear(purchase_length_mm=3000, kerf_mm=3, min_reusable_remnant_mm=300)


def pieces(*lengths: int) -> list[CutPiece]:
    return [CutPiece(length_mm=l, requirement_id=f"r{i}") for i, l in enumerate(lengths)]


def bar_invariant(plan):
    for bar in plan.bars:
        assert (
            sum(p.length_mm for p in bar.pieces) + SEM.kerf_mm * (len(bar.pieces) - 1)
            <= bar.stock_length_mm
        )


def test_piece_exactly_equal_to_stock():
    plan = plan_cuts("RAIL-3000", SEM, pieces(3000))
    assert plan.new_bar_count == 1
    assert plan.bars[0].leftover_mm == 0
    assert plan.waste_mm == 0
    bar_invariant(plan)


def test_piece_longer_than_stock_rejected():
    with pytest.raises(ValueError):
        plan_cuts("RAIL-3000", SEM, pieces(3001))


def test_exact_kerf_fit_shares_bar():
    # 1500 + 3 (kerf) + 1497 == 3000: must share one bar
    plan = plan_cuts("RAIL-3000", SEM, pieces(1500, 1497))
    assert plan.new_bar_count == 1
    assert len(plan.bars[0].pieces) == 2
    assert plan.bars[0].leftover_mm == 0
    assert plan.certified_optimal
    bar_invariant(plan)


def test_one_mm_over_kerf_fit_needs_second_bar():
    # 1500 + 3 + 1498 == 3001 > 3000
    plan = plan_cuts("RAIL-3000", SEM, pieces(1500, 1498))
    assert plan.new_bar_count == 2
    bar_invariant(plan)


def test_remnant_exactly_at_reuse_threshold():
    # piece 2697: leftover = 3000 - 2697 - 3 = 300 == threshold -> reusable
    plan = plan_cuts("RAIL-3000", SEM, pieces(2697))
    assert plan.bars[0].leftover_mm == 300
    assert plan.bars[0].leftover_reusable
    assert plan.waste_mm == 0


def test_remnant_one_mm_below_threshold_is_waste():
    plan = plan_cuts("RAIL-3000", SEM, pieces(2698))
    assert plan.bars[0].leftover_mm == 299
    assert not plan.bars[0].leftover_reusable
    assert plan.waste_mm == 299


def test_empty_demand():
    plan = plan_cuts("RAIL-3000", SEM, [])
    assert plan.bars == []
    assert plan.new_bar_count == 0
    assert plan.lp_lower_bound == 0
    assert plan.certified_optimal


def test_remnant_first_allocation():
    remnant = RemnantStock(inventory_item_id="inv1", length_mm=1250)
    plan = plan_cuts("RAIL-3000", SEM, pieces(1200, 1200), [remnant])
    sources = sorted(b.source for b in plan.bars)
    assert sources == ["inv1", "new"]
    inv_bar = next(b for b in plan.bars if b.source == "inv1")
    assert [p.length_mm for p in inv_bar.pieces] == [1200]
    assert plan.new_bar_count == 1


def test_remnant_never_increases_bar_count():
    # both 1500s fit pairwise-impossibly (1500+3+1500 > 3000) so 2 new bars without
    # remnants; a useless tiny remnant must not change that
    remnant = RemnantStock(inventory_item_id="inv1", length_mm=400)
    plan = plan_cuts("RAIL-3000", SEM, pieces(1500, 1500), [remnant])
    assert plan.new_bar_count == 2
    assert all(b.source == "new" for b in plan.bars if b.pieces)


def test_piece_conservation():
    demand = pieces(1500, 1200, 900, 800, 700, 2500)
    plan = plan_cuts("RAIL-3000", SEM, demand)
    planned = sorted((p.length_mm, p.requirement_id) for b in plan.bars for p in b.pieces)
    assert planned == sorted((p.length_mm, p.requirement_id) for p in demand)
    bar_invariant(plan)


def test_provably_optimal_plan_is_certified_when_the_lp_bound_is_loose():
    """1800 mm pieces from 3000 mm stock: 1803 + 1803 > 3003, so one piece per bar
    IS the minimum. The fractional relaxation says 7 and can never be reached —
    calling that plan "heuristic" told four users the tool pads orders."""
    plan = plan_cuts("RAIL-3000", SEM, pieces(*([1800] * 10)))
    assert plan.new_bar_count == 10
    assert plan.lp_lower_bound == 7  # the relaxation, reported unchanged
    assert plan.lower_bound == 10  # what is actually provable
    assert plan.certified_optimal


def test_bound_lets_small_pieces_ride_along_with_the_big_ones():
    # three 1800s each need their own bar; the 100 fits alongside one of them
    plan = plan_cuts("RAIL-3000", SEM, pieces(1800, 1800, 1800, 100))
    assert plan.new_bar_count == 3
    assert plan.lower_bound == 3
    assert plan.certified_optimal


def test_plan_we_cannot_prove_optimal_stays_uncertified():
    """2003 + 1003 > 3003 and 3 x 1003 > 3003, so 3 bars really is optimal — but
    no bound we compute proves it. The label stays honest instead of claiming a
    certificate it does not have."""
    plan = plan_cuts("RAIL-3000", SEM, pieces(2000, 1000, 1000, 1000))
    assert plan.new_bar_count == 3
    assert plan.lower_bound == 2
    assert not plan.certified_optimal


def test_bound_credits_remnant_capacity():
    # one 1200 goes on the remnant, one on a new bar: 1 new bar is provably minimal
    remnant = RemnantStock(inventory_item_id="inv1", length_mm=1250)
    plan = plan_cuts("RAIL-3000", SEM, pieces(1200, 1200), [remnant])
    assert plan.new_bar_count == 1
    assert plan.lower_bound == 1
    assert plan.certified_optimal


def test_determinism():
    demand = pieces(1500, 1200, 900, 800, 700, 2500)
    p1 = plan_cuts("RAIL-3000", SEM, demand)
    p2 = plan_cuts("RAIL-3000", SEM, list(reversed(demand)))
    assert p1.model_dump() == p2.model_dump()


# ---- the cut plan's user-facing surface (persona lab run 2, §4) ----
# A BOM note is printed verbatim into a Hebrew table. Solver vocabulary there is
# both untranslated and unreadable — and it read as an admission of padding.

def test_bom_line_for_an_uncertified_plan_carries_no_solver_jargon(catalog):
    from fenceai.demand.derive import RequirementLine
    from fenceai.fulfillment.fulfill import fulfill

    reqs = [
        RequirementLine(id=f"r{i}", sku="RAIL-3000", engineering_qty=1, unit="cut",
                        cut_length_mm=length)
        for i, length in enumerate((2000, 1000, 1000, 1000))
    ]
    bom = fulfill(reqs, catalog)
    assert not bom.cut_plans["RAIL-3000"].certified_optimal
    line = next(l for l in bom.lines if l.sku == "RAIL-3000")
    assert line.notes == []
