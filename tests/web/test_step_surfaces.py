"""A road step scopes the screen to its own work (static/js/step-surfaces.js).

Built as navigation alone, the road moved an underline while the screen
underneath stayed identical: in `sales` every step showed all nine tools and
every side panel at once, and the user's verdict on seeing it was "not all the
buttons and options should show up in each step." `step-surfaces.js` is the
fix — each step names what it KEEPS, and the module derives what it hides.

The step keys checked here are the eight real ones `js/roads.js: SALES_ROAD`
defines (`docs/superpowers/specs/2026-09-07-eight-step-road-design.md`), which
is what `document.documentElement.dataset.step` is ever actually set to. The
surface table in `docs/superpowers/specs/2026-09-06-salesperson-road-design.md`
("A step SHOWS only its own work") predates that split and still names six
steps; `step-surfaces.js`'s own header comment records the direct
correspondence. Testing against the doc's stale six keys instead of the real
eight would pass while `property`, `sideview` and `model` sat completely
unscoped in the running app — green tests, and the bug the user rejected still
on screen for three of eight steps.

Two failure modes this file exists to catch, mirroring `test_role_module.py`
and `test_role_sync.py` for the analogous role list:

- a step with no entry hides nothing and silently shows the whole app
  (`test_every_step_has_a_surface_list`);
- a selector nothing on the real page matches hides nothing, breaks no test,
  and looks fine on screen (`test_every_scoped_selector_exists`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { STEP_HIDDEN, hiddenForStep } from "./js/step-surfaces.js";
import { ROADS } from "./js/roads.js";

const out = {};
// The real step keys `road.js` ever sets `data-step` to — not a list
// `step-surfaces.js` invents, since it imports nothing and cannot check
// itself against the road it is scoping.
out.step_keys = ROADS.sales.steps.map((s) => s.key);
out.hidden = {};
for (const key of out.step_keys) out.hidden[key] = hiddenForStep(key);
out.unknown = hiddenForStep("nonsense-not-a-step");
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _live_ids() -> set[str]:
    """Every id the running app actually has — copied from
    `test_role_module.py`, which needed it for the same reason: an id can be
    real and absent from `index.html`, created instead by the module that
    owns it (`#choices`, `#job-panel`, `#context-panel`, `#handover-panel`)."""
    ids = set(re.findall(r'id="([^"]+)"', (STATIC / "index.html").read_text()))
    for mod in (STATIC / "js").glob("*.js"):
        src = mod.read_text()
        ids |= set(re.findall(r'\.id\s*=\s*"([^"]+)"', src))
        ids |= set(re.findall(r'"id":\s*"([^"]+)"', src))
        ids |= set(re.findall(r'\bid:\s*"([^"]+)"', src))
        ids |= set(re.findall(r'id="([^"{}]+)"', src))
    return ids


def _from_css_steps() -> dict[str, set[str]]:
    """Every `html[data-step="X"] <selector>` in the stylesheet, per step.

    Parsed per RULE BLOCK rather than per line, because one rule in this
    stylesheet uses the same `html[data-step="X"] selector` shape without
    hiding anything: `html[data-step="job"] #canvas { pointer-events: none }`
    makes the canvas read-only where no tool is offered. Sweeping that into
    the hidden set would fail `test_the_two_copies_are_equal` for a selector
    that is deliberately never hidden — `#canvas` stays on screen in every
    step — so only blocks that actually say `display: none` are counted.
    """
    css = (STATIC / "style.css").read_text()
    out: dict[str, set[str]] = {}
    for block in re.split(r"(?<=})", css):
        if "display: none" not in block:
            continue
        for step, selector in re.findall(
                r'html\[data-step="(\w+)"\]\s+([^,{\n]+)', block):
            out.setdefault(step, set()).add(selector.strip())
    return out


def test_every_step_has_a_surface_list(out):
    """A step with no entry scopes nothing and silently shows the whole app —
    which is the state the user rejected."""
    assert set(out["step_keys"]) == set(out["hidden"])


def test_an_unknown_step_hides_nothing_rather_than_everything(out):
    """The same degrade-to-nothing rule `role.js: hiddenFor` uses for an
    unrecognised role: a stored preference from a future version, or a typo,
    must not blank the screen."""
    assert out["unknown"] == []


def test_every_scoped_selector_exists(out):
    """The assertion that earns this file, and the same one
    `test_role_module.py` makes: a selector matching nothing hides nothing,
    breaks no test, and looks fine on screen."""
    ids = _live_ids()
    for step, selectors in out["hidden"].items():
        for sel in selectors:
            assert sel.startswith("#"), f"{step}: {sel!r} is not an id"
            assert sel[1:] in ids, f"{step}: no element {sel}"


def test_the_job_step_hides_every_tool(out):
    """Step 1 offers no drawing tools, so the canvas must not edit — a canvas
    that edits with no tool selected makes the scoping a lie."""
    for tool in ("#tool-draw", "#tool-gate", "#tool-base", "#tool-ground",
                 "#tool-height", "#tool-model", "#tool-house", "#tool-street"):
        assert tool in out["hidden"]["job"], tool


def test_each_step_keeps_the_tools_it_needs(out):
    """The doc's six-step table groups these under `layout` (draw, house,
    street) and `details` (ground, base, height, model); the real road splits
    them into `property` / `layout` and `sideview` / `model` (see this file's
    module docstring). The assertion is the same either way: a step must not
    hide the tool its own work needs."""
    keeps = {"property": ["#tool-house", "#tool-street"],
             "layout": ["#tool-draw"],
             "sideview": ["#tool-ground", "#tool-base", "#tool-height"],
             "model": ["#tool-model"],
             "gates": ["#tool-gate"]}
    for step, tools in keeps.items():
        for tool in tools:
            assert tool not in out["hidden"][step], f"{step} needs {tool}"


def test_the_drawing_is_never_scoped_away(out):
    """The place stays on screen in every step. A form on an empty screen is
    the "project 7" problem one layer up."""
    for step, selectors in out["hidden"].items():
        assert "#canvas" not in selectors, step
        assert "#road" not in selectors, step


def test_step_and_role_lists_stay_independent(out):
    """`data-role` answers who is looking; `data-step` answers what they are
    doing now. Merged, "is the inspector visible?" would have six answers."""
    src = (STATIC / "js" / "step-surfaces.js").read_text()
    assert "role" not in src.lower().replace("role.js", ""), (
        "step-surfaces.js must not reason about roles")


def test_the_two_copies_are_equal(out):
    """`test_role_sync.py`'s rule, applied to steps: CSS cannot read a JS
    array, so the list exists twice and the copies must be EQUAL."""
    css = _from_css_steps()
    for step in out["step_keys"]:
        js = set(out["hidden"][step])
        assert css.get(step, set()) == js, (
            f"{step}: step-surfaces.js and style.css disagree — "
            f"only in step-surfaces.js: {js - css.get(step, set())}, "
            f"only in style.css: {css.get(step, set()) - js}")
    # and nothing in the stylesheet names a step this module does not know
    assert set(css) <= set(out["step_keys"])
