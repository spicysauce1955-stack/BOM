"""The road's render layer (static/js/road.js) — label coverage.

`road.js` touches the DOM, so its actual rendering is the browser smoke's job
(the ui_smoke suite). What is worth pinning here, without a browser, is the
thing that fails silently: a step whose label key is missing renders its own
key (`road.sideview`) to a salesperson instead of a name.
"""

from __future__ import annotations

import json
from pathlib import Path

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


def test_the_badge_keys_off_state_not_skipped():
    """`state` and `skipped` are deliberately decoupled: a contradicted claim
    (`no_gates` stated but the drawing has a gate) reads `state === "missing"`
    while `skipped` stays `true`. The badge must key off `state` only, or a
    contradicted claim shows a tidy "you said none" and the unexpected gate
    reaches the office unmentioned. The `state === "skipped"` branch must also
    come before the `gaps.length` branch."""
    src = (STATIC / "js" / "road.js").read_text()
    assert "step.skipped" not in src, (
        "the badge must not key off `skipped` — that decouples it from a "
        "contradicted claim's real state")
    skipped_at = src.index('step.state === "skipped"')
    gaps_at = src.index("step.gaps.length")
    assert skipped_at < gaps_at, (
        "the skipped branch must come before the gaps.length branch")
