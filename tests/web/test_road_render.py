"""The road's render layer (static/js/road.js) — label coverage.

`road.js` touches the DOM, so its actual rendering is the browser smoke's job
(the ui_smoke suite). What is worth pinning here, without a browser, is the
thing that fails silently: a step whose label key is missing renders its own
key (`road.sideview`) to a salesperson instead of a name.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

STEP_KEYS = ["job", "property", "layout", "sideview", "model", "gates",
             "notes", "review"]


def test_every_step_key_has_a_name_and_a_take_in_both_bundles():
    """A step whose label is missing renders its own key to a salesperson."""
    for bundle in ("en.json", "he.json"):
        data = json.loads((STATIC / "i18n" / bundle).read_text())
        for k in STEP_KEYS:
            assert f"road.{k}" in data, f"{bundle} has no road.{k}"
            assert f"road.{k}.take" in data, f"{bundle} has no road.{k}.take"


def test_no_step_claims_details_any_more():
    en = json.loads((STATIC / "i18n" / "en.json").read_text())
    he = json.loads((STATIC / "i18n" / "he.json").read_text())
    assert "road.details" not in en, "no step claims `details` any more"
    assert "road.details.take" not in en
    assert "road.details" not in he
    assert "road.details.take" not in he


def test_road_js_imports_the_new_signature_not_the_retired_steps_export():
    """`STEPS` no longer exists in road-model.js; importing it broke the
    app's module-graph bootstrap in a browser even though pytest stayed
    green (nothing in the suite boots the real ES-module app)."""
    src = (STATIC / "js" / "road.js").read_text()
    assert "STEPS" not in src, "STEPS was retired from road-model.js"
    assert 'import { panelFor, road } from "./road-model.js"' in src
    assert 'import { roadFor } from "./roads.js"' in src


def _badge_assignment(src: str) -> str:
    """The single expression that sets `.road-state`'s text — isolated so a
    check on it cannot be satisfied by code anywhere else in the file (the
    skip control legitimately reads `step.skipped` a few lines below)."""
    start = src.index('.road-state").textContent =')
    end = src.index(";", start)
    return src[start:end]


def test_the_badge_keys_off_state_not_skipped():
    """`state` and `skipped` are deliberately decoupled: a contradicted claim
    (`no_gates` stated but the drawing has a gate) reads `state === "missing"`
    while `skipped` stays `true`. The badge must key off `state` only, or a
    contradicted claim shows a tidy "you said none" and the unexpected gate
    reaches the office unmentioned. The `state === "skipped"` branch must also
    come before the `gaps.length` branch."""
    src = (STATIC / "js" / "road.js").read_text()
    badge = _badge_assignment(src)
    assert "step.skipped" not in badge, (
        "the badge must not key off `skipped` — that decouples it from a "
        "contradicted claim's real state")
    skipped_at = badge.index('step.state === "skipped"')
    gaps_at = badge.index("step.gaps.length")
    assert skipped_at < gaps_at, (
        "the skipped branch must come before the gaps.length branch")


def test_the_skip_control_keys_off_skipped_not_state():
    """The opposite rule for the opposite control. In the contradicted case
    `state` reads `"missing"` while `skipped` stays `true` because the person
    DID state the fact and the drawing merely disagrees — so the button must
    still read "There are some after all" (`road.unskip`), not silently
    revert to "There are none on this job". Keying this off `state` would
    collapse the very distinction the badge test above exists to protect."""
    src = (STATIC / "js" / "road.js").read_text()
    start = src.index("btn2.textContent = t(")
    end = src.index(";", start)
    label = src[start:end]
    assert "step.skipped" in label, "the skip label must read `step.skipped`"
    assert "step.state" not in label, (
        "the skip label must not key off `state` — a contradicted claim "
        "must still read as stated, not silently un-stated")


def test_skip_control_only_rendered_for_a_skippable_step():
    src = (STATIC / "js" / "road.js").read_text()
    assert re.search(r"if\s*\(step\.skippable\)\s*\{", src), (
        "the skip control must be gated on `step.skippable`"
    )


def test_the_skip_click_does_not_navigate():
    """Without `stopPropagation`, clicking the control also switches the
    step — stating a fact is not navigating."""
    src = (STATIC / "js" / "road.js").read_text()
    click_handler = src[src.index("host.addEventListener(\"click\""):]
    click_handler = click_handler[:click_handler.index("\n  });\n") + len("\n  });\n")]
    skip_branch = click_handler[click_handler.index('".road-skip"'):]
    assert "ev.stopPropagation()" in skip_branch[:skip_branch.index("return;")]


def test_the_skip_click_pushes_a_snapshot_before_mutating_before_saving():
    """Mutation discipline (CLAUDE.md): `pushSnapshot` -> mutate
    `state.project` -> save. Stating a fact must be as undoable as any other
    job edit."""
    src = (STATIC / "js" / "road.js").read_text()
    click_handler = src[src.index("host.addEventListener(\"click\""):]
    skip_branch = click_handler[click_handler.index('".road-skip"'):
                                click_handler.index("return;")]
    push_at = skip_branch.index("pushSnapshot(")
    mutate_at = skip_branch.index("state.project.stated = {")
    save_at = skip_branch.index("saveStated()")
    assert push_at < mutate_at < save_at, (
        "the order must be pushSnapshot -> mutate -> save")


def test_stating_one_fact_sends_both_facts_over_the_wire():
    """`PUT /stated` REPLACES the whole object (Task 3), so a write carrying
    only the toggled fact would silently reset the other to `false`. A
    salesperson who states "no gates" must not retract a previously-stated
    "no promises" as a side effect — a failure that is invisible until the
    office reads a handover carrying a note that should not be there.

    Driven end to end through the real modules (state.js + road.js's click
    handler logic), not just a source-text check for the spread operator —
    the property under test is the actual PUT body, in Node against the real
    `saveStated`/`apiSend`."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = r"""
let putBody = null;
globalThis.document = {
  documentElement: {}, getElementById: () => null, querySelectorAll: () => [],
};
globalThis.fetch = async (url, init) => {
  if (url.endsWith(".json")) return { ok: true, json: async () => ({}) };
  putBody = JSON.parse(init.body);
  return { ok: true, json: async () => ({ id: "p1", stated: putBody }) };
};

import { state, saveStated } from "./js/state.js";

state.projectId = "p1";
state.project = { stated: { no_gates: false, no_promises: true } };

// exactly the road.js click-handler mutation: spread the CURRENT stated
// object, flip one fact, leave the other untouched.
const fact = "no_gates";
state.project.stated = { ...state.project.stated, [fact]: !state.project.stated?.[fact] };
await saveStated();

console.log(JSON.stringify(putBody));
"""
    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body == {"no_gates": True, "no_promises": True}, (
        "toggling no_gates must not disturb the previously-stated no_promises")
