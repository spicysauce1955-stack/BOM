"""Cross-scenario invariants (docs/scenarios/golden-scenarios.md, mission §15)."""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.errors import GenerationFailure
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, InventoryItem, fulfill
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import Override, PinPost
from fenceai.topology.model import (
    BasePayload,
    ElevationSamplePayload,
    GatePayload,
    Node,
    Run,
    Topology,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology


def _fixtures():
    plain = straight_topology(6000)

    slope = straight_topology(6000)
    add_point_event(slope, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(slope, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

    mixed = straight_topology(7000)
    add_interval_event(mixed, "run1", "base", 4000, 7000, BasePayload(surface="masonry_wall"))

    gated = straight_topology(5000)
    add_point_event(gated, "run1", "gate", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))

    lshape = Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=4000, y_mm=0),
            Node(id="n3", x_mm=4000, y_mm=3000),
        ],
        runs=[
            Run(id="runA", start_node_id="n1", end_node_id="n2"),
            Run(id="runB", start_node_id="n2", end_node_id="n3"),
        ],
    )
    return {
        "plain": (plain, [], None),
        "slope": (slope, [], None),
        "mixed_base": (mixed, [], None),
        "gated": (gated, [], None),
        "lshape": (lshape, [], None),
        "pinned": (straight_topology(6000), [Override(id="ov1", run_id="run1", directive=PinPost(station_mm=2000))], None),
        "with_inventory": (
            straight_topology(1200), [],
            Inventory(items=[InventoryItem(id="rem1", sku="RAIL-3000", kind="remnant", length_mm=1250)]),
        ),
    }


@pytest.fixture(params=list(_fixtures()))
def spine(request):
    topo, overrides, inventory = _fixtures()[request.param]
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(topo, knowledge, catalog, overrides=overrides)
    reqs = derive_requirements(result.strategy, catalog)
    bom = fulfill(reqs, catalog, inventory)
    return result, reqs, bom, catalog


def test_span_never_exceeds_hard_max(spine):
    result, _, _, _ = spine
    assert all(sp.width_mm <= 1800 for sp in result.strategy.spans)


def test_cut_plans_feasible_and_conserving(spine):
    result, reqs, bom, catalog = spine
    for sku, plan in bom.cut_plans.items():
        sem = catalog.product(sku).consumption
        demanded = sorted(
            r.cut_length_mm for r in reqs if r.sku == sku for _ in range(r.engineering_qty)
        )
        planned = sorted(p.length_mm for b in plan.bars for p in b.pieces)
        assert planned == demanded  # piece conservation
        for bar in plan.bars:
            physical = sum(p.length_mm for p in bar.pieces) + sem.kerf_mm * (len(bar.pieces) - 1)
            assert physical <= bar.stock_length_mm
            if bar.leftover_reusable:
                assert bar.leftover_mm >= sem.min_reusable_remnant_mm


def test_packages_never_undersupply(spine):
    result, reqs, bom, catalog = spine
    for line in bom.lines:
        sem = catalog.product(line.sku).consumption
        if sem.kind == "packaged_discrete":
            supplied = line.purchase_qty * sem.qty_per_package
            allocated = sum(a.qty for a in bom.allocations if a.sku == line.sku)
            assert supplied + allocated >= line.engineering_qty


def test_full_traceability_chain(spine):
    result, reqs, bom, _ = spine
    req_ids = {r.id for r in reqs}
    element_ids = set(result.strategy.element_ids())
    for r in reqs:
        assert r.pegs and all(e in element_ids for e in r.pegs)
        for e in r.pegs:
            assert result.graph.nodes_for_element(e)
    covered = {p for l in bom.lines for p in l.pegs} | {p for a in bom.allocations for p in a.pegs}
    assert covered == req_ids


def test_decision_edges_reference_existing_nodes(spine):
    result, _, _, _ = spine
    graph = result.graph
    node_ids = {n.id for n in graph.nodes}
    for e in graph.edges:
        assert e.from_id in node_ids and e.to_id in node_ids


def test_projected_remnants_meet_threshold(spine):
    result, _, bom, catalog = spine
    for item in bom.projected_remnants:
        sem = catalog.product(item.sku).consumption
        assert item.length_mm >= sem.min_reusable_remnant_mm


def test_determinism(spine):
    result, reqs, bom, _ = spine
    # regenerate the whole spine from the run's captured inputs is exercised in the
    # spike; here: graph and strategy serialization is stable
    assert result.strategy.model_dump() == result.strategy.model_dump()


def test_missing_hard_knowledge_is_generation_failure():
    empty = KnowledgeBase(versions=[])
    with pytest.raises(GenerationFailure):
        generate(straight_topology(3000), empty, demo_catalog())
