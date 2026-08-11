# Structure & parts — implementation plan

**Status: complete** — all five tasks shipped (report, endpoint, tab, tagged drawings + dimensions, print sheet). Deviations from the plan as written are noted per task.

Spec: `docs/superpowers/specs/2026-08-11-structure-and-parts-design.md`

**Goal:** the strategy shows how the structure is laid out and what each piece consists of.

**Architecture:** one new pure read-model (`fenceai/report/structure.py`) over an existing
run, one read-only endpoint, one new frontend tab plus tags/dimensions on the two drawings.
No new persisted state, no generation change.

**Tech:** Python 3.12 + Pydantic v2 (backend), vanilla ES modules (frontend), pytest +
node-run JS tests + the CDP smoke suite.

## Global constraints

- Int mm at rest; the report carries mm and the client converts (ADR-0002 addendum).
- Tags derived per run, never stored; element ids unchanged.
- Every user-visible string through `t()`/`tu()`, both bundles, `esc()` on interpolation.
- The report never re-derives quantities: it inverts existing pegs.

---

### Task 1 — the read model

**Files:** create `src/fenceai/report/__init__.py`, `src/fenceai/report/structure.py`;
test `tests/report/test_structure.py`.

**Interfaces produced:** `build_structure(topology, strategy, requirements, bom) ->
StructureReport` and the models in the spec.

- [x] Test first: a straight 6 m run with a gate → sections tagged `A`, posts `P1..Pn` in
      station order, bays `B1..`, gate `G1`; `stations[i].spacing_mm == station[i] -
      station[i-1]`; the last station equals the run length.
- [x] Test: Σ parts per SKU across all elements ≡ BOM engineering qty per SKU, and anything
      unpegged appears in `Totals.unassigned`.
- [x] Test: purity — two calls on the same inputs return equal reports; the report contains
      no object identity from the strategy (mutating the strategy afterwards doesn't change
      a built report).
- [x] Implement by inverting `RequirementLine.pegs` and `BomLine.pegs`; cut pieces via
      `CutPlan.bars[].pieces[].requirement_id` for `from_bar`.
- [x] Commit.

### Task 2 — the endpoint

**Files:** modify `src/fenceai/api/app.py`; test `tests/api/test_api.py`.

- [x] Test: `GET /api/runs/{run_id}/structure` returns sections/bays/parts for a generated
      run; unknown run → 404; the response is byte-identical on a second call.
- [x] Implement next to `/bom` (same `_run` + requirements/bom derivation path).
- [x] Commit.

### Task 3 — the Structure tab

**Files:** modify `src/fenceai/web/static/index.html`, create
`src/fenceai/web/static/js/structure.js`, modify `app.js`, `style.css`, both `i18n/*.json`;
test `tests/web/test_locale_bundles.py` (key parity is automatic), smoke additions.

- [x] Section cards: setting-out table (tag · station · spacing · kind · SKU) and bay table
      (tag · width · height · mode · parts summary), gates row; all lengths via `tu()`.
- [x] Row click → `setSelection({runId, elementId})`; the canvas, side view and inspector
      already follow selection.
- [x] Detail toggle: installer (default) / customer — the customer view drops screw/concrete
      lines and shows materials as a described scope (spec §"Two presentations").
- [x] Smoke: generate → open the tab → a bay row shows its parts; clicking it selects the
      element on the canvas; the customer view has no screw line.
- [x] Commit.

### Task 4 — tags and dimensions on the drawings

*Deviation: the tag cache became its own module (`js/structure-data.js`) rather than living
in the tab, so the tab, the plan canvas and the side view all read the same tags; and
`tabs.js` now announces `tab-changed` through `state.js` instead of calling into another
module. The tolerance mark went to the CLOSING bay, not the widest one — a crew sets out
from the start, so that is where accumulated tape error lands.*

**Files:** modify `js/editor.js` (plan tags), `js/profile.js` (side-view tags + dimension
string); `style.css`; smoke additions.

- [x] Post tags along the run in the plan; bay tags inside the panels in the side view.
- [x] One chained centre-to-centre dimension string under the side view plus an overall run
      dimension; the closing bay marked as the tolerance-absorbing one (AIA-minimal).
- [x] Tag derivation lives in ONE place — reuse the report's ordering via the endpoint, so a
      tag in the table and a tag in the drawing can never disagree.
- [x] Smoke: the tag drawn on a bay equals the tag in its table row.
- [x] Commit.

### Task 5 — the printable sheet

**Files:** `style.css` (`@media print`), a print button in the Structure tab.

- [x] Print stylesheet: drawing + schedules, one page, no chrome; landscape hint.
- [x] Smoke: the print stylesheet hides the toolbar and the tab bar (checked via
      `matchMedia('print')` styles, not by printing).
- [x] Commit.

## Staging

Tasks 1–3 are the feature ("what is it, and what is it made of"). Task 4 makes the tables
usable against the drawing. Task 5 is what goes to site. Each stage ships on its own.

## Self-review notes

- The report must not become a second BOM: the Σ-equivalence test (Task 1) is the guard.
- Selection is the only coupling between the tab and the drawings — no module reaches into
  another's DOM.
- If `requirements`/`bom` derivation turns out to be expensive for large projects, the
  endpoint can cache per run id; do not optimise before measuring.
