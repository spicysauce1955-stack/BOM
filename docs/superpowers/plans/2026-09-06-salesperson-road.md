# The Salesperson's Road Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `sales` role a six-step road that is the only navigation on the screen, whose per-step state is derived from the handover gaps rather than computed a second time.

**Architecture:** Two modules, following `base-top.js` / `profile.js`: **`js/road-model.js` is pure** — no imports, no DOM — and groups what `handover_gaps()` already returns into six steps; **`js/road.js`** renders it and activates panels through a new `setTab()` export on `tabs.js`. The split is not tidiness: it is what lets the step model be tested in node without stubbing a DOM, and what keeps "which step owns which gap" readable in one screen. `#tabs` is hidden for `sales` via the existing `role.js` hide-list. `js/checklist.js` is deleted, and the handover panel's gap rows move to the road while its estimate stays put.

**Tech Stack:** Vanilla ES modules, no build step; Python 3.12 + FastAPI + Pydantic v2; pytest; node-driven frontend unit tests; CDP browser smoke.

**Spec:** `docs/superpowers/specs/2026-09-06-salesperson-road-design.md`

## Scope: this plan is ONE slice, and here is everything it leaves out

This plan builds **the navigation**: six steps, derived state, the strip gone, one surface answering *what is left*. It ends with the user opening the app and walking the road.

Four parts of the spec are deliberately NOT here. Each is named with where it goes, because a deferral nobody wrote down is indistinguishable from an omission:

| Spec section | Why not now |
|---|---|
| **"Silent defaults must LOOK silent" (U05)** | Independent of navigation and independently valuable. See below — it has its own hazards and its own plan. |
| **"Step 3, in detail: Ground, Base, Fence"** | Regrouping four existing tools under one panel is a second, self-contained UI change. The road can name step 3 and select the stretch before the panel behind it is rearranged. Next plan after U05. |
| **The per-stretch summary card (U03)** | Depends on step 3's panel existing. Same plan as the regrouping. |
| **"What else to lift from the storyboard"** — Plan-zoom scope label, unfolded-elevation caption with the corner marked, drawing legend, job bar | Five independent polish items, none of which the road needs. They are cheap and should be one small plan of their own once the road is real. |

Bundling any of these would produce exactly the failure `docs/superpowers/specs/2026-09-04-sales-mvp-design.md` was written about: a large correct change the user first sees at the end.

### The deferred U05 plan must record these

`2026-09-07-silent-defaults.md` (not yet written) must carry the governing rule this plan's research established:

> **A field seeded from a real reading stays seeded; a field seeded from a policy default opens empty.**
> `pop-start`/`pop-end` (0 and run length), `pop-z` (the node's actual elevation) and `pop-width` (the kit's declared opening) are readings. `1800` (`editor.js:870`) and `soil` (`editor.js:846-850`, by option order) are policy defaults.

That deferred plan must also handle two hazards found here:
1. `base` is absent from `save()`'s `needed` allowlist (`editor.js:903-905`) **and** its handler deletes the run's existing `base` and `post_tilt` events *before* writing (`editor.js:927-930`). An empty `<select>` yields `""`, passes the absent guard, wipes both events locally, then 422s on `BasePayload.surface`. Guard **and** reorder, or an untouched form is a destructive no-op.
2. `soil` exists as three unshared literals (`topology/station.py:261`, `report/handover.py:40`, `editor.js:847`) and `1800` as two (`strategy/generator.py:97`, `editor.js:870`). The spec's invariant "popover defaults and gap codes name the same set" cannot be tested while they are copies.
3. `tools/ui_smoke.py:3200-3214` asserts a blank height field is `.invalid`. Under the rule above a blank height is *unstated*, not invalid — that check inverts and must be rewritten, not deleted (its "no null reaches the API" half stays true).

## Global Constraints

Copied from `CLAUDE.md` and the spec. Every task's requirements implicitly include these.

- **Integer millimetres at rest, float only transient** (ADR-0002). No length is stored or PUT as a float.
- **ES modules communicate ONLY via `state.js`** (events + exports). No module touches another module's DOM subtree.
- **`road.js` may never compute coverage.** `_uncovered_mm` is `report/handover.py`'s, and one answer to *is this job complete?* is the point of the module.
- **Every user-visible string goes through `t()` / `tu()` or `data-i18n`.** `i18n/he.json` and `en.json` must keep identical key sets.
- **Locale keys for this feature are named `road.*`, never `sales.road.*`.** A `sales.` prefix requires the plain key to also exist AND the module to subscribe to `role-changed`; it buys nothing on a surface that only renders for `sales`.
- **No literal `mm`/`cm`/`מ"מ`/`ס"מ` in any bundle value** (`test_lengths_carry_the_unit_placeholder_not_a_literal`). A string carrying `{u}` or `{c}` must be rendered with `tu()`, not `t()`.
- **Bundle keys sit at exactly two-space top-level indent**, are non-empty in both bundles, and contain no `\uXXXX` escapes.
- **CSS uses logical properties only** (`margin-inline-start`, not `margin-left`). The plan canvas and profile SVG are NEVER mirrored in RTL.
- **Any id that lands on a hide-list must be a literal string in its template** — `test_role_module.py::_live_ids` scans `id="([^"{}]+)"`, so an interpolated id is invisible to it.
- **Mutation discipline:** `pushSnapshot(label)` → mutate `state.project` → `saveTopology()`. Non-user changes never push history; use `reloadProject()`, not `openProject()`.
- Run: `uv run pytest -q` (full suite, currently 2540 passing) and `uv run --with websocket-client python tools/ui_smoke.py` (currently 344/344).

---

### Task 1: `setTab()` — the seam the road switches panels through

`tabs.js` has no programmatic switcher today; the only two programmatic sites `.click()` a button (`editor.js:1604`, and ~57 sites in `ui_smoke.py`). `road.js` must not do that — a `.click()` on a `display:none` button is exactly the reach-into-another-subtree the module map forbids.

**Files:**
- Modify: `src/fenceai/web/static/js/tabs.js:22-33`
- Test: `tests/web/test_tabs_module.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `export function setTab(name: string): void` — activates `#tabs button[data-tab=name]` and `#tab-<name>`, calls the three lazy renderers, emits `tab-changed`. Inert (returns without emitting) when either element is missing.

- [ ] **Step 1: Write the failing test**

Create `tests/web/test_tabs_module.py`:

```python
"""One path switches a tab (static/js/tabs.js).

`road.js` has to activate the annotations panel, and the only way to do that
today is `.click()` on a button — which, once `#tabs` is hidden for sales, is a
module reaching into a subtree it does not own to poke an invisible element.

So the switch becomes an export, and the click handler calls it. This test holds
the property that makes the export worth having: there is ONE place that moves
the `active` class, so the road and the strip can never disagree about which
panel is showing.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"


def test_tabs_exports_a_programmatic_switch():
    src = (STATIC / "js" / "tabs.js").read_text()
    assert re.search(r"^export function setTab\(", src, re.M), (
        "road.js needs a way to switch panels that is not a click on a hidden "
        "button")


def test_only_set_tab_moves_the_active_class():
    """A second site that adds `.active` to a `.tab` is a second answer to
    which panel is showing. The click handler must delegate, not duplicate."""
    for mod in (STATIC / "js").glob("*.js"):
        src = mod.read_text()
        for line_no, line in enumerate(src.splitlines(), 1):
            if 'classList.add("active")' not in line:
                continue
            assert mod.name == "tabs.js", f"{mod.name}:{line_no} moves .active"
    body = (STATIC / "js" / "tabs.js").read_text()
    set_tab = body[body.index("export function setTab("):]
    set_tab = set_tab[:set_tab.index("\n}\n") + 1]
    assert set_tab.count('classList.add("active")') == 2, (
        "setTab activates exactly the button and its panel")


def test_the_click_handler_delegates_to_set_tab():
    src = (STATIC / "js" / "tabs.js").read_text()
    init = src[src.index("export function initTabs("):]
    init = init[:init.index("\n}\n") + 1]
    assert "setTab(" in init, "initTabs must call setTab, not repeat it"
    assert 'emit("tab-changed"' not in init, (
        "the emit belongs to setTab, or a programmatic switch is silent")


def test_an_unknown_panel_name_is_inert():
    """Spec invariant 8. A step naming a panel that does not exist must be a
    no-op, not a thrown error that stops the road rendering the other five."""
    src = (STATIC / "js" / "tabs.js").read_text()
    set_tab = src[src.index("export function setTab("):]
    set_tab = set_tab[:set_tab.index("\n}\n") + 1]
    assert re.search(r"if \(!btn \|\| !panel\) return;", set_tab), (
        "setTab must guard both lookups before touching anything")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_tabs_module.py -q`
Expected: FAIL — `test_tabs_exports_a_programmatic_switch` asserts on a `setTab` that does not exist.

- [ ] **Step 3: Write the implementation**

In `src/fenceai/web/static/js/tabs.js`, replace the body of `initTabs`'s click handler (currently lines 22-33) with:

```js
/** Switch to a tab by name — the ONE path that moves the `active` class.
 *
 *  Extracted from the click handler because `road.js` must be able to show the
 *  annotations panel without touching it: once `#tabs` is hidden for sales, a
 *  `.click()` on the button is a module poking an invisible element in a
 *  subtree it does not own.
 *
 *  An unknown name is INERT rather than a throw. The road resolves a step to a
 *  panel name, and a typo there must cost one dead step, not the whole
 *  navigation — which, with the strip hidden, is the entire way around the app.
 */
export function setTab(name) {
  const btn = document.querySelector(`#tabs button[data-tab="${name}"]`);
  const panel = document.getElementById(`tab-${name}`);
  if (!btn || !panel) return;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
  btn.classList.add("active");
  panel.classList.add("active");
  // These three render lazily, on first sight of their tab.
  if (name === "knowledge") renderKnowledge();
  if (name === "review") renderCandidates();
  if (name === "bom") renderBom();
  emit("tab-changed", name);
}

export function initTabs() {
  document.querySelectorAll("#tabs button").forEach((btn) =>
    btn.addEventListener("click", () => setTab(btn.dataset.tab)));
```

Keep the rest of `initTabs` (everything after the `forEach`) exactly as it is.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/web/test_tabs_module.py -q`
Expected: PASS (4 tests)

Run: `uv run pytest -q`
Expected: PASS, 2544 total

- [ ] **Step 5: Verify in the browser — this is a refactor of the app's navigation**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: `344/344 checks passed`. All 57 existing `.click()` sites now route through `setTab`; if any tab stopped rendering, the `structure`/`bom`/`knowledge` cases fail here and nowhere else.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static/js/tabs.js tests/web/test_tabs_module.py
git commit -m "refactor(web): one path switches a tab, and road.js can call it"
```

---

### Task 2: Gaps name the stretches they are about

`height_assumed` and `base_assumed` carry `runs` (a count) and `uncovered_mm` (a sum), so the salesperson is told *"2 stretches, 4000 mm"* and has to go and find which two. The per-run data already exists at the emitting sites.

**Files:**
- Modify: `src/fenceai/report/handover.py:136-155`
- Test: `tests/report/test_handover.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `height_assumed` and `base_assumed` gain `params["run_ids"]: list[str]`, sorted, only runs with uncovered millimetres. Every other code is unchanged.

**Why this is additive and needs no locale change:** `t()` (`js/i18n.js:33-38`) iterates params and `replaceAll`s `{k}`; a param with no placeholder is never printed and never an error. Precedent: `StrategyWarning` already carries `run_id` alongside rendered params. **Carry the ids, do not render them** — a Hebrew sentence naming `run3, run7` is worse than a clickable row.

- [ ] **Step 1: Write the failing test**

Append to `tests/report/test_handover.py`:

```python
def test_an_assumed_gap_names_the_stretches_it_is_about():
    """The office phones about a specific stretch, and so does the salesperson
    looking for the one they missed. A count saves neither call.

    Carried, never rendered: the sentence in both bundles interpolates
    `{runs}` and `{uncovered_mm}`, and a Hebrew sentence naming `run3, run7`
    would be worse than a row you can click.
    """
    project = _complete()
    # two runs, neither with a height stated over its whole length
    for run in project.topology.runs:
        run.interval_events = [ev for ev in run.interval_events
                               if ev.payload.kind != "height_intent"]
    gaps = {g.code: g for g in handover_gaps(project)}

    named = gaps["height_assumed"].params["run_ids"]
    assert named == sorted(r.id for r in project.topology.runs)
    # the count and the sum stay: they are what the sentence renders
    assert gaps["height_assumed"].params["runs"] == len(named)


def test_only_the_uncovered_stretches_are_named():
    """A run whose height IS stated must not appear in the list, or clicking
    the row lands the salesperson on a stretch with nothing wrong with it."""
    project = _complete()
    covered = project.topology.runs[0]
    bare = project.topology.runs[1]
    bare.interval_events = [ev for ev in bare.interval_events
                            if ev.payload.kind != "height_intent"]
    gaps = {g.code: g for g in handover_gaps(project)}
    assert gaps["height_assumed"].params["run_ids"] == [bare.id]
    assert covered.id not in gaps["height_assumed"].params["run_ids"]


def test_a_base_gap_names_its_stretches_too():
    project = _complete()
    for run in project.topology.runs:
        run.interval_events = [ev for ev in run.interval_events
                               if ev.payload.kind != "base"]
    gaps = {g.code: g for g in handover_gaps(project)}
    assert gaps["base_assumed"].params["run_ids"] == sorted(
        r.id for r in project.topology.runs)
```

If `_complete()` builds a single-run project, give these tests a two-run fixture rather than changing `_complete()` — the existing assertions at `test_handover.py:95-101, 120, 193, 201, 257` are key lookups and must stay untouched.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/report/test_handover.py -q -k "names"`
Expected: FAIL with `KeyError: 'run_ids'`

- [ ] **Step 3: Write the implementation**

In `src/fenceai/report/handover.py`, replace the two emitting blocks (currently lines 136-155):

```python
    bare_height = {r.id: _uncovered_mm(topo, r, "height_intent") for r in topo.runs}
    if any(bare_height.values()):
        # The number is in the params because "no height" and "assumed 1800" are
        # different sentences, and only the second one a person can act on.
        # `uncovered_mm` is there for the same reason one step further in: "four
        # metres of this run" is actionable where "this run" is not.
        #
        # `run_ids` goes one step further again, and is CARRIED, never rendered:
        # the road's gap row uses it to select the stretch, while the sentence in
        # both bundles still says "2 stretches". A Hebrew sentence naming
        # `run3, run7` would be worse than a row you can click. It is valid for
        # the payload that carried it and is not a durable reference — run ids
        # can be reused after a delete and reopen (`state.js` re-derives
        # `runSeq` as max-suffix + 1), the same discipline ADR-0004 applies to
        # overrides.
        out.append(HandoverGap(code="height_assumed", params={
            "height_mm": DEFAULT_POLICY["default_height_mm"],
            "runs": sum(1 for v in bare_height.values() if v),
            "run_ids": sorted(rid for rid, v in bare_height.items() if v),
            "uncovered_mm": sum(bare_height.values())}))

    bare_base = {r.id: _uncovered_mm(topo, r, "base") for r in topo.runs}
    if any(bare_base.values()):
        # Not in the audit, and the same defect: `base_surface_at` resolves per
        # STATION, so an uncovered remainder stands on silent `soil` exactly as
        # an uncovered remainder is built at 1800.
        out.append(HandoverGap(code="base_assumed", params={
            "surface": DEFAULT_SURFACE,
            "runs": sum(1 for v in bare_base.values() if v),
            "run_ids": sorted(rid for rid, v in bare_base.items() if v),
            "uncovered_mm": sum(bare_base.values())}))
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/report/test_handover.py -q`
Expected: PASS — including the six pre-existing param assertions, which are key lookups and never dict equality.

Run: `uv run pytest -q`
Expected: PASS, 2547 total

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/report/handover.py tests/report/test_handover.py
git commit -m "feat(handover): an assumed gap names the stretches it is about"
```

---

### Task 3: `road-model.js` — the step model, pure and node-tested

The heart of the plan. This task produces no UI: it produces the function, tested the way `projectModelState` and `estimateNoteKey` already are.

**`road-model.js` imports NOTHING.** That is the whole reason it is a separate file from `road.js`, and it is the repo's existing pattern — CLAUDE.md: *"the side view's base actions are point-list transforms in `base-top.js` with no DOM or state — `profile.js` only wires them to buttons. Keep new profile math there so it stays testable in node."* A model that imported `tabs.js` would drag the entire rendering tree into the node test and need a stubbed `document`, `localStorage` and `fetch` (compare `tests/web/test_fence_models_module.py:31-71`) — for a function that is a `for` loop over a list of gap codes.

**Files:**
- Create: `src/fenceai/web/static/js/road-model.js`
- Test: `tests/web/test_road_module.py` (create)

**Interfaces:**
- Consumes: `HandoverGap` shape from Task 2 (`{code, params, blocking}`).
- Produces, all from `road-model.js`:
  - `export const STEPS` — six `{key, panel}` in road order: `job`/`canvas`, `layout`/`canvas`, `details`/`canvas`, `gates`/`canvas`, `notes`/`annotations`, `review`/`canvas`.
  - `export const GAP_STEPS` — `{<handover code>: <step key>}`, total over `HANDOVER_CODES`.
  - `export function road(project, handover, role)` → `null` for any role but `"sales"`, else `[{key, panel, state, gaps}]` where `state` ∈ `"blocked" | "missing" | "done" | "empty"`.
  - `export function panelFor(stepKey)` → the panel name, or `null`.

- [ ] **Step 1: Write the failing test**

Create `tests/web/test_road_module.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_road_module.py -q`
Expected: FAIL — node cannot resolve `./js/road-model.js`.

- [ ] **Step 3: Write the implementation**

Create `src/fenceai/web/static/js/road-model.js`. **It imports nothing — keep it that way.**

```js
// The salesperson's road: six steps, and which of them is still missing
// something. See docs/superpowers/specs/2026-09-06-salesperson-road-design.md.
//
// The MODEL half. No imports, no DOM, no state — `road.js` renders this, the
// way `profile.js` renders `base-top.js`. That split is what lets the step
// model be tested in node without stubbing a document, and it is the rule
// CLAUDE.md states for new frontend logic.
//
// **A map, never a wizard.** Every step is enterable at any time. The
// salesperson works on a laptop after the visit, from paper — they may hold the
// sketch and not the address, or do the gates first because the gates are what
// the customer talked about. A wizard demanding order would be defeated by
// typing junk to get past a step, which turns a completeness report into a
// completeness LIE, and that is the one failure this MVP exists to prevent.
// It is `report/handover.py`'s own rule: reported, never enforced.
//
// **It computes no completeness of its own.** Three surfaces already answered
// "what is left" and disagreed: checklist.js's three hardcoded items, the
// handover panel, and `#gaps` — which answers a different question entirely
// (what the KNOWLEDGE cannot answer, for any job). A fourth would be the B03
// defect at a larger scale. So this module GROUPS `handover_gaps()` and never
// recomputes it.

/** The six steps, in the order the job is actually done, each with the panel it
 *  shows. `notes` is the only one whose panel is not the canvas, and it is the
 *  reason the tab strip goes: with the strip kept, a promise made during the
 *  sale would be the one thing the road could not report on. */
export const STEPS = [
  { key: "job", panel: "canvas" },
  { key: "layout", panel: "canvas" },
  { key: "details", panel: "canvas" },
  { key: "gates", panel: "canvas" },
  { key: "notes", panel: "annotations" },
  { key: "review", panel: "canvas" },
];

/** Which step owns each handover code. TOTAL over `HANDOVER_CODES` — a code
 *  with no entry here would vanish from the road while the API still reported
 *  it, so `tests/web/test_road_module.py` asserts the mapping covers the list.
 *
 *  A registry in `handover.py`'s sense: adding a code and its step is a one-line
 *  change and needs no discussion. */
export const GAP_STEPS = {
  customer_missing: "job",
  address_missing: "job",
  sold_by_missing: "job",
  sold_on_missing: "job",
  no_fence_drawn: "layout",
  no_property_context: "layout",
  height_assumed: "details",
  base_assumed: "details",
  no_model_chosen: "details",
};

/** Where a code with no step goes. Never reached while the totality test
 *  passes; it exists so that if one ever does reach a browser, it is visible to
 *  the person who can act on it rather than silently dropped. */
const ORPHAN_STEP = "review";

/** The road for a role, or `null` for a role that has no road.
 *
 *  Refusing rather than defaulting is deliberate: the office person's road and
 *  the super user's are unwritten, and showing them the salesperson's map would
 *  be worse than showing them none.
 *
 *  `handover` is the payload of `GET /api/projects/{id}/handover` — passed in
 *  rather than fetched here, so this stays pure and so there is exactly one
 *  request behind the road and the estimate. */
export function road(project, handover, role = "sales") {
  if (role !== "sales") return null;
  const gaps = handover?.gaps || [];
  const drawn = (project?.topology?.runs || []).length > 0;

  const owned = Object.fromEntries(STEPS.map((s) => [s.key, []]));
  for (const gap of gaps)
    owned[GAP_STEPS[gap.code] || ORPHAN_STEP].push(gap);

  return STEPS.map((step) => {
    const mine = owned[step.key];
    let state;
    if (mine.some((g) => g.blocking)) state = "blocked";
    else if (mine.length) state = "missing";
    else if (!drawn && step.key !== "job") state = "empty";
    else state = "done";
    return { key: step.key, panel: step.panel, state, gaps: mine };
  });
}

/** The panel a step shows, or `null` for a step nobody defined. `road.js` hands
 *  this to `tabs.js: setTab` — the model never switches anything itself. */
export function panelFor(stepKey) {
  return STEPS.find((s) => s.key === stepKey)?.panel || null;
}
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/web/test_road_module.py -q`
Expected: PASS (10 tests)

If node reports `Cannot find package` or a `document is not defined`, `road-model.js` has grown an import — that is `test_the_model_half_imports_nothing` telling you the same thing, and the fix is to move whatever needed the import into `road.js` (Task 4), not to stub it here.

Note: `test_a_blocking_gap_makes_its_step_blocked` uses the `no_fence_drawn` case, where `handover_gaps` returns that gap ALONE. If `out["empty"]["job"]["state"]` is not what you expect, that is the short-circuit at `handover.py:117` doing its job, not a bug here.

Run: `uv run pytest -q`
Expected: PASS, 2557 total

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/road-model.js tests/web/test_road_module.py
git commit -m "feat(web): the six steps, derived from the handover gaps and nothing else"
```

---

### Task 4: The road renders, and the tab strip goes

**Files:**
- Create: `src/fenceai/web/static/js/road.js` (the rendering half)
- Modify: `src/fenceai/web/static/index.html` (add the `<nav id="road">` host)
- Modify: `src/fenceai/web/static/app.js` (import and init)
- Modify: `src/fenceai/web/static/js/role.js:55-66` (add `"#tabs"`)
- Modify: `src/fenceai/web/static/style.css:764-781` (the matching rule) and add road styles
- Modify: `src/fenceai/web/static/i18n/en.json`, `i18n/he.json`
- Modify: `tests/web/test_role_module.py:141-151` (docstring)

**Interfaces:**
- Consumes: `road()`, `showStep()`, `STEPS` from Task 3.
- Produces: `export function initRoad(): void`, called from `app.js` `main()` after `initRole()`.

**The exact shapes the guards demand** (do not improvise these):

| Where | Exact text |
|---|---|
| `js/role.js` `SALES_HIDDEN` | the string `"#tabs"` — not `"nav#tabs"`, not `"#tabs button"` |
| `style.css` sales group | a line `html[data-role="sales"] #tabs,` |
| the eight `[data-tab=…]` entries | **keep all of them**, in both copies |

`test_role_sync.py::_from_css` strips the literal `#tabs button` from the middle of a selector and then demands **set equality**; `nav#tabs` normalises to `nav#tabs` and fails, `#tabs button` normalises to the empty string and fails mystifyingly. The eight per-tab entries must stay because `test_sales_tabs_and_the_hidden_tabs_partition_the_page` asserts `set(SALES_TABS) | hidden == all ten tabs`.

- [ ] **Step 1: Write the failing test**

Append to `tests/web/test_road_module.py`:

```python
def test_the_road_has_a_literal_host_id():
    """`test_role_module.py::_live_ids` scans `id="([^"{}]+)"`, so an id built
    by interpolation is invisible to the hide-list check. Any road element that
    ever lands on a hide-list needs a literal id."""
    src = (STATIC / "js" / "road.js").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'id="road"' in html, "the road's host belongs in index.html"
    assert "${" not in src[src.index('id="road-step'):src.index('id="road-step') + 40] \
        if 'id="road-step' in src else True


def test_the_band_is_rendered_once_and_only_toggled_after():
    """The prototype's own fix for lost keyboard focus: re-`innerHTML`ing the
    band on every state change drops focus to BODY, and with the tab strip gone
    the band is the only navigation on the screen."""
    src = (STATIC / "js" / "road.js").read_text()
    assert "children.length" in src or "dataset.built" in src, (
        "guard the band's innerHTML so it is built once")
```

Add the invariant-7 test deferred from Task 3:

```python
def test_road_reaches_no_panel_dom():
    """Spec invariant 7. The road switches panels through `tabs.js: setTab`;
    querying inside a panel is the module-map violation this navigation change
    is most likely to introduce."""
    src = (STATIC / "js" / "road.js").read_text()
    assert "#tab-" not in src
    assert "setTab" in src
```

And to `tests/web/test_role_module.py`, replace the docstring of
`test_a_promise_made_during_the_sale_keeps_a_home` (currently lines 141-151) —
the assertions stay, their meaning does not:

```python
def test_a_promise_made_during_the_sale_keeps_a_home(out):
    """Annotations stay reachable — but READ THIS, because what makes it true
    changed. `#tabs` is now hidden for sales, so "not on the hide-list" no
    longer means "reachable by a tab": the road's step 5 is what reaches the
    annotations panel, through `tabs.js: setTab`.

    `SALES_TABS` is therefore no longer a navigation list. It is the set of
    panels the road may activate, and `annotations` being in it is what stops
    step 5 from being a dead end.

    It is a NOTE and not an override on purpose: an override is a technical
    instruction that survives into generation, and a promise is a sentence the
    office person has to read and decide about.
    """
    assert '[data-tab="annotations"]' not in set(out["sales"])
    assert "annotations" in out["sales_tabs"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/web/test_road_module.py -q`
Expected: FAIL — `id="road"` is not in `index.html`.

- [ ] **Step 3: Add the host, in `index.html`, immediately after `</nav>` (the `#tabs` nav, line 41)**

```html
  <nav id="road" aria-label="Job steps"></nav>
```

- [ ] **Step 4: Add the locale keys — both bundles, two-space indent, alphabetical**

`en.json`:

```json
  "road.details": "The details",
  "road.details.take": "Fence height is measured above its base, not above the ground.",
  "road.gates": "Gates",
  "road.gates.take": "A gate's width and its distance from a corner are what the office orders from.",
  "road.job": "The job",
  "road.job.take": "The customer, the address, who sold it and when.",
  "road.layout": "The layout",
  "road.layout.take": "Written measurements define the fence. The sketch only shows the arrangement.",
  "road.notes": "Notes",
  "road.notes.take": "A promise made during the sale reaches the office as a sentence somebody reads.",
  "road.review": "Review",
  "road.review.take": "What the office still needs, while you can still answer it.",
  "road.state.blocked": "cannot start",
  "road.state.done": "nothing missing",
  "road.state.empty": "not started",
  "road.state.missing": "{n} still missing",
```

`he.json`:

```json
  "road.details": "הפרטים",
  "road.details.take": "גובה הגדר נמדד מעל הבסיס שלה, לא מעל הקרקע.",
  "road.gates": "שערים",
  "road.gates.take": "רוחב השער והמרחק שלו מהפינה הם מה שהמשרד מזמין לפיו.",
  "road.job": "העבודה",
  "road.job.take": "הלקוח, הכתובת, מי מכר ומתי.",
  "road.layout": "הפריסה",
  "road.layout.take": "מידות כתובות מגדירות את הגדר. הסקיצה מראה רק את הסידור.",
  "road.notes": "הערות",
  "road.notes.take": "הבטחה שניתנה במכירה מגיעה למשרד כמשפט שמישהו קורא.",
  "road.review": "סיכום",
  "road.review.take": "מה שהמשרד עוד צריך, בזמן שעוד אפשר לענות.",
  "road.state.blocked": "אי אפשר להתחיל",
  "road.state.done": "לא חסר כלום",
  "road.state.empty": "טרם התחיל",
  "road.state.missing": "חסרים עוד {n}",
```

None of these carries `{u}` or `{c}`, so `t()` is correct and `tu()` is not needed. None contains a length, a unit token or a currency symbol.

- [ ] **Step 5: Render — create `src/fenceai/web/static/js/road.js`**

```js
// The road, rendered. `road-model.js` decides WHAT the six steps are and which
// is missing something; this file only draws it and switches panels — the
// `base-top.js` / `profile.js` split, applied again.
//
// It reaches no panel's DOM. `setTab` is the one path that moves the `active`
// class, so the road and the strip can never disagree about which panel shows.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { currentRole } from "./role.js";
import { on, state } from "./state.js";
import { setTab } from "./tabs.js";
import { STEPS, panelFor, road } from "./road-model.js";

let current = "job";

function showStep(stepKey) {
  const panel = panelFor(stepKey);
  if (panel) setTab(panel);
}

/** Build the band ONCE, then only toggle attributes.
 *
 *  Re-`innerHTML`ing on every state change drops keyboard focus to BODY — and
 *  with `#tabs` hidden this band is the only navigation on the screen, so
 *  losing focus here strands a keyboard user completely. The buttons are always
 *  enabled: the road is a map, not a wizard. */
function build(host) {
  if (host.children.length) return;
  host.innerHTML = STEPS.map((s, i) => `<button data-step="${esc(s.key)}">`
    + `<span class="road-index">${String(i + 1).padStart(2, "0")}</span>`
    + `<span class="road-name">${esc(t(`road.${s.key}`))}</span>`
    + `<span class="road-state"></span></button>`).join("");
  host.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-step]");
    if (!btn) return;
    current = btn.dataset.step;
    showStep(current);
    render();
  });
}

export function render() {
  const host = document.getElementById("road");
  if (!host) return;
  const steps = road(state.project, state.handover, currentRole());
  // A role with no road shows none — and the tab strip is what it navigates by.
  host.hidden = steps === null;
  if (steps === null) return;
  build(host);
  for (const step of steps) {
    const btn = host.querySelector(`[data-step="${step.key}"]`);
    if (!btn) continue;
    btn.dataset.state = step.state;
    if (step.key === current) btn.setAttribute("aria-current", "step");
    else btn.removeAttribute("aria-current");
    btn.querySelector(".road-name").textContent = t(`road.${step.key}`);
    btn.querySelector(".road-state").textContent = step.gaps.length
      ? t("road.state.missing", { n: step.gaps.length })
      : t(`road.state.${step.state}`);
  }
}

export function initRoad() {
  render();
  on("project-loaded", render);
  on("handover-changed", render);
  on("locale-changed", render);
  on("role-changed", render);
}
```

- [ ] **Step 6: Wire it in `app.js`**

Add the import beside the other module imports:

```js
import { initRoad } from "./js/road.js";
```

and call it in `main()` immediately after `initRole()`:

```js
  initRole();       // ...and who is looking, before anything is drawn for them
  initRoad();       // ...and the road they navigate by, before the panels load
```

- [ ] **Step 7: Hide the strip — BOTH copies, exactly**

`js/role.js`, in `SALES_HIDDEN`, above the `...ALL_TABS.filter(...)` spread, with its reason:

```js
//   #tabs             the strip itself. The road is the navigation for this
//                     role (spec, "The road IS the navigation"), and two
//                     navigations on one screen is the smaller version of the
//                     fault the road exists to fix. The eight per-tab entries
//                     below STAY: they are what keeps the strip correct if it
//                     is ever shown, and `test_sales_tabs_and_the_hidden_tabs_
//                     partition_the_page` requires them.
  "#tabs",
```

`style.css`, inside the sales group (lines 764-781), as its own line:

```css
html[data-role="sales"] #tabs,
```

- [ ] **Step 8: Style the band — logical properties only**

```css
/* The road: the salesperson's only navigation. Logical properties throughout —
   `margin-left` on the index would put the number on the wrong side in RTL. */
#road { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
        border-block-end: 1px solid var(--line); }
#road[hidden] { display: none; }
#road button { display: flex; align-items: center; gap: 8px; text-align: start;
               padding: 10px 12px; border: 0; border-block-end: 3px solid transparent;
               border-radius: 0; background: transparent; min-height: 48px; }
#road button[aria-current="step"] { border-block-end-color: var(--accent);
                                    font-weight: 700; }
#road .road-index { font-size: 11px; opacity: .65; }
#road .road-state { font-size: 11px; opacity: .75; margin-inline-start: auto; }
#road button[data-state="blocked"] .road-state,
#road button[data-state="missing"] .road-state { color: var(--warn); }
```

Use the project's existing `--accent`/`--warn`/`--line` custom properties; if a name differs, use the repo's, do not introduce new ones.

- [ ] **Step 9: Run everything**

Run: `uv run pytest tests/web/ -q`
Expected: PASS, including `test_role_sync.py` (which fails loudly if the two copies of the hide-list disagree) and `test_bundle_key_parity`.

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 10: Look at it — this is the checkpoint**

```bash
uv run uvicorn fenceai.api.app:app --reload
```

Open http://localhost:8000, switch the role selector to Salesperson. **The tab strip must be gone and six numbered steps must be in its place.** Click step 5 and confirm the annotations panel appears. Reload the page and confirm the road is still there — audit observation 2 was exactly this shape.

- [ ] **Step 11: Commit**

```bash
git add src/fenceai/web/static/js/road.js src/fenceai/web/static/js/role.js \
        src/fenceai/web/static/app.js src/fenceai/web/static/index.html \
        src/fenceai/web/static/style.css src/fenceai/web/static/i18n/ \
        tests/web/test_road_module.py tests/web/test_role_module.py
git commit -m "feat(web): the road is the salesperson's navigation, and the tab strip goes"
```

---

### Task 4B: A step shows only its own work

Added 2026-09-07 after the user saw Task 4 running. Their verdict: *"for each step I want it to be clear, simple and intuitive what the user should do in that step — not all the buttons and options should show up in each step."* Built as navigation alone, the road moves an underline while the screen underneath stays identical — all nine tools and every side panel, on every step. See the spec's new section, "A step SHOWS only its own work", which is the authority for the table below.

**Files:**
- Create: `src/fenceai/web/static/js/step-surfaces.js` (the list; imports nothing)
- Modify: `src/fenceai/web/static/js/road.js` (set `<html data-step>`)
- Modify: `src/fenceai/web/static/style.css` (the matching rules)
- Test: `tests/web/test_step_surfaces.py` (create)

**Interfaces:**
- Consumes: `STEPS` from `road-model.js`.
- Produces: `export const STEP_HIDDEN` — `{<step key>: [selector, …]}`; `export function hiddenForStep(key)` returning a copy, `[]` for an unknown key.

**What each step hides** (everything NOT in its row, from the union of all scoped selectors):

| Step | Tools it KEEPS | Panels it KEEPS |
|---|---|---|
| `job` | none | `#job-panel` |
| `layout` | `#tool-select` `#tool-draw` `#tool-house` `#tool-street` | `#context-panel` |
| `details` | `#tool-select` `#tool-ground` `#tool-base` `#tool-height` `#tool-model` | `#model-row` `#run-events` `#profile` |
| `gates` | `#tool-select` `#tool-gate` | `#run-events` |
| `notes` | none | none (the annotations panel is its own tab) |
| `review` | none | `#handover-panel` `#warnings` `#site-conditions` |

`#canvas` is shown in every step. `#road` itself, the header, undo/redo and Clear are never scoped.

**Three properties this must not break, each already load-bearing elsewhere:**
1. **Role wins over step.** A surface `role.js` hides from `sales` stays hidden in every step. The two lists are independent; never merge them.
2. **The lists must be EQUAL in both copies** — JS and CSS — not overlapping. `test_role_sync.py` enforces this for the role list and this task adds the same check for steps.
3. **Every selector must resolve against the real page.** A hide-list is the one kind of list that fails silently.

- [ ] **Step 1: Write the failing test**

Create `tests/web/test_step_surfaces.py`, mirroring `tests/web/test_role_module.py`'s node harness (`node --input-type=module -e SCRIPT` with `cwd=STATIC`) and reusing its `_live_ids()` approach. Assert:

```python
def test_every_step_has_a_surface_list(out):
    """A step with no entry scopes nothing and silently shows the whole app —
    which is the state the user rejected."""
    assert set(out["step_keys"]) == set(out["hidden"])


def test_every_scoped_selector_exists(out):
    """The assertion that earns this file, and the same one
    test_role_module.py makes: a selector matching nothing hides nothing,
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
    keeps = {"layout": ["#tool-draw", "#tool-house", "#tool-street"],
             "details": ["#tool-ground", "#tool-base", "#tool-height",
                         "#tool-model"],
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


def test_the_two_copies_are_equal():
    """`test_role_sync.py`'s rule, applied to steps: CSS cannot read a JS
    array, so the list exists twice and the copies must be EQUAL."""
    # parse `html[data-step="<key>"] <selector>` out of style.css and compare
    # per-step sets against hiddenForStep(key)
```

Write the last one out in full following `tests/web/test_role_sync.py:56-71`'s parsing shape.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/web/test_step_surfaces.py -q`
Expected: FAIL — node cannot resolve `./js/step-surfaces.js`.

- [ ] **Step 3: Write `step-surfaces.js`** — imports nothing, for `road-model.js`'s reason. Derive each step's hidden list by subtracting its keeps from the union of all scoped selectors, so adding a tool to one step cannot silently leave it visible in the other five.

- [ ] **Step 4: Set `data-step` in `road.js`** — in `render()`, `document.documentElement.dataset.step = current` when the role is `sales`; remove the attribute otherwise, so `office`/`all` have no step rules at all.

- [ ] **Step 5: Write the CSS** — one `html[data-step="<key>"] <selector> { display: none; }` line per entry, matching the JS list exactly. Add `html[data-step="job"] #canvas, html[data-step="review"] #canvas { pointer-events: none; }` so a toolless step cannot edit. Logical properties only.

- [ ] **Step 6: Verify**

`uv run pytest tests/web/ -q`, then `uv run pytest -q`, then `uv run --with websocket-client python tools/ui_smoke.py` — all in the FOREGROUND. The smoke may fail where a case clicks a tool while a step hides it; if so, report which, do not edit `tools/ui_smoke.py` (Task 8 owns it) unless the failure is a sales-mode case that this task genuinely invalidates.

- [ ] **Step 7: Commit**, then the human looks at it. This task ends at a checkpoint: each step must show only its own controls, with the drawing visible throughout.

---

### Task 5: The "see the priced BOM" dead end

`editor.js:1595-1605` renders a link that switches to the BOM panel by clicking the button. Only the *button* is on the sales hide-list; `#tab-bom` is not. Today the strip provides the way back. **With `#tabs` hidden it is a dead end with no visible navigation at all** — the app becomes unusable for the role until reload. This is audit observation 5, escalated from cosmetic to blocking by Task 4.

**Files:**
- Modify: `src/fenceai/web/static/js/editor.js:1595-1605`
- Modify: `src/fenceai/web/static/js/role.js` + `style.css` (one hide-list entry)
- Test: `tests/web/test_role_module.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/web/test_role_module.py`:

```python
def test_no_sales_surface_links_into_a_hidden_tab(out):
    """With `#tabs` hidden, a link that switches to a panel the role cannot
    navigate away from is a dead end: no strip, no road entry, no way back
    without a reload.

    `#summary-to-bom` is the one that existed — audit observation 5, which was
    cosmetic while the strip was there and is not any more.
    """
    hidden_tabs = {s[len('[data-tab="'):-len('"]')] for s in out["sales"]
                   if s.startswith("[data-tab=")}
    src = (STATIC / "js" / "editor.js").read_text()
    for tab in hidden_tabs:
        assert f'data-tab="{tab}"' not in src, (
            f"editor.js navigates to {tab}, which sales cannot navigate back "
            f"from")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/web/test_role_module.py::test_no_sales_surface_links_into_a_hidden_tab -q`
Expected: FAIL — `editor.js` contains `data-tab="bom"`.

- [ ] **Step 3: Route it through `setTab` and hide it for the role**

In `editor.js`, replace the `.click()` handler with a `setTab` call (import `setTab` from `./tabs.js`):

```js
    // Through `setTab` rather than a click on the button: the button is hidden
    // for sales, and clicking an invisible element in another module's subtree
    // is the thing the module map forbids.
    document.getElementById("summary-to-bom")
      ?.addEventListener("click", () => setTab("bom"));
```

Then give the link's element the id `summary-to-bom` if it does not already have it, and add `"#summary-to-bom"` to `SALES_HIDDEN` in `role.js` with the matching `html[data-role="sales"] #summary-to-bom,` line in `style.css`.

**Both copies, or `test_role_sync.py` fails.** The id must be a literal in the template string, or `_live_ids` cannot see it.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/web/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/editor.js src/fenceai/web/static/js/role.js \
        src/fenceai/web/static/style.css tests/web/test_role_module.py
git commit -m "fix(sales): a priced-BOM link is not a door out of the only navigation"
```

---

### Task 6: Delete `checklist.js`, and repoint what silently depended on it

**Files:**
- Delete: `src/fenceai/web/static/js/checklist.js`
- Modify: `src/fenceai/web/static/app.js:6` (import) and `:91` (call)
- Modify: `src/fenceai/web/static/index.html:80-86` (host)
- Modify: `src/fenceai/web/static/style.css:442-451` and `:666` (print hide-list)
- Modify: `src/fenceai/web/static/i18n/en.json:172-176`, `he.json:172-176` (5 keys each)
- Modify: `tools/persona_lab/outline.py:128`
- Modify: `docs/architecture/05-frontend.md:43`

**The silent one:** `tools/persona_lab/outline.py:128` does `add('getting started', document.getElementById('checklist'))`. `add()` guards a null, so after deletion the "getting started" feedback region goes permanently empty for every persona run — and `tests/tools/test_persona_driver.py:227` keeps passing, because it asserts the literal string `"checklist"` is in `FEEDBACK_JS`. **Repoint it at `#road`.**

- [ ] **Step 1: Write the failing test**

Append to `tests/web/test_road_module.py`:

```python
def test_no_module_still_answers_what_is_left_beside_the_road():
    """Spec invariant 6. `checklist.js` had three hardcoded items — a run
    exists, a gate exists, a strategy was computed — and no idea whether a
    height was ever stated. A dismissible surface that still disagrees is a
    surface somebody re-enables."""
    assert not (STATIC / "js" / "checklist.js").exists()
    app = (STATIC / "app.js").read_text()
    assert "checklist" not in app
    html = (STATIC / "index.html").read_text()
    assert 'id="checklist"' not in html
    for name in ("en", "he"):
        bundle = (STATIC / "i18n" / f"{name}.json").read_text()
        assert '"checklist.' not in bundle, f"{name}.json keeps dead keys"
```

And in `tests/tools/test_persona_driver.py`, change the assertion at line 227 from `"checklist"` to `"road"`, so the region a persona is asked about is one that exists.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/web/test_road_module.py -q -k what_is_left`
Expected: FAIL — the module still exists.

- [ ] **Step 3: Delete and repoint**

```bash
git rm src/fenceai/web/static/js/checklist.js
```

Remove the import and the `initChecklist()` call from `app.js`; remove `index.html:80-86`; remove `style.css:442-451` and the `#checklist` token from the print hide-list at `:666`; remove the five `checklist.*` keys from both bundles.

In `tools/persona_lab/outline.py:128`:

```python
        add('getting started', document.getElementById('road'));
```

In `docs/architecture/05-frontend.md:43`, replace the `CH["checklist.js"]` node with `RD["road.js"]` and note in the same commit that the road is the sales navigation — CLAUDE.md requires code and these docs to change together.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(web): delete checklist.js — one surface answers what is left"
```

---

### Task 7: The road shows the gaps, and the handover panel keeps its estimate

The gap rows move; the estimate stays. **One fetch**: if `road.js` and `handover.js` both request `/handover`, there are two answers to the same question — the defect this spec exists to prevent.

**Files:**
- Modify: `src/fenceai/web/static/js/handover.js` (own the fetch, publish the payload, drop the gap rows)
- Modify: `src/fenceai/web/static/js/state.js` (add `state.handover` + `handover-changed` to the documented event list at `:24-26`)
- Modify: `src/fenceai/web/static/js/road.js` (render the rows under their step)
- Modify: `src/fenceai/web/static/style.css:806-814` (gap-row rules move; `:815-821` stay)
- Modify: `tests/web/test_handover_module.py`

**`readinessShown` stays exactly where it is.** It answers *has the check actually succeeded* — a property of the fetch, which `handover.js` still owns — and it is audit B01's guard. `road.js` imports it. Moving it would mean editing its three assertions in `tests/web/test_handover_module.py:47-57` for no gain; an import is what "modules communicate via exports" means.

`handover.js` also keeps `estimateReady`, `estimateNoteKey` and the BOM fetch.

- [ ] **Step 1: Write the failing test**

Add to `tests/web/test_road_module.py`:

```python
def test_a_gap_row_names_the_stretch_it_is_about():
    """Audit U02. Today the panel says "2 stretches, 4000 mm" and the
    salesperson has to go and find which two. `run_ids` (Task 2) is what makes
    the row a control rather than a sentence."""
    src = (STATIC / "js" / "road.js").read_text()
    assert "run_ids" in src, "the row must carry the ids the gap named"


def test_exactly_one_module_fetches_the_handover():
    """Two requests behind one question is two answers to it — the defect this
    whole spec exists to prevent, in miniature. handover.js fetches and
    publishes; road.js reads `state.handover`."""
    hits = [m.name for m in (STATIC / "js").glob("*.js")
            if "/handover" in m.read_text()]
    assert hits == ["handover.js"], hits
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/web/test_road_module.py -q -k "gap_row or fetches"`
Expected: FAIL — `road.js` does not mention `run_ids`.

- [ ] **Step 3: Publish the payload instead of rendering it**

In `state.js`, add `handover: null` to the `state` object and add `"handover-changed"` to the documented event list at `:24-26`.

In `handover.js`'s `refresh()` (currently `:111-120`), after a successful fetch:

```js
  // Published rather than rendered here: the road shows the gaps and this panel
  // keeps the estimate, and both must be looking at ONE response. A second
  // fetch would be a second answer to "is this job complete?".
  state.handover = payload;
  emit("handover-changed", payload);
```

Delete the gap-row half of `render()` (`handover.js:84-95`) and keep the estimate block (`:99-107`). Export `readinessShown` if it is not already exported.

- [ ] **Step 4: Render the rows, in `road.js`**

```js
/** The gaps for the step being looked at, as rows that DO something.
 *
 *  `run_ids` comes from the gap's own params (report/handover.py) and is valid
 *  for the payload that carried it — run ids can be reused after a delete and
 *  reopen, so this is never stored, only clicked.
 */
function rowsHtml(step) {
  if (!step.gaps.length) return "";
  return `<ul class="road-gaps">` + step.gaps.map((g) => {
    const ids = (g.params?.run_ids || []).join(" ");
    return `<li${g.blocking ? ' class="blocking"' : ""}`
      + (ids ? ` data-run-ids="${esc(ids)}"` : "")
      + `>${esc(gapSentence(g))}</li>`;
  }).join("") + `</ul>`;
}
```

Reuse `gapSentence` by importing it from `handover.js` — including its `tu()`-vs-`t()` branch on `uncovered_mm`/`height_mm` intact, because `test_unit_bearing_keys_are_rendered_with_tu` scans every `js/*.js` and a copy that lost the branch would render millimetres to a reader working in centimetres.

Wire a click on `[data-run-ids]` to select the first named run and open the editor for that gap's step.

- [ ] **Step 5: Move the CSS**

`style.css:806-814` (`.handover-gaps`, its `li`, `li::before`, `li.blocking::before`, `.handover-ready`) become `.road-gaps` equivalents. `:815-821` (`.handover-estimate`, `.handover-amount`, `.handover-amount .num`, `.handover-amount-label`) stay untouched.

- [ ] **Step 6: Run everything, then look**

Run: `uv run pytest -q` — expected PASS.
Run: `uv run --with websocket-client python tools/ui_smoke.py` — `_smoke_handover_sheet` **will fail here, expectedly**: its reader queries `.handover-gaps li` inside `#handover-panel` (`ui_smoke.py:1160-1172`) and those rows now live on the road. Repointing it is Task 8. Do not "fix" it by leaving a duplicate gap list in the panel.

Then open the app in sales mode and confirm a gap row names a stretch and selects it when clicked.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(web): the road shows the gaps, the panel keeps the estimate"
```

---

### Task 8: The smoke, told to catch absence

The existing sales case would pass identically **if the road never rendered at all** — its probes read tab buttons through `getComputedStyle`, which still reports a child's own `display` under a hidden parent. A hidden strip plus a road that failed to render is a screen with no navigation and no thrown error. That is the defect class this project's own retrospective is about.

**Files:**
- Modify: `tools/ui_smoke.py` — `_smoke_sales_mode` (`:833-943`), `_smoke_handover_sheet` (`:1147-1296`), `_CHOICE_CASES` (`:1299-1308`)

**Registration rules** (`tests/web/test_smoke_cases_registered.py`): a case is a module-level `def _smoke_<name>(c) -> None:` above `main()`, added as a **bare `Name`** to the single annotated `_CHOICE_CASES: list = [...]`. Do not drop the `: list` annotation — the test reads `AnnAssign` and raises `IndexError` without it. Any module-level function named `_smoke_*` is forced into the list, so helpers get another prefix. A sales case must restore `role` to `'all'` before returning, or it poisons every later case through `localStorage`.

- [ ] **Step 1: Add the cases**

Here is the first one in full — the others follow its shape exactly, so read it before writing them. Note the two things that make it catch absence: both halves are asserted **in one read** (a hidden strip and a missing road each pass the other's half alone), and the role is restored before returning.

```python
def _smoke_road_replaces_the_tab_strip(c) -> None:
    """The strip is gone AND the road is there — asserted together.

    Apart, either half passes on a broken screen: `#tabs` hidden with no road
    is a page with no navigation at all, and it throws nothing. Four of the
    five defects the last MVP shipped were silent in exactly this way.
    """
    c.new_project("road-strip")
    c.js("""
      const sel = document.getElementById('role-select');
      sel.value = 'sales';
      sel.dispatchEvent(new Event('change'));
    """)
    seen = c.js("""JSON.stringify({
      tabs: getComputedStyle(document.querySelector('nav#tabs')).display,
      steps: document.querySelectorAll('#road [data-step]').length,
      names: [...document.querySelectorAll('#road .road-name')]
               .map(n => n.textContent.trim()).filter(Boolean).length,
    })""")
    seen = json.loads(seen)
    check("the tab strip is gone for a salesperson", seen["tabs"] == "none")
    check("and the road is there in its place, six steps", seen["steps"] == 6)
    check("every step is labelled, not a raw key or a blank",
          seen["names"] == 6)
    c.shot("54-road-sales.png")
    # Restore, or every case after this one runs as a salesperson: the role
    # persists in localStorage (`role.js:96`) and case order must not matter.
    c.js("""
      const sel = document.getElementById('role-select');
      sel.value = 'all';
      sel.dispatchEvent(new Event('change'));
    """)
```

`c.new_project`, `c.js`, `c.shot` and `check` are this file's existing helpers — match the surrounding call style rather than the sketch above if it differs.

Add these, each registered:

```
_smoke_road_replaces_the_tab_strip     #tabs computes display:none AND six road
                                       steps are on screen, in ONE read — either
                                       half alone passes on a broken screen
_smoke_road_is_the_only_navigation     no #tabs button is reachable by a real
                                       pointer click (element_center + c.click,
                                       never .click()), so a merely
                                       visually-hidden strip fails
_smoke_road_step_five_reaches_annotations
                                       the one step whose surface is another
                                       panel, and the reason the strip goes
_smoke_every_road_step_activates_a_panel
                                       click all six; each leaves a .tab.active
                                       whose name is in SALES_TABS (invariant 8)
_smoke_road_matches_the_handover_sheet read /handover for the same project and
                                       assert every gap code appears under
                                       exactly one step (invariant 1, at runtime)
_smoke_road_is_not_a_wizard            from an empty job, step 6 is enterable
                                       without touching 1-5 (invariant 3)
_smoke_road_survives_a_reload_in_sales reload with role=sales persisted; the
                                       road is still the navigation — the exact
                                       shape of audit observation 2
_smoke_office_keeps_the_tab_strip      in role=office, #tabs is shown and no
                                       road renders; the road leaking into
                                       another role is a silent regression
_smoke_checklist_is_gone               #checklist absent in every role and no
                                       checklist.* string on screen (invariant 6)
```

- [ ] **Step 2: Repoint the two existing cases**

- `_smoke_sales_mode:892-895` proves the sales vocabulary through `tabs.canvas` — an element the role no longer shows. Repoint at a road step label.
- `_smoke_sales_mode`'s `shown` map (`:852-871`) gains `road:` and `tabs: vis('nav#tabs')`.
- `_smoke_handover_sheet`'s reader (`:1160-1172`) queries `.handover-gaps li` inside `#handover-panel`; repoint at the road's rows. Its `:1244` arithmetic (`len(gaps) == before - 4`) becomes the road's step-1 assertion.

- [ ] **Step 3: Run**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: all checks pass, count above 344.

- [ ] **Step 4: Re-read the screenshots**

Deleting `#checklist` shifts the drawing up ~110 px in **all 22 canvas screenshots**. There is no image diffing (`tools/smoke_baseline/` does not exist), so a changed screenshot fails nothing — these need human eyes. Open at least `tools/smoke-out/50-sales-mode.png` (the strip gone, the road there) and `53-handover-sheet.png`.

- [ ] **Step 5: Commit**

```bash
git add tools/ui_smoke.py tools/smoke-out/
git commit -m "test(smoke): the road is checked for absence, not just for errors"
```

---

### Task 9: Close the slice

- [ ] **Step 1: Full verification**

```bash
uv run pytest -q
uv run pytest tests/scenarios -q
uv run --with websocket-client python tools/ui_smoke.py
(cd docs/integration-contract && sha256sum -c contract.sha256)
```

- [ ] **Step 2: Update `plan/current-status.md`** with a new session-close section at the top: what the road is, that it replaced the strip and `checklist.js`, what the browser caught that the unit tests could not, and that U05 is the next slice.

- [ ] **Step 3: Delete this plan** — `docs/superpowers/plans/README.md`: *"Keep a plan while its work is in flight. Delete it in the commit that finishes it."*

```bash
git rm docs/superpowers/plans/2026-09-06-salesperson-road.md
git add plan/current-status.md
git commit -m "docs(status): the salesperson's road is the navigation"
```
