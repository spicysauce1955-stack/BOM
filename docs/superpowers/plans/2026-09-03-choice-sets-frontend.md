# Hand Placement and the Choices Panel — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person drag any post exactly where it goes — in the plan view or the side
view — and answer the plan's open questions from the plan itself.

**Architecture:** One pure module holds the drag arithmetic, and two thin adapters feed it
from two canvases that share no code. Neither adapter touches the other's DOM; both write
one override through `state.js`. The panel reads `run.choice_sets` and writes selections.
**The browser computes positions, never quantities** — every count comes from the backend.

**Tech Stack:** Vanilla ES modules, inline SVG, no framework and no build step. pytest +
node for the pure module; `tools/ui_smoke.py` (CDP) for the gestures.

**Spec:** `docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md` —
§9 and §10 are this plan's sections. Read §0 first: rev 1's frontend tasks had no
executable assertion between them.

**Status:** Task 1 **DONE** (`c52a334`). Tasks 2–6 open.

**Companion plan:** `2026-09-03-choice-sets-backend.md`. **Correction:** an earlier draft of
this header said Task 1 needed nothing from the backend plan. That was false and an agent
proved it — Task 1's own test imports `yield_threshold` from `fenceai.strategy.layout`,
which is the backend plan's Task 2. The MODULE is pure and independent; the TEST that keeps
its twin honest is not. **Task 1 depends on backend Task 2.** Tasks 2–5 additionally need
the backend's anchored overrides (its Tasks 3–4) and the choices CRUD (its Task 5).

## Global Constraints

- **Modules communicate ONLY via `state.js`.** No module touches another's DOM subtree.
  `pushSnapshot` lives in **`history.js`**, not `state.js`.
- **Mutation order:** `pushSnapshot(label)` → mutate `state.project` → `saveTopology()`.
  After a non-topology mutation use `reloadProject()`, never `openProject()`, or the undo
  stack is wiped.
- **A pure module imports nothing from a view** — and `units.js` imports `state.js`, so
  `post-drag.js` cannot use `snapStep()`. The display unit arrives as a parameter.
- **Anchors are segment-local:** author with `geom.anchorFor`, resolve with
  `geom.stationOfAnchor`; never read `anchor.offset_mm` as a station.
- **Display units** convert at the field boundary (`toDisplayValue`/`toMm`) and render
  through `tu()`. Storage and payloads stay integer millimetres.
- **i18n:** every user-visible string through `t()` or `data-i18n`; `en.json` and `he.json`
  keep identical key sets. **Obligation 5 — the source's own lexeme is displayed beside our
  millimetres** (`24" (610 mm)`), and `Quantity.value_raw` carries it.
- CSS uses logical properties only. **The plan canvas and the side-view profile are NEVER
  mirrored in RTL.** Any user text through `esc()`.
- **No auto-generation.** Generation stays behind the explicit button. A drop draws the
  placement as a **pending marker** from `state.project.overrides` — distinct from a
  generated post — because the overlay still holds the previous run's posts and without the
  marker the dropped post springs back.
- `tools/ui_smoke.py` records pass/fail **only** through `check(name, ok, detail)`. It
  does no image diffing and `tools/smoke_baseline/` does not exist — so a screenshot-only
  case reports PASS while the bug ships. **Every smoke case here asserts through
  `check()`.**

---

## File structure

| File | Responsibility |
|---|---|
| `src/fenceai/web/static/js/post-drag.js` | **new.** Preview layout, snap candidates (pre-filtered), violations, the yield threshold. Pure. |
| `tests/web/test_post_drag_module.py` | **new.** The pure module in node, including the cross-language threshold grid. |
| `src/fenceai/web/static/js/choices.js` | **new.** The panel. |
| `src/fenceai/web/static/js/editor.js` | adapter A — the plan canvas. |
| `src/fenceai/web/static/js/profile.js` | adapter B — the side view. |
| `src/fenceai/web/static/js/inspector.js` | the post inspector: three directives get their first control. |
| `src/fenceai/web/static/js/history.js` | `project.choices` in the snapshot. |
| `src/fenceai/web/static/i18n/{en,he}.json` | every new key, both bundles. |
| `tools/ui_smoke.py` | four new cases, all with `check()` assertions. |

---

### Task 1: `post-drag.js` — the arithmetic, out of both views

**Files:**
- Create: `src/fenceai/web/static/js/post-drag.js`
- Test: `tests/web/test_post_drag_module.py`

**Interfaces:**
- Consumes: **nothing.** No DOM, no `state.js`, no `units.js`, no view import.
- Produces: `layoutWithPin(fixed, length, station, {maxSpanMm, minSpanMm})`,
  `snapCandidates({station, prev, next, maxSpanMm, minSpanMm, displayUnit, stock, piecesPerBay, pieceShorterByMm})`,
  `violations(widths, {maxSpanMm, minSpanMm})`, `yieldThreshold(stockMm, kerfMm, pieces)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_post_drag_module.py
"""Post-drag arithmetic (static/js/post-drag.js), run in node.

Two canvases drag a post: the plan view, where a pointer must be projected onto
the run's polyline, and the side view, where the axis is a chained global
coordinate. The arithmetic they share lives here so they cannot drift — the same
arrangement `base-top.js` has for the profile's base transforms.

`yieldThreshold` exists in Python too (`strategy/layout.py`), deliberately. The
grid below is the only thing keeping the two honest.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { layoutWithPin, snapCandidates, violations, yieldThreshold }
  from "./js/post-drag.js";

const grid = {};
for (const [s, k, p] of [[2000,3,1],[2000,3,2],[2000,3,3],[2000,0,2],
                         [2438,3,2],[6000,5,4],[0,3,2],[2000,3,0]]) {
  grid[`${s}/${k}/${p}`] = yieldThreshold(s, k, p);
}
console.log(JSON.stringify({
  grid,
  pinned: layoutWithPin([0, 5000], 5000, 2500, {maxSpanMm: 2000}).widths,
  snaps: snapCandidates({
    station: 3960, prev: 2000, next: 5000, maxSpanMm: 2000, minSpanMm: 0,
    displayUnit: "mm", stock: {lengthMm: 2000, kerfMm: 3},
    piecesPerBay: 10, pieceShorterByMm: 0,
  }).map((s) => [s.kind, s.station]),
  bad: violations([1281, 1281, 2438], {maxSpanMm: 1676, minSpanMm: 0}),
}));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True)
    # The line that makes this a test: without it a module that fails to parse
    # produces no assertion failure at all.
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_two_yield_thresholds_are_one_formula(out):
    """The Python side is the reference — NOT a second literal. Rev 1 hard-coded
    998 in both languages and called that pinning them together."""
    from fenceai.strategy.layout import yield_threshold
    for key, got in out["grid"].items():
        stock, kerf, pieces = (int(x) for x in key.split("/"))
        assert got == yield_threshold(stock, kerf, pieces), key


def test_a_pin_splits_a_run_and_the_maximum_still_applies(out):
    """Rev 1 asserted `[2500, 2500]` "because neither exceeds the maximum" —
    2500 exceeds 2000. The preview must be the layout the backend will build, or
    the drag is a half-priced promise."""
    from fenceai.strategy.layout import equal_layout
    assert out["pinned"] == [1250, 1250, 1250, 1250]
    assert out["pinned"] == equal_layout(2500, 2000) + equal_layout(2500, 2000)


def test_no_snap_is_offered_that_the_module_would_itself_refuse(out):
    """Rev 1's yield tick at 3998 made the PREVIOUS bay 1998 — and at 4002, 2002,
    2 mm over the maximum passed into the same call. A rail that offers a
    violation rewards a person with a permanent warning on the customer's
    quote."""
    stations = [s for _, s in out["snaps"]]
    assert stations, "some snap is offered"
    assert all(s - 2000 <= 2000 and 5000 - s <= 2000 for s in stations)


def test_a_violation_names_the_bay_the_code_and_the_overshoot(out):
    assert out["bad"] == [{"index": 2, "code": "span_placed_over_maximum",
                            "over_mm": 762}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_post_drag_module.py -q`
Expected: FAIL — node cannot resolve `./js/post-drag.js`

- [ ] **Step 3: Write minimal implementation**

```javascript
// Pure drag arithmetic for a post: what the layout becomes, where it may snap,
// and what rule a placement breaks. No DOM, no state, no view imports — and no
// units.js, which imports state.js. The plan canvas and the side view both call
// this, and the only way they cannot drift is if neither of them owns it.
// Tested in node (tests/web/test_post_drag_module.py), as base-top.js is.
//
// It computes POSITIONS. It never computes a quantity: every board count on the
// panel comes from the backend, because a second implementation of the packing
// would eventually advertise a saving the cut list does not deliver — and
// plan_cuts packs GLOBALLY, pairing a 998 with a 1002 across bays, so per-bay
// yield is not decomposable into a run-level promise anyway.

/** The longest PIECE that still yields `pieces` per stock length. Mirrors
 *  strategy/layout.py::yield_threshold — and tests/web/test_post_drag_module.py
 *  compares the two over a grid rather than trusting two literals. */
export function yieldThreshold(stockMm, kerfMm, pieces) {
  if (pieces < 1 || stockMm <= 0) return 0;
  return Math.floor((stockMm + kerfMm) / pieces) - kerfMm;
}
```

...plus `layoutWithPin` (insert the station into the fixed list and fill each gap the way
`layout.equal_layout` does — `ceil`, then the remainder spread one millimetre at a time,
which the node test pins against the Python function), `violations`, and
`snapCandidates` — which builds round / equal-to-neighbour / yield candidates, converts the
yield threshold from a **piece** length to a bay width by adding `pieceShorterByMm`, and
**returns only candidates that `violations()` accepts.**

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/web/test_post_drag_module.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/post-drag.js tests/web/test_post_drag_module.py
git commit -m "feat(web): pure post-drag arithmetic, shared by both canvases and pinned to the Python threshold"
```

---

### Task 1b: Mirror the re-anchor policy in `geom.js`

**Files:**
- Modify: `src/fenceai/web/static/js/geom.js`
- Test: `tests/web/test_geom_anchor_module.py` (create, node)

Backend Task 3 put a `reanchor: "proportional" | "rigid"` policy on `Anchor` and honoured
it inside `anchor_station`. **`geom.stationOfAnchor` still resolves everything
proportionally** — verified: `grep reanchor js/geom.js` finds nothing. Nothing is broken
today because no JS code creates a rigid anchor yet, but the frontend contract is explicit
that these two functions *"mirror backend `make_anchor`/`anchor_station` exactly"*, and the
moment Task 2 posts a rigid anchor the canvas would draw a dragged post in a different
place from the generator — 800 mm apart on the spec's own worked example.

- [ ] **Step 1:** a node test asserting `stationOfAnchor` on a stretched segment returns the
  proportional station for a `proportional` anchor and the rigid offset for a `rigid` one,
  with the same numbers `tests/topology/test_anchor_reanchor.py` pins on the Python side.
  Copy the harness from `tests/web/test_base_top_module.py`, including
  `assert proc.returncode == 0, proc.stderr`.
- [ ] **Step 2:** run it; the rigid case fails.
- [ ] **Step 3:** branch on `anchor.reanchor`, defaulting to `proportional` when the field
  is absent — a stored anchor has no such key and must keep its behaviour.
- [ ] **Step 4:** `uv run pytest tests/web -q`, then the full suite.
- [ ] **Step 5:** commit.

**Do this before Task 2**, not after: Task 2 is what starts posting rigid anchors.

**Known, pre-existing, and deliberately not fixed here.** Python's `round()` is
banker's rounding; JS `Math.round` is half-up. On a *proportional* anchor whose scaled
offset lands exactly on `.5`, the two resolvers differ by 1 mm — inside
`NUMERIC_TOLERANCE_MM`, present long before this work, and outside the one function this
task touches. The agent that found it chose case values avoiding the tie rather than
hiding it. Flagged because the frontend contract's wording is *"mirror … exactly"*: if
that is to be literally true, the proportional arm needs its own change and its own
reason.

---

### Task 2: Adapter A — dragging in the plan canvas

**Files:**
- Modify: `src/fenceai/web/static/js/editor.js`, `tools/ui_smoke.py`,
  `src/fenceai/web/static/i18n/{en,he}.json`

**Interfaces:**
- Consumes: `post-drag.js`; `geom.stationAtPoint` (**returns `{station, dist}`**),
  `geom.anchorFor`, `history.pushSnapshot`, `apiSend`, `reloadProject`.
- Produces: a `drag.kind === "post"` session that DELETEs the pin it started from and
  POSTs a `pin_post` carrying a **rigid** anchor.

- [ ] **Step 1: Add the smoke cases first, with real assertions**

```python
# tools/ui_smoke.py — new cases
check("a post can be dragged and lands where the pointer did",
      c.js("state.project.overrides.filter(o => o.directive.kind === 'pin_post').length")
      == "1")
check("the pin carries a segment-local RIGID anchor, not a station",
      c.js("JSON.stringify(state.project.overrides"
           ".filter(o => o.directive.kind === 'pin_post')"
           ".map(o => [o.directive.anchor.segment_index,"
           "           o.directive.anchor.offset_mm,"
           "           o.directive.anchor.reanchor]))")
      == '[[0,2500,"rigid"]]')
check("dragging the same post twice leaves ONE pin",
      c.js("state.project.overrides.filter(o => o.directive.kind === 'pin_post').length")
      == "1")
check("a drag does not also open the inspector",
      c.js("document.querySelector('#inspector').dataset.open || ''") == "")
check("one drag is one undo step",
      c.js("String(window.__historyDepth)") == "1")
```

The overlay is gated behind `#chk-overlay` and posts only exist once a run does, so the
case generates first and ticks the box.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: the new cases FAIL — the post `<circle>`s carry no `data-*` attributes, so
nothing is draggable. The other 262 pass.

- [ ] **Step 3: Write minimal implementation**

Four edits, in this order:

1. **Give a post identity.** Where the overlay draws each post, add `data-post`,
   `data-run` and `data-station` — none exist today.
2. **Extend the existing drag session** rather than adding a second one:
   `drag = {kind: "post", runId, from: +ds.station, start: [ev.clientX, ev.clientY]}`.
   The 4 px threshold, the single `pushSnapshot`, and pointer capture are reused.
3. **`onDragMove`:** `const {station} = stationAtPoint(run, mx, my)` — it returns an
   object — then `snapCandidates(...)`, then draw into a **preview layer only**. Never
   `state.project`, never history, never a fetch.
4. **`pointerup`:** DELETE the override the drag started from (the session carries
   `from`), then POST `{kind: "pin_post", anchor: {...anchorFor(runId, station),
   reanchor: "rigid"}}`, then `reloadProject()`. Set a `suppressClick` latch so the
   completed drag does not also fire the circle's existing `click`→`inspect`; a gesture
   under the threshold is the click, and opens the inspector.
5. **Draw the pending marker.** `reloadProject()` does not refresh `state.result`, so the
   overlay still holds the previous run's posts. Render each `pin_post` override as a
   pending post at its resolved station, visibly distinct from a generated one, so the
   dropped post stays where it was dropped. This is not cosmetic: a pin is saved project
   state, a post position is un-recomputed run state, and the two must not look alike.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run --with websocket-client python tools/ui_smoke.py && uv run pytest tests/web -q`
Expected: all cases pass.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/editor.js tools/ui_smoke.py \
        src/fenceai/web/static/i18n/en.json src/fenceai/web/static/i18n/he.json
git commit -m "feat(web): drag a post in the plan canvas — projected, anchored, and one pin per post"
```

---

### Task 3: Adapter B — dragging in the side view

**Files:**
- Modify: `src/fenceai/web/static/js/profile.js`, `tools/ui_smoke.py`

**Interfaces:**
- Consumes: the same `post-drag.js` exports. **No import from `editor.js`.**
- Produces: the same override shape as Task 2, through `state.js`.

**The premise rev 1 got wrong:** the profile's x axis is **not** the station.
`buildChain()` chains several runs with `GAP_MM` spacers and a `reversed` flag —
`gsOf = offset + (reversed ? L - s : s)`. A naive division moves the post the wrong way on
a reversed run and into the wrong run on a chain. Use `localStationOf(entry, x)`.

- [ ] **Step 1: Add the smoke cases first**

```python
check("a post dragged in the side view lands on the right run",
      c.js("JSON.stringify(state.project.overrides.map(o => o.run_id))")
      == '["run2"]')
check("a reversed section drags in the direction the pointer moved",
      c.js("String(state.project.overrides[0].directive.anchor.offset_mm > 1000)")
      == "true")
check("the plan canvas shows the same post moved, without either module knowing the other",
      c.js("document.querySelectorAll('[data-post][data-pinned=\"1\"]').length") == "1")
```

The third is the cross-view property, and it holds only because both adapters write one
override through `state.js` and both re-render from state.

- [ ] **Step 2: Run it and watch it fail.**
- [ ] **Step 3: Implement** — the same gesture idiom the profile already uses for top dots
  (including its proximity snap), with every number delegated to `post-drag.js`. Do not
  inline the arithmetic; that is the rule `base-top.js` exists to enforce.
- [ ] **Step 4: Run the smoke suite and `tests/web`.**
- [ ] **Step 5: Commit.**

---

### Task 4: The choices panel

**Files:**
- Create: `src/fenceai/web/static/js/choices.js`
- Modify: `js/tabs.js` (mount), `js/history.js`, `i18n/{en,he}.json`
- Test: `tests/web/test_choices_panel.py` (node), plus a smoke case

**Interfaces:**
- Consumes: `state.result.choice_sets`, `state.project.choices`, `apiSend`,
  `reloadProject`, `t`, `tu`, `esc`.
- Produces: `renderChoices(host, sets, selections)`; `deltaLabel(point)`;
  `valueLabel(point, key)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_choices_panel.py
"""The panel's two pieces of arithmetic-shaped logic.

The renderer is DOM and belongs in the smoke suite. `deltaLabel` and
`valueLabel` are the parts that are wrong at 3 a.m. — a sign, a plural, and an
obligation.
"""
SCRIPT = """
import { deltaLabel, valueLabel } from "./js/choices.js";
console.log(JSON.stringify({
  saving: deltaLabel({delta: {posts: -3, boards: -5}}),
  none: deltaLabel({delta: {}}),
  worse: deltaLabel({delta: {cuts: 20}}),
  concrete: deltaLabel({delta: {concrete_l: -66, holes: -3}}),
  lexeme: valueLabel({bindings: {footing_depth_mm: 610},
                      lexemes: {footing_depth_mm: '24\\"'}}, "footing_depth_mm"),
  bare: valueLabel({bindings: {footing_depth_mm: 610}, lexemes: {}},
                   "footing_depth_mm"),
}));
"""
```

Asserted, with `assert proc.returncode == 0, proc.stderr` first:

- `saving == "−3 posts · −5 boards"` — a real minus sign (U+2212), not a hyphen;
- `none == "no material change"` — a statement, not a blank;
- `worse == "+20 cuts"`;
- `concrete == "−66 L concrete · −3 holes"` — the open axes reaching the label;
- **`lexeme == '24" (610 mm)'`** — obligation 5: the source's own words, ours in
  parentheses;
- `bare == "610 mm"` — no invented lexeme where the publisher gave none.

- [ ] **Step 2: Run it and watch it fail** — node cannot resolve `./js/choices.js`.
- [ ] **Step 3: Implement** the module: read state, render into the given host only, write
  through `apiSend` + `reloadProject()`, every string through `t()`, every interpolated
  label through `esc()`, lengths through `tu()`. Add `project.choices` to `history.js`'s
  `snapshot()` — it is not there, so undo currently pops the wrong gesture.
- [ ] **Step 4: Run** `uv run pytest tests/web -q` and the smoke suite with a case
  asserting that answering a question changes `state.project.choices`, leaves
  `state.result` untouched — **not** an auto-generation — and shows the answer as pending,
  the same treatment a dropped post gets:

```python
check("answering a question does not fire a generation",
      c.js("state.result.run.id") == before_run_id)
check("the answer is visible as pending rather than silently stored",
      c.js("document.querySelectorAll('.choice-pending').length") == "1")
```
- [ ] **Step 5: Commit.**

---

### Task 5: The post inspector — three directives that have never had a control

**Files:**
- Modify: `src/fenceai/web/static/js/inspector.js`, `i18n/{en,he}.json`,
  `tools/ui_smoke.py`

- [ ] **Step 1: Add the smoke cases** — select a post, force its sku, assert the BOM line's
  sku changes; force masonry mounting, assert the footing line changes; and assert that
  **dropping a post onto a corner is refused at the pointer** rather than creating an
  override that immediately reports itself orphaned (only a line post can be suppressed).
- [ ] **Step 2: Run it and watch it fail** — there is no post inspector.
- [ ] **Step 3: Implement** — the selected post's panel, one control per directive
  (`force_post_sku`, `force_mounting`, `force_vertical`) plus the suppress button, every
  label in both bundles.
- [ ] **Step 4: Run the smoke suite and the full python suite.**
- [ ] **Step 5: Commit.**

---

## Self-review

**Spec coverage.** §9.1 the pure module → Task 1; adapter A → Task 2; adapter B → Task 3.
§9.2 the gesture discipline → Task 2 steps 3–4 and Task 3. §2's panel → Task 4. §8.1's
four unreachable directives → Tasks 2 (suppress) and 5. §13's obligation 5 → Task 4's
`valueLabel` test. §16's no-auto-generation → Task 4 step 4.

**Placeholders:** none. Tasks 3 and 5 carry their assertions as `check()` calls and their
implementations as named edits, because the deliverable there is a gesture in a browser and
the arithmetic behind it is fully specified in Task 1.

**Type consistency:** `layoutWithPin`, `snapCandidates`, `violations`, `yieldThreshold`,
`deltaLabel`, `valueLabel` — each defined once and called with the same shape after. The
override payload is written in exactly one shape by both adapters.

**The three failure modes, checked:** no assertion here is a screenshot (every smoke case
calls `check()`); no test rebuilds the object under test; and the node fixtures are
module-scoped over a **pure** module with no state to leak. The one thing I cannot check
from here is whether `node` is installed on the runner — hence the explicit skip, matching
`test_base_top_module.py`.
