"""Cross-scenario invariants (docs/scenarios/golden-scenarios.md, mission §15)."""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.errors import GenerationFailure
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, InventoryItem, fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import ForceVertical, Override, PinPost
from fenceai.topology.model import (
    BasePayload,
    ElevationSamplePayload,
    GatePayload,
    Node,
    Run,
    Topology,
)
from fenceai.fencemodel.demo import demo_models
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from tests.conftest import add_interval_event, add_point_event, straight_topology

LIBRARY = FenceModelLibrary(models=list(demo_models().values()))
SLAT = FenceModelChoice(model_id="M-SLAT")


def _fixtures():
    plain = straight_topology(6000)

    slope = straight_topology(6000)
    add_point_event(slope, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(slope, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

    mixed = straight_topology(7000)
    add_interval_event(mixed, "run1", "base", 4000, 7000, BasePayload(surface="masonry_wall"))

    gated = straight_topology(5000)
    add_point_event(gated, "run1", "gate", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))

    # A RAKED run. The suite had none: the demo KB carries an unscoped
    # PreferVertical(stepped) (K-STEP-SLOPE), so every sloped fixture above
    # resolves to stepped and `grep -rn raked tests/` found nothing. Raked is
    # the only mode that puts a span on `rail_cut_basis="slope"`, so the
    # slope-length branch in fencemodel/resolve.py was reachable by no test at
    # all — deleting it left the suite green while rails were cut to plan width
    # instead of slope length.
    raked = straight_topology(6000)
    add_point_event(raked, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(raked, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

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
    # SLAT fixtures. Every shape above is M-LEGACY — two rails and eight screws —
    # so the whole infill path (a fitted pattern, a spread residual, per-crossing
    # fixings, a member cut to the panel height) sat outside this battery. Proved
    # by mutation: dropping infill lines from `BomLine.pegs` left the suite green
    # while the BOM -> requirement -> element -> decision chain was broken. The
    # raked one matters separately — it is the only mode that puts a span on
    # `rail_cut_basis="slope"` WITH members that must NOT follow the grade.
    slat_plain = straight_topology(6000)
    slat_raked = straight_topology(6000)
    add_point_event(slat_raked, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(slat_raked, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

    return {
        "plain": (plain, [], None),
        "slope": (slope, [], None),
        "slat": (slat_plain, [], None, SLAT),
        "slat_raked": (
            slat_raked,
            [Override(id="ov_rake", run_id="run1",
                      directive=ForceVertical(start_station_mm=0, end_station_mm=6000,
                                              mode="raked"))],
            None, SLAT,
        ),
        "raked": (
            raked,
            [Override(id="ov_rake", run_id="run1",
                      directive=ForceVertical(start_station_mm=0, end_station_mm=6000,
                                              mode="raked"))],
            None,
        ),
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
    topo, overrides, inventory, *model = _fixtures()[request.param]
    choice = model[0] if model else None
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(topo, knowledge, catalog, overrides=overrides,
                      models=LIBRARY, default_model=choice)
    reqs = derive_requirements(result.strategy, catalog)
    reqs = resolve_supply(reqs, catalog, inventory).requirements
    bom = fulfill(reqs, catalog, inventory)
    return result, reqs, bom, catalog, (topo, overrides, inventory, knowledge, choice)


@pytest.fixture()
def rerun(spine):
    """Regenerate the whole spine from the same inputs (real determinism check)."""
    _, _, _, catalog, (topo, overrides, inventory, knowledge, choice) = spine
    result = generate(topo, knowledge, catalog, overrides=overrides,
                      models=LIBRARY, default_model=choice)
    reqs = derive_requirements(result.strategy, catalog)
    reqs = resolve_supply(reqs, catalog, inventory).requirements
    bom = fulfill(reqs, catalog, inventory)
    return result, reqs, bom


def test_span_never_exceeds_hard_max(spine):
    result, _, _, _, _ = spine
    assert all(sp.width_mm <= 1800 for sp in result.strategy.spans)


def test_cut_plans_feasible_and_conserving(spine):
    result, reqs, bom, catalog, _ = spine
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
    result, reqs, bom, catalog, _ = spine
    for line in bom.lines:
        sem = catalog.product(line.sku).consumption
        if sem.kind == "packaged_discrete":
            supplied = line.purchase_qty * sem.qty_per_package
            allocated = sum(a.qty for a in bom.allocations if a.sku == line.sku)
            assert supplied + allocated >= line.engineering_qty
        elif sem.kind == "coverage_based":
            # purchase * den >= applications * num  <=>  supply covers demand exactly
            assert (
                line.purchase_qty * sem.qty_per_application.den
                >= line.engineering_qty * sem.qty_per_application.num
            )


def test_full_traceability_chain(spine):
    result, reqs, bom, _, _ = spine
    req_ids = {r.id for r in reqs}
    element_ids = set(result.strategy.element_ids())
    for r in reqs:
        assert r.pegs and all(e in element_ids for e in r.pegs)
        for e in r.pegs:
            assert result.graph.nodes_for_element(e)
    covered = {p for l in bom.lines for p in l.pegs} | {p for a in bom.allocations for p in a.pegs}
    assert covered == req_ids


def test_decision_edges_reference_existing_nodes(spine):
    result, _, _, _, _ = spine
    graph = result.graph
    node_ids = {n.id for n in graph.nodes}
    for e in graph.edges:
        assert e.from_id in node_ids and e.to_id in node_ids


def test_projected_remnants_meet_threshold(spine):
    result, _, bom, catalog, _ = spine
    for item in bom.projected_remnants:
        sem = catalog.product(item.sku).consumption
        assert item.length_mm >= sem.min_reusable_remnant_mm


def test_determinism(spine, rerun):
    """Real double-run: regenerate the whole spine from the same inputs and demand
    byte-identical output — across every fixture shape (test-review finding 1)."""
    result, reqs, bom, _, _ = spine
    result2, reqs2, bom2 = rerun
    assert result2.strategy.model_dump() == result.strategy.model_dump()
    assert result2.graph.model_dump() == result.graph.model_dump()
    assert result2.run.id == result.run.id
    assert [r.model_dump() for r in reqs2] == [r.model_dump() for r in reqs]
    assert bom2.model_dump() == bom.model_dump()


def test_knowledge_refs_resolve_to_snapshot(spine):
    """Every governed_by/defeated edge cites a version present in the run's
    knowledge snapshot (test-review finding 7)."""
    result, _, _, _, _ = spine
    snapshot = {f"{oid}@v{ver}" for oid, ver in result.run.knowledge_snapshot}
    for e in result.graph.edges:
        if e.knowledge_ref is not None:
            assert e.knowledge_ref in snapshot, e.knowledge_ref


def test_coverage_and_cap_quantities_plain():
    """S01 spine: 5 posts -> 5 caps; 5 soil footings at 0.5 bag -> 3 bags (odd
    round-up boundary) — coverage semantics numerically pinned (finding 2/3)."""
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(6000), knowledge, catalog)
    reqs = derive_requirements(result.strategy, catalog)
    reqs = resolve_supply(reqs, catalog).requirements
    bom = fulfill(reqs, catalog)
    caps = next(l for l in bom.lines if l.sku == "POST-CAP")
    assert caps.engineering_qty == 5 and caps.purchase_qty == 5
    conc = next(l for l in bom.lines if l.sku == "CONC-25")
    assert conc.engineering_qty == 5  # applications
    assert conc.purchase_qty == 3     # ceil(5 * 1/2)


def test_sliver_span_warning_cites_preference():
    """Run shorter than the preferred minimum span -> surfaced sliver warning
    citing K-SLIVER (test-review finding 4)."""
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(400), knowledge, catalog)
    assert [sp.width_mm for sp in result.strategy.spans] == [400]
    warning = next(w for w in result.strategy.warnings if w.code == "sliver_span")
    node = result.graph.node(warning.decision_ref)
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id) if e.type == "governed_by"}
    assert "K-SLIVER@v1" in refs


def test_missing_hard_knowledge_is_generation_failure():
    empty = KnowledgeBase(versions=[])
    with pytest.raises(GenerationFailure):
        generate(straight_topology(3000), empty, demo_catalog())


@pytest.mark.parametrize("name", sorted(_fixtures()))
def test_no_generated_run_carries_a_pinned_product(name):
    """`ResolvedSlot.pinned_sku` is a PREVIEW concept living on a persisted type.

    A drawer can ask "what would this panel cost in cedar", and the resolver
    narrows the slot's eligibility to answer — request-scoped, refused rather
    than bypassed, and labelled a what-if on screen. What it must never be is a
    product override that reached a stored run: it carries no `Override` record,
    no anchor and no decision node, so a run holding one would price a product
    nothing in the graph chose. The invariant was written down as a comment on
    the field; the architecture review pointed out that a comment is not an
    enforcement, and that a future caller wiring `slot_skus` into generation
    would create exactly the fifth category the architecture forbids.
    """
    topo, overrides, inventory, *model = _fixtures()[name]
    result = generate(topo, demo_knowledge(), demo_catalog(), overrides=overrides,
                      models=LIBRARY, default_model=model[0] if model else None)
    pinned = [(sp.id, slot.slot_key, slot.pinned_sku)
              for sp in result.strategy.spans
              for slot in (sp.panel.slots if sp.panel else [])
              if slot.pinned_sku]
    assert not pinned, pinned
