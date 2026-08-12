"""Golden scenarios S07-S12 (docs/scenarios/golden-scenarios.md)."""

from __future__ import annotations

from fenceai.ai.stub import StubProposer
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, InventoryItem, fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.learning.model import Correction, ReviewAction
from fenceai.learning.review import apply_review
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import Override, PinPost
from fenceai.topology.model import GatePayload
from tests.conftest import add_point_event, straight_topology


def _spine(topo, knowledge, catalog, inventory=None, overrides=None):
    result = generate(topo, knowledge, catalog, overrides=overrides)
    reqs = derive_requirements(result.strategy, catalog)
    reqs = resolve_supply(reqs, catalog, inventory).requirements
    bom = fulfill(reqs, catalog, inventory)
    return result, reqs, bom


def test_s07_rail_cutting_with_kerf(knowledge, catalog):
    result, reqs, bom = _spine(straight_topology(3000), knowledge, catalog)
    # 2 spans of 1500, 2 rails each -> 4 cuts of 1500
    rail_reqs = [r for r in reqs if r.sku == "RAIL-3000"]
    assert [r.cut_length_mm for r in rail_reqs] == [1500, 1500]
    assert all(r.engineering_qty == 2 for r in rail_reqs)

    plan = bom.cut_plans["RAIL-3000"]
    # 1500+3+1500 > 3000: one 1500 per bar, remnant 1497 reusable
    assert plan.new_bar_count == 4
    for bar in plan.bars:
        assert sum(p.length_mm for p in bar.pieces) + 3 * (len(bar.pieces) - 1) <= 3000
        assert bar.leftover_mm == 1497
        assert bar.leftover_reusable
    # 4 bars is provably minimal (1500+3+1500 > 3000), even though the fractional
    # LP bound of 3 can never be reached — labelling this "heuristic" is what made
    # persona-lab readers conclude the tool pads orders
    assert plan.certified_optimal
    assert (plan.lp_lower_bound, plan.lower_bound) == (3, 4)
    line = next(l for l in bom.lines if l.sku == "RAIL-3000")
    assert line.purchase_qty == 4
    assert len(bom.projected_remnants) == 4


def test_s08_screw_packaging(knowledge, catalog):
    result, reqs, bom = _spine(straight_topology(9600), knowledge, catalog)
    line = next(l for l in bom.lines if l.sku == "SCREW-S10")
    assert (line.engineering_qty, line.purchase_qty, line.overage_qty) == (48, 3, 12)
    # pegged back to span screw demands
    assert line.pegs
    req_ids = {r.id for r in reqs if r.sku == "SCREW-S10"}
    assert set(line.pegs) == req_ids


def test_s09_remnant_reuse(knowledge, catalog):
    inventory = Inventory(
        items=[InventoryItem(id="inv_rem1", sku="RAIL-3000", kind="remnant", length_mm=1250)]
    )
    result, reqs, bom = _spine(straight_topology(1200), knowledge, catalog, inventory)
    # 1 span of 1200 -> 2 rail cuts of 1200; remnant takes one (1200+3 <= 1253)
    plan = bom.cut_plans["RAIL-3000"]
    assert plan.new_bar_count == 1
    remnant_bar = next(b for b in plan.bars if b.source == "inv_rem1")
    assert [p.length_mm for p in remnant_bar.pieces] == [1200]
    alloc = next(a for a in bom.allocations if a.inventory_item_id == "inv_rem1")
    assert alloc.length_used_mm == 1200
    line = next(l for l in bom.lines if l.sku == "RAIL-3000")
    assert line.purchase_qty == 1  # one fewer new bar thanks to the remnant


def test_s10_gate_with_reinforced_posts(knowledge, catalog):
    topo = straight_topology(5000)
    add_point_event(topo, "run1", "ev_gate", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    result, reqs, bom = _spine(topo, knowledge, catalog)
    s = result.strategy

    assert len(s.gates) == 1
    gate = s.gates[0]
    assert (gate.start_station_mm, gate.end_station_mm, gate.kit_sku) == (2000, 3000, "GATE-KIT-1000")

    gate_posts = sorted((p for p in s.posts if p.kind == "gate"), key=lambda p: p.station_mm)
    assert [p.station_mm for p in gate_posts] == [2000, 3000]
    assert all(p.reinforced and p.sku == "POST-S-HD" for p in gate_posts)
    # no spans inside the opening; 2+2 spans on the flanks
    assert sorted(sp.width_mm for sp in s.spans) == [1000, 1000, 1000, 1000]

    # reinforcement decision cites the gate rule AND the gate topology event
    d = result.graph.nodes_for_element(gate_posts[0].id)[0]
    refs = {e.knowledge_ref for e in result.graph.in_edges(d.id) if e.type == "governed_by"}
    assert "K-GATE-REINF@v1" in refs
    gate_facts = [
        a for a in result.graph.ancestors(d.id)
        if a.action == "gate_event" and a.payload.get("event_id") == "ev_gate"
    ]
    assert gate_facts, "gate post decision must cite the gate topology event (S10)"

    kit_line = next(l for l in bom.lines if l.sku == "GATE-KIT-1000")
    assert kit_line.purchase_qty == 1
    assert any("kit includes" in n for n in kit_line.notes)


def test_s11_pinned_post_override(knowledge, catalog):
    override = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=2000))
    result, _, _ = _spine(straight_topology(6000), knowledge, catalog, overrides=[override])
    s = result.strategy

    pinned = [p for p in s.posts if p.pinned]
    assert len(pinned) == 1
    assert pinned[0].station_mm == 2000
    # layout respects the pin: [0,2000] -> 2x1000; [2000,6000] -> 1334+1333+1333
    assert sorted(sp.width_mm for sp in s.spans) == [1000, 1000, 1333, 1333, 1334]
    assert "ov1" in result.run.overrides_applied
    assert result.orphaned_overrides == []
    assert override.status == "active"  # generate() never mutates caller state
    # decision trail: pinned post decision has an override_applied ancestor
    d = result.graph.nodes_for_element(pinned[0].id)[0]
    assert d.status == "pinned"
    assert any(a.kind == "override_applied" for a in result.graph.ancestors(d.id))


def test_s11_orphaned_override_surfaces_warning(knowledge, catalog):
    override = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=9999))
    result, _, _ = _spine(straight_topology(6000), knowledge, catalog, overrides=[override])
    assert result.orphaned_overrides == ["ov1"]
    assert override.status == "active"  # purity: caller decides whether to persist orphan status
    assert any(w.code == "orphaned_override" for w in result.strategy.warnings)


def test_s12_correction_to_candidate_workflow(knowledge, catalog):
    correction = Correction(
        id="corr1",
        project_id="p1",
        generation_run_id="run_x",
        element_ref="post@run1:1500",
        before={"station_mm": 1500},
        after={"station_mm": 1450},
        comment="always use existing foundations when within 300 mm",
        author="expert-jane",
    )
    proposals = StubProposer().propose([correction])
    assert len(proposals) == 1
    cand = proposals[0]
    assert cand.status == "proposed"
    assert cand.type == "candidate"
    assert cand.scope == {"project_id": "p1"}  # narrowest scope by default
    assert cand.derived_from == ["corr1"]
    assert cand.source_text == correction.comment  # verbatim

    # candidates are inert: generation identical with candidate present
    base = generate(straight_topology(6000), knowledge, catalog)
    knowledge.versions.append(cand)
    with_cand = generate(straight_topology(6000), knowledge, catalog)
    assert base.strategy.model_dump() == with_cand.strategy.model_dump()

    # approval is an explicit human act producing a NEW active version
    approved = apply_review(
        cand, ReviewAction(action="approve", reviewer="expert-admin")
    )
    assert approved.status == "active"
    assert approved.version == cand.version + 1
    assert approved.derived_from == [cand.ref]
    assert approved.attributed_to == "expert-admin"
    assert cand.status == "retired"


def test_s12_rejected_candidate_is_kept(knowledge):
    correction = Correction(
        id="corr2", project_id="p1", generation_run_id="r",
        comment="use existing foundation here",
    )
    cand = StubProposer().propose([correction])[0]
    rejected = apply_review(cand, ReviewAction(action="reject", reviewer="boss", reason="one-off"))
    assert rejected.status == "rejected"  # kept, suppresses re-proposal
