"""The six steps, as a function (static/js/road.js).

The road groups what `handover_gaps()` already returned. It computes no
completeness of its own, and that is the whole reason it is a separate module
with its own test: three surfaces already answered "what is left" and disagreed
— `checklist.js`'s three hardcoded items, the handover panel, and `#gaps`, which
answers a different question entirely. A fourth would be the B03 defect at a
larger scale.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.report.handover import HANDOVER_CODES

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
// No stubs: road-model.js imports nothing, which is why it is its own file.
import { road, panelFor, STATES } from "./js/road-model.js";
import { SALES_ROAD, ROADS, roadFor } from "./js/roads.js";

const g = (code, extra = {}) => ({ code, blocking: false, params: {}, ...extra });
const st = (o = {}) => ({ no_gates: false, no_promises: false, ...o });
const byKey = (r) => Object.fromEntries(r.map((s) => [s.key, s]));
const drawn = [];                    // no anchor code present == started

const out = {};
out.step_keys = SALES_ROAD.steps.map((s) => s.key);
out.panels = Object.fromEntries(SALES_ROAD.steps.map((s) => [s.key, s.panel]));
out.states = STATES;
out.roles = Object.keys(ROADS);

// the engine takes no project
out.arity = road.length;

// handover has not arrived
out.unloaded = byKey(road(SALES_ROAD, null, st()));

// nothing drawn: the anchor is present
out.empty = byKey(road(SALES_ROAD, [g("no_fence_drawn", { blocking: true })], st()));

// a drawn job, two required job fields open and one nice-to-have
out.gappy = byKey(road(SALES_ROAD, [
  g("customer_missing"), g("sold_by_missing"), g("height_assumed"),
], st()));

// everything answered, nothing stated
out.clean = byKey(road(SALES_ROAD, drawn, st()));

// stated: no gates, and the drawing agrees
out.skipped = byKey(road(SALES_ROAD, drawn, st({ no_gates: true })));

// stated: no gates, but the drawing has one
out.contradicted = byKey(road(SALES_ROAD, [g("gates_contradicted")],
                              st({ no_gates: true })));

// nothing drawn AND a fact stated: empty beats skipped
out.empty_beats_skip = byKey(road(SALES_ROAD,
  [g("no_fence_drawn", { blocking: true })], st({ no_gates: true })));

// a code no step claims must not vanish
out.orphan = byKey(road(SALES_ROAD, [g("invented_code")], st()));

// a code colliding with an inherited Object key must not throw
out.proto = byKey(road(SALES_ROAD, [g("constructor")], st()));

out.panel_of_notes = panelFor(SALES_ROAD, "notes");
out.panel_of_nothing = panelFor(SALES_ROAD, "not_a_step");
out.road_for_sales = roadFor("sales") === SALES_ROAD;
// Every code any road can carry, driven against every registered road.
const HANDOVER = ["no_fence_drawn", "no_model_chosen", "customer_missing",
  "address_missing", "sold_by_missing", "sold_on_missing", "no_property_context",
  "gate_swing_unstated", "height_assumed", "base_assumed", "gates_contradicted",
  "promises_contradicted"];
const READINESS = ["sale_unread", "choices_unanswered", "no_run",
  "warnings_unreviewed", "supply_unresolved", "no_plan_committed", "plan_stale",
  "not_priced"];
// What each road is actually FED. The salesperson's screen never fetches the
// run-scoped half, so requiring her road to claim it would pin a rule nobody
// wants — and hide the one that matters, which is that a road must claim every
// code it DOES receive.
const FED = { sales: HANDOVER, backoffice: [...HANDOVER, ...READINESS] };
out.commits = Object.fromEntries(Object.entries(ROADS).map(([k, def_]) =>
  [k, Object.fromEntries(def_.steps.map((s) => [s.key, s.commits === true]))]));
out.orphan_totality = {};
out.unclaimed = {};
for (const [k, def] of Object.entries(ROADS)) {
  out.orphan_totality[k] = {};
  const claimed = new Set(def.steps.flatMap((s) => [...s.requires, ...s.wants]));
  out.unclaimed[k] = (FED[k] || []).filter((c) => !claimed.has(c));
  // Every code ANY road can carry is driven at every road, because not
  // throwing is a property of the engine and not of who is fed what.
  for (const c of [...HANDOVER, ...READINESS]) {
    try { road(def, [{code: c, params: {}, blocking: false}], {});
          out.orphan_totality[k][c] = "ok"; }
    catch (e) { out.orphan_totality[k][c] = "THREW"; }
  }
}
out.road_for_backoffice = roadFor("backoffice");
out.road_for_all = roadFor("all");
out.road_for_inherited = ["constructor", "toString", "hasOwnProperty"]
  .map((k) => roadFor(k));

out.claimed_codes = SALES_ROAD.steps.map((s) => [...s.requires, ...s.wants]);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_road_is_eight_steps_in_the_order_the_job_is_done(out):
    assert out["step_keys"] == ["job", "property", "layout", "sideview",
                                "model", "gates", "notes", "review"]


def test_every_step_works_on_the_drawing(out):
    """`notes` used to be the exception, and is not any more.

    Its surface was the Annotations TAB, whose form asked a salesperson to pick
    the target out of a `<select>` of run ids — so attaching "keep a post clear
    of that window" to the house meant knowing that the house is not in the
    list and that `r2` is the stretch along the street. The user's instruction
    is that a note is attached by CLICKING the thing it is about, which makes
    the map that step's surface like every other. The tab still exists for the
    office person; it is no longer where the promise is written down."""
    assert out["panels"] == {k: "canvas" for k in out["panels"]}


def test_the_engine_takes_no_project(out):
    """`road(roadDef, gaps, stated)`. The project argument existed only to
    compute `!drawn`, which `anchor` now names. Three arguments, and a fourth
    would mean somebody reached for the project again."""
    assert out["arity"] == 3


def test_every_handover_code_is_claimed_by_exactly_one_step(out):
    claimed = [c for step in out["claimed_codes"] for c in step]
    assert sorted(claimed) == sorted(HANDOVER_CODES), (
        "a code with no step vanishes from the road while the API still "
        "reports it; a step naming a code that does not exist reads done "
        "forever")
    assert len(claimed) == len(set(claimed)), "two steps claim one code"


def test_a_step_reads_unknown_until_the_handover_arrives(out):
    assert {s["state"] for s in out["unloaded"].values()} == {"unknown"}


def test_nothing_drawn_makes_every_other_step_empty_not_done(out):
    assert out["empty"]["layout"]["state"] == "blocked"
    others = {k: v["state"] for k, v in out["empty"].items() if k != "layout"}
    assert set(others.values()) == {"empty"}


def test_a_required_gap_is_missing_and_a_nice_to_have_is_not(out):
    job = out["gappy"]["job"]
    assert job["state"] == "missing"
    assert sorted(g["code"] for g in job["gaps"]) == [
        "customer_missing", "sold_by_missing"], (
        "a wants gap is CARRIED so the UI can show it, it just does not "
        "decide the state")


def test_a_step_whose_only_open_gap_is_a_want_reads_done(out):
    """`sold_by_missing` alone must not make step 1 amber."""
    assert out["gappy"]["sideview"]["state"] == "missing"   # height_assumed
    assert out["gappy"]["model"]["state"] == "done"


def test_a_stated_fact_makes_its_step_skipped(out):
    gates = out["skipped"]["gates"]
    assert gates["state"] == "skipped"
    assert gates["skippable"] is True
    assert gates["skipped"] is True


def test_only_a_step_with_satisfied_by_is_skippable(out):
    skippable = {k for k, v in out["clean"].items() if v["skippable"]}
    assert skippable == {"gates", "notes"}


def test_a_contradicted_claim_stops_being_a_skip(out):
    """The claim is stated but the drawing disagrees, so the `skipped` rung
    does not match and the question is reported instead."""
    gates = out["contradicted"]["gates"]
    assert gates["state"] == "missing"
    assert [g["code"] for g in gates["gaps"]] == ["gates_contradicted"]


def test_empty_beats_skipped(out):
    """Evidence outranks assertion: a job with nothing drawn has not started
    regardless of what it claims to lack."""
    assert out["empty_beats_skip"]["gates"]["state"] == "empty"


def test_a_code_no_step_claims_still_reaches_somebody(out):
    """Never reached while the totality test passes. It exists so that if one
    ever does reach a browser it is visible to the person who can act on it."""
    assert out["orphan"]["review"]["gaps"][0]["code"] == "invented_code"


def test_a_code_named_like_an_object_key_does_not_throw(out):
    assert out["proto"]["review"]["gaps"][0]["code"] == "constructor"


def test_panel_for_is_road_scoped(out):
    """A step this road does not define resolves to `null` rather than to some
    other road's step of the same name. (`notes` reads `canvas` now — see
    `test_every_step_works_on_the_drawing`.)"""
    assert out["panel_of_notes"] == "canvas"
    assert out["panel_of_nothing"] is None


def test_a_view_with_no_road_gets_none(out):
    """`all` is the engineer's view of the whole app and deliberately has no
    road: it is the view somebody chooses precisely to see everything at once,
    and a map over it would be claiming an order that view exists to escape.

    `backoffice` HAS one now. It read `None` from the day `roadFor` was written
    until the office road landed, which is what that null was always for —
    `roadFor` returns null rather than defaulting to the salesperson's, because
    "showing an office person a salesperson's map would be worse than showing
    them none"."""
    assert out["road_for_sales"] is True
    assert out["road_for_backoffice"] is not None
    assert out["road_for_all"] is None


def test_a_role_named_like_an_object_key_is_not_a_road(out):
    """`ROADS[role] || null` would hand back `Object` itself. `road()` guards
    gap codes the same way; both keys come from data."""
    assert out["road_for_inherited"] == [None, None, None]


def test_the_engine_imports_nothing():
    """The moment this file imports anything it can import coverage
    arithmetic, and then there are two answers to "is this job complete?"."""
    src = (STATIC / "js" / "road-model.js").read_text()
    assert not re.search(r"^\s*import\s", src, re.M), (
        "road-model.js must import nothing — put data in roads.js")


def test_no_registered_road_throws_on_a_code_no_step_of_it_claims(out):
    """The defect this file existed and did not catch.

    `ORPHAN_STEP` was the literal `"review"` — the salesperson's last step. The
    bucket map is built from THIS road's keys, so an unclaimed code on a road
    without a `review` step reached `held["review"].push` on `undefined` and
    threw. Four handover codes are unclaimed by the office road and one of them
    is `no_fence_drawn`, that road's own ANCHOR, so it fired on nearly every
    job — and `render()` calls `road()` before `build()`, so the band was never
    drawn at all.

    The old orphan test exercised `SALES_ROAD` only, which is exactly why 3184
    tests were green over a crash. This one drives EVERY registered road against
    EVERY code any road can carry.
    """
    for road_key, results in out["orphan_totality"].items():
        for code, outcome in results.items():
            assert outcome == "ok", f"{road_key} threw on {code}"


def test_every_road_claims_every_code_it_is_actually_fed(out):
    """Not throwing is the floor; landing somewhere a person will LOOK is the
    property.

    Per road, because the two are fed different things: the salesperson's screen
    never fetches the run-scoped half, so requiring her road to claim it would
    pin a rule nobody wants. What both must satisfy is that nothing they receive
    falls into the orphan bucket, where it is one line at the bottom of the last
    step instead of the thing that step is for.
    """
    for road_key, unclaimed in out["unclaimed"].items():
        assert unclaimed == [], f"{road_key} claims no step for: {unclaimed}"


def test_each_road_says_which_steps_carry_their_own_control(out):
    """Pinned in BOTH directions. The allowlist test below only looks at steps
    where `commits` is TRUE, so flipping one back to false — which is exactly
    what shipping a control undoes — makes its loop skip the step entirely."""
    assert out["commits"]["sales"] == {
        "job": True, "property": False, "layout": False, "sideview": False,
        "model": False, "gates": False, "notes": False, "review": False}
    assert out["commits"]["backoffice"] == {
        "sale": True, "blanks": False, "questions": False, "generate": True,
        "materials": False, "plan": True, "price": False}


def test_no_step_suppresses_the_done_button_without_having_its_own(out):
    """`commits: true` hides the road's Done button, on the grounds that the
    step "already has an explicit I-have-finished control of its own".

    Four office steps claimed it while their controls were unbuilt, which left
    those steps with no way to be finished at all — a road you cannot walk.
    Sales' step 1 earns it: `#job-panel` has a Save that advances.

    The rule is not "office steps may not commit"; it is that the claim must be
    true when it is made. A step flips to `true` in the commit that ships its
    button.
    """
    for road_key, steps in out["commits"].items():
        for step, commits in steps.items():
            if not commits:
                continue
            assert (road_key, step) in {
                ("sales", "job"),          # #job-panel's Save, which advances
                # `js/desk-actions.js`, shipped 2026-09-16 with these three:
                ("backoffice", "sale"),      # "I have read what she sold"
                ("backoffice", "generate"),  # "I have read these warnings"
                ("backoffice", "plan"),      # "Commit this plan"
            }, (
                f"{road_key}/{step} suppresses Done and has no control of its own")
