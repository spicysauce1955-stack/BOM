"""A new interval carves the older ones of its kind (static/js/intervals.js).

The height tool used to append, and the generator reads the first height that
covers a station, so a height stated over an older one was never built. These
pin the carving itself; `tests/strategy/test_height_carving.py` pins what the
generator then builds.

Anchors here are plain `{at: station}` objects: the module takes `stationOf` and
`anchorAt` as callbacks precisely so it never anchors anything itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { carveInterval } from "./js/intervals.js";

const at = (s) => ({ at: s });
let seq = 0;
const deps = { stationOf: (a) => a.at, anchorAt: at, newId: () => `new${++seq}` };
const height = (id, s0, s1, h) => ({
  id, start_anchor: at(s0), end_anchor: at(s1),
  payload: { kind: "height_intent", height_mm: h },
});
const base = (id, s0, s1) => ({
  id, start_anchor: at(s0), end_anchor: at(s1),
  payload: { kind: "base", surface: "soil" },
});
const brief = (evs) => evs.map((e) => [e.id, e.payload.kind, e.start_anchor.at,
                                        e.end_anchor.at, e.payload.height_mm ?? null]);

const out = {};
out.covered = brief(carveInterval([height("a", 0, 6000, 1800)], "height_intent",
                                  0, 6000, deps));
out.covered_inside = brief(carveInterval([height("a", 1000, 2000, 1800)],
                                         "height_intent", 0, 6000, deps));
out.overhang_start = brief(carveInterval([height("a", 0, 6000, 1800)],
                                         "height_intent", 3000, 6000, deps));
out.overhang_end = brief(carveInterval([height("a", 0, 6000, 1800)],
                                       "height_intent", 0, 2000, deps));
seq = 0;
out.contains = brief(carveInterval([height("a", 0, 6000, 1800)], "height_intent",
                                   2000, 4000, deps));
out.touching = brief(carveInterval([height("a", 0, 3000, 1800),
                                    height("b", 4000, 6000, 1700)],
                                   "height_intent", 3000, 4000, deps));
out.other_kinds = brief(carveInterval([base("b1", 0, 6000), height("a", 0, 6000, 1800),
                                       base("b2", 0, 6000)],
                                      "height_intent", 0, 6000, deps));
const input = [height("a", 0, 6000, 1800)];
const frozen = JSON.stringify(input);
const result = carveInterval(input, "height_intent", 2000, 4000, deps);
out.input_untouched = JSON.stringify(input) === frozen;
out.new_array = result !== input;
out.payload_copied_not_shared = result[1].payload === input[0].payload;

// an event the new stretch does not overlap is passed through AS IS: a fresh
// copy would be re-anchored by the editor's anchorAt and logged as a move
const touchingIn = [height("a", 0, 3000, 1800), height("b", 4000, 6000, 1700)];
const touchingOut = carveInterval(touchingIn, "height_intent", 3000, 4000, deps);
out.touching_same_objects = touchingOut.length === 2
  && touchingOut[0] === touchingIn[0] && touchingOut[1] === touchingIn[1];
const mixedIn = [base("b1", 0, 6000), height("a", 0, 6000, 1800)];
out.other_kind_same_object = carveInterval(mixedIn, "height_intent", 0, 6000, deps)[0]
  === mixedIn[0];
out.empty_stretch = brief(carveInterval([height("a", 0, 6000, 1800)], "height_intent",
                                        3000, 3000, deps));
out.reversed_stretch = brief(carveInterval([height("a", 0, 6000, 1800)], "height_intent",
                                           4000, 2000, deps));
// every branch leaves its input alone, not only the split
for (const [name, s0, s1] of [["overhang_start", 3000, 6000], ["overhang_end", 0, 2000],
                               ["covered", 0, 6000]]) {
  const ins = [height("a", 0, 6000, 1800)];
  const frozenIn = JSON.stringify(ins);
  carveInterval(ins, "height_intent", s0, s1, deps);
  out[`${name}_input_untouched`] = JSON.stringify(ins) === frozenIn;
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def carve():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_height_it_covers_is_dropped(carve):
    assert carve["covered"] == []
    assert carve["covered_inside"] == []


def test_a_height_overhanging_the_start_keeps_the_part_before(carve):
    assert carve["overhang_start"] == [["a", "height_intent", 0, 3000, 1800]]


def test_a_height_overhanging_the_end_keeps_the_part_after(carve):
    assert carve["overhang_end"] == [["a", "height_intent", 2000, 6000, 1800]]


def test_a_height_that_contains_it_is_split_in_two(carve):
    # the part before keeps the id; the part after is a new event, same height
    assert carve["contains"] == [
        ["a", "height_intent", 0, 2000, 1800],
        ["new1", "height_intent", 4000, 6000, 1800],
    ]


def test_touching_at_a_boundary_is_not_overlap(carve):
    assert carve["touching"] == [
        ["a", "height_intent", 0, 3000, 1800],
        ["b", "height_intent", 4000, 6000, 1700],
    ]


def test_other_kinds_pass_through_in_order(carve):
    assert carve["other_kinds"] == [
        ["b1", "base", 0, 6000, None],
        ["b2", "base", 0, 6000, None],
    ]


def test_the_input_is_never_mutated(carve):
    assert carve["input_untouched"] is True
    assert carve["new_array"] is True


def test_the_two_halves_of_a_split_do_not_share_a_payload(carve):
    # an in-place edit of one half must not rewrite the other
    assert carve["payload_copied_not_shared"] is False


def test_an_event_it_does_not_touch_is_passed_through_as_is(carve):
    assert carve["touching_same_objects"] is True
    assert carve["other_kind_same_object"] is True


def test_an_empty_or_reversed_stretch_takes_nothing(carve):
    assert carve["empty_stretch"] == [["a", "height_intent", 0, 6000, 1800]]
    assert carve["reversed_stretch"] == [["a", "height_intent", 0, 6000, 1800]]


@pytest.mark.parametrize("case", ["overhang_start", "overhang_end", "covered"])
def test_no_branch_edits_its_input(carve, case):
    assert carve[f"{case}_input_untouched"] is True
