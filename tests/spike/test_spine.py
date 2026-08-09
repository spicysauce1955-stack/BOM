"""Spike: the minimal executable spine (plan/tasks/00-spike.md).

Topology -> knowledge -> strategy -> decisions -> requirements -> fulfillment -> BOM
on S01/S07/S08-shaped fixtures, plus determinism and traceability.
"""

from __future__ import annotations

from fenceai.catalog.model import DivisibleLinear
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.cutplan import CutPiece, plan_cuts
from fenceai.fulfillment.fulfill import fulfill
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def test_s01_straight_fence_spans_and_posts(knowledge, catalog):
    topo = straight_topology(6000)
    result = generate(topo, knowledge, catalog)
    spans = result.strategy.spans
    posts = result.strategy.posts

    assert [s.width_mm for s in spans] == [1500, 1500, 1500, 1500]
    assert len(posts) == 5  # 2 node posts + 3 line posts
    assert all(p.sku == "POST-S" for p in posts)
    assert all(p.mounting == "ground" for p in posts)


def test_s01_layout_decision_cites_rules(knowledge, catalog):
    topo = straight_topology(6000)
    result = generate(topo, knowledge, catalog)
    graph = result.graph

    layout_nodes = [n for n in graph.nodes if n.action == "layout_spans"]
    assert len(layout_nodes) == 1
    refs = {
        e.knowledge_ref
        for e in graph.in_edges(layout_nodes[0].id)
        if e.type == "governed_by"
    }
    assert "K-MAXSPAN@v1" in refs
    assert "K-EQUAL@v1" in refs


def test_s02_rejected_alternative_recorded(knowledge, catalog):
    topo = straight_topology(3000)
    result = generate(topo, knowledge, catalog)
    assert [s.width_mm for s in result.strategy.spans] == [1500, 1500]
    layout = next(n for n in result.graph.nodes if n.action == "layout_spans")
    assert layout.payload["alternatives"] == [
        {"widths": [1800, 1200], "rejected_because": "K-EQUAL@v1"}
    ]


def test_s07_cut_plan_kerf_accounting(catalog):
    sem = catalog.product("RAIL-3000").consumption
    assert isinstance(sem, DivisibleLinear)
    pieces = [CutPiece(length_mm=1500, requirement_id=f"r{i}") for i in range(4)]
    plan = plan_cuts("RAIL-3000", sem, pieces)

    # 1500+3+1500 = 3003 > 3000: two 1500s cannot share a 3000 bar
    assert plan.new_bar_count == 4
    for bar in plan.bars:
        assert sum(p.length_mm for p in bar.pieces) + sem.kerf_mm * (len(bar.pieces) - 1) <= bar.stock_length_mm
        assert bar.leftover_mm == 1497
        assert bar.leftover_reusable  # >= 300 min remnant
    assert plan.lp_lower_bound == 3  # honest: heuristic used 4, bound is weaker
    assert not plan.certified_optimal


def test_s08_package_rounding(knowledge, catalog):
    topo = straight_topology(9600)  # ceil(9600/1800) = 6 spans of 1600 -> 48 screws
    result = generate(topo, knowledge, catalog)
    reqs = derive_requirements(result.strategy, knowledge, catalog)
    screws = sum(r.engineering_qty for r in reqs if r.sku == "SCREW-S10")
    assert screws == 48

    bom = fulfill(reqs, catalog)
    line = next(l for l in bom.lines if l.sku == "SCREW-S10")
    assert line.purchase_qty == 3
    assert line.engineering_qty == 48
    assert line.overage_qty == 12


def test_full_spine_traceability(knowledge, catalog):
    topo = straight_topology(6000)
    result = generate(topo, knowledge, catalog)
    reqs = derive_requirements(result.strategy, knowledge, catalog)
    bom = fulfill(reqs, catalog)

    req_by_id = {r.id: r for r in reqs}
    element_ids = set(result.strategy.element_ids())
    for line in bom.lines:
        assert line.pegs, f"BOM line {line.sku} has no pegs"
        for peg in line.pegs:
            req = req_by_id[peg]
            assert req.pegs, f"requirement {req.id} has no element pegs"
            for el in req.pegs:
                assert el in element_ids
                # every element has at least one decision citing it
                assert result.graph.nodes_for_element(el), f"no decision for {el}"


def test_determinism_double_run(knowledge, catalog):
    topo = straight_topology(6000)
    r1 = generate(topo, knowledge, catalog)
    r2 = generate(topo, knowledge, catalog)
    assert r1.strategy.model_dump() == r2.strategy.model_dump()
    assert r1.graph.model_dump() == r2.graph.model_dump()
    assert r1.run.id == r2.run.id

    reqs1 = derive_requirements(r1.strategy, knowledge, catalog)
    reqs2 = derive_requirements(r2.strategy, knowledge, catalog)
    assert [r.model_dump() for r in reqs1] == [r.model_dump() for r in reqs2]
    bom1, bom2 = fulfill(reqs1, catalog), fulfill(reqs2, catalog)
    assert bom1.model_dump() == bom2.model_dump()
