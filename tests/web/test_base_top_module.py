"""Base-top profile geometry (static/js/base-top.js).

The side view's four base actions — give it a height, make it horizontal, meet
the neighbouring section, add a step — are pure point-list transforms, so they
are tested here rather than only by aiming a mouse at a diamond in a browser.

`z_mm` is height ABOVE LOCAL GROUND (backend base_top_at semantics), which is
what makes "horizontal" non-trivial: a level top needs a point wherever the
ground changes slope.
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
  STEP_RISE_MM, flatPoints, levelPoints, matchEnds, stepPositions, topZAt, withStep,
} from "./js/base-top.js";

const out = {};

// ground: flat 0 to station 2000, then climbing to 1000 mm at station 6000
const STATIONS = [0, 2000, 6000];
const groundAt = (s) => (s <= 2000 ? 0 : Math.round(((s - 2000) * 1000) / 4000));
out.ground_check = STATIONS.map(groundAt);

out.flat = flatPoints(600);
out.flat_negative = flatPoints(-50);

// horizontal at 1600 mm absolute over the whole 0..6000 section
out.level = levelPoints(STATIONS, groundAt, 0, 6000, 1600);
// the top of a LEVEL base must sit at the same absolute elevation everywhere
out.level_abs = [0, 1000, 2000, 4000, 6000].map((s) => {
  const pos = Math.round((s * 1000) / 6000);
  return groundAt(s) + topZAt(out.level, pos);
});
// a two-point profile at the same height is NOT level — it follows the ground
out.follow_abs = [0, 4000, 6000].map((s) => {
  const pos = Math.round((s * 1000) / 6000);
  return groundAt(s) + topZAt(flatPoints(1600), pos);
});
// a level top over a section that starts high enough never goes negative
out.level_clamped = levelPoints(STATIONS, groundAt, 0, 6000, 200);

// step: a plateau, not a ramp — everything after it rises too
const before = flatPoints(600);
out.step = withStep(before, 500);
out.step_rise = STEP_RISE_MM;
out.step_positions = stepPositions(out.step);
out.step_profile = [0, 400, 499, 500, 600, 1000].map((p) => topZAt(out.step, p));
out.step_untouched_input = before;
// a step on a profile that already has one
out.two_steps = stepPositions(withStep(out.step, 800));

// match: move the ends to the neighbours' absolute tops; ends without a
// neighbour (null) keep exactly what they had
out.match_both = matchEnds(flatPoints(600), {
  startAbs: 900, endAbs: 2000, groundStart: 0, groundEnd: 1000,
});
out.match_one_end = matchEnds(flatPoints(600), {
  startAbs: null, endAbs: 2000, groundStart: 0, groundEnd: 1000,
});
out.match_no_neighbour = matchEnds(flatPoints(600), {
  startAbs: null, endAbs: null, groundStart: 0, groundEnd: 1000,
});
out.match_below_ground = matchEnds(flatPoints(600), {
  startAbs: -500, endAbs: null, groundStart: 0, groundEnd: 1000,
});

// topZAt boundary rules (mirrors backend base_top_at)
const stepped = [{ pos_permille: 0, z_mm: 100 }, { pos_permille: 500, z_mm: 100 },
                 { pos_permille: 500, z_mm: 400 }, { pos_permille: 1000, z_mm: 400 }];
out.right_side_wins = topZAt(stepped, 500);
out.flat_beyond_ends = [topZAt(stepped, -20), topZAt(stepped, 1200)];
out.empty_profile = topZAt([], 500);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def bt():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_fixture_ground_is_flat_then_climbing(bt):
    assert bt["ground_check"] == [0, 0, 1000]


def test_flat_is_a_constant_height_above_ground(bt):
    assert bt["flat"] == [{"pos_permille": 0, "z_mm": 600},
                          {"pos_permille": 1000, "z_mm": 600}]
    assert bt["flat_negative"][0]["z_mm"] == 0     # never below the ground


def test_level_puts_a_point_at_every_ground_break(bt):
    # 0 / 2000 / 6000 -> permille 0 / 333 / 1000
    assert [p["pos_permille"] for p in bt["level"]] == [0, 333, 1000]
    assert [p["z_mm"] for p in bt["level"]] == [1600, 1600, 600]


def test_level_really_is_level(bt):
    """The point of the button: ONE absolute elevation across the section.

    Point positions are stored in permille of the interval (ADR-0003 anchors),
    so a station that falls between two permille steps can land 1 mm off — that
    is NUMERIC_TOLERANCE_MM, the tolerance the whole system compares geometry
    with. Level to within a millimetre; not level to within a metre, which is
    what a two-point profile gives (test below).
    """
    assert all(abs(z - 1600) <= 1 for z in bt["level_abs"]), bt["level_abs"]


def test_a_constant_height_is_not_level(bt):
    """Contrast case — this is what the user got before, and complained about."""
    assert bt["follow_abs"] == [1600, 2100, 2600]


def test_level_never_dips_below_the_ground(bt):
    assert all(p["z_mm"] >= 0 for p in bt["level_clamped"])


def test_step_is_a_plateau_not_a_ramp(bt):
    assert bt["step_rise"] == 200
    assert bt["step_positions"] == [500]
    # flat at 600 up to the step, then flat at 800 all the way to the end
    assert bt["step_profile"] == [600, 600, 600, 800, 800, 800]


def test_step_does_not_mutate_the_input_profile(bt):
    assert bt["step_untouched_input"] == [{"pos_permille": 0, "z_mm": 600},
                                          {"pos_permille": 1000, "z_mm": 600}]


def test_steps_accumulate(bt):
    assert bt["two_steps"] == [500, 800]


def test_match_converts_neighbour_elevations_to_heights_above_ground(bt):
    # start: 900 abs over ground 0 -> 900; end: 2000 abs over ground 1000 -> 1000
    assert bt["match_both"][0]["z_mm"] == 900
    assert bt["match_both"][-1]["z_mm"] == 1000


def test_match_leaves_ends_without_a_neighbour_alone(bt):
    assert bt["match_one_end"][0]["z_mm"] == 600      # untouched
    assert bt["match_one_end"][-1]["z_mm"] == 1000
    assert bt["match_no_neighbour"] == [{"pos_permille": 0, "z_mm": 600},
                                        {"pos_permille": 1000, "z_mm": 600}]


def test_match_clamps_at_the_ground(bt):
    assert bt["match_below_ground"][0]["z_mm"] == 0


def test_top_z_boundary_rules_mirror_the_backend(bt):
    assert bt["right_side_wins"] == 400          # right side of a step wins
    assert bt["flat_beyond_ends"] == [100, 400]  # flat beyond the end points
    assert bt["empty_profile"] == 0
