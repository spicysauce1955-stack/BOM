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
out.road_for_office = roadFor("office");
out.road_for_all = roadFor("all");

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


def test_notes_is_the_one_step_whose_surface_is_another_panel(out):
    assert out["panels"]["notes"] == "annotations"
    assert {k: v for k, v in out["panels"].items() if k != "notes"} == {
        k: "canvas" for k in out["panels"] if k != "notes"}


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
    assert out["panel_of_notes"] == "annotations"
    assert out["panel_of_nothing"] is None


def test_a_role_with_no_road_gets_none(out):
    assert out["road_for_sales"] is True
    assert out["road_for_office"] is None
    assert out["road_for_all"] is None


def test_the_engine_imports_nothing():
    """The moment this file imports anything it can import coverage
    arithmetic, and then there are two answers to "is this job complete?"."""
    src = (STATIC / "js" / "road-model.js").read_text()
    assert not re.search(r"^\s*import\s", src, re.M), (
        "road-model.js must import nothing — put data in roads.js")
