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
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.report.handover import HANDOVER_CODES

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
// No stubs: road-model.js imports nothing, which is why it is its own file.
import { GAP_STEPS, STEPS, road } from "./js/road-model.js";

const run = (id) => ({ id, interval_events: [], point_events: [] });
const proj = (...runs) => ({ topology: { runs }, context: { landmarks: [] } });
const hv = (...gaps) => ({ gaps, estimate_ready: !gaps.some((g) => g.blocking) });
const byKey = (r) => Object.fromEntries(r.map((s) => [s.key, s]));

const out = {};
out.step_keys = STEPS.map((s) => s.key);
out.panels = Object.fromEntries(STEPS.map((s) => [s.key, s.panel]));
out.gap_steps = GAP_STEPS;

// nothing drawn, nothing said
out.empty = byKey(road(proj(), hv({ code: "no_fence_drawn", blocking: true })));

// a drawn job missing four identity fields and a height
const gappy = road(proj(run("run1")), hv(
  { code: "customer_missing" }, { code: "address_missing" },
  { code: "height_assumed", params: { runs: 1, run_ids: ["run1"] } },
));
out.gappy = byKey(gappy);
out.gappy_job_codes = byKey(gappy).job.gaps.map((g) => g.code);

// everything answered
out.clean = byKey(road(proj(run("run1")), hv()));

// role gate
out.office = road(proj(run("run1")), hv(), "office");
out.all = road(proj(run("run1")), hv(), "all");

// a code the road has never heard of must not vanish silently
out.unknown = byKey(road(proj(run("run1")), hv({ code: "invented_code" })));

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


def test_the_road_is_six_steps_in_the_order_the_job_is_done(out):
    assert out["step_keys"] == ["job", "layout", "details", "gates", "notes",
                                "review"]


def test_notes_is_the_one_step_whose_surface_is_another_panel(out):
    """The reason the tab strip goes. With it kept, Notes would be reached by a
    TAB while every other step was reached by the road, and the road could never
    say whether a promise made during the sale was written down."""
    assert out["panels"]["notes"] == "annotations"
    assert {v for k, v in out["panels"].items() if k != "notes"} == {"canvas"}


def test_every_handover_code_belongs_to_exactly_one_step(out):
    """Spec invariant 1. A code with no step vanishes from the road while the
    panel still reports it — the silent class this repo has shipped green four
    times."""
    assert set(out["gap_steps"]) == set(HANDOVER_CODES), {
        "unmapped": sorted(set(HANDOVER_CODES) - set(out["gap_steps"])),
        "invented": sorted(set(out["gap_steps"]) - set(HANDOVER_CODES)),
    }
    assert set(out["gap_steps"].values()) <= set(out["step_keys"])


def test_a_blocking_gap_makes_its_step_blocked(out):
    assert out["empty"]["layout"]["state"] == "blocked"


def test_a_step_owns_its_own_gaps_and_no_others(out):
    assert sorted(out["gappy_job_codes"]) == ["address_missing",
                                              "customer_missing"]
    assert out["gappy"]["job"]["state"] == "missing"
    assert out["gappy"]["details"]["state"] == "missing"
    assert out["gappy"]["gates"]["state"] == "done"


def test_a_step_with_no_gaps_is_done(out):
    for key in out["step_keys"]:
        assert out["clean"][key]["state"] == "done", key


def test_the_road_refuses_a_role_it_has_no_road_for(out):
    """The office person's road and the super user's are unwritten. Defaulting
    to the salesperson's would show the wrong person the wrong map."""
    assert out["office"] is None
    assert out["all"] is None


def test_an_unmapped_code_lands_on_review_rather_than_disappearing(out):
    """Belt and braces beside the totality test: if a code ever reaches the
    browser without a step, it must still be visible to the person who can act
    on it."""
    assert "invented_code" in [g["code"] for g in out["unknown"]["review"]["gaps"]]


def test_road_computes_no_coverage(out):
    """Spec invariant 2. One answer to "is this job complete?", and it is
    handover.py's. The moment this module does interval arithmetic there are
    two."""
    src = (STATIC / "js" / "road-model.js").read_text()
    for forbidden in ("uncovered", "_uncovered_mm", "interval_events",
                      "anchor_station"):
        assert forbidden not in src, (
            f"road-model.js must not reason about coverage; found {forbidden!r}")


def test_the_model_half_imports_nothing():
    """It is a separate file so it can be tested in node without stubbing a
    DOM — `base-top.js` / `profile.js`, the pattern CLAUDE.md names. One import
    of a rendering module and this test's harness needs `document`,
    `localStorage` and `fetch` for a loop over gap codes."""
    src = (STATIC / "js" / "road-model.js").read_text()
    assert "import " not in src, "road-model.js must import nothing"
    assert "document" not in src


# NOTE: `test_road_reaches_no_panel_dom` belongs to Task 4, which creates
# `road.js`. Adding it here would fail on a file that does not exist yet.
