"""Golden scenarios S01-S06 (docs/scenarios/golden-scenarios.md)."""

from __future__ import annotations

from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    BasePayload,
    ElevationSamplePayload,
    Node,
    Run,
    Topology,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology


def test_s01_straight_fence(knowledge, catalog):
    result = generate(straight_topology(6000), knowledge, catalog)
    s = result.strategy
    assert [sp.width_mm for sp in s.spans] == [1500, 1500, 1500, 1500]
    assert len(s.posts) == 5
    assert all(p.sku == "POST-S" for p in s.posts)
    layout = next(n for n in result.graph.nodes if n.action == "layout_spans")
    refs = {e.knowledge_ref for e in result.graph.in_edges(layout.id) if e.type == "governed_by"}
    assert {"K-MAXSPAN@v1", "K-EQUAL@v1"} <= refs


def test_s02_nominal_alternative_recorded(knowledge, catalog):
    result = generate(straight_topology(3000), knowledge, catalog)
    assert [sp.width_mm for sp in result.strategy.spans] == [1500, 1500]
    layout = next(n for n in result.graph.nodes if n.action == "layout_spans")
    assert layout.payload["alternatives"] == [
        {"widths": [1800, 1200], "rejected_because": "K-EQUAL@v1"}
    ]


def l_shape_topology() -> Topology:
    return Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=4000, y_mm=0, kind="junction"),
            Node(id="n3", x_mm=4000, y_mm=3000),
        ],
        runs=[
            Run(id="runA", start_node_id="n1", end_node_id="n2"),
            Run(id="runB", start_node_id="n2", end_node_id="n3"),
        ],
    )


def test_s03_corner_shares_one_post(knowledge, catalog):
    result = generate(l_shape_topology(), knowledge, catalog)
    s = result.strategy
    corner_posts = [p for p in s.posts if p.run_ref == "node:n2"]
    assert len(corner_posts) == 1  # one physical post for both runs
    assert corner_posts[0].kind == "corner"
    # runA: 4000 -> 3 spans; runB: 3000 -> 2 spans
    assert sorted(sp.width_mm for sp in s.spans if sp.run_ref == "runA") == [1333, 1333, 1334]
    assert sorted(sp.width_mm for sp in s.spans if sp.run_ref == "runB") == [1500, 1500]
    # 3 node posts + 2 interior on runA + 1 interior on runB
    assert len(s.posts) == 6
    # corner post decision cites the topology node
    decisions = result.graph.nodes_for_element(corner_posts[0].id)
    assert decisions
    fact_ancestors = [
        a for d in decisions for a in result.graph.ancestors(d.id) if a.action == "topology_node"
    ]
    assert any(a.payload.get("node_id") == "n2" for a in fact_ancestors)


def test_s04_uphill_stepped(knowledge, catalog):
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "ev_z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "ev_z1", 6000, ElevationSamplePayload(z_mm=1000))
    result = generate(topo, knowledge, catalog)
    s = result.strategy

    assert all(sp.vertical == "stepped" for sp in s.spans)
    vert = next(n for n in result.graph.nodes if n.action == "choose_vertical_mode")
    refs = {e.knowledge_ref for e in result.graph.in_edges(vert.id) if e.type == "governed_by"}
    assert "K-STEP-SLOPE@v1" in refs
    # per-span step data and per-post ground elevation recorded
    assert [sp.bottom_z_start_mm for sp in s.spans] == [0, 250, 500, 750]
    assert [sp.bottom_z_end_mm for sp in s.spans] == [250, 500, 750, 1000]
    stations = {p.station_mm: p for p in s.posts if p.kind == "line"}
    assert stations[1500].ground_z_mm == 250
    assert stations[3000].ground_z_mm == 500
    # stepped panels: rails cut to plan width, not slope length
    assert all(sp.rail_cut_basis == "width" for sp in s.spans)
    assert all(sp.slope_len_mm == sp.width_mm for sp in s.spans)


def test_s05_base_transition(knowledge, catalog):
    topo = straight_topology(7000)
    add_interval_event(topo, "run1", "ev_base", 4000, 7000, BasePayload(surface="masonry_wall"))
    result = generate(topo, knowledge, catalog)
    s = result.strategy

    transition = [p for p in s.posts if p.kind == "transition"]
    assert len(transition) == 1
    assert transition[0].station_mm == 4000
    # segments laid out independently: [0,4000] -> 3 spans, [4000,7000] -> 2 spans
    widths = sorted(sp.width_mm for sp in s.spans)
    assert widths == [1333, 1333, 1334, 1500, 1500]
    # mounting per side
    by_station = {p.station_mm: p for p in s.posts if p.run_ref == "run1"}
    assert by_station[1334].sku == "POST-S" and by_station[1334].mounting == "ground"
    assert by_station[4000].sku == "POST-M" and by_station[4000].mounting == "masonry"
    assert by_station[5500].sku == "POST-M"
    # masonry mounting decision cites K-MASONRY
    d = result.graph.nodes_for_element(by_station[4000].id)[0]
    refs = {e.knowledge_ref for e in result.graph.in_edges(d.id) if e.type == "governed_by"}
    assert "K-MASONRY@v1" in refs
