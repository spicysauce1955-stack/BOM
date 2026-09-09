"""Landmark geometry (static/js/landmark-shape.js).

"The property" step asks for the things that are NOT the fence: the house, the
street it faces, a tree in the way. Each is drawn with a different gesture —
a house walked corner by corner, a street dragged along its centre line, a tree
dragged out from its trunk — and each of those is a coordinate transform with
an inverse, because the angle/length/width panel has to read a stored point
list back into numbers a person can retype.

That makes the whole surface pure, so it is tested here in node rather than by
aiming a mouse at an SVG. The property the edit panel rests on is the ROUND
TRIP: reading a rectangle and rebuilding it from what was read must give back
the rectangle, or a user who opens the panel and changes nothing still moves
their street.
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
  DEFAULT_WIDTH_MM, GESTURE, LANDMARK_KINDS, MIN_MM, OTHER_KINDS, PRIMARY_KINDS,
  TREE_SIDES, bandRect, circleFromMetrics, circleMetrics, circlePolygon,
  gestureFor, metricsKind, polygonFromClicks, rectFromMetrics, rectMetrics,
  shapeFor,
} from "./js/landmark-shape.js";

const out = {};
out.kinds = LANDMARK_KINDS;
out.primary = PRIMARY_KINDS;
out.other_kinds = OTHER_KINDS;
out.gestures = LANDMARK_KINDS.map(gestureFor);
out.gesture_unknown = gestureFor("helicopter-pad");
out.min_mm = MIN_MM;
out.tree_sides = TREE_SIDES;
out.default_widths = DEFAULT_WIDTH_MM;

// ---- one gesture per kind --------------------------------------------------
out.house = shapeFor("house", [0, 0], [8000, 6000]);
out.pool = shapeFor("pool", [0, 0], [8000, 6000]);
out.pool_backwards = shapeFor("pool", [8000, 6000], [0, 0]);
out.boundary = shapeFor("boundary", [0, 0], [8000, 6000]);
out.other = shapeFor("other", [0, 0], [8000, 6000]);
out.street = shapeFor("street", [0, 0], [20000, 0]);
out.sidewalk = shapeFor("sidewalk", [0, 0], [10000, 0]);
out.tree = shapeFor("tree", [1000, 2000], [1000, 3500]);
out.thin_street = shapeFor("street", [0, 0], [9000, 40]);
// the box gesture: the drag states the width itself, so no default is imposed
out.street_box = shapeFor("street", [0, 0], [20000, 4000]);
out.street_box_metrics = rectMetrics(out.street_box.points);
// ...and a box dragged UP the page is a street running up the page, not a
// two-metre street thirty metres wide
out.street_box_tall = rectMetrics(shapeFor("street", [0, 0], [3000, 18000]).points);
out.sidewalk_box_metrics = rectMetrics(shapeFor("sidewalk", [0, 0], [12000, 1200]).points);

// refusals
out.tiny = shapeFor("pool", [0, 0], [100, 100]);
out.tiny_tree = shapeFor("tree", [0, 0], [200, 200]);
out.no_drag = shapeFor("pool", [0, 0], null);
out.unknown = shapeFor("swimming-pool", [0, 0], [5000, 5000]);

// ---- the band's corner order IS the contract -------------------------------
const band = bandRect([0, 0], [20000, 0], 4000);
out.band = band;
const seg = (a, b) => Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]));
out.band_len_axis = seg(band[0], band[1]);
out.band_width_axis = seg(band[1], band[2]);
out.band_zero_length = bandRect([5000, 5000], [5000, 5000], 4000);

// ---- rectMetrics / rectFromMetrics -----------------------------------------
const band45 = bandRect([0, 0], [10000, 10000], 3000);
out.band45 = band45;
out.band45_metrics = rectMetrics(band45);
out.band45_back = rectFromMetrics(rectMetrics(band45));

out.bbox_metrics = rectMetrics(out.pool.points);
out.bbox_back = rectFromMetrics(rectMetrics(out.pool.points));
out.bbox_down = shapeFor("pool", [0, 6000], [8000, 0]).points;
out.bbox_down_back = rectFromMetrics(rectMetrics(shapeFor("pool", [0, 6000], [8000, 0]).points));

// angle normalisation: the SAME rectangle drawn in the opposite direction
out.band_forward_angle = rectMetrics(bandRect([0, 0], [20000, 0], 4000)).angle_deg;
out.band_reverse_angle = rectMetrics(bandRect([20000, 0], [0, 0], 4000)).angle_deg;
out.band_down_left_angle = rectMetrics(bandRect([10000, 10000], [0, 0], 3000)).angle_deg;

// an edited width writes back a rectangle on the same centre line
out.widened = rectFromMetrics({ ...rectMetrics(band), width_mm: 6000 });
out.widened_metrics = rectMetrics(out.widened);

// refusals: a trapezoid, a skewed parallelogram, a 5-gon, a line
out.trapezoid = rectMetrics([[0, 0], [10000, 0], [8000, 5000], [2000, 5000]]);
out.parallelogram = rectMetrics([[0, 0], [10000, 0], [12000, 4000], [2000, 4000]]);
out.five_points = rectMetrics([[0, 0], [5000, 0], [6000, 4000], [2000, 5000], [0, 3000]]);
out.flat_rect = rectMetrics([[0, 0], [10000, 0], [10000, 0], [0, 0]]);

// ---- circles ---------------------------------------------------------------
const tree = circlePolygon([1000, 2000], 1500);
out.tree_points = tree.length;
out.tree_metrics = circleMetrics(tree);
out.tree_back = circleFromMetrics([1000, 2000], 1500);
out.tree_roundtrip_same = JSON.stringify(tree) === JSON.stringify(out.tree_back);
out.hexagon = circleMetrics(circlePolygon([0, 0], 1500, 6));
out.ellipse = circleMetrics(circlePolygon([0, 0], 1500).map(([x, y]) => [x * 2, y]));
out.tiny_radius = circleFromMetrics([0, 0], 0);

// ---- the house, click by click ---------------------------------------------
out.clicks = polygonFromClicks([[0, 0], [8000, 0], [8000, 6000], [0, 6000]]);
out.clicks_double = polygonFromClicks(
  [[0, 0], [0, 100], [8000, 0], [8000, 6000], [0, 6000]]);
out.clicks_closing = polygonFromClicks(
  [[0, 0], [8000, 0], [8000, 6000], [0, 6000], [50, 120]]);
out.clicks_two = polygonFromClicks([[0, 0], [8000, 0]]);
out.clicks_collapsed = polygonFromClicks([[0, 0], [100, 0], [200, 0]]);
out.clicks_l_shaped = polygonFromClicks(
  [[0, 0], [8000, 0], [8000, 3000], [4000, 3000], [4000, 6000], [0, 6000]]);

// ---- which panel a landmark offers -----------------------------------------
out.metrics_kind_rect = metricsKind({ kind: "street", points: band });
out.metrics_kind_circle = metricsKind({ kind: "tree", points: tree });
out.metrics_kind_none = metricsKind({ kind: "house", points: out.clicks_l_shaped.points });
out.metrics_kind_empty = metricsKind(null);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def ls() -> dict:
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


# --- the registry -------------------------------------------------------------

def test_every_kind_has_a_gesture(ls):
    """A kind with no gesture is a toolbar button that does nothing when
    pressed, and the failure shows up in a browser rather than here."""
    assert set(ls["gestures"]) <= {"polygon", "band", "rect", "circle"}
    assert dict(zip(ls["kinds"], ls["gestures"])) == {
        "house": "polygon", "street": "band", "sidewalk": "band",
        "pool": "rect", "tree": "circle", "boundary": "rect", "other": "rect",
    }


def test_the_two_kinds_every_job_has_are_the_two_buttons(ls):
    """A toolbar with seven buttons is a toolbar nobody reads. The split is
    about frequency, and together the halves must still be the whole registry —
    a kind in neither list is unreachable from the UI."""
    assert ls["primary"] == ["house", "street"]
    assert ls["primary"] + ls["other_kinds"] == ls["kinds"]


def test_an_unknown_kind_still_draws_something(ls):
    """`gestureFor` is lenient so a renderer that has not heard of a new kind
    still puts a box on the screen; `shapeFor` is the strict one, because that
    is where an unknown kind would otherwise reach the API and 422 far from the
    gesture that caused it."""
    assert ls["gesture_unknown"] == "rect"
    assert ls["unknown"] is None


# --- what each gesture makes --------------------------------------------------

def test_a_house_is_not_dragged(ls):
    """A building has as many corners as it has. A drag can only ever describe
    four of them, so the house tool collects clicks and `shapeFor` refuses it
    outright rather than quietly handing back a bounding box that squares off
    an L-shaped house nobody drew that way."""
    assert ls["house"] is None


def test_a_box_kind_is_the_rectangle_the_drag_spanned(ls):
    assert ls["pool"]["closed"] is True
    assert ls["pool"]["points"] == [[0, 0], [8000, 0], [8000, 6000], [0, 6000]]
    assert ls["boundary"]["points"] == ls["pool"]["points"]
    assert ls["other"]["points"] == ls["pool"]["points"]


def test_a_box_dragged_backwards_is_the_same_shape(ls):
    """A person drags from whichever corner they started at. The rectangle must
    not depend on which one — the corner order differs, the outline does not."""
    assert ls["pool_backwards"]["closed"] is True
    assert set(map(tuple, ls["pool_backwards"]["points"])) == \
           set(map(tuple, ls["pool"]["points"]))


def test_a_street_is_a_rectangle_because_a_road_has_width(ls):
    """A bare centre line reads as "the fence runs to here", not as the road
    the salesperson pointed at. 4 m is a residential carriageway; being roughly
    right beats being zero, because a zero-width street draws as a line and
    then the width field has nothing to edit."""
    assert ls["street"]["closed"] is True
    assert ls["street"]["points"] == [[0, 2000], [20000, 2000],
                                      [20000, -2000], [0, -2000]]
    assert ls["sidewalk"]["points"] == [[0, 750], [10000, 750],
                                        [10000, -750], [0, -750]]
    assert ls["default_widths"] == {"street": 4000, "sidewalk": 1500}


def test_a_street_dragged_as_a_box_takes_its_width_from_the_drag(ls):
    """"The street has a fixed width and is not easy to place."

    So a band has two gestures now, and this is the one the complaint asked
    for: drag the box the road occupies and BOTH numbers come out of the one
    drag. `DEFAULT_WIDTH_MM` is never imposed on a drag that stated a width.
    """
    assert ls["street_box"]["closed"] is True
    assert ls["street_box_metrics"]["length_mm"] == 20000
    assert ls["street_box_metrics"]["width_mm"] == 4000
    assert ls["street_box_metrics"]["angle_deg"] == 0
    assert ls["sidewalk_box_metrics"] == {
        "center": [6000, 600], "angle_deg": 0,
        "length_mm": 12000, "width_mm": 1200}


def test_a_box_is_wound_long_side_first_whichever_way_it_was_dragged(ls):
    """The corner ORDER is what `rectMetrics` reads length and width off, so a
    box wound the other way reports an 18 m street as 3 m long and 18 m wide —
    and the panel then offers those two numbers to be typed the wrong way
    round. The winding is the fix; the outline is identical either way."""
    assert ls["street_box_tall"]["length_mm"] == 18000
    assert ls["street_box_tall"]["width_mm"] == 3000
    assert ls["street_box_tall"]["angle_deg"] == 90


def test_a_street_dragged_straight_along_one_axis_still_counts(ls):
    """The minimum applies per axis, not to both at once: a street IS a long
    thin thing, and requiring 300 mm of drift in the short direction would
    refuse the most ordinary gesture in this tool."""
    assert ls["thin_street"] is not None
    assert len(ls["thin_street"]["points"]) == 4
    # and THIS is the branch the default width exists for: the drag stated no
    # width, so one is supplied rather than storing a 40 mm sliver
    assert ls["default_widths"]["street"] == 4000


def test_a_tree_is_dragged_out_from_its_trunk(ls):
    """The press point is the trunk and the distance dragged is the radius —
    a tree has no corner to start a box from."""
    assert ls["tree"]["closed"] is True
    assert len(ls["tree"]["points"]) == ls["tree_sides"] == 16
    # first vertex at angle 0, radius 1500 from the press point
    assert ls["tree"]["points"][0] == [2500, 2000]


def test_a_stray_click_leaves_no_invisible_landmark(ls):
    """A tool is active, somebody clicks. Without this there is a 3 mm landmark
    on the drawing that nobody can see and the office person then has to ask
    about."""
    assert ls["tiny"] is None
    assert ls["tiny_tree"] is None
    assert ls["no_drag"] is None
    assert ls["min_mm"] == 300


# --- the band's corner order --------------------------------------------------

def test_the_band_puts_the_length_first_and_the_width_second(ls):
    """Corner order is the contract every other function here reads through:
    p0->p1 is the length axis, p1->p2 the width. Without it `rectMetrics` would
    have to guess which pair of sides a user calls "the length of the road",
    and would guess differently for a road that happens to be wider than it is
    long."""
    assert ls["band"] == [[0, 2000], [20000, 2000], [20000, -2000], [0, -2000]]
    assert ls["band_len_axis"] == 20000
    assert ls["band_width_axis"] == 4000


def test_a_zero_length_band_is_not_a_road(ls):
    assert ls["band_zero_length"] is None


# --- the round trip the edit panel rests on -----------------------------------

def test_a_rotated_band_survives_being_read_and_rebuilt(ls):
    """Open the panel, change nothing, close it. If this drifts, every visit to
    the angle/length/width fields moves the street a little."""
    m = ls["band45_metrics"]
    assert m["angle_deg"] == pytest.approx(45.0, abs=0.01)
    assert m["length_mm"] == pytest.approx(14142, abs=1)
    assert m["width_mm"] == pytest.approx(3000, abs=1)
    assert m["center"] == [5000, 5000]
    # NUMERIC_TOLERANCE_MM: the corners are integers, so a rebuild lands within
    # a millimetre of them, never further.
    assert _dev(ls["band45_back"], ls["band45"]) <= 1


def test_an_axis_aligned_box_reads_as_the_box_it_is(ls):
    assert ls["bbox_metrics"] == {"center": [4000, 3000], "angle_deg": 0.0,
                                  "length_mm": 8000, "width_mm": 6000}
    assert _dev(ls["bbox_down_back"], ls["bbox_down"]) <= 1


def test_a_rebuilt_box_is_the_same_box_even_when_it_winds_the_other_way(ls):
    """Four numbers cannot say which way round a rectangle was traversed, and
    four numbers are what the panel edits. A bbox drag that went UP the page
    comes back with the same four corners in the opposite traversal — the same
    outline, drawn identically by a closed path — rather than a flipped shape.
    Asserted, not merely tolerated, because a later "canonicalise the winding"
    change must not turn this into a silent reflection."""
    assert ls["bbox_back"] != ls["pool"]["points"]
    assert ls["bbox_back"] == list(reversed(ls["pool"]["points"]))


def test_the_same_rectangle_drawn_backwards_reads_as_the_same_angle(ls):
    """A rectangle at 190 degrees and one at 10 are the same rectangle. Showing
    a user 190 in a field they then re-type is how a shape flips when nothing
    was changed, so the angle is normalised into [0, 180)."""
    assert ls["band_forward_angle"] == ls["band_reverse_angle"] == 0.0
    assert ls["band_down_left_angle"] == pytest.approx(45.0, abs=0.01)
    assert 0 <= ls["band_down_left_angle"] < 180


def test_typing_a_new_width_keeps_the_centre_line(ls):
    """What the panel is for: the road stays where it is and gets wider."""
    assert ls["widened_metrics"]["width_mm"] == 6000
    assert ls["widened_metrics"]["length_mm"] == 20000
    assert ls["widened_metrics"]["center"] == [10000, 0]
    assert ls["widened_metrics"]["angle_deg"] == 0.0


# --- what is not a rectangle --------------------------------------------------

def test_a_four_point_shape_that_is_not_a_rectangle_is_refused(ls):
    """A trapezoid and a skewed parallelogram both have four corners. Reading
    either as {angle, length, width} would square it off the moment a user
    touched a field — an edit that changes the shape without being asked for is
    worse than no panel at all."""
    assert ls["trapezoid"] is None
    assert ls["parallelogram"] is None


def test_a_polygon_with_the_wrong_number_of_corners_is_refused(ls):
    assert ls["five_points"] is None
    assert ls["flat_rect"] is None      # a line with four points is not a box


# --- circles ------------------------------------------------------------------

def test_a_tree_reads_back_as_a_circle(ls):
    """There is one shape in the storage model, so a tree is a polygon that
    READS as a circle. If that reading drifts, the radius field starts editing
    a number that is not the tree's radius."""
    assert ls["tree_points"] == 16
    assert ls["tree_metrics"] == {"center": [1000, 2000], "radius_mm": 1500}
    assert ls["tree_roundtrip_same"] is True


def test_a_shape_that_is_not_round_is_not_a_circle(ls):
    """A hexagon is a shape somebody drew on purpose, and an ellipse is not a
    tree. Both would otherwise be offered a radius field that squashes them
    round on the first keystroke."""
    assert ls["hexagon"] is None
    assert ls["ellipse"] is None
    assert ls["tiny_radius"] is None


# --- the house, click by click ------------------------------------------------

def test_clicks_become_a_closed_shape(ls):
    assert ls["clicks"] == {"points": [[0, 0], [8000, 0], [8000, 6000], [0, 6000]],
                            "closed": True}
    assert len(ls["clicks_l_shaped"]["points"]) == 6


def test_a_double_click_while_placing_does_not_make_two_corners(ls):
    """Two vertices on one corner are a zero-length wall that every consumer
    downstream then has to special-case."""
    assert ls["clicks_double"]["points"] == ls["clicks"]["points"]


def test_the_last_click_back_at_the_start_closes_rather_than_adds(ls):
    """That click is the "close it" gesture. Keeping it would put a corner a
    few centimetres from the first one and leave a sliver wall in the shape."""
    assert ls["clicks_closing"]["points"] == ls["clicks"]["points"]


def test_a_shape_with_fewer_than_three_corners_is_refused(ls):
    """`Landmark`'s own validator refuses a closed shape with fewer than three
    points. Getting a 422 back after drawing is worse than the gesture quietly
    needing one more corner."""
    assert ls["clicks_two"] is None
    assert ls["clicks_collapsed"] is None


# --- which panel a landmark offers --------------------------------------------

def test_metrics_kind_says_which_fields_a_landmark_has(ls):
    """A click-built house has no angle, length or width to type. Inventing a
    bounding box for the panel would silently square off the shape somebody
    drew the moment they touched a field, so the answer is "none"."""
    assert ls["metrics_kind_rect"] == "rect"
    assert ls["metrics_kind_circle"] == "circle"
    assert ls["metrics_kind_none"] == "none"
    assert ls["metrics_kind_empty"] == "none"
