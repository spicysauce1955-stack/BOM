# Eight-Step Road Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the six-step road with eight single-responsibility steps, where the two steps nothing can check are answered by a stated fact the backend can contradict.

**Architecture:** Three moves. (1) `Project.stated` holds named facts — `no_gates`, `no_promises` — and `handover_gaps()` gains two codes that fire when a fact disagrees with the drawing. (2) `road-model.js` becomes a pure engine over `(roadDef, gaps, stated)`, losing its `project` argument by naming an `anchor` check instead of computing `!drawn`. (3) `roads.js` holds the road definitions as data, so a second role is a registry entry rather than an engine change.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite; vanilla ES modules, no build step; pytest, and node for the pure-module tests.

**Spec:** `docs/superpowers/specs/2026-09-07-eight-step-road-design.md`

## Global Constraints

- **Integer millimetres and cents at rest; float only transient** (ADR-0002). Nothing in this plan handles a dimension, but do not introduce one.
- **`Stated` is unrevisioned.** Setting a fact must not bump `topology.revision`, or every derived view 409s because somebody said there are no gates.
- **Every user-visible string goes through `t("key")` or `data-i18n`**, and `i18n/he.json` and `en.json` must keep **identical key sets** — `tests/web/test_locale_bundles.py` fails otherwise. Hebrew values must be Hebrew.
- **A new `HANDOVER_CODES` entry needs a `handover.<code>` key in BOTH bundles.** The prefix is the one the existing nine use (`handover.address_missing`, `en.json:412`).
- **`road-model.js` imports nothing.** That is what makes it node-testable and what keeps a second answer to *is this job complete?* out of the frontend.
- **`road.js` may never touch a panel's DOM.** `setTab` is the only path that moves the `active` class.
- **Mutation discipline in the frontend, always in this order:** `pushSnapshot(label)` → mutate `state.project` → save. Non-user changes never push history.
- **The plan canvas and profile SVG are never mirrored in RTL.** Not touched here; do not change it.
- **Release gate:** `uv run pytest tests/scenarios -q` must stay green (281 passed at plan time). If it moves, stop and report rather than adjusting a scenario.

---

### Task 1: `Stated` on the project

**Files:**
- Modify: `src/fenceai/project/model.py` (add class near `SiteContext`, add field to `Project` at ~line 258)
- Test: `tests/project/test_stated.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `Stated(no_gates: bool = False, no_promises: bool = False)`; `Project.stated: Stated`.

- [ ] **Step 1: Write the failing test**

```python
"""`Stated` — what the salesperson says this job does NOT have."""

from __future__ import annotations

from fenceai.project.model import Project, Stated


def test_a_new_project_states_nothing():
    """Absence of a claim is not a claim. Every project that exists today has
    no `stated` on it and none of them may break."""
    p = Project(id="proj_1", name="x")
    assert p.stated == Stated()
    assert p.stated.no_gates is False
    assert p.stated.no_promises is False


def test_a_project_round_trips_a_stated_fact():
    p = Project(id="proj_1", name="x", stated=Stated(no_gates=True))
    back = Project.model_validate_json(p.model_dump_json())
    assert back.stated.no_gates is True
    assert back.stated.no_promises is False


def test_stating_a_fact_does_not_touch_the_topology_revision():
    """The whole reason `stated` sits beside `job` rather than in `Topology`:
    a claim about what is absent changes no quantity, so it must not make a
    derived view stale."""
    p = Project(id="proj_1", name="x")
    before = p.topology.revision
    p.stated.no_gates = True
    assert p.topology.revision == before


def test_an_old_document_with_no_stated_key_still_loads():
    """Forward compatibility in the direction that actually happens: the
    projects already in the database were written before this field."""
    p = Project.model_validate_json('{"id": "proj_1", "name": "x"}')
    assert p.stated == Stated()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/project/test_stated.py -q`
Expected: FAIL — `ImportError: cannot import name 'Stated'`

- [ ] **Step 3: Write the implementation**

In `src/fenceai/project/model.py`, add above `class Project`:

```python
class Stated(BaseModel):
    """What the salesperson has stated this job does NOT have.

    Named facts, never step keys. A step key would put a screen's structure
    into the project record, and `road_skips: ["gates"]` could be contradicted
    by nothing — the road engine is pure and cannot see a gate. `no_gates` is a
    claim about the FENCE, so `handover_gaps` can check it against the drawing
    without knowing that a road or a step exists.

    The point is the difference between silence and an answer. "No gates on
    this job" and "nobody got to the gates" are the same bytes today, which is
    exactly the defect `height_assumed` exists to prevent: a fence left on the
    silent 1800 mm default is indistinguishable from one confirmed at 1.8 m.
    """

    no_gates: bool = False
    no_promises: bool = False
```

And on `Project`, beside `site`:

```python
    # What the salesperson says this job does not have. Unrevisioned for
    # `job`'s reason: a claim about an absence changes no quantity, so it must
    # not bump the topology revision and 409 every derived view.
    stated: Stated = Stated()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/project/test_stated.py -q`
Expected: PASS, 4 tests

- [ ] **Step 5: Run the gate**

Run: `uv run pytest tests/scenarios -q`
Expected: 281 passed — a defaulted field adds no behaviour

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/project/model.py tests/project/test_stated.py
git commit -m "feat(project): Stated — what a job does not have"
```

---

### Task 2: The two contradiction checks

**Files:**
- Modify: `src/fenceai/report/handover.py` (`HANDOVER_CODES` at ~line 175, `handover_gaps` at ~line 107)
- Modify: `src/fenceai/web/static/i18n/en.json`, `src/fenceai/web/static/i18n/he.json`
- Test: `tests/report/test_handover_contradictions.py` (create)

**Interfaces:**
- Consumes: `Stated` from Task 1.
- Produces: codes `gates_contradicted` and `promises_contradicted` in `HANDOVER_CODES`, emitted by `handover_gaps(project)`, both `blocking=False`.

- [ ] **Step 1: Write the failing test**

```python
"""A stated fact can be wrong, and then it is a question the office asks."""

from __future__ import annotations

from fenceai.project.model import Annotation, Project, Stated
from fenceai.report.handover import HANDOVER_CODES, handover_gaps
from fenceai.topology.model import GatePayload, Node, PointEvent, Run, Topology


def _drawn() -> Topology:
    """A one-run fence, so `no_fence_drawn` does not short-circuit the list."""
    return Topology(
        revision=0,
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=8000, y_mm=0)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2")],
    )


def _with_gate() -> Topology:
    topo = _drawn()
    topo.runs[0].point_events = [
        PointEvent(id="pe1", station_mm=4000, payload=GatePayload(width_mm=1000))
    ]
    return topo


def _codes(project: Project) -> list[str]:
    return [g.code for g in handover_gaps(project)]


def test_both_codes_are_registered():
    assert "gates_contradicted" in HANDOVER_CODES
    assert "promises_contradicted" in HANDOVER_CODES


def test_no_gates_with_no_gate_is_not_contradicted():
    p = Project(id="p", name="x", topology=_drawn(), stated=Stated(no_gates=True))
    assert "gates_contradicted" not in _codes(p)


def test_no_gates_with_a_gate_on_the_drawing_is_contradicted():
    p = Project(id="p", name="x", topology=_with_gate(),
                stated=Stated(no_gates=True))
    assert "gates_contradicted" in _codes(p)


def test_a_gate_without_the_claim_is_just_a_gate():
    """The check is about the CLAIM, not about gates. A job with gates and no
    claim has nothing to report."""
    p = Project(id="p", name="x", topology=_with_gate())
    assert "gates_contradicted" not in _codes(p)


def test_no_promises_with_an_annotation_is_contradicted():
    p = Project(id="p", name="x", topology=_drawn(),
                annotations=[Annotation(id="a1", target_ref="project",
                                        text="leave the gate clear")],
                stated=Stated(no_promises=True))
    assert "promises_contradicted" in _codes(p)


def test_no_promises_with_no_annotation_is_not_contradicted():
    p = Project(id="p", name="x", topology=_drawn(),
                stated=Stated(no_promises=True))
    assert "promises_contradicted" not in _codes(p)


def test_neither_code_blocks_the_estimate():
    """A contradicted claim is a question, not a reason to withhold a price.
    `blocking` is narrow on purpose — it gates the estimate."""
    p = Project(id="p", name="x", topology=_with_gate(),
                stated=Stated(no_gates=True))
    contradiction = next(g for g in handover_gaps(p)
                         if g.code == "gates_contradicted")
    assert contradiction.blocking is False


def test_an_undrawn_job_reports_only_that():
    """`no_fence_drawn` is returned ALONE. A contradiction on a blank project
    would be a second item under "you have not drawn anything"."""
    p = Project(id="p", name="x", stated=Stated(no_gates=True))
    assert _codes(p) == ["no_fence_drawn"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/report/test_handover_contradictions.py -q`
Expected: FAIL — `assert 'gates_contradicted' in HANDOVER_CODES`

`Annotation` requires `id`, `target_ref` and `text` (`project/model.py:173-176`); `target_ref` is one of `"project"`, `"run:<id>"`, `"node:<id>"`, `"event:<id>"`.

- [ ] **Step 3: Write the implementation**

Add to `HANDOVER_CODES` (keep the existing order; append):

```python
    "gates_contradicted",
    "promises_contradicted",
```

Add to `handover.py`, above `handover_gaps`:

```python
def _contradiction_gaps(project: Project) -> list[HandoverGap]:
    """A stated absence the drawing disagrees with.

    `Stated` exists so that "no gates on this job" is an answer rather than a
    silence — and an answer can be wrong. A claim contradicted by the drawing
    is precisely one of the questions the office would otherwise phone about,
    which is what this module is for.

    NOT blocking: the office can price a fence whose gate note is stale.
    """
    out: list[HandoverGap] = []
    if project.stated.no_gates:
        gates = sum(1 for r in project.topology.runs
                    for e in r.point_events if e.payload.kind == "gate")
        if gates:
            out.append(HandoverGap(code="gates_contradicted",
                                   params={"gates": gates}))
    if project.stated.no_promises and project.annotations:
        out.append(HandoverGap(code="promises_contradicted",
                               params={"notes": len(project.annotations)}))
    return out
```

And in `handover_gaps`, after the `if not topo.runs:` early return and with the other appends, add:

```python
    out.extend(_contradiction_gaps(project))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/report/test_handover_contradictions.py -q`
Expected: PASS, 8 tests

- [ ] **Step 5: Add both locale keys to both bundles**

`en.json`, in the `handover.*` block, keeping the file's alphabetical order:

```json
  "handover.gates_contradicted": "You said there are no gates, but the drawing has {gates}.",
  "handover.promises_contradicted": "You said nothing was promised, but {notes} note(s) are recorded.",
```

`he.json`, same keys:

```json
  "handover.gates_contradicted": "נאמר שאין שערים, אבל בשרטוט יש {gates}.",
  "handover.promises_contradicted": "נאמר שלא ניתנו הבטחות, אבל קיימות {notes} הערות.",
```

- [ ] **Step 6: Run the locale guard and the gate**

Run: `uv run pytest tests/web/test_locale_bundles.py -q && uv run pytest tests/scenarios -q`
Expected: both PASS. The bundle guard is what fails if only one bundle got the key.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/report/handover.py src/fenceai/web/static/i18n/en.json \
        src/fenceai/web/static/i18n/he.json \
        tests/report/test_handover_contradictions.py
git commit -m "feat(handover): a stated absence the drawing disagrees with"
```

---

### Task 3: `PUT /api/projects/{id}/stated`

**Files:**
- Modify: `src/fenceai/api/app.py` (beside `put_job` at ~line 341)
- Test: `tests/api/test_stated_route.py` (create)

**Interfaces:**
- Consumes: `Stated` from Task 1.
- Produces: `PUT /api/projects/{project_id}/stated` taking a `Stated` body, returning the `Project`.

- [ ] **Step 1: Write the failing test**

```python
"""Stating a fact is a project edit, and it revises nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project_id(client) -> str:
    return client.post("/api/projects", json={"name": "demo"}).json()["id"]


def test_stating_no_gates_persists(client, project_id):
    r = client.put(f"/api/projects/{project_id}/stated",
                   json={"no_gates": True, "no_promises": False})
    assert r.status_code == 200
    assert r.json()["stated"]["no_gates"] is True

    again = client.get(f"/api/projects/{project_id}").json()
    assert again["stated"]["no_gates"] is True


def test_stating_a_fact_does_not_bump_the_topology_revision(client, project_id):
    """Unrevisioned on purpose. A bump here would 409 the structure sheet
    because somebody said there are no gates."""
    before = client.get(f"/api/projects/{project_id}").json()["topology"]["revision"]
    client.put(f"/api/projects/{project_id}/stated", json={"no_gates": True})
    after = client.get(f"/api/projects/{project_id}").json()["topology"]["revision"]
    assert after == before


def test_a_fact_can_be_withdrawn(client, project_id):
    client.put(f"/api/projects/{project_id}/stated", json={"no_gates": True})
    client.put(f"/api/projects/{project_id}/stated", json={"no_gates": False})
    assert client.get(f"/api/projects/{project_id}").json()["stated"]["no_gates"] is False


def test_an_unknown_project_is_a_404(client):
    assert client.put("/api/projects/proj_nope/stated",
                      json={"no_gates": True}).status_code == 404
```

This is the fixture shape `tests/api/test_fence_model_routes.py:21` already uses; `tests/api/conftest.py` also pins `FENCEAI_DB` autouse, and the per-test setting wins because `monkeypatch` is function-scoped.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/api/test_stated_route.py -q`
Expected: FAIL with 405 or 404 — the route does not exist

- [ ] **Step 3: Write the implementation**

```python
@app.put("/api/projects/{project_id}/stated")
def put_stated(project_id: str, stated: Stated) -> Project:
    """Say what this job does not have.

    Unrevisioned, like `/job` and unlike `/site` and `/topology`. Those are
    INPUTS to generation, so a derived view must be able to tell whether it is
    stale against them; a claim that there are no gates changes no quantity.

    The claim is stored as given and never validated against the drawing —
    `handover_gaps` reports the disagreement instead. Refusing the claim here
    would mean the salesperson could not record what they believe, which is
    the one thing this field exists to capture.
    """
    project = _project(project_id)
    project.stated = stated
    state.store.save_project(project)
    return project
```

Add `Stated` to the `fenceai.project.model` import at the top of `app.py`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/api/test_stated_route.py -q`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/api/app.py tests/api/test_stated_route.py
git commit -m "feat(api): PUT /projects/{id}/stated"
```

---

### Task 4: The engine, and the roads as data

**Files:**
- Rewrite: `src/fenceai/web/static/js/road-model.js`
- Create: `src/fenceai/web/static/js/roads.js`
- Rewrite: `tests/web/test_road_module.py`

**Interfaces:**
- Consumes: the two code names from Task 2.
- Produces: from `road-model.js` — `road(roadDef, gaps, stated) -> [Step]`, `panelFor(roadDef, key) -> panel | null`, `STATES`. From `roads.js` — `SALES_ROAD`, `ROADS`, `roadFor(role) -> RoadDef | null`. `Step` is `{ key, panel, state, gaps, skippable, skipped }`.

- [ ] **Step 1: Write `roads.js`** — data only, no logic

```js
// The road DEFINITIONS. Data, not behaviour: `road-model.js` is the engine and
// imports nothing, so everything role-specific lives here.
//
// See docs/superpowers/specs/2026-09-07-eight-step-road-design.md.
//
// Adding a role is one entry in `ROADS` and touches no engine code — the
// registry idiom this project uses everywhere: adding an entry is never a
// breaking change.

/** The salesperson's road. Eight steps, one responsibility each.
 *
 *  `anchor` is the check meaning THIS JOB HAS NOT STARTED. It replaces the
 *  hardcoded `!drawn` test the engine used to compute from the project, which
 *  is the whole reason the engine no longer needs one.
 *
 *  `requires` drives a step's state; `wants` is carried and rendered but never
 *  stops a step reading `done` — a nice-to-have that is absent is not
 *  incompleteness. Required-ness is a property of the STEP, not the check:
 *  `sold_by_missing` matters to a salesperson's handover and not to an office
 *  person's road over the same gaps.
 *
 *  `satisfiedBy` names the `Stated` fact that answers a step nothing can
 *  check. A step is skippable exactly when it has one. */
export const SALES_ROAD = {
  role: "sales",
  anchor: "no_fence_drawn",
  steps: [
    { key: "job", panel: "canvas",
      requires: ["customer_missing", "address_missing"],
      wants: ["sold_by_missing", "sold_on_missing"], satisfiedBy: null },
    { key: "property", panel: "canvas",
      requires: ["no_property_context"], wants: [], satisfiedBy: null },
    { key: "layout", panel: "canvas",
      requires: ["no_fence_drawn"], wants: [], satisfiedBy: null },
    { key: "sideview", panel: "canvas",
      requires: ["height_assumed", "base_assumed"], wants: [], satisfiedBy: null },
    { key: "model", panel: "canvas",
      requires: ["no_model_chosen"], wants: [], satisfiedBy: null },
    { key: "gates", panel: "canvas",
      requires: ["gates_contradicted"], wants: [], satisfiedBy: "no_gates" },
    { key: "notes", panel: "annotations",
      requires: ["promises_contradicted"], wants: [], satisfiedBy: "no_promises" },
    { key: "review", panel: "canvas",
      requires: [], wants: [], satisfiedBy: null },
  ],
};

/** Roads by role. A role absent here has no road, and `roadFor` returns null
 *  rather than defaulting to the salesperson's: showing an office person a
 *  salesperson's map would be worse than showing them none. */
export const ROADS = { sales: SALES_ROAD };
```

- [ ] **Step 2: Write the failing node test**

Rewrite `tests/web/test_road_module.py`. Keep the module docstring's argument and the existing runner (`node --input-type=module -e SCRIPT`, `cwd=STATIC`); replace `SCRIPT` and the assertions:

```python
SCRIPT = """
// No stubs: road-model.js imports nothing, which is why it is its own file.
import { road, panelFor, STATES } from "./js/road-model.js";
import { SALES_ROAD, ROADS, roadFor } from "./js/roads.js";

const g = (code, extra = {}) => ({ code, blocking: false, params: {}, ...extra });
const st = (o = {}) => ({ no_gates: false, no_promises: false, ...o });
const byKey = (r) => Object.fromEntries(r.map((s) => [s.key, s]));
const drawn = [];                    // no anchor code present == started

const out = {};
out.step_keys = SALES_ROAD.steps.map((s) => s.key);
out.panels = Object.fromEntries(SALES_ROAD.steps.map((s) => [s.key, s.panel]));
out.states = STATES;
out.roles = Object.keys(ROADS);

// the engine takes no project
out.arity = road.length;

// handover has not arrived
out.unloaded = byKey(road(SALES_ROAD, null, st()));

// nothing drawn: the anchor is present
out.empty = byKey(road(SALES_ROAD, [g("no_fence_drawn", { blocking: true })], st()));

// a drawn job, two required job fields open and one nice-to-have
out.gappy = byKey(road(SALES_ROAD, [
  g("customer_missing"), g("sold_by_missing"), g("height_assumed"),
], st()));

// everything answered, nothing stated
out.clean = byKey(road(SALES_ROAD, drawn, st()));

// stated: no gates, and the drawing agrees
out.skipped = byKey(road(SALES_ROAD, drawn, st({ no_gates: true })));

// stated: no gates, but the drawing has one
out.contradicted = byKey(road(SALES_ROAD, [g("gates_contradicted")],
                              st({ no_gates: true })));

// nothing drawn AND a fact stated: empty beats skipped
out.empty_beats_skip = byKey(road(SALES_ROAD,
  [g("no_fence_drawn", { blocking: true })], st({ no_gates: true })));

// a code no step claims must not vanish
out.orphan = byKey(road(SALES_ROAD, [g("invented_code")], st()));

// a code colliding with an inherited Object key must not throw
out.proto = byKey(road(SALES_ROAD, [g("constructor")], st()));

out.panel_of_notes = panelFor(SALES_ROAD, "notes");
out.panel_of_nothing = panelFor(SALES_ROAD, "not_a_step");
out.road_for_sales = roadFor("sales") === SALES_ROAD;
out.road_for_office = roadFor("office");
out.road_for_all = roadFor("all");

console.log(JSON.stringify(out));
"""
```

And the assertions:

```python
def test_the_road_is_eight_steps_in_the_order_the_job_is_done(out):
    assert out["step_keys"] == ["job", "property", "layout", "sideview",
                                "model", "gates", "notes", "review"]


def test_notes_is_the_one_step_whose_surface_is_another_panel(out):
    assert out["panels"]["notes"] == "annotations"
    assert {k: v for k, v in out["panels"].items() if k != "notes"} == {
        k: "canvas" for k in out["panels"] if k != "notes"}


def test_the_engine_takes_no_project(out):
    """`road(roadDef, gaps, stated)`. The project argument existed only to
    compute `!drawn`, which `anchor` now names. Three arguments, and a fourth
    would mean somebody reached for the project again."""
    assert out["arity"] == 3


def test_every_handover_code_is_claimed_by_exactly_one_step(out):
    from fenceai.report.handover import HANDOVER_CODES
    claimed = [c for step in out["claimed_codes"] for c in step]
    assert sorted(claimed) == sorted(HANDOVER_CODES), (
        "a code with no step vanishes from the road while the API still "
        "reports it; a step naming a code that does not exist reads done "
        "forever")
    assert len(claimed) == len(set(claimed)), "two steps claim one code"


def test_a_step_reads_unknown_until_the_handover_arrives(out):
    assert {s["state"] for s in out["unloaded"].values()} == {"unknown"}


def test_nothing_drawn_makes_every_other_step_empty_not_done(out):
    assert out["empty"]["layout"]["state"] == "blocked"
    others = {k: v["state"] for k, v in out["empty"].items() if k != "layout"}
    assert set(others.values()) == {"empty"}


def test_a_required_gap_is_missing_and_a_nice_to_have_is_not(out):
    job = out["gappy"]["job"]
    assert job["state"] == "missing"
    assert sorted(g["code"] for g in job["gaps"]) == [
        "customer_missing", "sold_by_missing"], (
        "a wants gap is CARRIED so the UI can show it, it just does not "
        "decide the state")


def test_a_step_whose_only_open_gap_is_a_want_reads_done(out):
    """`sold_by_missing` alone must not make step 1 amber."""
    assert out["gappy"]["sideview"]["state"] == "missing"   # height_assumed
    assert out["gappy"]["model"]["state"] == "done"


def test_a_stated_fact_makes_its_step_skipped(out):
    gates = out["skipped"]["gates"]
    assert gates["state"] == "skipped"
    assert gates["skippable"] is True
    assert gates["skipped"] is True


def test_only_a_step_with_satisfied_by_is_skippable(out):
    skippable = {k for k, v in out["clean"].items() if v["skippable"]}
    assert skippable == {"gates", "notes"}


def test_a_contradicted_claim_stops_being_a_skip(out):
    """The claim is stated but the drawing disagrees, so the `skipped` rung
    does not match and the question is reported instead."""
    gates = out["contradicted"]["gates"]
    assert gates["state"] == "missing"
    assert [g["code"] for g in gates["gaps"]] == ["gates_contradicted"]


def test_empty_beats_skipped(out):
    """Evidence outranks assertion: a job with nothing drawn has not started
    regardless of what it claims to lack."""
    assert out["empty_beats_skip"]["gates"]["state"] == "empty"


def test_a_code_no_step_claims_still_reaches_somebody(out):
    """Never reached while the totality test passes. It exists so that if one
    ever does reach a browser it is visible to the person who can act on it."""
    assert out["orphan"]["review"]["gaps"][0]["code"] == "invented_code"


def test_a_code_named_like_an_object_key_does_not_throw(out):
    assert out["proto"]["review"]["gaps"][0]["code"] == "constructor"


def test_panel_for_is_road_scoped(out):
    assert out["panel_of_notes"] == "annotations"
    assert out["panel_of_nothing"] is None


def test_a_role_with_no_road_gets_none(out):
    assert out["road_for_sales"] is True
    assert out["road_for_office"] is None
    assert out["road_for_all"] is None
```

The totality check reads the definition out of the node dump, so add this to `SCRIPT` before the `console.log`:

```js
out.claimed_codes = SALES_ROAD.steps.map((s) => [...s.requires, ...s.wants]);
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/web/test_road_module.py -q`
Expected: FAIL — `road-model.js` does not export `roadFor` or `STATES`, and `road` still takes a project

- [ ] **Step 4: Rewrite `road-model.js`**

```js
// The road ENGINE. See docs/superpowers/specs/2026-09-07-eight-step-road-design.md.
//
// No imports, no DOM, no state — `road.js` renders this, the way `profile.js`
// renders `base-top.js`. That split is what lets the step model be tested in
// node without stubbing a document, and it is the rule CLAUDE.md states for
// new frontend logic.
//
// **A map, never a wizard.** Every step is enterable at any time. The
// salesperson works on a laptop after the visit, from paper — they may hold
// the sketch and not the address, or do the gates first because the gates are
// what the customer talked about. A wizard demanding order would be defeated
// by typing junk to get past a step, which turns a completeness report into a
// completeness LIE.
//
// **It computes no completeness of its own.** It GROUPS what `handover_gaps()`
// already returned and never recomputes it. Three surfaces once answered
// "what is left" and disagreed; a fourth would be the B03 defect at a larger
// scale. The moment this file computes coverage arithmetic there are two
// answers to *is this job complete?*
//
// **It does not know what a project is.** The old signature took one solely to
// compute `!drawn`; a road now names that check as its `anchor`, so this is a
// pure function of three plain values and a role whose "not started" means
// something else changes no code here.

/** The six states, most severe first after the two that are not judgements.
 *  Exported so a renderer cannot invent a seventh by typo. */
export const STATES = ["unknown", "empty", "skipped", "blocked", "missing",
                       "done"];

/** Where a gap no step claims goes. Never reached while the totality test
 *  passes; it exists so that if one ever does reach a browser, it is visible
 *  to the person who can act on it rather than silently dropped. */
const ORPHAN_STEP = "review";

/** The panel a step shows, or `null` for a step this road does not define.
 *  Road-scoped, so two roads may each have a `review` step — a search over one
 *  global list would silently return the first match. */
export function panelFor(roadDef, stepKey) {
  return roadDef.steps.find((s) => s.key === stepKey)?.panel || null;
}

/** The road, as steps with state.
 *
 *  `gaps` is `handover.gaps` — passed in rather than fetched, so this stays
 *  pure and so one request is behind both the road and the estimate. `null`
 *  means the answer has not arrived: every step then reads `unknown` rather
 *  than defaulting to `done`. This repo shipped that bug once (audit B01, a
 *  `cache = null` painting a clean bill of health), which is why
 *  `js/handover.js: readinessShown` exists.
 *
 *  The `gaps` arrays returned hold the SAME gap objects passed in, not copies:
 *  a caller that tags one writes through into the payload it still holds. */
export function road(roadDef, gaps, stated) {
  const blank = (step) => ({
    key: step.key, panel: step.panel, state: "unknown", gaps: [],
    skippable: step.satisfiedBy !== null, skipped: false,
  });
  if (gaps == null) return roadDef.steps.map(blank);

  const owner = {};
  for (const step of roadDef.steps) {
    owner[step.key] = [];
    for (const code of [...step.requires, ...step.wants]) owner[code] = step.key;
  }
  const mine = Object.fromEntries(roadDef.steps.map((s) => [s.key, []]));
  for (const gap of gaps) {
    const key = Object.hasOwn(owner, gap.code) && typeof owner[gap.code] === "string"
      ? owner[gap.code] : ORPHAN_STEP;
    mine[key].push(gap);
  }

  const started = !gaps.some((g) => g.code === roadDef.anchor);
  const facts = stated || {};

  return roadDef.steps.map((step) => {
    const held = mine[step.key];
    const required = new Set(step.requires);
    const open = held.filter((g) => required.has(g.code));
    const skippable = step.satisfiedBy !== null;
    const claimed = skippable && facts[step.satisfiedBy] === true;

    let state;
    if (!started && !step.requires.includes(roadDef.anchor)) state = "empty";
    // A stated fact answers a step nothing can check — but only while it holds.
    // A claim the drawing contradicts arrives as a required gap, and then this
    // rung must not match: a skip that has stopped being true is not a skip.
    else if (claimed && open.length === 0) state = "skipped";
    else if (open.some((g) => g.blocking)) state = "blocked";
    else if (open.length) state = "missing";
    else state = "done";

    return { key: step.key, panel: step.panel, state, gaps: held,
             skippable, skipped: claimed };
  });
}
```

`road-model.js` has **no import line at all**, which is the spec's invariant and is why `roadFor` lives in `roads.js` instead. Add the textual test for it:

```python
def test_the_engine_imports_nothing():
    """The moment this file imports anything it can import coverage
    arithmetic, and then there are two answers to "is this job complete?"."""
    src = (STATIC / "js" / "road-model.js").read_text()
    assert not re.search(r"^\s*import\s", src, re.M), (
        "road-model.js must import nothing — put data in roads.js")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/web/test_road_module.py -q`
Expected: PASS. If `test_the_engine_takes_no_project` fails on arity, `road` has picked up a default parameter — remove it rather than changing the assertion.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static/js/road-model.js \
        src/fenceai/web/static/js/roads.js tests/web/test_road_module.py
git commit -m "feat(web): the road engine loses its project, roads become data"
```

---

### Task 5: Render eight steps

**Files:**
- Modify: `src/fenceai/web/static/js/road.js`
- Modify: `src/fenceai/web/static/i18n/en.json`, `he.json`
- Test: `tests/web/test_road_render.py` (create) — or extend the existing render test if one exists; check `tests/web/` first.

**Interfaces:**
- Consumes: `road`, `panelFor`, `roadFor` from Task 4; `state.stated` from Task 3.
- Produces: nothing new for later tasks.

- [ ] **Step 1: Add the locale keys to both bundles**

`en.json` — add three names, three takes, one state; **remove** `road.details` and `road.details.take`, which no step now claims:

```json
  "road.property": "The property",
  "road.property.take": "The house, the road, the trees — what the fence has to fit around.",
  "road.sideview": "The side view",
  "road.sideview.take": "Fence height is measured above its base, not above the ground.",
  "road.model": "Which fence",
  "road.model.take": "The model this fence is built to.",
  "road.state.skipped": "you said none",
```

`he.json`, matching the existing style:

```json
  "road.property": "הנכס",
  "road.property.take": "הבית, הכביש, העצים — מה שהגדר צריכה להשתלב איתו.",
  "road.sideview": "חתך",
  "road.sideview.take": "גובה הגדר נמדד מעל הבסיס שלה, לא מעל הקרקע.",
  "road.model": "איזו גדר",
  "road.model.take": "הדגם שהגדר נבנית לפיו.",
  "road.state.skipped": "נאמר שאין",
```

`road.sideview.take` is `road.details.take`'s sentence, which was always the side view's insight and is why the split is right.

- [ ] **Step 2: Run the locale guard to verify it passes**

Run: `uv run pytest tests/web/test_locale_bundles.py -q`
Expected: PASS. It fails if the key sets differ or if a `road.*` key is referenced in JS and missing.

- [ ] **Step 3: Update `road.js` to the new signature**

Three changes, and nothing else in the file moves:

```js
// the import
import { panelFor, road } from "./road-model.js";
import { roadFor } from "./roads.js";

// showStep and build need the road, so resolve it once per call
function currentRoad() {
  return roadFor(currentRole());
}

function showStep(stepKey) {
  const def = currentRoad();
  if (!def) return;
  const panel = panelFor(def, stepKey);
  if (panel) setTab(panel);
}
```

`build(host)` takes the definition rather than the module-level `STEPS`:

```js
function build(host, def) {
  if (host.children.length) return;
  host.innerHTML = def.steps.map((s, i) => `<button data-step="${esc(s.key)}">`
    + `<span class="road-index">${String(i + 1).padStart(2, "0")}</span>`
    + `<span class="road-name">${esc(t(`road.${s.key}`))}</span>`
    + `<span class="road-state"></span></button>`).join("");
  // …click handler unchanged
}
```

and `render()`:

```js
export function render() {
  const host = document.getElementById("road");
  if (!host) return;
  const def = currentRoad();
  host.hidden = def === null;
  if (def === null) return;
  const steps = road(def, state.handover?.gaps ?? null,
                     state.project?.stated ?? {});
  build(host, def);
  // …the rest unchanged, plus the skipped badge:
  //   btn.querySelector(".road-state").textContent =
  //     step.state === "unknown" ? ""
  //     : step.state === "skipped" ? t("road.state.skipped")
  //     : step.gaps.length ? t("road.state.missing", { n: step.gaps.length })
  //     : t(`road.state.${step.state}`);
}
```

The `skipped` branch must come **before** the `gaps.length` branch: a skipped step carries no gaps today, but a future `wants` on it would otherwise render a count over a skip.

- [ ] **Step 4: Write the label test**

`road.js` touches the DOM, so its rendering is the browser smoke's job (Task 6, step 5). What is worth pinning here is the thing that fails silently — a step whose label key is missing renders its own key to a salesperson:

```python
def test_every_step_key_has_a_name_and_a_take_in_both_bundles():
    """A step whose label is missing renders its own key to a salesperson."""
    import json
    from pathlib import Path
    static = Path("src/fenceai/web/static")
    keys = ["job", "property", "layout", "sideview", "model", "gates",
            "notes", "review"]
    for bundle in ("en.json", "he.json"):
        data = json.loads((static / "i18n" / bundle).read_text())
        for k in keys:
            assert f"road.{k}" in data, f"{bundle} has no road.{k}"
    en = json.loads((static / "i18n" / "en.json").read_text())
    assert "road.details" not in en, "no step claims `details` any more"
```

- [ ] **Step 5: Run it, then the full suite**

Run: `uv run pytest tests/web -q && uv run pytest tests/scenarios -q`
Expected: both PASS

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static/js/road.js \
        src/fenceai/web/static/i18n/en.json \
        src/fenceai/web/static/i18n/he.json tests/web/test_road_render.py
git commit -m "feat(web): render the eight steps"
```

---

### Task 6: Saying "there are none"

**Files:**
- Modify: `src/fenceai/web/static/js/road.js` (the skip control)
- Modify: `src/fenceai/web/static/js/state.js` (a `saveStated()` beside `saveContext()`)
- Modify: `src/fenceai/web/static/i18n/en.json`, `he.json`
- Test: extend `tests/web/test_road_render.py`

**Interfaces:**
- Consumes: `PUT /projects/{id}/stated` from Task 3; `Step.skippable` / `Step.skipped` from Task 4.
- Produces: nothing for later tasks.

- [ ] **Step 1: Add `saveStated` to `state.js`, beside `saveContext`**

```js
/** Persist what this job does NOT have.
 *
 *  Unrevisioned, like `saveJob` — a claim about an absence changes no
 *  quantity. Emits `project-loaded` rather than a bespoke event because the
 *  handover must be re-fetched: stating a fact can CREATE a gap
 *  (`gates_contradicted`), so the road's own state depends on the round trip.
 */
export async function saveStated() {
  state.project = await apiSend(
    "PUT", `/api/projects/${state.projectId}/stated`, state.project.stated
  );
  emit("project-loaded", state.project);
}
```

- [ ] **Step 2: Add the two locale keys to both bundles**

`en.json`:

```json
  "road.skip": "There are none on this job",
  "road.unskip": "There are some after all",
```

`he.json`:

```json
  "road.skip": "אין כאלה בעבודה הזו",
  "road.unskip": "בעצם יש",
```

- [ ] **Step 3: Render the control on a skippable step**

In `road.js`'s `render()`, after the badge is set:

```js
    // Only a step nothing can check offers this, and the wording is a
    // STATEMENT rather than a "skip": the office reads it as a fact the
    // salesperson asserted, not as a step somebody bypassed.
    if (step.skippable) {
      let btn2 = btn.querySelector(".road-skip");
      if (!btn2) {
        btn2 = document.createElement("span");
        btn2.className = "road-skip";
        btn2.dataset.fact = def.steps.find((s) => s.key === step.key).satisfiedBy;
        btn.appendChild(btn2);
      }
      btn2.textContent = t(step.skipped ? "road.unskip" : "road.skip");
    }
```

and in the click handler, before the step-change branch:

```js
    const skip = ev.target.closest(".road-skip");
    if (skip) {
      ev.stopPropagation();          // stating a fact is not navigating
      const fact = skip.dataset.fact;
      pushSnapshot("state-fact");     // as undoable as any other job edit
      state.project.stated = { ...state.project.stated,
                               [fact]: !state.project.stated?.[fact] };
      saveStated();
      return;
    }
```

Import `pushSnapshot` from `./history.js` and `saveStated` from `./state.js`.

- [ ] **Step 4: Verify the mutation order by reading it back**

The order must be `pushSnapshot` → mutate → save. Confirm by eye against CLAUDE.md's rule, then run:

Run: `uv run pytest tests/web -q && uv run pytest tests/scenarios -q`
Expected: both PASS

- [ ] **Step 5: Drive it in a real browser**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: the suite passes. It has a landmark section that places a house and a street; the road band is on screen throughout, so a thrown exception in `render()` shows up as a cascade of unrelated red checks rather than one.

If the smoke has an assertion on the six step keys or on `road.details`, update it — that is a real expectation change, not a test being bent.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static/js/road.js src/fenceai/web/static/js/state.js \
        src/fenceai/web/static/i18n/en.json \
        src/fenceai/web/static/i18n/he.json tests/web/test_road_render.py
git commit -m "feat(web): state that a job has no gates"
```

---

## Not in this plan, and why

- **New landmark kinds** (pool, wall, existing fence) and the property step's richer tools. Three lines each, but they are step 2's *content* rather than the step model, and the spec keeps them separate.
- **A tree.** `Landmark._is_a_shape` requires two points and a tree is one. The spec names it as needing its own decision; do not encode a tree as a 2 mm line to get past the validator.
- **House-versus-apartment.** A fact about the job, not a landmark, and the first thing that changes what installation *means*.
- **The office road.** `ROADS` has the seam and there is no `office_gaps()` to fill it.
- **Flipping the default role to `sales`.** Its own change, with the browser smoke updated on purpose.
