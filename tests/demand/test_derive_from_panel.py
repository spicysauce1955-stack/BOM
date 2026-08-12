"""Demand expands the panel's slots. Posts, caps, concrete and gate kits are NOT
panel parts and keep their existing path."""

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fencemodel.resolve import ResolvedPanel, ResolvedSlot
from fenceai.fulfillment.supply import resolve_supply
from fenceai.fulfillment.fulfill import fulfill
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.strategy.model import Span, Strategy
from tests.conftest import straight_topology


def test_span_lines_come_from_the_panel_and_carry_slot_key_and_eligibility():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    reqs = derive_requirements(result.strategy, demo_catalog(), result.run.demand_skus)
    rails = [r for r in reqs if r.role == "rail"]
    assert rails and all(r.slot_key == "rail" for r in rails)
    assert all(r.sku == "" for r in rails)          # resolved in fulfillment
    assert all([m.sku for m in r.eligibility.members] == ["RAIL-3000"] for r in rails)


def test_post_lines_are_untouched_by_the_panel_path():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    reqs = derive_requirements(result.strategy, demo_catalog(), result.run.demand_skus)
    posts = [r for r in reqs if r.role == "post"]
    assert posts and all(r.sku for r in posts)      # still named directly
    assert all(r.slot_key == "" for r in posts)


def test_one_line_per_slot_not_one_per_member():
    """A 40-slat bay must be one line of 40. This is what keeps the decision graph
    and the BOM from exploding on a 100 m fence."""
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    reqs = derive_requirements(result.strategy, demo_catalog(), result.run.demand_skus)
    per_span_rail_lines = [r for r in reqs if r.role == "rail"]
    assert len(per_span_rail_lines) == len(result.strategy.spans)
    assert all(r.engineering_qty == 2 for r in per_span_rail_lines)


def test_a_span_with_no_panel_raises_rather_than_silently_defaulting():
    """A run generated before the fence-model change has rail_count/screws_count
    but no panel; regenerating is the only correct answer — silently falling
    back to those legacy fields would make demand disagree with what's shown."""
    strategy = Strategy(id="s1", spans=[
        Span(id="span1", run_ref="run1", start_station_mm=0, end_station_mm=1500,
             width_mm=1500, slope_len_mm=1500, panel=None)
    ])
    with pytest.raises(ValueError, match="span1"):
        derive_requirements(strategy, demo_catalog())


def test_a_zero_qty_slot_produces_a_zero_qty_line_that_fulfils_harmlessly():
    """A knowledge param overridden to 0 (e.g. rails_per_span=0) resolves to a
    ResolvedSlot with qty=0 rather than the slot being omitted (Task 3 finding,
    carried forward). derive_requirements does not special-case it — the line
    flows through with engineering_qty=0, and it must not produce a spurious BOM
    line, cut plan entry, or warning."""
    panel = ResolvedPanel(model_ref="M-TEST", slots=[
        ResolvedSlot(
            slot_key="rail", role="rail", qty=0, length_mm=1500, length_basis="width",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),
        ),
    ])
    strategy = Strategy(id="s1", spans=[
        Span(id="span1", run_ref="run1", start_station_mm=0, end_station_mm=1500,
             width_mm=1500, slope_len_mm=1500, panel=panel)
    ])
    reqs = derive_requirements(strategy, demo_catalog())
    zero_line = next(r for r in reqs if r.role == "rail")
    assert zero_line.engineering_qty == 0

    resolution = resolve_supply(reqs, demo_catalog())
    assert resolution.warnings == []
    assert resolution.requirements[0].sku == "RAIL-3000"

    bom = fulfill(resolution.requirements, demo_catalog())
    assert bom.lines == []
    assert bom.cut_plans["RAIL-3000"].bars == []
    assert bom.cut_plans["RAIL-3000"].new_bar_count == 0


def test_unit_is_derived_from_length_not_guessed_from_an_allowlisted_role():
    """A role that isn't "rail"/"infill" (fence-model roles are free-form, e.g.
    "spacer" per fencemodel/model.py:57) must still get the SAME unit fulfill()
    derives from the product's consumption kind — fulfill() never reads
    RequirementLine.unit at all, so a role-keyed guess that disagrees with it
    double-books the parts ledger, which keys asked/purchased on (sku, unit)."""
    panel = ResolvedPanel(model_ref="M-TEST", slots=[
        ResolvedSlot(
            slot_key="brace", role="spacer", qty=2, length_mm=900, length_basis="width",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),  # divisible_linear
        ),
    ])
    strategy = Strategy(id="s1", spans=[
        Span(id="span1", run_ref="run1", start_station_mm=0, end_station_mm=1500,
             width_mm=1500, slope_len_mm=1500, panel=panel)
    ])
    reqs = derive_requirements(strategy, demo_catalog())
    spacer_req = next(r for r in reqs if r.role == "spacer")

    resolution = resolve_supply(reqs, demo_catalog())
    bom = fulfill(resolution.requirements, demo_catalog())
    bom_line = next(l for l in bom.lines if l.sku == "RAIL-3000")
    assert spacer_req.unit == bom_line.engineering_unit == "cut"
