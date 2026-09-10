"""Gate geometry (static/js/gate-geom.js).

A gate on the plan is a station and a width, and until Generate runs the drawing
shows neither: no opening, no swing. "The placement is not sufficient for an
opening fence" — so the plan has to draw the hole and the way it opens, live
from the topology event, for single-swing, double-swing and sliding gates.

That is all coordinate arithmetic, so it is tested here in node rather than by
aiming a mouse at an SVG. Two properties carry the rest:

  * the LEFT/RIGHT convention (left is `(-uy, ux)` in a y-up world) is pinned by
    explicit expected vectors, because a sign flip is invisible in any test that
    only checks perpendicularity — and a flipped sign draws every gate in the
    country opening into the garden instead of out of it;

  * the opening is CLAMPED to the run, exactly as `strategy/generator.py` clamps
    it before raising `gate_past_run_end`. A drawing that did not clamp would
    show a hole the generator refuses to build.

The L-shaped run is not decoration. A gate near a corner is where a naive
implementation silently picks the wrong segment, and it is a shape a
salesperson actually draws.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import {
  ARC_POINTS, SWING_DEG, directionAtStationOn, normalOf, openingEdges,
  pointAtStationOn, screenSideOf, sideProbe, slideArrow, swingLeaf,
} from "./js/gate-geom.js";

const out = {};
out.swing_deg = SWING_DEG;
out.arc_points = ARC_POINTS;

// A straight 20 m run along +x, and an L: 10 m east, then 8 m north.
const straight = [[0, 0], [20000, 0]];
const ell = [[0, 0], [10000, 0], [10000, 8000]];
// the same straight run with a redundant middle vertex — splitting a segment
// must not change a single answer
const split = [[0, 0], [7000, 0], [20000, 0]];

// ---- pointAtStationOn: the clamp ------------------------------------------
out.p_start = pointAtStationOn(straight, 0);
out.p_mid = pointAtStationOn(straight, 5000);
out.p_end = pointAtStationOn(straight, 20000);
out.p_before = pointAtStationOn(straight, -4000);
out.p_past = pointAtStationOn(straight, 99000);
out.p_split_mid = pointAtStationOn(split, 5000);
out.p_ell_corner = pointAtStationOn(ell, 10000);
out.p_ell_up = pointAtStationOn(ell, 14000);
out.p_ell_past = pointAtStationOn(ell, 50000);
out.p_bad_list = pointAtStationOn([[0, 0]], 100);
out.p_null_list = pointAtStationOn(null, 100);
out.p_bad_station = pointAtStationOn(straight, "5000");
out.p_nan = pointAtStationOn(straight, NaN);

// ---- directionAtStationOn: which segment, and floats -----------------------
out.d_straight = directionAtStationOn(straight, 5000);
out.d_split = directionAtStationOn(split, 7000);
out.d_ell_before = directionAtStationOn(ell, 9999);
out.d_ell_corner = directionAtStationOn(ell, 10000);   // ENTERS the second leg
out.d_ell_after = directionAtStationOn(ell, 10001);
out.d_ell_end = directionAtStationOn(ell, 18000);
out.d_ell_past = directionAtStationOn(ell, 99000);
out.d_diagonal = directionAtStationOn([[0, 0], [3000, 4000]], 1000);
out.d_zero_run = directionAtStationOn([[5000, 5000], [5000, 5000]], 0);
out.d_one_point = directionAtStationOn([[0, 0]], 0);

// ---- openingEdges ----------------------------------------------------------
out.op = openingEdges(straight, 5000, 3000);
out.op_at_start = openingEdges(straight, 0, 3000);
// the gate that overruns the end: the generator clamps and warns, so does this
out.op_overrun = openingEdges(straight, 19000, 3000);
out.op_at_end = openingEdges(straight, 20000, 3000);
out.op_before_start = openingEdges(straight, -5000, 3000);
out.op_corner = openingEdges(ell, 9000, 2000);          // spans the corner
out.op_zero_width = openingEdges(straight, 5000, 0);
out.op_negative = openingEdges(straight, 5000, -3000);
out.op_bad_points = openingEdges([[0, 0]], 0, 3000);

// ---- normalOf: the convention, pinned --------------------------------------
out.n_left = normalOf([1, 0], "left");
out.n_right = normalOf([1, 0], "right");
out.n_up_left = normalOf([0, 1], "left");
out.n_up_right = normalOf([0, 1], "right");
out.n_unnormalised = normalOf([3, 0], "left");
out.n_diag = normalOf([0.6, 0.8], "left");
out.n_zero = normalOf([0, 0], "left");
out.n_bad_side = normalOf([1, 0], "sideways");
out.n_bad_dir = normalOf("east", "left");

// ---- sideProbe -------------------------------------------------------------
out.probe_left = sideProbe(straight, 5000, 3000, "left", 2000);
out.probe_right = sideProbe(straight, 5000, 3000, "right", 2000);
out.probe_corner = sideProbe(ell, 9000, 2000, "left", 1414);
out.probe_bad_side = sideProbe(straight, 5000, 3000, "middle", 2000);
out.probe_bad_dist = sideProbe(straight, 5000, 3000, "left", null);
out.probe_bad_width = sideProbe(straight, 5000, 0, "left", 2000);

// ---- swingLeaf: both hinges, both sides ------------------------------------
out.leaf_start_left = swingLeaf(straight, 5000, 3000, "start", "left");
out.leaf_start_right = swingLeaf(straight, 5000, 3000, "start", "right");
out.leaf_end_left = swingLeaf(straight, 5000, 3000, "end", "left");
out.leaf_end_right = swingLeaf(straight, 5000, 3000, "end", "right");
out.leaf_corner = swingLeaf(ell, 9000, 2000, "start", "left");
out.leaf_bad_hinge = swingLeaf(straight, 5000, 3000, "middle", "left");
out.leaf_bad_side = swingLeaf(straight, 5000, 3000, "start", "outward");
out.leaf_clamped_away = swingLeaf(straight, 20000, 3000, "start", "left");
out.leaf_bad_points = swingLeaf([[0, 0]], 0, 3000, "start", "left");

// a DOUBLE gate: two calls, each over its OWN HALF of a 4 m opening, same side
out.double_a = swingLeaf(straight, 5000, 2000, "start", "left");
out.double_b = swingLeaf(straight, 7000, 2000, "end", "left");
// ...and what the same opening looks like as a single leaf, for the contrast
out.single_4m = swingLeaf(straight, 5000, 4000, "start", "left");

// ---- slideArrow ------------------------------------------------------------
out.slide_start = slideArrow(straight, 5000, 3000, "start");
out.slide_end = slideArrow(straight, 5000, 3000, "end");
out.slide_clamped_start = slideArrow(straight, 1000, 3000, "start");
out.slide_clamped_end = slideArrow(straight, 16000, 3000, "end");
out.slide_round_corner = slideArrow(ell, 12000, 4000, "start");
out.slide_bad_dir = slideArrow(straight, 5000, 3000, "backwards");
out.slide_bad_width = slideArrow(straight, 5000, 0, "start");
out.slide_bad_points = slideArrow(null, 5000, 3000, "start");

// ---- screenSideOf: all four, and the y-up / y-down flip --------------------
out.screen_up = screenSideOf([1, 0], "left");     // +y normal -> TOP of drawing
out.screen_down = screenSideOf([1, 0], "right");
out.screen_left = screenSideOf([0, 1], "left");
out.screen_right = screenSideOf([0, 1], "right");
out.screen_west_left = screenSideOf([-1, 0], "left");
out.screen_diag = screenSideOf([1, 1], "left");   // 45 deg: horizontal wins
out.screen_from_run = screenSideOf(directionAtStationOn(ell, 14000), "left");
out.screen_bad_side = screenSideOf([1, 0], "north");
out.screen_bad_dir = screenSideOf([0, 0], "left");

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def gg() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _dot(u: list, v: list) -> float:
    return u[0] * v[0] + u[1] * v[1]


def _sub(p: list, q: list) -> list:
    return [p[0] - q[0], p[1] - q[1]]


def _len(v: list) -> float:
    return math.hypot(v[0], v[1])


# --- the point on the run -----------------------------------------------------

def test_a_station_lands_where_the_arc_length_says(gg):
    assert gg["p_start"] == [0, 0]
    assert gg["p_mid"] == [5000, 0]
    assert gg["p_end"] == [20000, 0]


def test_a_station_off_either_end_is_clamped_not_extrapolated(gg):
    """The drawing may not show fence where there is none. `geom.js` clamps the
    same way, and the two must not disagree about where a gate is."""
    assert gg["p_before"] == [0, 0]
    assert gg["p_past"] == [20000, 0]
    assert gg["p_ell_past"] == [10000, 8000]


def test_a_station_walks_around_a_corner(gg):
    """Station is arc length along the polyline, so 14 m on an L that turns at
    10 m is 4 m up the second leg — not 14 m along the first."""
    assert gg["p_ell_corner"] == [10000, 0]
    assert gg["p_ell_up"] == [10000, 4000]


def test_splitting_a_straight_run_changes_no_answer(gg):
    """An interior vertex on a straight run is a drawing detail. If it moved a
    station, every gate would shift the moment somebody added a corner
    elsewhere on the run."""
    assert gg["p_split_mid"] == gg["p_mid"]
    assert gg["d_split"] == gg["d_straight"]


# --- the direction ------------------------------------------------------------

def test_a_direction_is_a_unit_vector_and_stays_a_float(gg):
    """Rounding a direction to integer millimetres would collapse it to one of
    nine values and quantise every angle on the drawing."""
    assert gg["d_straight"] == [1, 0]
    assert gg["d_diagonal"] == pytest.approx([0.6, 0.8])
    assert _len(gg["d_diagonal"]) == pytest.approx(1.0)


def test_at_a_corner_the_direction_is_the_segment_the_station_enters(gg):
    """Dragging a gate along an L, there must be no station at which the swing
    symbol still belongs to the leg behind it. Right up to the corner it is the
    near leg; at the corner and after, the far one."""
    assert gg["d_ell_before"] == [1, 0]
    assert gg["d_ell_corner"] == [0, 1]
    assert gg["d_ell_after"] == [0, 1]
    assert gg["d_ell_end"] == [0, 1]


def test_a_station_past_the_end_keeps_the_last_real_segment(gg):
    assert gg["d_ell_past"] == [0, 1]


def test_a_run_with_no_length_has_no_direction(gg):
    """Two coincident nodes are not a run. Returning `[0, 0]` here would flow
    into `normalOf` and put a leaf of length zero on the drawing instead of
    nothing at all."""
    assert gg["d_zero_run"] is None
    assert gg["d_one_point"] is None


# --- the opening --------------------------------------------------------------

def test_the_opening_is_the_two_points_the_gate_spans(gg):
    assert gg["op"] == {"a": [5000, 0], "b": [8000, 0],
                        "aStation": 5000, "bStation": 8000}
    assert gg["op_at_start"]["a"] == [0, 0]


def test_an_opening_that_overruns_the_run_is_clamped_like_the_generator(gg):
    """`strategy/generator.py` does `ge = min(gs + opening, length)` and raises
    `gate_past_run_end`. If the drawing did not clamp too, the salesperson would
    be looking at a hole that is not in the plan — the picture and the plan must
    agree about where the hole is, and the warning is what says it is too
    small."""
    assert gg["op_overrun"] == {"a": [19000, 0], "b": [20000, 0],
                                "aStation": 19000, "bStation": 20000}


def test_a_gate_at_the_very_end_is_a_zero_width_opening_not_a_lie(gg):
    """Clamped away entirely. The edges are honest about it — and `swingLeaf`
    refuses to draw a leaf for it rather than inventing one."""
    assert gg["op_at_end"]["a"] == gg["op_at_end"]["b"] == [20000, 0]
    assert gg["leaf_clamped_away"] is None


def test_a_station_before_the_run_starts_at_the_run(gg):
    assert gg["op_before_start"]["aStation"] == 0
    assert gg["op_before_start"]["bStation"] == 3000


def test_an_opening_can_span_a_corner(gg):
    """1 m of the first leg and 1 m of the second. Both edges are on the fence,
    which is the whole reason stations are arc length."""
    assert gg["op_corner"] == {"a": [9000, 0], "b": [10000, 1000],
                               "aStation": 9000, "bStation": 11000}


def test_an_opening_with_no_width_is_refused(gg):
    assert gg["op_zero_width"] is None
    assert gg["op_negative"] is None
    assert gg["op_bad_points"] is None


# --- the left/right convention ------------------------------------------------

def test_left_is_minus_uy_ux_and_it_is_pinned_by_the_vector(gg):
    """The one convention this whole module rests on, asserted as an explicit
    expected vector rather than through a perpendicularity check — a sign flip
    passes every test that only asks "is it at right angles", and draws every
    gate opening into the garden instead of out of it."""
    assert gg["n_left"] == [0, 1]
    assert gg["n_right"] == [0, -1]
    assert gg["n_up_left"] == [-1, 0]
    assert gg["n_up_right"] == [1, 0]
    assert gg["n_diag"] == pytest.approx([-0.8, 0.6])


def test_a_normal_is_a_unit_vector_whatever_length_came_in(gg):
    """Callers hand in a chord, not a normalised direction."""
    assert gg["n_unnormalised"] == [0, 1]


def test_a_normal_refuses_what_it_cannot_turn(gg):
    assert gg["n_zero"] is None
    assert gg["n_bad_side"] is None
    assert gg["n_bad_dir"] is None


# --- reading a stored side back out -------------------------------------------

def test_the_probe_is_the_opening_midpoint_pushed_off_the_fence(gg):
    """This is what turns a stored `left` into "opens toward the house": the
    caller hands this point to a point-in-polygon test over the landmarks. The
    side is stored run-relative because a house can move and a run can be
    redrawn end-for-end; the sentence is re-derived every time."""
    assert gg["probe_left"] == [6500, 2000]
    assert gg["probe_right"] == [6500, -2000]


def test_the_probe_on_a_corner_gate_leaves_the_fence_squarely(gg):
    """Across a corner the opening's own chord is what the leaf and the probe
    hang off — a normal taken from the incoming leg alone would send the probe
    along the outgoing one."""
    p = gg["probe_corner"]
    mid = [9500, 500]
    off = _sub(p, mid)
    assert _len(off) == pytest.approx(1414, abs=2)
    assert _dot(off, [1, 1]) == pytest.approx(0, abs=2)   # perpendicular to the chord
    assert off[0] < 0 and off[1] > 0                      # ...on the left of it


def test_the_probe_refuses_what_it_cannot_place(gg):
    assert gg["probe_bad_side"] is None
    assert gg["probe_bad_dist"] is None
    assert gg["probe_bad_width"] is None


# --- the swing symbol ---------------------------------------------------------

@pytest.mark.parametrize("key,pivot,free,tip", [
    ("leaf_start_left", [5000, 0], [8000, 0], [5000, 3000]),
    ("leaf_start_right", [5000, 0], [8000, 0], [5000, -3000]),
    ("leaf_end_left", [8000, 0], [5000, 0], [8000, 3000]),
    ("leaf_end_right", [8000, 0], [5000, 0], [8000, -3000]),
])
def test_the_leaf_hinges_where_it_is_told_and_opens_the_way_it_is_told(
        gg, key, pivot, free, tip):
    """Four combinations, four different drawings, and the salesperson can only
    tell them apart if each one is right. The hinge picks which edge of the
    opening the leaf turns on; the side picks which way it swings."""
    leaf = gg[key]
    assert leaf["pivot"] == pivot
    assert leaf["free"] == free
    assert leaf["tip"] == tip


def test_the_open_leaf_is_perpendicular_to_the_closed_one(gg):
    """A 90 degree sweep, so the tip is square to the opening and the leaf
    clears the hole it came out of."""
    assert gg["swing_deg"] == 90
    for key in ("leaf_start_left", "leaf_end_right", "leaf_corner"):
        leaf = gg[key]
        closed = _sub(leaf["free"], leaf["pivot"])
        opened = _sub(leaf["tip"], leaf["pivot"])
        assert _dot(closed, opened) == pytest.approx(0, abs=2)
        assert _len(opened) == pytest.approx(_len(closed), abs=2)


def test_the_arc_runs_from_the_closed_leaf_to_the_open_one(gg):
    """The leaf is drawn CLOSED and the arc shows where it goes — the convention
    on every architectural plan. The endpoints are pinned to `free` and `tip`
    rather than recomputed, so rounding cannot open a gap between the leaf and
    its arc."""
    assert gg["arc_points"] == 9
    for key in ("leaf_start_left", "leaf_start_right",
                "leaf_end_left", "leaf_end_right", "leaf_corner"):
        leaf = gg[key]
        arc = leaf["arc"]
        assert len(arc) == gg["arc_points"]
        assert arc[0] == leaf["free"]
        assert arc[-1] == leaf["tip"]
        radius = _len(_sub(leaf["free"], leaf["pivot"]))
        for p in arc:
            assert _len(_sub(p, leaf["pivot"])) == pytest.approx(radius, abs=2)


def test_the_arc_bulges_toward_the_side_the_gate_opens(gg):
    """Halfway round a left-hand swing is 45 degrees off the closed leaf, on the
    left. An arc swept the other way would be the same radius and the same two
    endpoints, and would show the gate opening into the wrong garden."""
    left_mid = gg["leaf_start_left"]["arc"][4]
    right_mid = gg["leaf_start_right"]["arc"][4]
    r45 = 3000 / math.sqrt(2)
    assert left_mid == pytest.approx([5000 + r45, r45], abs=2)
    assert right_mid == pytest.approx([5000 + r45, -r45], abs=2)


def test_a_double_gate_is_two_calls_over_the_two_halves_of_the_opening(gg):
    """Half the opening each, hinged at opposite ends, same side. The two free
    edges land on the SAME point — the middle of the hole, where the leaves meet
    when the gate is shut — and each leaf sweeps only its own half.

    Calling this twice at the FULL width instead (the obvious misreading of "two
    calls, one per edge") draws two leaves through each other, each swinging a
    whole opening's width past the posts. Pinned here so the renderer's
    convention is stated in a test and not only in a doc comment.

    There is deliberately no `doubleSwingLeaves`: a second function would only be
    a second place for the side convention to drift."""
    a, b = gg["double_a"], gg["double_b"]
    assert a["pivot"] == [5000, 0] and b["pivot"] == [9000, 0]
    assert a["free"] == b["free"] == [7000, 0]          # they meet in the middle
    # both swing to the same side, each through its own half-width
    assert a["tip"] == [5000, 2000]
    assert b["tip"] == [9000, 2000]
    # and neither reaches as far as a single leaf over the same opening would
    assert gg["single_4m"]["tip"] == [5000, 4000]


def test_a_leaf_on_a_corner_gate_hangs_off_the_opening_it_closes(gg):
    leaf = gg["leaf_corner"]
    assert leaf["pivot"] == [9000, 0]
    assert leaf["free"] == [10000, 1000]


def test_the_leaf_refuses_what_it_cannot_draw(gg):
    assert gg["leaf_bad_hinge"] is None
    assert gg["leaf_bad_side"] is None
    assert gg["leaf_bad_points"] is None


# --- the sliding gate ---------------------------------------------------------

def test_the_slide_arrow_points_the_way_the_leaf_retracts(gg):
    """A sliding gate needs clear fence to retract into, and the arrow is drawn
    at its TRUE length so it is obvious when there is not enough."""
    assert gg["slide_start"] == {"from": [5000, 0], "to": [2000, 0]}
    assert gg["slide_end"] == {"from": [8000, 0], "to": [11000, 0]}


def test_the_slide_arrow_stops_at_the_end_of_the_fence(gg):
    """Clamped, and therefore visibly short of its own opening width — which is
    exactly the reading the salesperson needs. Shortening it to a token stub
    would hide the one thing this symbol exists to show."""
    short = gg["slide_clamped_start"]
    assert short == {"from": [1000, 0], "to": [0, 0]}
    assert abs(short["to"][0] - short["from"][0]) < 3000

    tail = gg["slide_clamped_end"]
    assert tail == {"from": [19000, 0], "to": [20000, 0]}


def test_the_slide_arrow_follows_the_fence_around_a_corner(gg):
    """Retraction is along the RUN, not along a straight line off into the
    garden: a leaf sliding back past a corner is drawn on the fence it slides
    behind."""
    assert gg["slide_round_corner"] == {"from": [10000, 2000], "to": [8000, 0]}


def test_the_slide_arrow_refuses_what_it_cannot_draw(gg):
    assert gg["slide_bad_dir"] is None
    assert gg["slide_bad_width"] is None
    assert gg["slide_bad_points"] is None


# --- naming a side without a landmark -----------------------------------------

def test_a_side_is_named_by_where_it_points_on_the_drawing(gg):
    """The world is y-UP and the canvas draws y DOWN, so a normal with positive
    y points at the TOP of the drawing. Getting that backwards is a one-word
    error that survives every test which only checks the vector."""
    assert gg["screen_up"] == "up"
    assert gg["screen_down"] == "down"
    assert gg["screen_left"] == "left"
    assert gg["screen_right"] == "right"
    assert gg["screen_west_left"] == "down"
    assert {gg["screen_up"], gg["screen_down"], gg["screen_left"],
            gg["screen_right"]} == {"up", "down", "left", "right"}


def test_the_screen_side_of_a_run_leg_reads_off_that_leg(gg):
    """On the L's second leg, running north, the left side faces west — and on
    a canvas that is never mirrored in RTL, "toward the left of the drawing" is
    a description the reader can verify by looking, in either language."""
    assert gg["screen_from_run"] == "left"


def test_a_diagonal_breaks_its_tie_the_same_way_every_time(gg):
    """The tie has to break somewhere. Breaking it consistently means a gate
    does not flip its description as a run is nudged through the diagonal."""
    assert gg["screen_diag"] == "left"


def test_naming_a_side_refuses_what_it_cannot_name(gg):
    assert gg["screen_bad_side"] is None
    assert gg["screen_bad_dir"] is None
