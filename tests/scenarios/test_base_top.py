"""Base top-line for built bases: slopes, steps, or both (sections-model addendum)."""

from __future__ import annotations

from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    BasePayload,
    BaseTopPayload,
    BaseTopPoint,
    HeightIntentPayload,
)
from fenceai.topology.station import base_top_at, base_top_step_stations
from tests.conftest import add_interval_event, straight_topology


def stepped_wall_topology():
    """6000 mm wall section; top: level 300, STEP to 700 at midpoint, sloping to 900."""
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "base", 0, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(
        topo, "run1", "top", 0, 6000,
        BaseTopPayload(points=[
            BaseTopPoint(pos_permille=0, z_mm=300),
            BaseTopPoint(pos_permille=500, z_mm=300),
            BaseTopPoint(pos_permille=500, z_mm=700),  # step +400 at station 3000
            BaseTopPoint(pos_permille=1000, z_mm=900),
        ]),
    )
    add_interval_event(topo, "run1", "hi", 0, 6000, HeightIntentPayload(height_mm=1800))
    return topo


def test_base_top_interpolation_and_step():
    topo = stepped_wall_topology()
    run = topo.run("run1")
    assert base_top_at(topo, run, 0) == (300, "top")
    assert base_top_at(topo, run, 1500) == (300, "top")   # level stretch
    assert base_top_at(topo, run, 2999) == (300, "top")   # left of the step
    assert base_top_at(topo, run, 3000) == (700, "top")   # AT the step: right side wins
    assert base_top_at(topo, run, 4500) == (800, "top")   # slope 700 -> 900
    assert base_top_at(topo, run, 6000) == (900, "top")
    assert base_top_step_stations(topo, run, 100) == [(3000, 400, "top")]
    assert base_top_step_stations(topo, run, 500) == []   # threshold above the step


def test_step_forces_post_citing_rule(knowledge, catalog):
    result = generate(stepped_wall_topology(), knowledge, catalog)
    s = result.strategy

    step_posts = [p for p in s.posts if p.kind == "transition"]
    assert [p.station_mm for p in step_posts] == [3000]
    # no span crosses the step
    assert all(not (sp.start_station_mm < 3000 < sp.end_station_mm) for sp in s.spans)

    d = result.graph.nodes_for_element(step_posts[0].id)[0]
    refs = {e.knowledge_ref for e in result.graph.in_edges(d.id) if e.type == "governed_by"}
    assert "K-STEP-POST@v1" in refs
    facts = [a for a in result.graph.ancestors(d.id) if a.action == "base_top_step"]
    assert facts and facts[0].payload["step_mm"] == 400


def test_small_step_does_not_force_post(knowledge, catalog):
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "base", 0, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(
        topo, "run1", "top", 0, 6000,
        BaseTopPayload(points=[
            BaseTopPoint(pos_permille=0, z_mm=300),
            BaseTopPoint(pos_permille=500, z_mm=300),
            BaseTopPoint(pos_permille=500, z_mm=350),  # 50 mm < K-STEP-POST's 100
            BaseTopPoint(pos_permille=1000, z_mm=350),
        ]),
    )
    result = generate(topo, knowledge, catalog)
    assert not [p for p in result.strategy.posts if p.kind == "transition"]


def test_panel_heights_and_bottoms_follow_the_top(knowledge, catalog):
    result = generate(stepped_wall_topology(), knowledge, catalog)
    spans = sorted(result.strategy.spans, key=lambda sp: sp.start_station_mm)
    # left of the step: top 300 -> panel 1500; right: 700..900 -> intent minus top
    left = [sp for sp in spans if sp.end_station_mm <= 3000]
    right = [sp for sp in spans if sp.start_station_mm >= 3000]
    assert all(sp.height_mm == 1500 for sp in left)
    assert all(sp.height_mm < 1500 for sp in right)
    # panel bottoms SIT ON the base top (ground 0 + top height)
    assert all(sp.bottom_z_start_mm >= 300 for sp in spans)
    assert left[0].bottom_z_start_mm == 300
    assert right[-1].bottom_z_end_mm == 900  # slope endpoint (1 mm inside rounds up)


def test_concrete_base_top_adjusts_heights_too(knowledge, catalog):
    topo = straight_topology(3000)
    add_interval_event(topo, "run1", "base", 0, 3000, BasePayload(surface="concrete"))
    add_interval_event(
        topo, "run1", "top", 0, 3000,
        BaseTopPayload(points=[
            BaseTopPoint(pos_permille=0, z_mm=200),
            BaseTopPoint(pos_permille=1000, z_mm=200),
        ]),
    )
    result = generate(topo, knowledge, catalog)
    assert all(sp.height_mm == 1600 for sp in result.strategy.spans)  # 1800 - 200


def test_wall_profile_fallback_still_works(knowledge, catalog):
    """S06 semantics unchanged: linear wall_profile is the 2-point special case."""
    from fenceai.topology.model import WallProfilePayload

    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "base", 0, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "wp", 0, 6000,
                       WallProfilePayload(top_z_start_mm=0, top_z_end_mm=400))
    add_interval_event(topo, "run1", "hi", 0, 6000, HeightIntentPayload(height_mm=1800))
    result = generate(topo, knowledge, catalog)
    assert [sp.height_mm for sp in result.strategy.spans] == [1750, 1650, 1550, 1450]
