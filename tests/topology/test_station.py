"""Station/anchor math tests (test-review finding 1)."""

from __future__ import annotations

import pytest

from fenceai.core.errors import InvalidTopology
from fenceai.topology.model import (
    Anchor,
    BasePayload,
    CornerOverridePayload,
    ElevationSamplePayload,
    Node,
    PointEvent,
    Run,
    Topology,
)
from fenceai.topology.station import (
    anchor_station,
    base_surface_at,
    base_transition_stations,
    corner_stations,
    cumulative_stations,
    ground_z,
    make_anchor,
    point_at_station,
    run_length,
    run_points,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology


def l_shape() -> Topology:
    """Two-segment run: (0,0)->(4000,0)->(4000,3000), total 7000."""
    return Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=4000, y_mm=3000)],
        runs=[
            Run(id="run1", start_node_id="n1", end_node_id="n2", interior_vertices=[(4000, 0)])
        ],
    )


def test_run_length_and_stations():
    topo = l_shape()
    run = topo.run("run1")
    assert run_length(topo, run) == 7000
    assert cumulative_stations(run_points(topo, run)) == [0, 4000, 7000]


def test_make_anchor_and_roundtrip():
    topo = l_shape()
    run = topo.run("run1")
    a = make_anchor(topo, run, 5500)  # second segment, offset 1500
    assert a.segment_index == 1
    assert a.offset_mm == 1500
    assert anchor_station(topo, run, a) == 5500


def test_make_anchor_clamps():
    topo = l_shape()
    run = topo.run("run1")
    assert anchor_station(topo, run, make_anchor(topo, run, -50)) == 0
    assert anchor_station(topo, run, make_anchor(topo, run, 99999)) == 7000


def test_anchor_rescales_proportionally_when_its_segment_changes():
    topo = l_shape()
    run = topo.run("run1")
    a = make_anchor(topo, run, 2000)  # midpoint of first segment (0..4000)
    # lengthen first segment: move interior vertex to (6000, 0)
    run.interior_vertices = [(6000, 0)]
    topo.node("n2").x_mm = 6000
    assert anchor_station(topo, run, a) == 3000  # 50% of 6000


def test_anchor_on_unchanged_segment_stays_put():
    topo = l_shape()
    run = topo.run("run1")
    a = make_anchor(topo, run, 5500)  # 1500 into second segment (len 3000)
    # lengthen FIRST segment only; second segment unchanged
    run.interior_vertices = [(6000, 0)]
    topo.node("n2").x_mm = 6000
    # station shifts by the first segment's growth, offset within segment 2 unchanged
    assert anchor_station(topo, run, a) == 6000 + 1500


def test_zero_length_segment_raises():
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=0, y_mm=0)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2")],
    )
    with pytest.raises(InvalidTopology):
        run_length(topo, topo.run("run1"))


def test_anchor_segment_out_of_range_raises():
    topo = l_shape()
    run = topo.run("run1")
    bad = Anchor(segment_index=5, offset_mm=0, seg_len_at_authoring_mm=1000)
    with pytest.raises(InvalidTopology):
        anchor_station(topo, run, bad)


def test_point_at_station():
    topo = l_shape()
    run = topo.run("run1")
    assert point_at_station(topo, run, 0) == (0, 0)
    assert point_at_station(topo, run, 4000) == (4000, 0)
    assert point_at_station(topo, run, 5500) == (4000, 1500)


def test_corner_classification_and_override():
    topo = l_shape()
    run = topo.run("run1")
    assert corner_stations(topo, run) == [4000]  # 90 degree turn
    add_point_event(topo, "run1", "ev_no_corner", 4000, CornerOverridePayload(is_corner=False))
    assert corner_stations(topo, run) == []


def test_shallow_turn_is_not_a_corner():
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=8000, y_mm=500)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2", interior_vertices=[(4000, 0)])],
    )
    assert corner_stations(topo, topo.run("run1")) == []  # ~7 degrees


def test_ground_interpolation():
    topo = straight_topology(6000)
    run = topo.run("run1")
    assert ground_z(topo, run, 3000) == 0  # no samples -> flat 0
    add_point_event(topo, "run1", "ev_z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "ev_z1", 6000, ElevationSamplePayload(z_mm=1000))
    assert ground_z(topo, run, 0) == 0
    assert ground_z(topo, run, 1500) == 250
    assert ground_z(topo, run, 6000) == 1000
    # extrapolation clamps to the outermost sample
    assert ground_z(topo, run, 7000) == 1000


def test_base_surface_and_transitions():
    topo = straight_topology(7000)
    run = topo.run("run1")
    assert base_surface_at(topo, run, 1000) == "soil"
    add_interval_event(topo, "run1", "ev_base", 4000, 7000, BasePayload(surface="masonry_wall"))
    assert base_surface_at(topo, run, 3999) == "soil"
    assert base_surface_at(topo, run, 4000) == "masonry_wall"
    assert base_transition_stations(topo, run) == [4000]


def test_node_elevations_anchor_ground():
    """Ground endpoints come from node z; a shared corner has ONE height fence-wide."""
    from fenceai.topology.station import ground_samples, max_slope_permille

    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0, z_mm=0),
               Node(id="n2", x_mm=4000, y_mm=0, z_mm=500),
               Node(id="n3", x_mm=4000, y_mm=3000, z_mm=500)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")],
    )
    runA, runB = topo.run("runA"), topo.run("runB")
    assert ground_z(topo, runA, 4000) == 500
    assert ground_z(topo, runB, 0) == 500  # same corner, same height, no re-entry
    assert ground_z(topo, runA, 2000) == 250  # interpolates node-to-node
    assert max_slope_permille(topo, runA) == 125  # 500/4000
    assert ground_samples(topo, runB) == [(0, 500), (3000, 500)]


def test_event_sample_overrides_node_at_endpoint():
    """Backwards compatibility: explicit endpoint events beat node elevations."""
    topo = straight_topology(6000)
    topo.node("n1").z_mm = 999  # would be wrong if used
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))
    run = topo.run("run1")
    assert ground_z(topo, run, 0) == 0
    assert ground_z(topo, run, 6000) == 1000
    assert ground_z(topo, run, 3000) == 500


def test_interior_events_combine_with_node_endpoints():
    topo = straight_topology(6000)
    topo.node("n2").z_mm = 600
    add_point_event(topo, "run1", "zm", 3000, ElevationSamplePayload(z_mm=300))
    run = topo.run("run1")
    assert ground_z(topo, run, 0) == 0      # node n1
    assert ground_z(topo, run, 3000) == 300  # event
    assert ground_z(topo, run, 6000) == 600  # node n2
    assert ground_z(topo, run, 4500) == 450
