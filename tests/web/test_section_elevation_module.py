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
    """1334 mm of 8000 is 167 thousandths of the drawing, and a card that drew
    six equal boxes would hide that the bays are not equal."""
    assert se["a_first_w_permille"] == round(1334 / 8000 * 1000)


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
