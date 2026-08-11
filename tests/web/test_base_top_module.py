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
  STEP_RISE_MM, enforceLocks, flatPoints, levelPoints, lockOf, matchEnds, setLock,
  stepPositions, topZAt, withStep,
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

// ---- segment locks: the rule the user sets STICKS -------------------------
// ground rises 0 -> 500 mm across the interval, so "horizontal" and "constant
// height above ground" are visibly different things
const groundAtPos = (pos) => Math.round((pos * 500) / 1000);

// a step is a VERTICAL riser followed by a HORIZONTAL tread
const riser = withStep(flatPoints(600), 500, 200, groundAtPos);
out.step_locks = riser.map((p) => p.lock ?? null);
out.step_positions_locked = stepPositions(riser);
out.step_tread_abs = [500, 750, 1000].map((p) => groundAtPos(p) + topZAt(riser, p));

// levelling marks every segment level, and the last point starts no segment
out.level_locks = levelPoints([0, 2000, 6000], (s) => (s <= 2000 ? 0 : (s - 2000) / 4),
                              0, 6000, 1600).map((p) => p.lock ?? null);

// dragging a point: locked neighbours follow it, free ones do not
const chain = [
  { pos_permille: 0, z_mm: 600, lock: "level" },
  { pos_permille: 500, z_mm: 350, lock: null },
  { pos_permille: 1000, z_mm: 100 },
];
const dragged = chain.map((p, i) => (i === 1 ? { ...p, z_mm: 550 } : { ...p }));
const settled = enforceLocks(dragged, groundAtPos, 1);
out.drag_follows_lock = settled.map((p) => p.z_mm);
out.drag_abs = settled.map((p) => groundAtPos(p.pos_permille) + p.z_mm);

// a vertical lock keeps the two ends at one position when either is dragged
const vertical = [
  { pos_permille: 300, z_mm: 200, lock: "step" },
  { pos_permille: 300, z_mm: 500, lock: null },
  { pos_permille: 1000, z_mm: 500 },
];
const slid = vertical.map((p, i) => (i === 1 ? { ...p, pos_permille: 640 } : { ...p }));
out.vertical_holds = enforceLocks(slid, groundAtPos, 1).map((p) => p.pos_permille);

// setting a segment free stops it following
const freed = setLock(chain, 0, null, groundAtPos);
out.freed_lock = freed[0].lock ?? null;
out.freed_z = enforceLocks(
  freed.map((p, i) => (i === 1 ? { ...p, z_mm: 550 } : { ...p })), groundAtPos, 1)
  .map((p) => p.z_mm);
out.lock_of = [lockOf(chain, 0), lockOf(chain, 1), lockOf(chain, 9)];

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


def test_a_step_is_a_riser_then_a_tread(bt):
    """The user's words: a step is a vertical line and a horizontal one after it."""
    assert bt["step_locks"] == [None, "step", "level", None]
    assert bt["step_positions_locked"] == [500]
    # the tread is HORIZONTAL: one absolute elevation, over rising ground
    assert len(set(bt["step_tread_abs"])) == 1


def test_levelling_locks_every_segment(bt):
    assert bt["level_locks"] == ["level", "level", None]


def test_a_locked_neighbour_follows_the_dragged_point(bt):
    """Segment 0 is held horizontal, so raising point 1 lifts point 0 with it —
    the lock is a standing rule, not a one-time arrangement."""
    assert bt["drag_follows_lock"][1] == 550          # what the user dragged
    assert bt["drag_abs"][0] == bt["drag_abs"][1]     # still horizontal
    assert bt["drag_follows_lock"][2] == 100          # free segment: untouched


def test_a_vertical_lock_keeps_both_ends_at_one_position(bt):
    assert bt["vertical_holds"] == [640, 640, 1000]


def test_freeing_a_segment_stops_it_following(bt):
    assert bt["freed_lock"] is None
    assert bt["freed_z"] == [600, 550, 100]          # point 0 stayed put


def test_lock_of_is_safe_off_the_end(bt):
    assert bt["lock_of"] == ["level", None, None]
