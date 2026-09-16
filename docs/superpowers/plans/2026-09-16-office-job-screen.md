# Office job screen implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A backoffice person takes a job and lands on a plan of it — every section open beside the map with its own elevation, every problem marked where it actually is — and turns editing on deliberately rather than landing in it.

**Architecture:** Two new pure read models (`report/sections.py`, `report/flags.py`) answer *what is each stretch* and *where does each problem live*. One new frontend module owns the screen and composes what already exists: `state.selection.runId` for the stretch, the note-marker anchoring idiom for the marks, `elevation.js`'s detached-SVG style for the card drawings. The office road is untouched and becomes what the edit switch opens.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest. Frontend: vanilla ES modules, no build step, no framework, Hebrew-first RTL.

**Spec:** `docs/superpowers/specs/2026-09-16-office-job-screen-design.md`. Read §3 (why the run is the click unit), §5 (layers never hide) and §6 (posture, not permission) before Task 1 — each records a decision that looks like a preference and is not.

## A note on the test code in this plan

**Tasks state the BEHAVIOUR each test must assert; they do not paste fixture code.** The last plan executed in this repo carried written-out test code and every unrun error in it shipped into the run: two vacuous assertions that provably could not fail, a test that could never go green, and a dataclass that could not hold its own subclass. Plan prose gets reasoned about; plan test code gets typed blind.

So each task names the assertions, their inputs and their expected outcomes precisely enough to write blind — and the executor writes the fixtures against the real types.

## Scope

Ends with **the product owner taking a job off the queue, landing on a map of it, seeing the 1 120 mm step marked on section A, clicking that mark, and reading that section's elevation without a single editing control on screen.**

**In scope:** the two read models and their routes, the screen, section cards with thumbnail elevations, placed flag marks, two-way selection, fit-to-section, the reading/editing switch, and the pre-generation rest state.

**Out of scope, with the trigger:**

* **Selecting a bay** (spec §3). The card's elevation is drawn from `Section.bays[]` and each bay carries its `element_id`, so the handler has somewhere to go. *Trigger: an office person asking why one bay came out that width.*
* **Dismissing a flag with a written reason** (spec §4). New stored fact, new command; this slice adds neither. *Trigger: the first "that warning is not a fault on this job".*
* **Extracting `drawProfile` from `js/profile.js`** (spec §10). *Trigger: the office asking for the full side view inside reading mode.*
* **Route-level capacity.** Unchanged from `2026-09-15-backoffice-design.md` §3. The switch is presentation and the plan says so out loud.
* **Hiding `#tabs` from the backoffice.** The screen ships beside the tabs, exactly as the road did, for the same reason.

## Global Constraints

- **Read models recompute nothing** (foundation §15). `report/sections.py` reads `topology/station.py`; `report/flags.py` reads what handover, readiness and the stored run already emit. Neither re-evaluates a rule or re-derives a quantity.
- **`report/` may not import the store or `fenceai.api`** — pinned by `tests/architecture/test_fitness.py`. The route loads, the read model decides, the route serialises.
- **Integer millimetres at rest** (ADR-0002). No float reaches a model field.
- **Every new code needs entries in BOTH `i18n/he.json` and `en.json`**, key sets identical, guarded the way `HANDOVER_CODES` is.
- **A quoted `DocumentWarning` is never a flag.** Flags are platform items with `code + params`. A manufacturer's sentence goes once into the annexe (contract §3.3.5) and never onto a mark.
- **A new route needs `docs/architecture/04-backend.md` updated** — the count line AND the table. `tests/architecture/` checks it.
- **Every user-visible string through `t()` or `data-i18n`.** Any user or expert text into `innerHTML` goes through `esc()`.
- **CSS uses logical properties only.** The plan canvas and every elevation are NEVER mirrored in RTL; station 0 stays on the left (spec §9).
- **Colour never encodes alone** (spec §4): every mark carries a glyph, every row names its state in words.
- Run everything with `uv run`. Both tiers before every commit: `uv run pytest -q` and `uv run --with websocket-client python tools/ui_smoke.py`.

## File Structure

| File | Responsibility |
|---|---|
| `src/fenceai/report/sections.py` | `SectionFacts`, `section_facts(topology)` — per-stretch facts that need no generation run. Pure. |
| `src/fenceai/report/structure.py` | `_section_tag` becomes public `section_tag(index)`; both read models use the one implementation. |
| `src/fenceai/report/flags.py` | `Place`, `JobFlag`, `job_flags(...)` — every platform item, each carrying where it belongs. Pure. |
| `src/fenceai/api/app.py` | `GET /api/projects/{id}/sections`, `GET /api/projects/{id}/flags`. |
| `src/fenceai/web/static/js/section-elevation.js` | Pure. Returns a detached SVG thumbnail for one section. No imports of state, no listeners. |
| `src/fenceai/web/static/js/job-screen.js` | The screen: two panes, card list, flag list, the switch. Owns `#job-screen` and its subtree only. |
| `src/fenceai/web/static/js/flag-marks.js` | Draws marks into `#g-flags`. Mirrors `notes.js: renderNoteMarkers` in shape; does not touch `#g-notes`. |
| `src/fenceai/web/static/js/editor.js` | Gains `fitToRun(runId)`. |
| `src/fenceai/web/static/js/state.js` | `drawingLockedFor` learns the office's answer. |
| `src/fenceai/web/static/index.html` | `#job-screen`, its two panes, `#g-flags` inside the canvas SVG. |
| `src/fenceai/web/static/style.css` | The screen's layout, the sticky map, the mark styles, the lock extension. |

---

## Task 1: `section_tag` becomes one implementation

The smallest possible first change, and it exists so Task 2 cannot invent a second lettering.

**Files:**
- Modify: `src/fenceai/report/structure.py` (`_section_tag`, and its call site)
- Test: `tests/report/test_structure.py`

**Interfaces:**
- Produces: `section_tag(index: int) -> str` — public, `0 -> "A"`, `25 -> "Z"`, `26 -> "AA"`.

- [ ] **Step 1: Write the failing test**

Assert that `section_tag` is importable from `fenceai.report.structure` and that it answers `"A"`, `"Z"`, `"AA"` and `"AB"` for `0`, `25`, `26` and `27`. Assert also that a built `StructureReport` over a two-run topology tags its sections `"A"` and `"B"` — so the rename cannot silently stop being used.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/report/test_structure.py -q`
Expected: FAIL on the import — `section_tag` does not exist.

- [ ] **Step 3: Rename**

Rename `_section_tag` to `section_tag`, keep the docstring verbatim, update the call site inside `build_structure`. No behaviour change.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS. A private-name reference anywhere else fails here.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/report/structure.py tests/report/test_structure.py
git commit -m "refactor(report): section_tag is public, so two read models cannot letter differently"
```

---

## Task 2: `report/sections.py` — what a stretch is, with no run

**Files:**
- Create: `src/fenceai/report/sections.py`
- Test: `tests/report/test_sections.py`

**Interfaces:**
- Consumes: `section_tag` (Task 1); `fenceai.topology.station` — `run_length`, `run_points`, `corner_stations`, `ground_samples`, `max_slope_permille`, `ground_step_stations`, `base_surface_at`, `base_transition_stations`, `base_top_at`, `base_top_step_stations`, `fence_model_at`.
- Produces:

```python
class GroundPoint(BaseModel):
    station_mm: Mm
    z_mm: Mm

class Step(BaseModel):
    """A cliff: where it is, and how far it jumps. A separate type from
    GroundPoint because `delta_mm` is a DIFFERENCE and `z_mm` is a height —
    one model carrying both would invite a renderer to draw a step at its
    own size above the ground."""
    station_mm: Mm
    delta_mm: Mm

class SurfaceRun(BaseModel):
    """One stretch of one base surface, half-open [start, end)."""
    start_mm: Mm
    end_mm: Mm
    surface: str

class SectionFacts(BaseModel):
    run_id: str
    tag: str
    length_mm: Mm
    surfaces: list[SurfaceRun]
    base_surface: str          # the one surface, or "mixed"
    ground: list[GroundPoint]
    max_slope_permille: int
    ground_steps: list[Step]
    base_top_steps: list[Step]
    corner_stations: list[Mm]
    height_intent_mm: Mm | None        # None = nobody said
    height_covered_mm: Mm              # how much of the run an intent covers
    fence_model_id: str                # "" = the project default applies

def section_facts(topology: Topology) -> list[SectionFacts]: ...
```

- [ ] **Step 1: Write the failing tests**

Assert, over a topology built in the test (three runs, one on `masonry_wall` throughout, one with a surface change part way, one with no base event at all):

1. **One entry per run, in topology order, tagged A, B, C.** Not sorted by id — the letters must follow the drawing.
2. **`length_mm` equals `run_length`** for each, and is an `int`.
3. **A run with one base event across its whole length reports `base_surface` equal to that surface and exactly one `SurfaceRun`.**
4. **A run whose surface changes part way reports `base_surface == "mixed"` and two `SurfaceRun`s whose `end_mm`/`start_mm` meet exactly**, with no gap and no overlap.
5. **A run with no base event reports the silent default `"soil"`** — the same answer `base_surface_at` gives — and it is *visible*, not omitted. This is the whole point of the read model: an unstated surface must arrive as a fact somebody can see, not as an absence.
6. **`height_intent_mm` is `None` when no `height_intent` event covers any of the run**, and `height_covered_mm` is `0`. When an intent covers 4 000 mm of an 8 000 mm run, `height_covered_mm` is `4000` — "half of this run has no stated height" must be answerable.
7. **`ground` is non-empty and its first and last stations are 0 and `length_mm`.**
8. **Pure:** calling it twice on the same topology returns equal results, and the topology is unchanged afterwards (compare a deep copy).

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/report/test_sections.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

A pure module in `handover.py`'s shape: a module docstring saying what it is for and why it is not part of the structure report (it must answer before a run exists), then the models above and one function that walks `topology.runs` in order.

Two rules to write into the code as comments, because both are decisions:

* **`base_surface` is `"mixed"`, never a guess.** A stretch standing on two things has no single answer, and picking the longer one would put a surface on a card that half the fence is not standing on.
* **The `"soil"` default is REPORTED, not hidden.** `base_surface_at` falls back to it; this model surfaces that fallback rather than leaving the field blank, because a blank reads as "nobody has looked".

- [ ] **Step 4: Run the tests and the suite**

Run: `uv run pytest tests/report/test_sections.py -q` then `uv run pytest -q`
Expected: PASS, including the architecture fitness tests — this module may import `fenceai.topology` and nothing from `fenceai.api` or `fenceai.store`.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/report/sections.py tests/report/test_sections.py
git commit -m "feat(report): what each stretch is, before anything is generated"
```

---

## Task 3: `GET /api/projects/{id}/sections`

**Files:**
- Modify: `src/fenceai/api/app.py`
- Modify: `docs/architecture/04-backend.md` (count line AND table)
- Test: `tests/api/test_sections_route.py`

**Interfaces:**
- Consumes: `section_facts` (Task 2).
- Produces: `GET /api/projects/{project_id}/sections` → `{"sections": [SectionFacts, ...]}`.

- [ ] **Step 1: Write the failing tests**

1. **200 with one entry per run** for the demo project fixture, tags `A`, `B`, `C`.
2. **404 for an unknown project id**, matching how the neighbouring project routes answer.
3. **It never 409s on a changed topology.** This route reads the topology itself, so there is nothing it can be stale against — unlike `/structure`, which refuses. Assert that bumping the topology revision and calling again returns 200 with the new geometry.
4. **An empty topology returns `{"sections": []}`**, not a 404 and not an error. A job with nothing drawn is a real state and the screen renders it (Task 10).

- [ ] **Step 2: Run and watch fail**

Run: `uv run pytest tests/api/test_sections_route.py -q`

- [ ] **Step 3: Add the route**

Beside `GET /api/projects/{id}/handover`. The route loads the project and serialises; it holds no logic.

- [ ] **Step 4: Update the backend doc**

`docs/architecture/04-backend.md` — increment the route count line and add the table row. The architecture fitness test fails without it, and only in the full suite.

- [ ] **Step 5: Run both tiers**

Run: `uv run pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/api/app.py docs/architecture/04-backend.md tests/api/test_sections_route.py
git commit -m "feat(api): GET /projects/{id}/sections"
```

---

## Task 4: `report/flags.py` — every problem, and where it lives

This is the read model the screen is really about. It carries no new findings; it places the ones we already emit.

**Files:**
- Create: `src/fenceai/report/flags.py`
- Test: `tests/report/test_flags.py`

**Interfaces:**
- Consumes: `HandoverGap` (`report/handover.py`), `ReadinessItem` (`report/readiness.py`), `StrategyWarning` (`strategy/model.py`), `ChoiceSet` (`strategy/choices.py`).
- Produces:

```python
Severity = Literal["blocking", "open", "answered"]

class Place(BaseModel):
    """Where a flag belongs on the drawing. Every field optional because the
    four kinds carry different handles; `kind` says which to read."""
    kind: Literal["job", "run", "station", "node", "element"]
    run_id: str = ""
    station_mm: Mm | None = None
    node_id: str = ""
    element_id: str = ""

class JobFlag(BaseModel):
    code: str
    params: dict = {}
    severity: Severity
    places: list[Place]     # a gap covering three runs has three places
    source: Literal["handover", "readiness", "strategy"]

def job_flags(*, gaps, items, warnings, choice_sets) -> list[JobFlag]: ...
```

- [ ] **Step 1: Write the failing tests**

Assert, from real shapes rather than invented ones:

1. **A `height_assumed` gap whose `params["run_ids"]` is `["run1","run2","run3"]` produces one flag with three `Place(kind="run")`** — one per run id, and none invented. The count of places equals the count of run ids.
2. **A gap with no `run_ids` produces one `Place(kind="job")`.** It is still placed; "the whole job" is a place.
3. **A `choices_unanswered` item whose `params["scopes"]` is `["gap:run2:0", "gap:run3:0"]` produces two places of kind `"station"`, with `run_id` `"run2"`/`"run3"` and `station_mm` `0`.** The scope string is parsed in exactly one place, this one.
4. **A malformed scope does not raise and does not vanish.** A scope that is not `gap:<run>:<int>` falls back to `Place(kind="job")` and the flag still appears. A screen that silently drops a flag it cannot place is worse than one that shows it unplaced — assert the flag is present.
5. **A `StrategyWarning` with `element_refs=["post@run1:4000"]` produces `Place(kind="element", element_id="post@run1:4000", run_id="run1", station_mm=4000)`** — parsed from the ref, so the mark lands at the step and not at the middle of the run.
6. **A warning with `params["node_id"]="n8"` and no element refs produces `Place(kind="node", node_id="n8")`.**
7. **Severity maps from the source, never from the code.** A `StrategyWarning` with `severity="error"` is `blocking`; `severity="warning"` is `open`; a `HandoverGap` with `blocking=True` is `blocking` and otherwise `open`. Assert one of each, and assert that no `ReadinessItem` is ever `blocking` — readiness deliberately has no blocking items and the mapping must not invent one.
8. **A `DocumentWarning` handed in anywhere is refused or ignored — never placed.** Assert `job_flags` produces no flag for one. Quoting a manufacturer's sentence onto a fence mark is the failure the split registry exists to prevent.
9. **Pure and ordered:** blocking first, then open, then answered; stable for equal inputs.

- [ ] **Step 2: Run and watch fail**

Run: `uv run pytest tests/report/test_flags.py -q`

- [ ] **Step 3: Implement**

One module. The scope parser and the element-ref parser are each one small function with a docstring naming the format they parse and what they do with a string that does not match it (fall back to the job, never drop).

- [ ] **Step 4: Run the tests and the suite**

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/report/flags.py tests/report/test_flags.py
git commit -m "feat(report): every flag, carrying where it belongs on the drawing"
```

---

## Task 5: `GET /api/projects/{id}/flags`

**Files:**
- Modify: `src/fenceai/api/app.py`
- Modify: `docs/architecture/04-backend.md`
- Test: `tests/api/test_flags_route.py`

**Interfaces:**
- Produces: `GET /api/projects/{project_id}/flags?run_id=<id>` → `{"flags": [JobFlag, ...], "run_id": str}`. `run_id` omitted means the project's latest run; no run at all means handover flags only.

- [ ] **Step 1: Write the failing tests**

1. **With no generation run, the answer contains handover flags and no strategy flags**, and the response's `run_id` is `""`. This is the pre-generation state and it must be a normal 200.
2. **After generating, the same project answers with strategy flags too**, including one whose place is an element.
3. **A `run_id` naming a run of a different project is refused**, not silently answered — match the existing refusal `run_not_on_this_job` used by the command door.
4. **The route never 409s on a stale topology.** Flags are *how you find out* something moved; refusing to list them because something moved is the wrong way round. Assert 200 after a topology change.

- [ ] **Step 2: Run and watch fail**

Run: `uv run pytest tests/api/test_flags_route.py -q`
Expected: FAIL — no such route, 404 from FastAPI.

- [ ] **Step 3: Add the route**

Beside `/sections` from Task 3. It loads the project, the named run (or the latest), that run's stored strategy and choice sets, calls `handover_gaps`, `readiness` and `job_flags`, and serialises. The route holds the loading and the refusal; `job_flags` holds every decision about placement.

**Read warnings off the STORED run.** Re-evaluating rules against the active snapshot re-resolves them to "current" (contract 3.2.1) and recomputes something the run already decided — the same constraint `warnings_unreviewed` carries.

- [ ] **Step 4: Update the backend doc**

`docs/architecture/04-backend.md` — the count line AND the table row. The architecture fitness test runs only in the full suite.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/api/app.py docs/architecture/04-backend.md tests/api/test_flags_route.py
git commit -m "feat(api): GET /projects/{id}/flags"
```

---

## Task 6: `js/section-elevation.js` — the thumbnail, pure

**Files:**
- Create: `src/fenceai/web/static/js/section-elevation.js`
- Test: `tests/web/test_section_elevation_module.py` (node, like `test_base_top_module.py`)

**Interfaces:**
- Consumes: nothing. **No imports at all** — this is the `elevation.js` contract, and it is what makes the module node-testable.
- Produces:

```javascript
/** A detached <svg> thumbnail of one section. Interactivity is opt-in. */
export function renderSectionElevation(section, opts) // opts: {width, height, onSelectBay}
/** Pure geometry, exported for the test: bay rectangles in svg units. */
export function bayRects(section, width, height)
```

`section` is either a `Section` from the structure report (`bays[]` with `start_station_mm`, `width_mm`, `height_mm`, `bottom_z_start_mm`, `bottom_z_end_mm`) or a `SectionFacts` from Task 2 (`ground[]`, `height_intent_mm`, no bays). The module answers for both.

- [ ] **Step 1: Write the failing node tests**

Assert over `bayRects`:

1. **Six bays in, six rectangles out**, in station order, the first starting at x=0 and the last ending at the full width.
2. **A bay with `height_mm: 0` produces a rectangle of zero panel height** and is flagged in the returned shape so the renderer can draw it as the "no fence here" marker rather than an invisible box. This is section A of the demo job — three of its six bays — and a thumbnail that silently drew nothing there would hide the exact thing the screen exists to show.
3. **Taller base means a lower panel:** for two bays of equal `height_mm` and different `bottom_z_*`, the one with the greater bottom z has the smaller y (higher on screen), and both have equal rectangle heights.
4. **A section with no bays but with `ground` renders the ground line and no panels**, returning an empty rect list rather than throwing. Pre-generation is a normal input.
5. **Station 0 is at x=0 regardless of locale.** The module takes no locale and has no mirroring; assert the first bay's x is the smallest.
6. **Pure:** two calls return equal results and the input object is not mutated.

- [ ] **Step 2: Run and watch fail**

Run: `uv run pytest tests/web/test_section_elevation_module.py -q`

- [ ] **Step 3: Implement**

Follow `js/elevation.js` exactly: build the element with `document.createElementNS`, return it, attach nothing. `bayRects` is the pure half and carries the arithmetic.

- [ ] **Step 4: Run the tests**

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/section-elevation.js tests/web/test_section_elevation_module.py
git commit -m "feat(web): a section's elevation as a pure, detached drawing"
```

---

## Task 7: The screen shell, and the cards

**Files:**
- Create: `src/fenceai/web/static/js/job-screen.js`
- Modify: `src/fenceai/web/static/index.html`, `style.css`, `js/app.js` (wire `initJobScreen`), `i18n/he.json`, `i18n/en.json`
- Test: `tools/ui_smoke.py`

**Interfaces:**
- Consumes: `/api/projects/{id}/sections`, `renderSectionElevation` (Task 6), `state.selection` and `setSelection` from `js/state.js`, `t()` from `js/i18n.js`, `esc()` from `js/api.js`.
- Produces: `initJobScreen()`; owns `#job-screen`, `#job-map`, `#job-sections`, `#job-flags`, `#job-mode`.

**New DOM ids are how this screen escapes `step-surfaces.js`** — that machinery is a deny-list of known ids, so an id in none of its four maps is in no step's hide list. Do not reuse an id it already scopes.

- [ ] **Step 1: Add the failing smoke assertions**

In a new `_smoke_office_job_screen`, signed in as the backoffice account with a job claimed:

1. **The screen is visible and the office road band is not** — landing on a job as backoffice shows `#job-screen`, and `#road` is hidden.
2. **One card per section, lettered A, B, C**, read off `#job-sections`.
3. **Each card names its length and what it stands on**, in Hebrew, with the length rendered through `tu()` so a `cm` display preference changes it.
4. **A card carries an elevation** — an `<svg>` inside it with at least one rectangle.
5. **No editing control is on screen**: assert `#toolbar .tool` is not visible, `#job-panel` is not visible, and `#profile-base-bar` is not visible.

- [ ] **Step 2: Run the smoke and watch them fail**

Run: `uv run --with websocket-client python tools/ui_smoke.py`

- [ ] **Step 3: Build the shell**

`index.html` gains `#job-screen` with two panes. `job-screen.js` fetches `/sections`, renders a card per section, mounts a thumbnail per card. Every string through `t()`; every length through `tu()`; customer and address through `esc()`.

The module **communicates only via `state.js`** and touches no other module's subtree.

- [ ] **Step 4: Add the locale entries**

Both bundles, identical key sets. `tests/web/test_locale_bundles.py` is what catches a miss.

- [ ] **Step 5: Run both tiers**

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static/js/job-screen.js src/fenceai/web/static/index.html src/fenceai/web/static/style.css src/fenceai/web/static/js/app.js src/fenceai/web/static/i18n/he.json src/fenceai/web/static/i18n/en.json tools/ui_smoke.py
git commit -m "feat(web): the office lands on a plan of the job, not on step one of a road"
```

---

## Task 8: Flag marks on the plan, and the list beside it

**Files:**
- Create: `src/fenceai/web/static/js/flag-marks.js`
- Modify: `src/fenceai/web/static/index.html` (`#g-flags` inside the canvas SVG, after `#g-notes`), `js/job-screen.js`, `style.css`, both locale bundles
- Test: `tools/ui_smoke.py`, `tests/web/test_locale_bundles.py`

**Interfaces:**
- Consumes: `/api/projects/{id}/flags`, `geom.pointAtStation`, `geom.runById`, `geom.toPx`, `setSelection`.
- Produces: `renderFlagMarks(flags)`; owns `#g-flags` **only**.

- [ ] **Step 1: Add the failing smoke assertions**

On the demo job, after generating:

1. **Five marks are drawn** — section A's step, two unanswered choice sets, the node disagreement, the gate mismatch — and the count in `#g-flags` equals the count of placed flags in the response. Not a hardcoded 5: read both and compare, so the check survives the job changing.
2. **A blocking mark and an open mark are distinguishable by more than colour** — assert the glyph text differs, not the fill.
3. **Clicking a mark selects its run**: `state.selection.runId` becomes `run1` after clicking section A's mark, and that card gains the selected attribute.
4. **Clicking a flag row does the same thing as clicking its mark.** Assert both paths reach the same selection — this is the click-through rule of spec §4.
5. **A flag whose place is the whole job has a row and no mark**, and does not throw.
6. **`#g-notes` is untouched**: assert the note-marker count is unchanged by flags rendering.

- [ ] **Step 2: Run the smoke and watch them fail**

- [ ] **Step 3: Implement**

`flag-marks.js` mirrors `notes.js: renderNoteMarkers` in shape — resolve each place to a point, draw a marker group, everything `pointer-events` controlled at the group. A `station` place resolves through `pointAtStation`; a `run` place resolves to the run's midpoint, the same rule `anchorPointFor` already uses for `run:<id>`; a `node` place resolves to the node; an `element` place resolves through its parsed run and station.

- [ ] **Step 4: Add locale entries for anything new**, both bundles.

- [ ] **Step 5: Run both tiers**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(web): every problem is drawn where it actually is"
```

---

## Task 9: Two-way selection and fit-to-section

**Files:**
- Modify: `src/fenceai/web/static/js/editor.js` (export `fitToRun`), `js/job-screen.js`
- Test: `tests/web/` node test for the viewBox arithmetic if it is extractable; otherwise `tools/ui_smoke.py`

**Interfaces:**
- Produces: `export function fitToRun(runId)` in `js/editor.js` — fits the canvas viewBox to that run's extent plus a margin. `fitView()` stays private and whole-project; this is a second, named capability, not a signature change to the first.

- [ ] **Step 1: Add the failing smoke assertions**

1. **Clicking a card selects its stretch on the map**: the run's polyline gains the selected styling and `state.selection.runId` matches the card.
2. **Clicking the map selects the card**: the reverse, asserted by reading the card's selected attribute.
3. **Selecting a section changes the canvas viewBox**, and selecting the whole job again restores a viewBox containing every run. Assert the viewBox actually changed — a fit that silently does nothing is the failure mode.
4. **Selection survives a locale switch.** Flipping to English re-renders the cards; assert the same run is still selected afterwards. Re-render wiping selection is the bug this catches.

- [ ] **Step 2: Run and watch fail**

- [ ] **Step 3: Implement**

`job-screen.js` listens for `selection-changed` and re-renders only its own selected state. It never writes the selection from inside its own render — that is a loop.

- [ ] **Step 4: Run both tiers**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): one selection, both directions, and the map follows it"
```

---

## Task 10: The pre-generation state

**Files:**
- Modify: `src/fenceai/web/static/js/job-screen.js`, both locale bundles
- Test: `tools/ui_smoke.py`

- [ ] **Step 1: Add the failing smoke assertions**

On a job with a drawing and **no generation run**:

1. **Cards still render**, one per section, carrying length, what it stands on, and the ground line — the facts `/sections` answers without a run.
2. **The card does NOT claim there are no problems.** Assert the card shows neither a "clear" state nor a bay count; assert instead that the screen carries the not-yet-generated sentence.
3. **Generate is the one obvious action**, and it is present and enabled.
4. **A failed `/sections` fetch renders as failed, not as empty.** Assert the three states are distinguishable: not yet loaded, loaded and empty, failed. This is audit finding B01 — a 500 once rendered as "Nothing missing — this job is ready to hand over".
5. **A job with nothing drawn renders the empty state**, not a crash, and says what to do.
6. **A generated job whose drawing then MOVED renders its generated half as stale, not as absent.** Move a node after generating, reload the screen, and assert: the card still shows its topology facts (length, surface, ground — those cannot be stale, the route reads the topology itself), the generated half is marked stale in words, and **nothing recomputed on its own**. Generation stays behind its button. This is spec §7's middle state and the 409 `topology_changed` the structure route already raises.

- [ ] **Step 2: Run and watch fail**

- [ ] **Step 3: Implement**

Four explicit states in the module, never `data || []`: not yet loaded, loaded and empty, loaded and stale, failed. `js/structure-data.js`'s `refusalKey()` is the existing model for turning a 409 into a rendered sentence — reuse the idiom rather than inventing a second one.

- [ ] **Step 4: Run both tiers**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): a job nobody has generated says so, instead of looking finished"
```

---

## Task 11: Reading and editing

The last task, and the one the product owner asked for first. It is last because a switch that reveals a road is meaningless until there is something to switch away from.

**Files:**
- Modify: `src/fenceai/web/static/js/job-screen.js`, `js/state.js` (`drawingLockedFor`), `js/road.js` (the band is hidden while reading), `style.css`, both locale bundles
- Test: `tests/web/test_state_module.py` (node, for `drawingLockedFor`), `tools/ui_smoke.py`

**Interfaces:**
- Produces: `drawingLockedFor(view, status, mode)` — the office's answer is its MODE, the salesperson's stays its STATUS. Existing callers pass no mode and keep today's answer.

- [ ] **Step 1: Write the failing node tests for `drawingLockedFor`**

1. **Sales is unchanged**: every existing case answers exactly as it does today. Assert the current truth table still holds — this function is called from five places.
2. **Backoffice reading is locked; backoffice editing is not.**
3. **The whole-app view is never locked by this**, so an admin playing both roles is not trapped.

- [ ] **Step 2: Add the failing smoke assertions**

1. **The office lands in reading**: the switch reads off, the road band is hidden, and no tool is visible.
2. **Turning it on reveals the road**, and the road opens on its first step rather than jumping somewhere.
3. **Turning it on unlocks the tools** — assert a tool is now visible that was not.
4. **Turning it back off re-locks and re-hides the road**, and the selection survives the round trip.
5. **The side view's base buttons are locked in reading mode.** `#profile-base-bar`'s controls must not be operable — this is the gap named in spec §6: `profile.js` never checks `drawingLocked()` and the CSS lock does not cover it.
6. **Reading mode is stated in words, not only by a lock icon**, and the mode is announced to assistive tech.

- [ ] **Step 3: Run and watch them fail**

- [ ] **Step 4: Implement**

The switch sets a mode on the document root; CSS does the hiding; `drawingLockedFor` gains the mode. Write into the module's header the sentence from spec §6: **this is presentation, not protection** — what gates a mutation is a capacity check on the server, and 73 routes still have none.

Extend the lock's CSS to `#profile-base-bar`'s controls.

- [ ] **Step 5: Run both tiers**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(web): the office reads by default and edits on purpose"
```

---

## Task 12: Layers that emphasise and cannot hide

Spec §5. The screen works without this — which is the point: a layer here adds emphasis to a complete picture, never restores something that was missing.

**Files:**
- Modify: `src/fenceai/web/static/js/job-screen.js`, `style.css`, both locale bundles
- Test: `tools/ui_smoke.py`

**Interfaces:**
- Produces: `PROTECTED` — the exported list of what no layer may ever affect: the runs, the gates, the landmarks, the section letters and every flag mark. Exported so the test can assert against the list rather than against a screenshot.

- [ ] **Step 1: Add the failing smoke assertions**

1. **Three switches exist** — ground, heights, notes — and all start in a state where the screen is already complete.
2. **Turning every switch OFF hides nothing in `PROTECTED`.** Assert that with all layers off, every run polyline, every gate, every section letter and every flag mark is still visible. This is the one assertion that matters and it is the whole reason the task exists.
3. **Turning a layer on changes the drawing** — assert something measurable appears or changes style, so the switch is not decorative.
4. **A layer's state does not survive into another job.** Assert opening a second job does not carry the first job's emphasis, so nobody inherits a view they did not choose.

- [ ] **Step 2: Run and watch them fail**

- [ ] **Step 3: Implement**

A layer sets a class on the screen root; CSS emphasises. No layer rule may contain `display: none` on anything in `PROTECTED` — write that sentence into the stylesheet where the rules live, and into the module header, with the reason: a toggle that can hide a fact makes the screen simpler and makes it possible to miss the 1 120 mm step that stops this job being buildable.

- [ ] **Step 4: Run both tiers**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): layers emphasise, and the base is protected from them"
```

---

## Task 13: Cut pieces on a section card

Spec §2's decision, made real. Last, and droppable — the checkpoint does not depend on it.

**Files:**
- Modify: `src/fenceai/web/static/js/job-screen.js`, both locale bundles
- Test: `tools/ui_smoke.py`

**Interfaces:**
- Consumes: `GET /api/runs/{run_id}/bom` → `grouped`, whose `BomGroup(kind="section")` carries `element_id` equal to a **run id**.

- [ ] **Step 1: Add the failing smoke assertions**

1. **A card lists its own section's lines**, matched by `element_id === section.run_id`, showing SKU, count and cut length.
2. **No money appears on a card.** Assert no currency string and no `total_cents`-derived figure is rendered inside `#job-sections`. Buying is pooled across the job; a price here would be an apportionment nothing measured, and the codebase already refused it one level up.
3. **A shared item is not silently double-counted.** A post on a node shared by two runs must not appear as a full item on both cards without saying it is shared — assert the shared marker is rendered.
4. **With no run, the card shows no materials block at all** rather than an empty one — consistent with Task 10's rule that absence is stated, never implied.

- [ ] **Step 2: Run and watch fail**

- [ ] **Step 3: Implement**

Read the grouped BOM the screen already has; render the lines for this card's run. No arithmetic in the client — the group is the answer.

- [ ] **Step 4: Run both tiers**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): a section says what gets cut for it, and never what it costs"
```

---

## Checkpoint

**Not the tests being green.** The product owner signs in as `yossi@`, takes bob's job off the queue, and without being told anything:

* sees the fence, lettered A B C with the gate at the top right;
* sees five marks and can say what each is about;
* clicks the mark on section A and reads that half of it carries no fence;
* finds no way to change anything by accident;
* turns editing on, picks a step, and is on the road that already worked.

Then, and only then, `architecture-critic` and `test-reviewer`, fix what they find, and merge.
