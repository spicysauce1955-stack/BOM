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


def test_determinism():
    demand = pieces(1500, 1200, 900, 800, 700, 2500)
    p1 = plan_cuts("RAIL-3000", SEM, demand)
    p2 = plan_cuts("RAIL-3000", SEM, list(reversed(demand)))
    assert p1.model_dump() == p2.model_dump()
