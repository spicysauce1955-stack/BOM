"""Run geometry (static/js/run-metrics.js).

A street landmark could be typed long before the fence could: select it and its
angle, length and width are number fields. A stretch of fence could only be
dragged until the label happened to read about right — a strange thing to ask of
a salesperson who has just measured the job and knows it is "12.4 m, turning 30
degrees". This module reads a run's length and bearing off its geometry and
writes them back, and because a gate is its own short run between two nodes, the
same two functions type a gate's opening and the angle it hangs at.

Being pure, it is tested here in node rather than by aiming a mouse at an SVG.
Three properties carry the edit surface, and each has a test that fails loudly:
the ROUND TRIP (read a run, write back what was read, get the run), the ANCHOR
(the start stays put and the end moves, or a typed length slides the fence off
the corner it was drawn from), and the CARRY (editing one leg of an L moves the
corner and the far end together, instead of stretching that leg past a corner
that stayed where it was).

Every angle below is pinned to an exact expected value. y is UP on this canvas
and degrees run counter-clockwise from +x, so a sign error is a fence pointing
into the neighbour's garden — and it is the kind of error that passes a test
asserting only that some number came back.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import {
  POLYLINE, STRAIGHT, runFromMetrics, runMetrics, segmentFromMetrics,
  segmentMetrics, shapeOf,
} from "./js/run-metrics.js";

const out = {};

// ---- which pair of functions a run is for ----------------------------------
const east = [[0, 0], [12400, 0]];
const ell = [[0, 0], [10000, 0], [10000, 6000]];
out.shape_straight = shapeOf(east);
out.shape_polyline = shapeOf(ell);
out.shape_one_point = shapeOf([[0, 0]]);
out.shape_empty = shapeOf([]);
out.shape_null = shapeOf(null);
out.shape_not_a_list = shapeOf("12400");
out.shape_bad_point = shapeOf([[0, 0], [1000, "north"]]);
out.shape_nan = shapeOf([[0, 0], [1000, NaN]]);

// ---- reading a straight run ------------------------------------------------
out.east = runMetrics(east);
out.north = runMetrics([[0, 0], [0, 8000]]);
out.south = runMetrics([[0, 0], [0, -3000]]);
out.west = runMetrics([[5000, 0], [0, 0]]);
out.diagonal = runMetrics([[0, 0], [10000, 10000]]);
out.diagonal_down = runMetrics([[0, 0], [-10000, -10000]]);
// the length is rounded per leg, exactly as geom.js runLength rounds it
out.awkward_length = runMetrics([[0, 0], [3000, 4001]]).length_mm;
out.awkward_expected = Math.round(Math.hypot(3000, 4001));

// refusals
out.metrics_polyline = runMetrics(ell);
out.metrics_zero_length = runMetrics([[4000, 4000], [4000, 4000]]);
out.metrics_one_point = runMetrics([[0, 0]]);
out.metrics_null = runMetrics(null);

// ---- writing it back -------------------------------------------------------
out.length_only = runFromMetrics(east, { length_mm: 20000 });
out.angle_only = runFromMetrics(east, { angle_deg: 30 });
out.both = runFromMetrics([[1000, 2000], [1000, 3000]],
                          { length_mm: 5000, angle_deg: 90 });
out.identity_empty = runFromMetrics(east, {});
out.identity_missing = runFromMetrics(east);

// a run drawn from a corner: the corner must not move when a length is typed
const offCorner = [[7000, -2500], [7000 + 12400, -2500]];
out.off_corner = runFromMetrics(offCorner, { length_mm: 18000 });

// a typed angle outside (-180, 180] is the same bearing, and reads back as one
out.typed_190 = runFromMetrics(east, { angle_deg: 190 });
out.typed_190_reread = runMetrics([east[0], runFromMetrics(east, { angle_deg: 190 }).end]);
out.typed_minus_170 = runFromMetrics(east, { angle_deg: -170 });

// a gate is its own short run, so its opening is typed by the same function
const gate = [[3000, 0], [4000, 0]];
out.gate_widened = runFromMetrics(gate, { length_mm: 1200 });

// refusals
out.write_zero = runFromMetrics(east, { length_mm: 0 });
out.write_negative = runFromMetrics(east, { length_mm: -3000 });
out.write_nan = runFromMetrics(east, { length_mm: NaN });
out.write_infinite_angle = runFromMetrics(east, { angle_deg: Infinity });
out.write_text = runFromMetrics(east, { length_mm: "12.4 m" });
out.write_polyline = runFromMetrics(ell, { length_mm: 20000 });
out.write_null_points = runFromMetrics(null, { length_mm: 20000 });

// ---- the round trip --------------------------------------------------------
const trips = [
  [[0, 0], [12400, 0]],
  [[0, 0], [0, -8000]],
  [[1234, -5678], [9876, 4321]],
  [[-2000, 500], [-13750, -6125]],
];
out.roundtrips = trips.map((pts) => {
  const back = runFromMetrics(pts, runMetrics(pts));
  return [pts, [back.start, back.end]];
});

// ---- a run with a corner ---------------------------------------------------
out.seg0 = segmentMetrics(ell, 0);
out.seg1 = segmentMetrics(ell, 1);
out.seg_past_end = segmentMetrics(ell, 2);
out.seg_negative = segmentMetrics(ell, -1);
out.seg_fractional = segmentMetrics(ell, 0.5);
out.seg_null_points = segmentMetrics(null, 0);
// a straight run has exactly one leg, and it is the run
out.seg_straight = segmentMetrics(east, 0);
out.seg_straight_second = segmentMetrics(east, 1);

// ---- editing one leg carries the rest --------------------------------------
out.leg0_longer = segmentFromMetrics(ell, 0, { length_mm: 15000 });
out.leg0_turned = segmentFromMetrics(ell, 0, { angle_deg: 90 });
out.leg1_straightened = segmentFromMetrics(ell, 1, { angle_deg: 0 });
// three legs, so there is a point AFTER the carried corner as well
const zed = [[0, 0], [10000, 0], [10000, 6000], [16000, 6000]];
out.zed = zed;
out.zed_leg0 = segmentFromMetrics(zed, 0, { length_mm: 14000 });
out.zed_leg1_lengths = segmentFromMetrics(zed, 1, { length_mm: 9000 });
out.zed_roundtrip = segmentFromMetrics(zed, 1, segmentMetrics(zed, 1));

out.seg_write_bad_index = segmentFromMetrics(ell, 7, { length_mm: 1000 });
out.seg_write_zero = segmentFromMetrics(ell, 0, { length_mm: 0 });
out.seg_write_nan_angle = segmentFromMetrics(ell, 0, { angle_deg: NaN });

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rm() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _dev(a: list, b: list) -> int:
    """Largest per-coordinate difference between two point lists."""
    assert len(a) == len(b)
    return max(max(abs(p[0] - q[0]), abs(p[1] - q[1])) for p, q in zip(a, b))


# --- which pair of functions a run is for -------------------------------------

def test_a_two_point_run_and_a_cornered_one_are_different_offers(rm):
    """The whole reason this module has two pairs of functions. A two-point run
    has ONE length and ONE angle a person can type; a run with a corner has one
    of each per leg, and a single "angle" field for it would straighten a shape
    somebody drew on the first keystroke."""
    assert rm["shape_straight"] == "straight"
    assert rm["shape_polyline"] == "polyline"


def test_what_is_not_a_run_gets_no_shape(rm):
    """Null rather than a guess: a panel asks `shapeOf` before it draws a single
    row, so an unusable point list has to end the question there."""
    assert rm["shape_one_point"] is None
    assert rm["shape_empty"] is None
    assert rm["shape_null"] is None
    assert rm["shape_not_a_list"] is None
    assert rm["shape_bad_point"] is None
    assert rm["shape_nan"] is None


# --- reading a straight run ---------------------------------------------------

def test_a_run_reads_as_the_two_numbers_a_person_measured(rm):
    assert rm["east"] == {"length_mm": 12400, "angle_deg": 0.0,
                          "start": [0, 0], "end": [12400, 0]}


def test_the_angle_is_counter_clockwise_from_east_on_a_y_up_canvas(rm):
    """Pinned to exact values in all four quadrants because y is UP here
    (`geom.js: toPx` does `OY - y*SCALE`). A sign error passes any test that only
    checks a number came back, and shows up as a fence pointing into the
    neighbour's garden."""
    assert rm["north"]["angle_deg"] == 90.0
    assert rm["south"]["angle_deg"] == -90.0
    assert rm["diagonal"]["angle_deg"] == pytest.approx(45.0, abs=1e-9)
    assert rm["diagonal_down"]["angle_deg"] == pytest.approx(-135.0, abs=1e-9)
    assert rm["diagonal"]["length_mm"] == 14142


def test_due_west_is_positive_180_not_negative_180(rm):
    """(-180, 180] is half-open at the negative end on purpose. Both numbers name
    the same bearing, and a field that flips between them across an edit that
    changed nothing is how a user stops trusting the panel."""
    assert rm["west"]["angle_deg"] == 180.0


def test_the_length_rounds_exactly_the_way_geom_run_length_rounds(rm):
    """`geom.js: runLength` rounds each leg to a whole millimetre and then sums.
    Rounding differently here would show one number in the panel and another on
    the canvas for the same fence, and a salesperson would be right to distrust
    both."""
    assert rm["awkward_length"] == rm["awkward_expected"] == 5001


def test_a_run_with_a_corner_is_refused_by_the_straight_reader(rm):
    """Not an oversight — `segmentMetrics` serves it per leg below. Handing back
    one angle for an L would square it off the moment the field was touched."""
    assert rm["metrics_polyline"] is None


def test_a_degenerate_run_has_no_bearing_to_report(rm):
    """Two nodes on one spot have no direction, and inventing zero would break
    the round trip (writing a zero length back is refused). That run is fixed by
    dragging an end, not by typing."""
    assert rm["metrics_zero_length"] is None
    assert rm["metrics_one_point"] is None
    assert rm["metrics_null"] is None


# --- writing it back ----------------------------------------------------------

def test_typing_a_length_slides_the_end_along_the_bearing_it_had(rm):
    assert rm["length_only"] == {"start": [0, 0], "end": [20000, 0]}


def test_typing_only_an_angle_pivots_the_run_about_its_start(rm):
    """"The user should also be able to change the angle of the fence." An
    omitted length keeps its current value, so this is a pure pivot: 12400 mm
    still, now at 30 degrees."""
    assert rm["angle_only"] == {"start": [0, 0], "end": [10739, 6200]}


def test_typing_both_rebuilds_the_run_from_its_start(rm):
    assert rm["both"] == {"start": [1000, 2000], "end": [1000, 7000]}


def test_an_edit_that_supplies_neither_figure_changes_nothing(rm):
    """The panel opens, the user changes nothing, the panel closes. If this
    drifted, every visit to the fields would move the fence a little."""
    assert rm["identity_empty"] == {"start": [0, 0], "end": [12400, 0]}
    assert rm["identity_missing"] == rm["identity_empty"]


def test_the_start_is_the_anchor_and_the_end_is_what_moves(rm):
    """A person typing a length is saying "this stretch is 18 m", not "centre an
    18 m stretch where this one was". Moving both ends would slide the fence off
    the corner it was drawn from and quietly detach it from the run before it."""
    assert rm["off_corner"]["start"] == [7000, -2500]
    assert rm["off_corner"]["end"] == [25000, -2500]


def test_an_angle_typed_outside_the_range_is_the_same_bearing(rm):
    """190 and -170 are one direction. Both must build the same run, and reading
    that run back must give the canonical -170 rather than echoing what was
    typed — otherwise the field flips on the next open.

    The re-read lands a thousandth of a degree off because the END is stored as
    whole millimetres (ADR-0002) and half a millimetre at 12.4 m is that much
    angle. That is the floor of the storage model, not slack in this module — and
    it is three orders of magnitude smaller than the whole-degree rounding
    `runMetrics` refuses to do."""
    assert rm["typed_190"] == rm["typed_minus_170"]
    assert rm["typed_190_reread"]["angle_deg"] == pytest.approx(-170.0, abs=0.01)


def test_a_gate_opening_is_typed_by_the_same_function(rm):
    """A gate is its own short run between two nodes, so "1.2 m opening" is the
    same operation on the same code. A second implementation for gates is a
    second place for the anchor rule to be got wrong."""
    assert rm["gate_widened"] == {"start": [3000, 0], "end": [4200, 0]}


def test_every_refusal_is_a_null_and_not_a_throw(rm):
    """A panel wiring a keystroke straight into this must be able to ignore a
    half-typed field, not catch an exception per character."""
    assert rm["write_zero"] is None
    assert rm["write_negative"] is None
    assert rm["write_nan"] is None
    assert rm["write_infinite_angle"] is None
    assert rm["write_text"] is None
    assert rm["write_polyline"] is None
    assert rm["write_null_points"] is None


# --- the round trip the edit surface rests on ---------------------------------

def test_reading_a_run_and_writing_back_what_was_read_gives_the_run(rm):
    """The property the whole edit surface rests on. Integer corners mean the
    rebuild lands within a millimetre, never further — and the angle is a float
    precisely so it stays within one: a whole-degree field would move the far end
    of a 20 m run by about 17 cm and this test would say so."""
    for original, rebuilt in rm["roundtrips"]:
        assert _dev(rebuilt, original) <= 1
        assert rebuilt[0] == original[0]     # and the start is EXACT


# --- a run with a corner ------------------------------------------------------

def test_a_cornered_run_offers_one_row_per_leg(rm):
    assert rm["seg0"] == {"length_mm": 10000, "angle_deg": 0.0,
                          "start": [0, 0], "end": [10000, 0]}
    assert rm["seg1"] == {"length_mm": 6000, "angle_deg": 90.0,
                          "start": [10000, 0], "end": [10000, 6000]}


def test_an_index_that_is_not_a_leg_gets_nothing(rm):
    """Three points are two legs. Leg 2 is the corner nobody drew."""
    assert rm["seg_past_end"] is None
    assert rm["seg_negative"] is None
    assert rm["seg_fractional"] is None
    assert rm["seg_null_points"] is None
    assert rm["seg_straight_second"] is None


def test_a_straight_run_is_its_own_first_leg(rm):
    """So a panel that has decided to render rows needs no second code path for
    the two-point case."""
    assert rm["seg_straight"] == rm["east"]


# --- the carry ----------------------------------------------------------------

def test_lengthening_a_leg_carries_every_later_point_with_it(rm):
    """The case a naive implementation gets wrong: it rebuilds the leg and leaves
    the corner where it was, so the first leg stretches PAST the corner and the L
    becomes a Z. The far end must move by exactly the same delta as the corner,
    and every other leg must keep its own length and bearing."""
    assert rm["leg0_longer"] == [[0, 0], [15000, 0], [15000, 6000]]
    assert rm["zed_leg0"] == [[0, 0], [14000, 0], [14000, 6000], [20000, 6000]]
    # asserted as a DELTA as well, because "the far end moved by exactly the
    # amount the leg grew" is the thing the naive version gets wrong
    far_before, far_after = rm["zed"][3], rm["zed_leg0"][3]
    assert [far_after[0] - far_before[0], far_after[1] - far_before[1]] == [4000, 0]


def test_turning_a_leg_swings_the_rest_of_the_run_rigidly(rm):
    """A translation, not a rotation of the tail: leg 1 keeps pointing the way it
    pointed. The user turned one stretch, not the whole fence."""
    assert rm["leg0_turned"] == [[0, 0], [0, 10000], [0, 16000]]


def test_the_points_before_the_edited_leg_never_move(rm):
    """Same reason the start anchors a straight run: the part already drawn from
    a real corner stays on it."""
    assert rm["leg1_straightened"] == [[0, 0], [10000, 0], [16000, 0]]
    assert rm["zed_leg1_lengths"] == [[0, 0], [10000, 0], [10000, 9000], [16000, 9000]]


def test_writing_a_leg_back_unchanged_returns_the_run(rm):
    assert _dev(rm["zed_roundtrip"], rm["zed"]) <= 1


def test_a_bad_leg_edit_is_a_null_and_not_a_mangled_run(rm):
    assert rm["seg_write_bad_index"] is None
    assert rm["seg_write_zero"] is None
    assert rm["seg_write_nan_angle"] is None
