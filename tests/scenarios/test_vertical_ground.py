"""Vertical & extreme terrain: the model must surface unbuildability, never
fabricate it away (foundation §15; user stress-test 2026-08-11)."""

from __future__ import annotations

from fenceai.strategy.generator import generate
from fenceai.topology.model import ElevationSamplePayload, Node, Run, Topology
from fenceai.topology.station import ground_step_stations, ground_z, max_slope_permille
from tests.conftest import add_interval_event, add_point_event, straight_topology


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


def test_stepped_gap_flagged_by_rule(knowledge, catalog):
    """S04 slope (250 mm steps): gaps exceed K-MAX-GAP's 200 mm -> flagged, and the
    downhill posts exceed the 2600 mm product length -> flagged too."""
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))
    result = generate(topo, knowledge, catalog)
    s = result.strategy

    gaps = [w for w in s.warnings if w.code == "excessive_gap"]
    assert len(gaps) == len(s.spans)  # every 250 mm gap > 200 limit
    assert all(w.params["gap_mm"] == 250 for w in gaps)
    assert all(w.severity == "warning" for w in gaps)  # notable, not unbuildable

    lengths = [w for w in s.warnings if w.code == "insufficient_post_length"]
    assert lengths, "downhill posts need 1800+250+600=2650 > 2600 mm POST-S"
    w = lengths[0]
    assert w.params["required_mm"] == 2650 and w.params["available_mm"] == 2600
    node = result.graph.node(w.decision_ref)
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id) if e.type == "governed_by"}
    assert "K-POST-EMBED@v1" in refs


def test_flat_ground_posts_fit(knowledge, catalog):
    result = generate(straight_topology(6000), knowledge, catalog)
    codes = {w.code for w in result.strategy.warnings}
    assert "insufficient_post_length" not in codes  # 1800+600=2400 <= 2600
    assert "excessive_gap" not in codes


def test_gate_on_slope_flagged(knowledge, catalog):
    from fenceai.topology.model import GatePayload

    topo = straight_topology(6000)
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", 6000, ElevationSamplePayload(z_mm=600))
    add_point_event(topo, "run1", "g", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    result = generate(topo, knowledge, catalog)
    w = next(w for w in result.strategy.warnings if w.code == "gate_on_slope")
    assert w.params["slope_permille"] == 100  # 10% across the opening > 5% limit
    node = result.graph.node(w.decision_ref)
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id) if e.type == "governed_by"}
    assert "K-GATE-SLOPE@v1" in refs


def test_gate_on_flat_ground_not_flagged(knowledge, catalog):
    from fenceai.topology.model import GatePayload

    topo = straight_topology(6000)
    add_point_event(topo, "run1", "g", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    result = generate(topo, knowledge, catalog)
    assert not [w for w in result.strategy.warnings if w.code == "gate_on_slope"]


def test_plumb_max_height_checked_when_rule_exists(knowledge, catalog):
    """Max legal height is measured PLUMB: stepped panels exceed at the downhill
    end even when the intent respects the limit. Checked only when a rule says so."""
    from fenceai.knowledge.model import KnowledgeVersion, SetParam

    topo = straight_topology(6000)
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

    # no rule -> no check
    r1 = generate(topo, knowledge, catalog)
    assert not [w for w in r1.strategy.warnings if w.code == "max_height_exceeded"]

    knowledge.versions.append(KnowledgeVersion(
        object_id="K-MAX-HEIGHT", version=1, type="hard_constraint",
        title="Municipal max fence height 2000 mm (plumb)",
        actions=[SetParam(param="max_fence_height_mm", value=2000)],
    ))
    r2 = generate(topo, knowledge, catalog)
    flagged = [w for w in r2.strategy.warnings if w.code == "max_height_exceeded"]
    assert len(flagged) == len(r2.strategy.spans)  # 1800 + 250 step = 2050 > 2000
    assert all(w.params["height_mm"] == 2050 and w.severity == "error" for w in flagged)


def tilted_section(mode="perpendicular", deg=0, slope_z=1000):
    from fenceai.topology.model import PostTiltPayload

    topo = straight_topology(6000)
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", 6000, ElevationSamplePayload(z_mm=slope_z))
    add_interval_event(topo, "run1", "tilt", 0, 6000,
                       PostTiltPayload(mode=mode, tilt_deg=deg))
    return topo


def test_plumb_is_the_default(knowledge, catalog):
    result = generate(straight_topology(6000), knowledge, catalog)
    assert all(p.tilt_deg == 0 for p in result.strategy.posts)


def test_perpendicular_posts_follow_the_slope(knowledge, catalog):
    from tests.conftest import add_interval_event as _  # noqa: F401

    result = generate(tilted_section("perpendicular"), knowledge, catalog)
    s = result.strategy
    line_posts = [p for p in s.posts if p.kind in ("line", "transition")]
    # 1000/6000 gradient = 9.46 degrees -> 9
    assert line_posts and all(p.tilt_deg == 9 for p in line_posts)
    # node (end/corner) posts stay plumb — braced plumb even in tilted fences
    assert all(p.tilt_deg == 0 for p in s.posts if p.run_ref.startswith("node:"))
    # tilted + stepped mismatch surfaced (slope > 15% forces stepped mode)
    assert any(w.code == "tilted_stepped" for w in s.warnings)
    # decision payload carries the tilt
    d = result.graph.nodes_for_element(line_posts[0].id)[0]
    assert d.payload["tilt_deg"] == 9


def test_custom_tilt_and_length_consequence(knowledge, catalog):
    """A 30-degree lean makes the post axis longer: exposed/cos(30) + embed."""
    result = generate(tilted_section("custom", deg=30), knowledge, catalog)
    s = result.strategy
    line_posts = [p for p in s.posts if p.kind == "line"]
    assert all(p.tilt_deg == 30 for p in line_posts)
    lengths = [w for w in s.warnings if w.code == "insufficient_post_length"]
    assert lengths
    # steepest case: exposed plumb 2050 -> axis 2367 + 600 = 2967 > 2600
    assert max(w.params["required_mm"] for w in lengths) == 2967


def test_gate_posts_stay_plumb_in_tilted_section(knowledge, catalog):
    from fenceai.topology.model import GatePayload, PostTiltPayload

    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "tilt", 0, 6000,
                       PostTiltPayload(mode="custom", tilt_deg=20))
    add_point_event(topo, "run1", "g", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    result = generate(topo, knowledge, catalog)
    gate_posts = [p for p in result.strategy.posts if p.kind == "gate"]
    assert gate_posts and all(p.tilt_deg == 0 for p in gate_posts)  # gates hang plumb
    line_posts = [p for p in result.strategy.posts if p.kind == "line"]
    assert all(p.tilt_deg == 20 for p in line_posts)


def test_tilt_clamped_at_45():
    import pytest
    from pydantic import ValidationError

    from fenceai.topology.model import PostTiltPayload

    with pytest.raises(ValidationError):
        PostTiltPayload(mode="custom", tilt_deg=60)
