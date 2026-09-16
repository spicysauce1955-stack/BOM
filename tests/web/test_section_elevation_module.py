"""The section thumbnail's geometry (static/js/section-elevation.js).

A card on the office job screen shows one stretch from the side: what it stands
on, and the fence on top of it. The arithmetic is a pure function of the
structure report's own numbers, so it is tested here rather than only by
looking at a drawing in a browser.

The case that matters is section A of the demo job, and it is why the card
exists at all: its wall steps up 1120 mm at 4.0 m and the fence top does not
follow, so three of its six bays carry NO FENCE. A thumbnail that drew those as
zero-height boxes would render the most important fact about the job as nothing
at all.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { bayRects } from "./js/section-elevation.js";

const out = {};

// Section A of the demo job, verbatim from the generated run:
// three bays of 860 mm fence on a 940 mm wall, then the wall steps to 2060 and
// the fence stops.
const A = {
  run_id: "run1", tag: "A", length_mm: 8000,
  bays: [
    {tag:"A/B1", element_id:"span@run1:0-1334",    start_station_mm:0,    width_mm:1334, height_mm:860, bottom_z_start_mm:940,  bottom_z_end_mm:940},
    {tag:"A/B2", element_id:"span@run1:1334-2667", start_station_mm:1334, width_mm:1333, height_mm:860, bottom_z_start_mm:940,  bottom_z_end_mm:940},
    {tag:"A/B3", element_id:"span@run1:2667-4000", start_station_mm:2667, width_mm:1333, height_mm:860, bottom_z_start_mm:940,  bottom_z_end_mm:940},
    {tag:"A/B4", element_id:"span@run1:4000-5334", start_station_mm:4000, width_mm:1334, height_mm:0,   bottom_z_start_mm:2060, bottom_z_end_mm:2060},
    {tag:"A/B5", element_id:"span@run1:5334-6667", start_station_mm:5334, width_mm:1333, height_mm:0,   bottom_z_start_mm:2060, bottom_z_end_mm:2060},
    {tag:"A/B6", element_id:"span@run1:6667-8000", start_station_mm:6667, width_mm:1333, height_mm:0,   bottom_z_start_mm:2060, bottom_z_end_mm:2060},
  ],
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 8000, z_mm: 0}],
};

const a = bayRects(A, 300, 80);
out.a_count = a.bays.length;
out.a_tags = a.bays.map((b) => b.tag);
out.a_first_x = a.bays[0].x;
out.a_pad = a.pad;
out.a_last_right = Math.round(a.bays[5].x + a.bays[5].w);
out.a_inner_right = Math.round(a.width - a.pad);
// widths in proportion to the bays they came from: B1 is 1334 of 8000
out.a_first_w_permille = Math.round((a.bays[0].w / (a.width - a.pad * 2)) * 1000);
out.a_empty = a.bays.map((b) => b.empty);
out.a_panel_h = a.bays.map((b) => Math.round(b.panelH));
out.a_ascending_x = a.bays.every((b, i, all) => i === 0 || b.x >= all[i - 1].x);
out.a_ground_points = a.ground.length;
out.a_element_ids = a.bays.map((b) => b.elementId);

// Bays of deliberately unequal width: 2000 and 500 of a 2500 mm stretch. The
// old fixture used 1334 of 8000, which rounds to 167 thousandths — and so does
// one-sixth of the drawing, so "the bays are not equal" could not be told from
// "six equal boxes" through a rounded ratio.
const UNEVEN = {
  run_id: "run7", tag: "U", length_mm: 2500,
  bays: [
    {tag:"U/B1", element_id:"u1", start_station_mm:0,    width_mm:2000, height_mm:900, bottom_z_start_mm:0, bottom_z_end_mm:0},
    {tag:"U/B2", element_id:"u2", start_station_mm:2000, width_mm:500,  height_mm:900, bottom_z_start_mm:0, bottom_z_end_mm:0},
  ],
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 2500, z_mm: 0}],
};
const uneven = bayRects(UNEVEN, 250, 60);
out.uneven_w_ratio = Math.round((uneven.bays[0].w / uneven.bays[1].w) * 100) / 100;

// A base that SLOPES: the panel must sit on the higher end, or a steep bay
// draws its panel through the ground at one end.
const SLOPED = {
  run_id: "run8", tag: "S", length_mm: 1000,
  bays: [{tag:"S/B1", element_id:"s1", start_station_mm:0, width_mm:1000,
          height_mm:500, bottom_z_start_mm:0, bottom_z_end_mm:600}],
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 1000, z_mm: 0}],
};
out.sloped_bottom = bayRects(SLOPED, 200, 60).bays[0].bottomZMm;

// A perfectly flat stretch: every z equal, so the vertical span is zero and a
// naive scale divides by it.
const FLAT = {
  run_id: "run6", tag: "F", length_mm: 4000,
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 4000, z_mm: 0}],
};
out.flat_finite = bayRects(FLAT, 200, 60).ground.every(
  (p) => Number.isFinite(p.x) && Number.isFinite(p.y));

// A zero-length stretch that nonetheless has a bay — the case that actually
// divides by the length. The empty-everything fixture below never does.
const ZERO_WITH_BAY = {
  run_id: "run5", tag: "E", length_mm: 0,
  bays: [{tag:"E/B1", element_id:"e1", start_station_mm:0, width_mm:0,
          height_mm:100, bottom_z_start_mm:0, bottom_z_end_mm:0}],
  ground: [],
};
out.zero_finite = bayRects(ZERO_WITH_BAY, 100, 40).bays.every(
  (b) => Number.isFinite(b.x) && Number.isFinite(b.w));

// A pre-generation stretch with a STATED height. The drawing must leave room
// for it, and the only way that is OBSERVABLE through this return shape is the
// ground: with 1800 mm of fence in range, RISING ground occupies a smaller
// slice of the box than it does when the ground is all there is. A flat-ground
// fixture cannot tell the two apart — both put the line at the bottom — which
// is why the first version of this assertion passed with the branch deleted.
const GROUND_ONLY = {
  run_id: "run4", tag: "I", length_mm: 4000,
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 4000, z_mm: 1200}],
};
const WITH_INTENT = { ...GROUND_ONLY, height_intent_mm: 1800 };
const spread = (sec) => {
  const g = bayRects(sec, 200, 60).ground;
  return Math.round(Math.abs(g[0].y - g[1].y));
};
out.ground_spread_alone = spread(GROUND_ONLY);
out.ground_spread_with_intent = spread(WITH_INTENT);

// A WALL on climbing ground, before anything is generated. `base_top` carries
// height ABOVE LOCAL GROUND (the event's own convention), so the drawing has to
// add the ground back — and the step must survive as two points at one station.
const WALL = {
  run_id: "run3", tag: "W", length_mm: 8000,
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 8000, z_mm: 800}],
  base_top: [{station_mm: 0, z_mm: 300}, {station_mm: 4000, z_mm: 300},
             {station_mm: 4000, z_mm: 1420}, {station_mm: 8000, z_mm: 1420}],
};
const wall = bayRects(WALL, 200, 80);
out.wall_points = wall.baseTop.length;
// two points at one station -> one x, two different y: the step, intact
out.wall_step_same_x = Math.abs(wall.baseTop[1].x - wall.baseTop[2].x) < 0.01;
out.wall_step_differs_y = Math.abs(wall.baseTop[1].y - wall.baseTop[2].y) > 1;
// the wall is ABOVE the ground at both ends, by the stated amount plus terrain
out.wall_above_ground = wall.baseTop[0].y < wall.ground[0].y
  && wall.baseTop[3].y < wall.ground[1].y;
// ...and the far end is higher in ABSOLUTE terms than the near end, because the
// ground climbed 800 under a wall that also stepped up
out.wall_rises = wall.baseTop[3].y < wall.baseTop[0].y;
// The assertion that actually proves the ground was ADDED: stations 0 and 4000
// state the SAME height above ground (300), and the ground climbs 400 mm
// between them — so their absolute elevations must differ. Ignoring the ground
// puts both at the same y, and every other assertion here stays true.
out.wall_follows_ground = Math.abs(wall.baseTop[0].y - wall.baseTop[1].y) > 1;
// ...and the whole wall has to fit the box it is drawn in. Left out of the
// vertical range, the top of a 2220 mm wall lands above the frame and is
// silently clipped.
out.wall_in_box = wall.baseTop.every((p) => p.y >= 0 && p.y <= 80);

// A stretch standing on soil draws NO wall — not a flat line at zero.
const NO_WALL = {
  run_id: "run3b", tag: "X", length_mm: 4000,
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 4000, z_mm: 0}],
};
out.no_wall = bayRects(NO_WALL, 200, 60).baseTop.length;

// Two bays, same fence height, different wall heights: the one on the taller
// wall must sit HIGHER on screen (smaller y) and be exactly as tall.
const TWO = {
  run_id: "run9", tag: "Z", length_mm: 2000,
  bays: [
    {tag:"Z/B1", element_id:"e1", start_station_mm:0,    width_mm:1000, height_mm:800, bottom_z_start_mm:0,    bottom_z_end_mm:0},
    {tag:"Z/B2", element_id:"e2", start_station_mm:1000, width_mm:1000, height_mm:800, bottom_z_start_mm:1000, bottom_z_end_mm:1000},
  ],
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 2000, z_mm: 0}],
};
const two = bayRects(TWO, 200, 80);
out.two_panel_y = two.bays.map((b) => b.panelY);
out.two_panel_h = two.bays.map((b) => Math.round(b.panelH));
out.two_base_h = two.bays.map((b) => Math.round(b.baseH));

// A stretch nobody has generated: ground and nothing else.
const UNGENERATED = {
  run_id: "run2", tag: "B", length_mm: 6000,
  ground: [{station_mm: 0, z_mm: 0}, {station_mm: 3000, z_mm: 400},
           {station_mm: 6000, z_mm: 1200}],
};
const un = bayRects(UNGENERATED, 300, 80);
out.un_bays = un.bays;
out.un_ground = un.ground.length;
out.un_ground_rising = un.ground[0].y > un.ground[2].y;

// A stretch with nothing at all must not throw.
out.empty_ok = (() => {
  try {
    const e = bayRects({run_id: "r", tag: "C", length_mm: 0}, 100, 40);
    return {bays: e.bays.length, ground: e.ground.length};
  } catch (err) { return "threw: " + err.message; }
})();

// Purity: same answer twice, and the input untouched.
const before = JSON.stringify(A);
bayRects(A, 300, 80);
out.input_untouched = JSON.stringify(A) === before;
out.stable = JSON.stringify(bayRects(A, 300, 80)) === JSON.stringify(a);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def se():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_one_rectangle_per_bay_in_station_order(se):
    assert se["a_count"] == 6
    assert se["a_tags"] == ["A/B1", "A/B2", "A/B3", "A/B4", "A/B5", "A/B6"]
    assert se["a_ascending_x"], "bays must read along the stretch"


def test_the_drawing_spans_the_whole_stretch(se):
    """Station 0 at the left edge of the box, the last bay ending at the right.

    Both ends asserted independently — a single "first equals last minus the
    span" check is true of any drawing at all, which is the shape of vacuous
    assertion this repo has shipped before.
    """
    assert se["a_first_x"] == se["a_pad"], "station 0 sits at the left inset"
    assert se["a_last_right"] == se["a_inner_right"], "the stretch fills the box"


def test_a_bay_is_as_wide_on_screen_as_it_is_on_the_ground(se):
    """A 2000 mm bay is four times a 500 mm one, and must draw that way.

    The first version of this asserted that section A's first bay was 167
    thousandths of the drawing — and one sixth of a drawing rounds to 167 too,
    so a renderer that drew six equal boxes passed the assertion written to
    catch exactly that. A ratio of 4 cannot be confused with a ratio of 1.
    """
    assert se["uneven_w_ratio"] == 4.0


def test_a_panel_sits_on_the_higher_end_of_a_sloping_base(se):
    """Every other fixture has a level base, so the rule the code argues for —
    take the max, because an average puts the panel through the ground at one
    end — was asserted nowhere and `Math.min` passed the suite."""
    assert se["sloped_bottom"] == 600


def test_a_perfectly_flat_stretch_does_not_divide_by_its_own_zero_span(se):
    assert se["flat_finite"], "a flat stretch must still produce real coordinates"


def test_a_zero_length_stretch_with_a_bay_still_produces_numbers(se):
    """The empty-everything fixture never divides by the length, so it proved
    nothing about the guard. This one has a bay to place."""
    assert se["zero_finite"]


def test_a_stated_height_makes_room_for_itself_before_anything_is_generated(se):
    """The card scales to hold the height somebody stated.

    Without it the 1200 mm of ground fills the whole box and a 1800 mm fence
    would have nowhere to be drawn; with it, the same ground takes two thirds.
    Asserted as a comparison between the two, because an absolute position is
    the same in both and proves nothing — the first version of this test passed
    with the behaviour removed.
    """
    assert se["ground_spread_with_intent"] < se["ground_spread_alone"]


def test_a_wall_is_drawn_above_the_ground_it_stands_on(se):
    """`base_top` is height ABOVE LOCAL GROUND, so the drawing adds the ground
    back. Getting that wrong is how a wall gets drawn underground."""
    assert se["wall_points"] == 4
    assert se["wall_above_ground"]
    assert se["wall_rises"], "climbing ground plus a step means a rising wall"
    assert se["wall_follows_ground"], (
        "two points at the same stated height over ground that climbed between "
        "them cannot share an elevation")
    assert se["wall_in_box"], "the wall must be inside the drawing's own scale"


def test_a_step_in_the_wall_survives_as_two_points_at_one_station(se):
    """The threshold-free way to say the wall jumps — and collapsing it would
    erase the one fact section A of the demo job exists to show."""
    assert se["wall_step_same_x"]
    assert se["wall_step_differs_y"]


def test_a_stretch_on_soil_draws_no_wall_at_all(se):
    """Empty, not a flat line at zero: a line would draw a wall that is not
    there, which on a card the office prices from is worse than silence."""
    assert se["no_wall"] == 0


def test_the_ground_line_is_drawn_from_its_own_samples(se):
    assert se["a_ground_points"] == 2


def test_a_bay_with_no_fence_is_flagged_rather_than_drawn_as_nothing(se):
    """Section A's headline fact: half of it carries no fence.

    A zero-height rectangle is invisible, so a renderer handed only a height
    would draw the most important thing about this job as blank wall — which is
    exactly what it looks like when nobody has noticed.
    """
    assert se["a_empty"] == [False, False, False, True, True, True]
    assert se["a_panel_h"][3:] == [0, 0, 0]
    assert all(h > 0 for h in se["a_panel_h"][:3])


def test_a_taller_base_lifts_the_panel_without_changing_its_height(se):
    low, high = se["two_panel_y"]
    assert high < low, "a panel on a taller wall sits higher on screen"
    assert se["two_panel_h"][0] == se["two_panel_h"][1]
    assert se["two_base_h"][1] > se["two_base_h"][0]


def test_a_bay_carries_the_handle_that_selects_it(se):
    """The seam for selecting one bay (spec §3): the id is already on the rect,
    so wiring a click has somewhere to go and needs no second lookup."""
    assert se["a_element_ids"][0] == "span@run1:0-1334"


def test_a_stretch_nobody_generated_draws_its_ground_and_no_panels(se):
    assert se["un_bays"] == []
    assert se["un_ground"] == 3
    assert se["un_ground_rising"], "rising ground must rise on screen"


def test_a_stretch_with_nothing_on_it_does_not_throw(se):
    assert se["empty_ok"] == {"bays": 0, "ground": 0}


def test_it_is_pure(se):
    assert se["input_untouched"]
    assert se["stable"]
