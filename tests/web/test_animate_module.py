"""The assembly animation's ordering and clock (static/js/animate.js).

The animation reveals rectangles the SERVER placed, in the order a crew would
build them. "Posts before slats" is therefore a claim about a pure function over
`[{id, role}]` — not about a browser — so it is pinned here, under node, the way
`base-top.js` and `runview.js` are.

What these tests are really guarding: that no part is ever left out. A reveal
schedule that silently dropped an unfamiliar role would end the animation with a
fence that is missing a part the BOM charged for, and it would look finished.
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
  STAGES, TIMING, assemblyPlan, clampMs, frameAt, msAtPermille,
  permilleAt, placedCount, revealedIds, stageOf,
} from "./js/animate.js";

const out = {};
out.stages = STAGES;

// A fence, given to the planner in a deliberately WRONG order: the drawing
// hands over whatever the two viewports drew, and the build order is this
// module's job rather than the caller's.
const fence = [
  { id: "slat-1", role: "infill" },
  { id: "cap-1", role: "cap" },
  { id: "post-1", role: "post" },
  { id: "footing-1", role: "concrete" },
  { id: "rail-1", role: "rail" },
  { id: "slat-2", role: "infill" },
  { id: "post-2", role: "post" },
  { id: "footing-2", role: "concrete" },
  { id: "bay-1", role: "bay" },
  { id: "gate-1", role: "gate_kit" },
  { id: "mystery-1", role: "a-role-nobody-has-written-yet" },
  { id: "unlabelled-1" },
];
const plan = assemblyPlan(fence);
out.order = plan.steps.map((s) => s.id);
out.step_stages = plan.steps.map((s) => s.stage);
out.stage_keys = plan.stages.map((s) => s.key);
out.stage_counts = plan.stages.map((s) => s.count);
out.at_ms = plan.steps.map((s) => s.at_ms);
out.stage_spans = plan.stages.map((s) => [s.start_ms, s.end_ms]);
out.duration = plan.duration_ms;

// nothing on site at zero; everything standing at the end
out.revealed_at_zero = revealedIds(plan, 0);
out.revealed_at_end = revealedIds(plan, plan.duration_ms).length;
out.total = plan.steps.length;
out.revealed_after_end = revealedIds(plan, plan.duration_ms * 10).length;

// the ordering claim, stated as the browser check states it: while any post is
// still to come, no infill has been placed
out.infill_waits_for_posts = plan.steps
  .filter((s) => s.stage === "infill")
  .every((infill) => plan.steps
    .filter((s) => s.stage === "posts")
    .every((post) => post.at_ms < infill.at_ms));
out.posts_wait_for_footings = plan.steps
  .filter((s) => s.stage === "posts")
  .every((post) => plan.steps
    .filter((s) => s.stage === "groundworks")
    .every((f) => f.at_ms < post.at_ms));

// role -> stage, including the two that must not be dropped
out.role_stages = ["concrete", "post", "bay", "rail", "infill", "cap", "spacer",
                   "screw", "gate_kit", "gizmo", "", undefined]
  .map((r) => stageOf(r));

// a stage with nothing in it takes no time at all
const posts_only = assemblyPlan([
  { id: "a", role: "post" }, { id: "b", role: "post" }]);
out.posts_only_stages = posts_only.stages.map((s) => s.key);
out.posts_only_duration = posts_only.duration_ms;

// nothing drawn: no schedule, no duration, and no exception
const empty = assemblyPlan([]);
out.empty = { stages: empty.stages.length, steps: empty.steps.length,
              duration: empty.duration_ms, placed: placedCount(empty, 5000),
              permille: permilleAt(empty, 0), ms: msAtPermille(empty, 500),
              frame: frameAt(empty, 0) };

// a 1200-member run: the step size is fitted to the target length, and the
// floor wins rather than the animation becoming a strobe
const many = assemblyPlan(
  Array.from({ length: 1200 }, (_, i) => ({ id: `m${i}`, role: "infill" })));
out.many = { duration: many.duration_ms, total: many.steps.length,
             gap: many.steps[1].at_ms - many.steps[0].at_ms,
             min_item: TIMING.minItemMs, max: TIMING.maxMs };
// …and a tiny one is not dragged out to fill the budget
const few = assemblyPlan([{ id: "a", role: "infill" }, { id: "b", role: "infill" }]);
out.few_gap = few.steps[1].at_ms - few.steps[0].at_ms;

// placedCount is the painter's reading of the same schedule revealedIds gives
out.cursor_agrees = plan.steps.every((s, i) =>
  placedCount(plan, s.at_ms) === i + 1
  && placedCount(plan, s.at_ms - 1) === i
  && revealedIds(plan, s.at_ms).length === i + 1);

// the caption: which stage is being placed, and when it is over
out.frames = [0, plan.stages[0].start_ms, plan.stages[1].start_ms,
              plan.duration_ms - 1, plan.duration_ms]
  .map((ms) => frameAt(plan, ms))
  .map((f) => [f.stage, f.placed, f.done]);
out.frame_totals = frameAt(plan, 0).total;

// the clock never leaves the film
out.clamped = [clampMs(plan, -500), clampMs(plan, plan.duration_ms + 500),
               clampMs(plan, NaN)];

// the scrub slider: permille in, milliseconds out, and back
out.scrub = [0, 250, 500, 1000].map((p) => permilleAt(plan, msAtPermille(plan, p)));
out.scrub_clamped = [msAtPermille(plan, -50), msAtPermille(plan, 5000),
                     permilleAt(plan, plan.duration_ms * 3)];

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def an():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_build_order_is_the_stage_order(an):
    assert an["stages"] == ["groundworks", "posts", "frame", "infill", "fixings"]
    assert an["stage_keys"] == an["stages"]
    # groundworks 2, posts 2, frame 2 (bay + rail), infill 2, fixings 4
    assert an["stage_counts"] == [2, 2, 2, 2, 4]


def test_parts_are_scheduled_in_build_order_whatever_order_they_were_drawn_in(an):
    """The input list is shuffled on purpose: a planner that just kept the
    caller's order would pass every timing test and animate nothing useful."""
    assert an["order"] == [
        "footing-1", "footing-2",      # groundworks
        "post-1", "post-2",            # posts
        "rail-1", "bay-1",             # frame, still in the order they were drawn
        "slat-1", "slat-2",            # infill
        "cap-1", "gate-1", "mystery-1", "unlabelled-1",   # fixings
    ]


def test_the_drawn_order_is_kept_within_a_stage(an):
    """Nothing here sorts by position — the macro view already draws posts along
    the run, and re-sorting would mean measuring the picture."""
    assert an["order"][:2] == ["footing-1", "footing-2"]
    assert an["order"][6:8] == ["slat-1", "slat-2"]


def test_a_role_nobody_has_written_yet_is_fixed_last_not_dropped(an):
    """The failure this prevents: an animation that ends with a part missing,
    looking finished. Unknown and absent roles are still parts."""
    assert an["role_stages"] == [
        "groundworks", "posts", "frame", "frame", "infill",
        "fixings", "fixings", "fixings", "fixings",
        "fixings", "fixings", "fixings",
    ]
    assert "mystery-1" in an["order"] and "unlabelled-1" in an["order"]


def test_every_drawn_part_is_on_screen_when_the_animation_ends(an):
    assert an["revealed_at_zero"] == []
    assert an["revealed_at_end"] == an["total"] == 12
    assert an["revealed_after_end"] == 12


def test_no_slat_arrives_before_the_post_it_hangs_on(an):
    assert an["infill_waits_for_posts"] is True
    assert an["posts_wait_for_footings"] is True


def test_the_schedule_is_ascending_so_a_frame_is_a_cursor(an):
    assert an["at_ms"] == sorted(an["at_ms"])
    assert an["cursor_agrees"] is True


def test_stages_do_not_overlap_so_the_caption_has_one_answer(an):
    spans = an["stage_spans"]
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), spans
    assert all(start < end for start, end in spans)
    assert an["duration"] == spans[-1][1]


def test_a_stage_with_nothing_in_it_takes_no_time(an):
    """A run with no footings must not open with a second of empty ground."""
    assert an["posts_only_stages"] == ["posts"]
    assert an["posts_only_duration"] == 240 + 90 + 200   # lead + one step + fade


def test_nothing_drawn_is_a_plan_of_nothing_not_an_exception(an):
    e = an["empty"]
    assert e["stages"] == 0 and e["steps"] == 0 and e["duration"] == 0
    assert e["placed"] == 0 and e["ms"] == 0
    # a zero-length film sits at its END: an empty tab must not look "not started"
    assert e["permille"] == 1000
    assert e["frame"]["done"] is True and e["frame"]["stage"] is None


def test_a_crowded_run_slows_down_rather_than_strobing(an):
    many = an["many"]
    assert many["total"] == 1200
    assert many["gap"] == many["min_item"]          # the floor wins
    assert many["duration"] > many["max"]           # …and the target gives way
    assert an["few_gap"] == 90                      # a small run runs at full pace


def test_the_caption_names_the_stage_being_placed_then_says_it_is_over(an):
    stages = [f[0] for f in an["frames"]]
    assert stages[0] == "groundworks"
    assert stages[1] == "groundworks"
    assert stages[2] == "posts"
    assert stages[3] == "fixings"
    assert stages[4] is None                        # fully assembled
    assert [f[2] for f in an["frames"]] == [False, False, False, False, True]
    assert an["frame_totals"] == 12


def test_the_clock_never_leaves_the_film(an):
    assert an["clamped"] == [0, an["duration"], an["duration"]]


def test_the_scrub_slider_round_trips(an):
    assert an["scrub"] == [0, 250, 500, 1000]
    assert an["scrub_clamped"] == [0, an["duration"], 1000]


def test_every_stage_has_a_word_in_both_bundles(an):
    """The caption is built by concatenation — `t("assembly.animate.stage." +
    stage)` — so key-parity scanning cannot see it, and `t()` returns the key
    itself when the bundle has no entry. A sixth stage added to `STAGES` would
    otherwise render `assembly.animate.stage.cladding` into a Hebrew UI, in both
    languages, with a green suite. Same hole the model editor's closed
    vocabularies have, closed the same way: from the code's own list."""
    en = json.loads((STATIC / "i18n" / "en.json").read_text())
    he = json.loads((STATIC / "i18n" / "he.json").read_text())
    missing = sorted(
        f"{lang}:{key}"
        for lang, table in (("en", en), ("he", he))
        for key in [f"assembly.animate.stage.{s}" for s in an["stages"]]
        if key not in table
    )
    assert not missing, missing
