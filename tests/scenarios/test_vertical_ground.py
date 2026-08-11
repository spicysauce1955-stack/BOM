"""Vertical & extreme terrain: the model must surface unbuildability, never
fabricate it away (foundation §15; user stress-test 2026-08-11)."""

from __future__ import annotations

from fenceai.strategy.generator import generate
from fenceai.topology.model import ElevationSamplePayload, Node, Run, Topology
from fenceai.topology.station import ground_step_stations, ground_z, max_slope_permille
from tests.conftest import add_point_event, straight_topology


def cliff_topology(drop=2000):
    """6 m run with a TRUE vertical ground step at station 3000."""
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "za", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "zb", 3000, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "zc", 3000, ElevationSamplePayload(z_mm=drop))
    add_point_event(topo, "run1", "zd", 6000, ElevationSamplePayload(z_mm=drop))
    return topo


def test_vertical_step_is_visible_not_flat():
    topo = cliff_topology()
    run = topo.run("run1")
    # the cliff is a discontinuity, not a grade — and it must be DETECTED
    assert max_slope_permille(topo, run) == 0
    assert ground_step_stations(topo, run, 100) == [(3000, 2000)]
    # right side wins at the step (half-open, like base-top and base-surface)
    assert ground_z(topo, run, 2999) == 0
    assert ground_z(topo, run, 3000) == 2000
    assert ground_z(topo, run, 3001) == 2000


def test_cliff_forces_post_and_surfaces_unbuildability(knowledge, catalog):
    result = generate(cliff_topology(), knowledge, catalog)
    s = result.strategy

    # a post lands exactly on the cliff; no span crosses it
    step_posts = [p for p in s.posts if p.kind == "transition"]
    assert [p.station_mm for p in step_posts] == [3000]
    assert all(not (sp.start_station_mm < 3000 < sp.end_station_mm) for sp in s.spans)

    # 2000 mm > K-MAX-STEP's 600 -> surfaced as an error citing the rule
    w = next(w for w in s.warnings if w.code == "excessive_step")
    assert w.severity == "error"
    assert w.params["step_mm"] == 2000 and w.params["max_mm"] == 600
    node = result.graph.node(w.decision_ref)
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id) if e.type == "governed_by"}
    assert "K-MAX-STEP@v1" in refs
    facts = [a for a in result.graph.ancestors(node.id) if a.action == "ground_step"]
    assert facts and facts[0].payload["step_mm"] == 2000


def test_buildable_cliff_gets_post_without_alarm(knowledge, catalog):
    """A 300 mm drop: post at the step (>=100 rule), no unbuildability warning."""
    result = generate(cliff_topology(drop=300), knowledge, catalog)
    assert [p.station_mm for p in result.strategy.posts if p.kind == "transition"] == [3000]
    assert not [w for w in result.strategy.warnings if w.code == "excessive_step"]


def test_near_vertical_slope_steps_and_warns(knowledge, catalog):
    """3 m of rise over 100 mm mid-run: stepped mode + per-span unbuildability."""
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "a", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "b", 2950, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "c", 3050, ElevationSamplePayload(z_mm=3000))
    add_point_event(topo, "run1", "d", 6000, ElevationSamplePayload(z_mm=3000))
    result = generate(topo, knowledge, catalog)
    assert all(sp.vertical == "stepped" for sp in result.strategy.spans)
    warnings = [w for w in result.strategy.warnings if w.code == "excessive_step"]
    assert warnings, "1500 mm panel steps must not pass silently"
    assert all(w.params["step_mm"] > 600 for w in warnings)


def test_steep_meets_steep_corner_is_consistent_and_flagged(knowledge, catalog):
    """Two 83% sections meet at a corner: geometry consistent (one corner height),
    each section steps, and the oversized per-span steps are flagged."""
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0, z_mm=0),
               Node(id="n2", x_mm=3000, y_mm=0, z_mm=2500),
               Node(id="n3", x_mm=3000, y_mm=3000, z_mm=0)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")],
    )
    result = generate(topo, knowledge, catalog)
    s = result.strategy
    corner = [p for p in s.posts if p.run_ref == "node:n2"]
    assert len(corner) == 1 and corner[0].ground_z_mm == 2500  # one height, both sections
    assert all(sp.vertical == "stepped" for sp in s.spans)
    flagged = [w for w in s.warnings if w.code == "excessive_step"]
    assert len(flagged) == len(s.spans)  # every 1250 mm step flagged, none silent
