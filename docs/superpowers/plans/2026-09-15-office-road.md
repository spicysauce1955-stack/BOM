# Office road implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A backoffice person opens a job and is on step 1 of seven, with each step showing only its own work and the map already saying which steps are waiting on something.

**Architecture:** One entry in `js/roads.js`, which `roadFor()` was written to accept and `road-model.js` needs no change for. Steps 1–2 read the handover sheet that already exists; steps 3–7 read one new pure read model. `step-surfaces.js` becomes road-scoped, which it is not today and which is the single largest source of risk here.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest. Frontend: vanilla ES modules, no build step, no framework.

**Spec:** `docs/superpowers/specs/2026-09-15-backoffice-design.md` §8 (the office road), with §4 (lifecycle) and §6 (the queue) for what feeds it. Read §8 in full before Task 1 — three landmines are named there and all three are real.

## Why this plan exists separately

`2026-09-15-backoffice-queue.md` built the screen BEFORE the road: the list, who has a job, and the commands that move it between desks. Opening a job from that list still lands on the engineer's app — nine tabs in no order, which is the exact thing the road replaces. The product owner's words: *"we said the backoffice will work in steps just like the sales agent — this is far from it."*

They are right, and the gap is one registry entry wide.

## Scope, and what is deliberately not here

Ends with **the product owner taking a job off the queue, landing on step 1, and walking to step 7 without being told where anything is.**

**In scope:** the road entry, the readiness read model, the two acknowledgements, road-scoped step surfaces, the job header, and making a queue row open its job.

**Out of scope, with the reason:**

* **`commit_plan` and the committed-plan view.** Step 6 renders `no_plan_committed` as a step that is never `done` until that lands — honest, and visibly unfinished rather than quietly wrong. *Trigger: this plan's checkpoint passing.*
* **Doing it by hand** (spec §9), including taking over the cut plan. Step 5 reports `supply_unresolved` and offers no takeover yet.
* **The agent proposing** (spec §11).
* **Hiding `#tabs` from the backoffice.** The road ships BESIDE the tabs. Flipping that is its own change with the smoke updated on purpose — the same discipline the sales MVP used for not flipping the default view in the commit that introduced the mechanism. *Trigger: the road being what people actually navigate by.*

## Global Constraints

- **No road step may gate `POST /generate`** (contract 3.2.4). Pinned by a test.
- **`warnings_unreviewed` reads warnings OFF THE STORED RUN.** It must never re-evaluate rules against the active snapshot — that re-resolves to "current" (contract 3.2.1) and recomputes a quantity (foundation §15).
- **It counts `StrategyWarning` only, never `DocumentWarning`** (contract 3.3.5). A warning quoted from a manufacturer's document goes once into the annexe and never onto a line.
- **Readiness items are `ReadinessItem`, never `Gap`.** `Gap` is a binding contract type with eight closed kinds; `HandoverGap` already shares the English word. Never routed to `POST /gaps`.
- **Every new code needs `readiness.<code>` in BOTH bundles**, with a `READINESS_CODES` list guarded the way `HANDOVER_CODES` is.
- **A new route needs `docs/architecture/04-backend.md` updated** — the count line AND the table.
- **Every user-visible string through `t()` or `data-i18n`**; `he.json` and `en.json` keep identical key sets.
- **Any user text into `innerHTML` goes through `esc()`.**
- Run everything with `uv run`. Both tiers before every commit: `uv run pytest -q` and `uv run --with websocket-client python tools/ui_smoke.py`.

## File Structure

| File | Responsibility |
|---|---|
| `src/fenceai/report/readiness.py` | `ReadinessItem`, `readiness(project, run, supply)`, `READINESS_CODES`. Pure; mirrors `handover.py` in shape and discipline. |
| `src/fenceai/api/app.py` | `GET /api/projects/{id}/readiness` — the run-scoped half, beside the existing `/handover`. |
| `src/fenceai/project/model.py` | `Acknowledgement` and `Project.acknowledgements`. |
| `src/fenceai/commands/desk.py` | two rows: `acknowledge_sale`, `acknowledge_warnings`. |
| `src/fenceai/web/static/js/roads.js` | `OFFICE_ROAD`, and `ROADS` gains a second key. |
| `src/fenceai/web/static/js/step-surfaces.js` | **road-scoped.** The maps become `{roadKey: {stepKey: [...]}}`. |
| `src/fenceai/web/static/js/road.js` | opens on `def.steps[0].key`; renders for any road, not only `sales`. |
| `src/fenceai/web/static/js/queue.js` | a row click opens its job. |

---

## Task 1: A queue row opens its job

The smallest gap and the most obviously broken: today only *Take it* is wired, so you take a job and stay on the list.

**Files:**
- Modify: `src/fenceai/web/static/js/queue.js`
- Test: `tools/ui_smoke.py` (extend `_smoke_backoffice_queue`)

**Interfaces:**
- Consumes: `openProject(id)` from `js/state.js` — the same call the project picker makes.
- Produces: nothing new.

- [ ] **Step 1: Add the failing smoke assertion**

In `_smoke_backoffice_queue`, after the Take-it assertions:

```python
    c.js("document.querySelector('#queue-list tr:nth-child(2) td').click(); 'ok'")
    wait_for(c, "!!document.getElementById('project-select').value", timeout=15)
    check("clicking a row opens that job",
          c.js("document.querySelector('#tabs button.active')?.dataset.tab") != "queue",
          c.js("document.querySelector('#tabs button.active')?.dataset.tab"))
```

- [ ] **Step 2: Run the smoke and watch that check fail**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: FAIL on "clicking a row opens that job" — the click does nothing.

- [ ] **Step 3: Wire the row**

In `queue.js`'s existing `#queue-list` click handler, before the `.queue-take` branch:

```javascript
    const row = e.target.closest("tr[data-id]");
    // A click on the Take-it button is not a click on the row: taking a job and
    // opening it are different intentions, and doing both would open a job the
    // person may only have meant to claim.
    if (row && !e.target.closest(".queue-take")) {
      const { openProject } = await import("./state.js");
      await openProject(row.dataset.id);
      setTab("canvas");
      return;
    }
```

- [ ] **Step 4: Run the smoke and watch it pass**

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/queue.js tools/ui_smoke.py
git commit -m "fix(web): a queue row opens its job"
```

---

## Task 2: The readiness read model

**Files:**
- Create: `src/fenceai/report/readiness.py`
- Test: `tests/report/test_readiness.py`

**Interfaces:**
- Consumes: `Strategy`, `GenerationRun` (`strategy/model.py`); `Bom` (`fulfillment/`); `Project`.
- Produces: `ReadinessItem(code: str, params: dict, blocking: bool)`, `readiness(project, *, run=None, strategy=None, bom=None) -> list[ReadinessItem]`, `READINESS_CODES: list[str]`.

The codes, and what each means:

| code | fires when |
|---|---|
| `choices_unanswered` | an open choice set has no `Selection` |
| `no_run` | no generation run exists |
| `warnings_unreviewed` | a run exists and no `warnings_reviewed` acknowledgement matches its id |
| `supply_unresolved` | the BOM has unresolved lines |
| `no_plan_committed` | `committed_run_id` is empty |
| `plan_stale` | the committed run's topology revision is behind the project's |
| `not_priced` | no quote exists for the committed run |
| `sale_unread` | no `sale_read` acknowledgement matches the current annotation ids |

- [ ] **Step 1: Write the failing test**

```python
import pytest

from fenceai.project.model import Project
from fenceai.report.readiness import READINESS_CODES, readiness


def test_a_fresh_job_needs_a_run_before_anything_downstream_is_a_question():
    """`no_run` is the anchor of the run-scoped half. Reporting "no plan
    committed" beside it would be three ways of saying the same thing."""
    codes = {i.code for i in readiness(Project(id="p", name="x"))}
    assert "no_run" in codes
    assert "warnings_unreviewed" not in codes
    assert "supply_unresolved" not in codes


def test_it_reads_warnings_off_the_STORED_run_and_never_re_evaluates():
    """Contract 3.2.1: re-fetch historical runs by hash, never re-resolve to
    "current". Re-running the evaluator here would also recompute a quantity in
    a read model, which foundation §15 forbids on its own.

    Pinned by signature: `readiness` takes a strategy and never a knowledge base,
    so there is nothing in scope to evaluate against.
    """
    import inspect
    params = inspect.signature(readiness).parameters
    assert "knowledge" not in params
    assert "snapshot" not in params


def test_a_document_warning_is_not_an_office_to_do():
    """Contract 3.3.5: a warning quoted from a manufacturer's document goes once
    into the plan's annexe and never onto a line. Counting one here would both
    misplace it and make a liability sentence look like our finding."""
    from fenceai.core.warnings import DocumentWarning
    from fenceai.strategy.model import Strategy, StrategyWarning

    strategy = Strategy(
        warnings=[StrategyWarning(code="gate_on_slope", severity="warning")])
    quoted = [DocumentWarning(text_raw="Do not install below 5C", lang="en")]
    items = readiness(Project(id="p", name="x"), strategy=strategy,
                      quoted_warnings=quoted)
    item = next(i for i in items if i.code == "warnings_unreviewed")
    assert item.params["n"] == 1


def test_every_code_it_can_emit_is_listed():
    """`HANDOVER_CODES`' rule, applied here: a code with no entry in both bundles
    reaches a screen as its own key, and that has shipped green four times in
    this repo."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "src" / "fenceai" / "report"
           / "readiness.py").read_text()
    emitted = set(re.findall(r'ReadinessItem\(code="([a-z_]+)"', src))
    assert emitted <= set(READINESS_CODES), sorted(emitted - set(READINESS_CODES))


def test_nothing_here_is_blocking_because_nothing_here_may_stop_a_run():
    """Contract 3.2.4: never fail a run over a gap. `blocking` exists on the
    type to match `HandoverGap`'s shape, and no office item sets it — a step
    that refused to let somebody generate would be the first thing worked
    around."""
    assert all(not i.blocking for i in readiness(Project(id="p", name="x")))
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/report/test_readiness.py -q`
Expected: FAIL — `No module named 'fenceai.report.readiness'`

- [ ] **Step 3: Write `readiness.py`**, mirroring `handover.py`'s docstring discipline: each check says what it prevents, and `READINESS_CODES` is hand-maintained beside the emitting sites.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Add `readiness.<code>` to both bundles** and extend the locale test the way `test_every_handover_code_has_locale_entries` does.

- [ ] **Step 6: Run `uv run pytest -q`, then commit**

```bash
git add src/fenceai/report/readiness.py tests/report/test_readiness.py \
        src/fenceai/web/static/i18n tests/web/test_locale_bundles.py
git commit -m "feat(report): what the office still has to do"
```

---

## Task 3: The two acknowledgements

**Files:**
- Modify: `src/fenceai/project/model.py`
- Modify: `src/fenceai/commands/desk.py`
- Test: `tests/project/test_acknowledgements.py`

**Interfaces:**
- Produces: `Acknowledgement(kind, anchor, by, at)`, `Project.acknowledgements: list[Acknowledgement]`; command kinds `acknowledge_sale`, `acknowledge_warnings`.

- [ ] **Step 1: Write the failing test**

```python
def test_reading_the_sale_stops_being_true_when_a_note_arrives():
    """Anchored to the SET of annotation ids at the time of reading. A promise
    added after somebody read the job is a promise nobody has read."""
    p = Project(id="p", name="x", annotations=[_note("a1")])
    p = perform("acknowledge_sale", {}, p, actor="user:u_y",
                capacity="backoffice", now=NOW)
    assert "sale_unread" not in {i.code for i in readiness(p)}

    p.annotations.append(_note("a2"))
    assert "sale_unread" in {i.code for i in readiness(p)}


def test_reviewing_warnings_dies_with_the_run_it_was_about():
    """Anchored to `run_id`, and orphaned the way an override is when its
    station moves. A new run means new warnings nobody has read."""
    p = _job_with_run("run_1")
    p = perform("acknowledge_warnings", {"run_id": "run_1"}, p,
                actor="user:u_y", capacity="backoffice", now=NOW)
    assert "warnings_unreviewed" not in _codes(p, run_id="run_1")
    assert "warnings_unreviewed" in _codes(p, run_id="run_2")


def test_an_acknowledgement_names_who_made_it():
    """The point of the whole exercise: "somebody read this" is worth nothing
    without a name against it."""
    p = perform("acknowledge_sale", {}, Project(id="p", name="x"),
                actor="user:u_yossi", capacity="backoffice", now=NOW)
    assert p.acknowledgements[-1].by == "user:u_yossi"


def test_acknowledging_twice_replaces_rather_than_accumulating():
    """One answer per question. A list that grows every time somebody presses
    the button is a list nothing can read."""
    p = Project(id="p", name="x")
    p = perform("acknowledge_sale", {}, p, actor="user:u_a", capacity="backoffice", now=NOW)
    p = perform("acknowledge_sale", {}, p, actor="user:u_b", capacity="backoffice", now=NOW)
    assert len([a for a in p.acknowledgements if a.kind == "sale_read"]) == 1
    assert p.acknowledgements[-1].by == "user:u_b"
```

- [ ] **Step 2: Run it and watch it fail.**

- [ ] **Step 3: Add `Acknowledgement` to `project/model.py`.** `anchor` is a plain string: the sorted annotation ids joined, or a run id. Named facts, never step keys — `Stated`'s own argument.

- [ ] **Step 4: Add the two command rows** to `desk.py`, `capacities={"backoffice", "admin"}`, `from_states=frozenset()` (any state).

- [ ] **Step 5: Run `uv run pytest -q`, then commit.**

---

## Task 4: `step-surfaces.js` becomes road-scoped

**The largest risk in this plan.** `STEP_TOOLS`, `STEP_PANELS` and `STEP_DRAWING` are global maps keyed by step key, with `STEP_KEYS = Object.keys(STEP_TOOLS)` deriving each step's hidden list by subtraction. `road-model.js`'s `panelFor` is *already* road-scoped for exactly this reason: *"two roads may each have a `review` step; a search over one global list would silently return the first match."*

**Files:**
- Modify: `src/fenceai/web/static/js/step-surfaces.js`, `js/road.js`, `style.css`
- Test: `tests/web/test_step_surfaces.py`

- [ ] **Step 1: Write the failing test**

```python
def test_two_roads_may_name_a_step_the_same_thing():
    """The collision this refactor exists to prevent. Sales step 3 is `layout`;
    an office road that also had one would get the salesperson's draw tool."""
    assert toolsFor("sales", "layout") != toolsFor("office", "generate")
    assert toolsFor("office", "nonexistent-step") == []
```

- [ ] **Step 2: Run it and watch it fail.**

- [ ] **Step 3: Make the maps two-level** — `{sales: {...}, office: {...}}` — and `hiddenForStep(road, step)` derive its union per road.

- [ ] **Step 4: Regenerate the stylesheet's mirrored copy.** `test_step_surfaces.py` checks the two for EQUALITY, not overlap.

- [ ] **Step 5: `road.js` opens on `def.steps[0].key`** rather than the hard-coded `"job"`, and sets `data-step` for any role with a road rather than only `sales`.

- [ ] **Step 6: Run `uv run pytest -q` and the smoke.** The sales road's 428 checks must not move — this task changes no sales behaviour, only where its lists live.

- [ ] **Step 7: Commit.**

---

## Task 5: `OFFICE_ROAD`

**Files:**
- Modify: `src/fenceai/web/static/js/roads.js`, `js/road.js`, `js/view.js`, `index.html`, both bundles
- Test: `tests/web/test_road_module.py`, `tools/ui_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_office_road_shares_no_step_key_with_the_salespersons():
    """Not one step is a rename. Her road captures what was sold; this one
    decides how it gets built — and a shared key is a shared surface list."""
    assert set(_keys("sales")) & set(_keys("office")) == set()


def test_the_office_road_is_seven_steps_and_starts_at_the_sale():
    assert _keys("office") == ["sale", "blanks", "questions", "generate",
                               "materials", "plan", "price"]


def test_every_office_step_owns_at_least_one_check():
    """The completeness lie the eight-step road was written against: three of
    six steps owned nothing and could only ever read `done`."""
    for step in ROADS["office"]["steps"]:
        assert step["requires"], step["key"]
```

- [ ] **Step 2: Run it and watch it fail.**

- [ ] **Step 3: Add `OFFICE_ROAD`** with the seven steps from spec §8, `anchor: "no_fence_drawn"`, `wants` the four job fields, `commits: true` on `sale`, `generate`, `plan`, `price`.

- [ ] **Step 4: `ROADS` gains `office`**, and `roadFor` is given the VIEW rather than the capacity — a view is what decides what is drawn.

- [ ] **Step 5: The job header** — breadcrumb, status, who has it, hand back.

- [ ] **Step 6: Extend the smoke case** — take a job, land on step 1, walk to step 7, assert each step's own surfaces are the only ones visible.

- [ ] **Step 7: Both tiers, then commit.**

**STOP. This is the plan's checkpoint.** The product owner takes a job off the queue and walks the seven steps.

---

## Self-review against the spec

| Spec §8 | Task |
|---|---|
| Seven steps, none a rename | 5 |
| Two sources of checks, neither called a gap | 2 |
| The acknowledgements | 3 |
| `step-surfaces.js` road-scoped · the `layout` collision · `road.js`'s hard-coded first step | 4 |
| Site conditions collapsed on Generate, no new check | 5 (markup only) |
| The loop, and derived state | 2 and 5 — nothing is ticked off; every state recomputes per render |

**Named rather than dropped:** step 6 can never read `done` until `commit_plan` exists, and step 7 never until a quote can name a committed run. Both are honest — a step that reports what is genuinely undone is the road working — but a reviewer should know they will look permanently amber on every job until the next plan lands.
