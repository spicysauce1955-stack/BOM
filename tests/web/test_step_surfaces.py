"""A road step scopes the screen to its own work (static/js/step-surfaces.js).

Built as navigation alone, the road moved an underline while the screen
underneath stayed identical: in `sales` every step showed all nine tools and
every side panel at once, and the user's verdict on seeing it was "not all the
buttons and options should show up in each step." `step-surfaces.js` is the
fix — each step names what it KEEPS, and the module derives what it hides.

The maps are keyed `{road key: {step key: [...]}}`, and that outer level is
load-bearing rather than tidy. Keyed on the step alone, as they were, a second
road naming a step `layout` got the salesperson's draw tool, and a step only
one road has got an empty keep list subtracted from the union of BOTH roads —
which hides everything. `road-model.js`'s `panelFor` was written road-scoped
from the start for the first of those two reasons; this module arrived at it
late, which is why the tests below name both failures.

The step keys checked here are the real ones `js/roads.js` defines
(`docs/superpowers/specs/2026-09-07-eight-step-road-design.md`), which is what
`document.documentElement.dataset.step` is ever actually set to. The surface
table in `docs/superpowers/specs/2026-09-06-salesperson-road-design.md` ("A
step SHOWS only its own work") predates the eight-step split and still names
six steps; `step-surfaces.js`'s own header comment records the direct
correspondence. Testing against the doc's stale six keys instead of the real
eight would pass while `property`, `sideview` and `model` sat completely
unscoped in the running app — green tests, and the bug the user rejected still
on screen for three of eight steps.

Three failure modes this file exists to catch, the first two mirroring
`test_view_module.py` and `test_view_sync.py` for the analogous view list:

- a step with no entry hides nothing and silently shows the whole app
  (`test_every_step_has_a_surface_list`);
- a selector nothing on the real page matches hides nothing, breaks no test,
  and looks fine on screen (`test_every_scoped_selector_exists`);
- a step key used by two roads, which the stylesheet cannot tell apart
  (`test_step_keys_are_unique_across_roads`) — see `test_the_two_copies_are_equal`
  for why that uniqueness is what lets the CSS stay keyed on the step alone.
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
import { STEP_HIDDEN, STEP_SCOPED, defaultToolForStep, hiddenForStep }
  from "./js/step-surfaces.js";
import { ROADS } from "./js/roads.js";

const out = {};
// Every road `step-surfaces.js` scopes — the outer level of its maps. It is
// allowed to know a road `ROADS` does not carry yet (that is how a road's
// surfaces land before the road does), but never the other way round.
out.surface_roads = Object.keys(STEP_HIDDEN);
// The union each road subtracts from, per road — the thing that must NOT
// be shared, and the only way to see that it is not while one road is empty.
out.scoped = STEP_SCOPED;
// The real step keys `road.js` ever sets `data-step` to, per road — not a
// list `step-surfaces.js` invents, since it imports nothing and cannot check
// itself against the roads it is scoping.
out.step_keys = {};
out.road_views = {};
for (const roadKey of Object.keys(ROADS)) {
  out.step_keys[roadKey] = ROADS[roadKey].steps.map((s) => s.key);
  out.road_views[roadKey] = ROADS[roadKey].view;
}
out.hidden = {};
out.tools = {};
for (const roadKey of out.surface_roads) {
  out.hidden[roadKey] = {};
  out.tools[roadKey] = {};
  for (const stepKey of Object.keys(STEP_HIDDEN[roadKey])) {
    out.hidden[roadKey][stepKey] = hiddenForStep(roadKey, stepKey);
    out.tools[roadKey][stepKey] = defaultToolForStep(roadKey, stepKey);
  }
}
out.unknown_step = hiddenForStep("sales", "nonsense-not-a-step");
out.unknown_road = hiddenForStep("nonsense-not-a-road", "layout");
// The collision, asked directly: `layout` is a real sales step and not an
// office one.
out.foreign_step = hiddenForStep("office", "layout");
out.foreign_tool = defaultToolForStep("office", "layout");
out.tool_unknown = defaultToolForStep("sales", "nonsense-not-a-step");
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
    `test_view_module.py`, which needed it for the same reason: an id can be
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
                r'html\[data-step="([\w-]+)"\]\s+([^,{\n]+)', block):
            out.setdefault(step, set()).add(selector.strip())
    return out


def _flat_hidden(out: dict) -> dict[str, set[str]]:
    """Every road's steps in one map, keyed on the step alone.

    Safe only because `test_step_keys_are_unique_across_roads` holds, and that
    is the same assumption `style.css` makes — which is the point of flattening
    here rather than reading the two-level map: this function fails the way the
    stylesheet would."""
    flat: dict[str, set[str]] = {}
    for steps in out["hidden"].values():
        for step, selectors in steps.items():
            flat.setdefault(step, set()).update(selectors)
    return flat


def test_two_roads_may_name_a_step_the_same_thing(out):
    """The collision this module's outer key exists to prevent.

    Sales step 3 is `layout`. An office road that also had a `layout` would,
    under a map keyed on the step alone, have been handed the salesperson's
    draw tool and her hide-list — silently, because a wrong hide-list still
    hides something and the screen looks deliberate.

    Asked of the office road while it has no `layout`, because "a road that
    does not have this step scopes nothing for it" is the same answer as "a
    road that has its own `layout` scopes its own" — one lookup, two roads,
    never a search over one global list (`road-model.js: panelFor`).
    """
    assert out["hidden"]["sales"]["layout"], "sales `layout` scopes nothing"
    assert out["foreign_step"] == [], out["foreign_step"]
    assert out["foreign_tool"] == "select", out["foreign_tool"]


def test_each_road_derives_its_hidden_lists_from_its_OWN_union(out):
    """The second failure the outer key prevents, and the quieter one.

    A step's hidden list is its keeps subtracted from the union of everything
    scoped — and that union has to be taken PER ROAD. Taken across all roads,
    a road whose own maps are still empty subtracts nothing from the other
    road's twenty-four selectors and hides every one of them, on every step:
    a blank screen produced by a map that says nothing. `STEP_SCOPED` is
    exported so this is checkable now rather than on the day the office road
    gets its first step, which is the day it would otherwise have shipped.
    """
    assert out["scoped"]["office"] == [], out["scoped"]["office"]
    assert out["scoped"]["sales"], "sales scopes nothing"
    for road, steps in out["hidden"].items():
        for step, selectors in steps.items():
            assert set(selectors) <= set(out["scoped"][road]), (road, step)


def test_the_office_road_has_a_surface_map_before_it_has_steps(out):
    """The shape, proven before anything depends on it.

    An empty inner map is the honest state for a road whose steps have not
    landed: every lookup degrades to nothing, which shows the whole screen
    rather than blanking it. The failure this pins is the other empty — a road
    key that is simply ABSENT, where `hiddenForStep` also returns nothing but
    for the reason that nobody noticed, and which would read identically right
    up to the moment the office road's surfaces were added under a key the
    module has never heard of.
    """
    assert "office" in out["surface_roads"], out["surface_roads"]


def test_a_road_key_is_its_view_key(out):
    """`road.js` hands `step-surfaces.js` the road's own `view` as the road
    key, because a module that imports nothing cannot look one up. If a road
    is ever registered under a key its `view` does not match, that handoff
    silently asks for surfaces nobody defined and every step shows everything.
    """
    for road, view in out["road_views"].items():
        assert view == road, (road, view)
        assert road in out["surface_roads"], road


def test_step_keys_are_unique_across_roads(out):
    """What lets `style.css` stay keyed on `html[data-step="X"]` alone.

    The JS maps are road-scoped and would survive a collision; the stylesheet
    cannot be, without every rule in it gaining a `[data-view]` and with it a
    specificity change across eight blocks of working CSS. So the collision is
    forbidden instead of accommodated — which is also what the office road's
    own design asks for: not one of its seven steps is a rename of hers.
    """
    seen: dict[str, str] = {}
    for road, steps in out["step_keys"].items():
        for step in steps:
            assert step not in seen, f"{step} is in both {seen[step]} and {road}"
            seen[step] = road


def test_every_step_has_a_surface_list(out):
    """A step with no entry scopes nothing and silently shows the whole app —
    which is the state the user rejected. Checked per road, against the steps
    that road actually defines."""
    for road, steps in out["step_keys"].items():
        assert set(steps) == set(out["hidden"][road]), road


def test_an_unknown_step_hides_nothing_rather_than_everything(out):
    """The same degrade-to-nothing rule `view.js: hiddenFor` uses for an
    unrecognised view: a stored preference from a future version, or a typo,
    must not blank the screen. An unknown ROAD degrades the same way, and it is
    the likelier typo now that there are two keys to get wrong."""
    assert out["unknown_step"] == []
    assert out["unknown_road"] == []


def test_every_scoped_selector_exists(out):
    """The assertion that earns this file, and the same one
    `test_view_module.py` makes: a selector matching nothing hides nothing,
    breaks no test, and looks fine on screen."""
    ids = _live_ids()
    for road, steps in out["hidden"].items():
        for step, selectors in steps.items():
            for sel in selectors:
                assert sel.startswith("#"), f"{road}/{step}: {sel!r} is not an id"
                assert sel[1:] in ids, f"{road}/{step}: no element {sel}"


def test_the_job_step_hides_every_tool(out):
    """Step 1 offers no drawing tools, so the canvas must not edit — a canvas
    that edits with no tool selected makes the scoping a lie."""
    for tool in ("#tool-draw", "#tool-gate", "#tool-base", "#tool-ground",
                 "#tool-height", "#tool-model", "#tool-house", "#tool-street"):
        assert tool in out["hidden"]["sales"]["job"], tool


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
            assert tool not in out["hidden"]["sales"][step], f"{step} needs {tool}"


MAP_STEPS = {"property", "layout", "sideview", "model", "gates", "notes"}


def test_the_generate_bar_follows_the_drawing_except_on_notes(out):
    """The one step that shows the map without the button that recomputes it.
    Named on purpose: `#generate-toolbar` sitting in `DRAWING` for six steps
    and separately for the seventh is the kind of near-copy that drifts, so if
    somebody folds `notes` back into `DRAWING` this says what breaks."""
    sales = out["hidden"]["sales"]
    bar_shown = {s for s in sales if "#generate-toolbar" not in sales[s]}
    assert bar_shown == MAP_STEPS - {"notes"}


def test_each_step_arms_a_tool_its_own_rail_offers(out):
    """A tool used to survive the step that offered it, and the screen then
    lied about what the next click would do: the gate tool armed on step 6 was
    still armed on step 7, where clicking the house to write a note on it
    placed a gate — on a step whose rail does not show the gate button at all.
    Hiding a control does not disarm it.

    The invariant, not the table: whatever a step arms, that step must not be
    hiding it. `#tool-select` is never scoped (no step hides it), so the
    neutral answer is always admissible. Checked for every road, because a road
    arming a tool out of another road's map is exactly the collision above.
    """
    for road, tools in out["tools"].items():
        for step, tool in tools.items():
            if tool == "select":
                continue
            assert f"#tool-{tool}" not in out["hidden"][road][step], (road, step, tool)


def test_a_step_whose_whole_job_is_one_tool_arms_it(out):
    """Derived from `STEP_TOOLS`, so it cannot drift from what the rail shows:
    exactly one kept tool means the step IS that tool. Several, or none, has no
    single answer and gets `select` — including a step nobody has heard of,
    which must degrade like every other unknown key in this module."""
    assert out["tools"]["sales"] == {
        "job": "select", "property": "select", "layout": "draw",
        "sideview": "select", "model": "model", "gates": "gate",
        "notes": "note", "review": "select"}
    assert out["tool_unknown"] == "select"


def test_the_road_band_is_never_scoped_away(out):
    """The band is the only navigation this mode has — `#tabs` is hidden for it
    — so a step that hid the band would strand a keyboard user completely."""
    for road, steps in out["hidden"].items():
        for step, selectors in steps.items():
            assert "#road" not in selectors, (road, step)


def test_the_drawing_is_scoped_to_the_steps_whose_work_is_on_it(out):
    """Steps 2-7, and nowhere else.

    This REVERSES the earlier rule that the drawing stays on screen throughout,
    on instruction: steps 1 and 8 are a form and a summary, and a map behind
    them invites a click that does nothing while making step 1 read as "draw
    something" when the only thing to do is type an address.

    Step 7 has since come BACK onto the list, by the same authority. A note is
    attached by clicking the thing it is about — the house, a stretch, the
    ground by the gate — so there the map is not furniture, it is the surface.
    What that step still hides is `#generate-toolbar`: working out the fence is
    step 8's business, and a note is written about what is already drawn.
    """
    sales = out["hidden"]["sales"]
    shown = {s for s in sales if "#canvas" not in sales[s]}
    assert shown == MAP_STEPS, (
        f"the map should be in {sorted(MAP_STEPS)}, it is in {sorted(shown)}")


def test_step_and_role_lists_stay_independent(out):
    """`data-view` answers who is looking; `data-step` answers what they are
    doing now. Merged, "is the inspector visible?" would have six answers.

    The road key this module now takes is NOT that merge: it says which MAP a
    step belongs to, and the caller supplies it. This module still never asks
    who is looking.
    """
    src = (STATIC / "js" / "step-surfaces.js").read_text()
    assert "role" not in src.lower().replace("view.js", ""), (
        "step-surfaces.js must not reason about views")


def test_the_two_copies_are_equal(out):
    """`test_view_sync.py`'s rule, applied to steps: CSS cannot read a JS
    array, so the list exists twice and the copies must be EQUAL.

    The stylesheet is keyed on the step alone while the module is keyed on the
    road and the step, so this compares a FLATTENED module map — which is sound
    exactly while `test_step_keys_are_unique_across_roads` passes, and which is
    why that test is the one that fails first if a road ever reuses a key.
    """
    css = _from_css_steps()
    js = _flat_hidden(out)
    for step, selectors in js.items():
        assert css.get(step, set()) == selectors, (
            f"{step}: step-surfaces.js and style.css disagree — "
            f"only in step-surfaces.js: {selectors - css.get(step, set())}, "
            f"only in style.css: {css.get(step, set()) - selectors}")
    # and nothing in the stylesheet names a step no road has
    assert set(css) <= set(js)
