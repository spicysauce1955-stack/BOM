# Backoffice queue implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A backoffice person signs in, sees a filtered list of the jobs salespeople have submitted, takes one, and everybody can see they took it.

**Architecture:** Four new fields on `Project` carry whose desk a job is on. A new `fenceai/commands/` package owns the closed table of what may be DONE to a job — extracted from `fenceai/agent/registry.py`, which was never the agent's table, only the subset an agent may propose. One route performs any command, checks capacity and status before it runs, and writes one activity row. The queue is a rebuilt `GET /api/projects` whose open-question count is the salesperson's existing handover sheet.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLite, pytest. Frontend: vanilla ES modules, no build step, no framework.

**Spec:** `docs/superpowers/specs/2026-09-15-backoffice-design.md` — §3 identity, §4 lifecycle, §5 assignee, §6 the queue, §10 one door. Read it first; this plan argues from it.

## Scope, and what is deliberately not here

This plan ends with **the product owner opening the app, signing in as a backoffice
account, filtering to "waiting this week", taking a job, and signing in as the
salesperson to see it is gone from their desk.** That is the checkpoint. Green
tests are not.

**In scope:** sign-in on screen, the four lifecycle fields, the command table and
the one route that performs a command, six desk commands, the rebuilt queue query,
and the queue screen.

**Out of scope, with the reason:**

* **`commit_plan` and the committed plan view** (spec §7) — it needs the strict
  staleness guards and a plan screen, it is one coherent slice, and nothing in the
  queue depends on it. *Trigger: this plan's checkpoint passing.*
* **The office road** (spec §8) — a read surface over `readiness()`, which does not
  exist. *Trigger: the same.*
* **Doing it by hand** (spec §9) — the largest slice, and it wants the command
  table this plan builds. *Trigger: the road landing.*
* **The agent proposing** (spec §11) — needs a surface. *Trigger: §9 landing.*
* **Enforcing capacity on the existing routes.** This plan gates the NEW command
  route only. Retrofitting 68 routes in the same slice that introduces the
  mechanism is how the choice-set feature ran away on 2026-09-03.

## Global Constraints

- **Integer millimetres and cents at rest; float only transient** (ADR-0002).
- **A capacity is checked on the server; a view is never a permission.** Nothing may
  call `may_choose_view` to decide whether an action is allowed.
- **The four new fields are project state, not topology.** They must not bump
  `topology.revision` — a fact that changes no quantity must not 409 a derived view.
- **No road step or queue field may gate `POST /generate`** (contract 3.2.4).
- **Every user-visible string goes through `t("key")` or `data-i18n`**, and
  `i18n/he.json` / `en.json` must keep identical key sets.
- **Any user text interpolated into `innerHTML` goes through `esc()`.**
- **A new route needs `docs/architecture/04-backend.md` updated** — the count on the
  `N routes.` line AND the table. `tests/architecture/test_fitness.py` fails
  otherwise, and only in the full `pytest -q`.
- **A new `code="..."` needs `error.<code>` in BOTH bundles** and an entry in
  `REFUSAL_CODES` in `tests/web/test_locale_bundles.py`.
- **Not signed in must keep working exactly as today**, writing `system`. That is
  what keeps 3054 tests and 428 browser checks passing.
- **The scenarios gate must not move:** `uv run pytest tests/scenarios -q`. Nothing
  here adds behaviour to `generate()`.
- Run everything with `uv run`. Both tiers before every commit:
  `uv run pytest -q` and `uv run --with websocket-client python tools/ui_smoke.py`.

## File Structure

| File | Responsibility |
|---|---|
| `src/fenceai/web/static/js/session.js` | Sign in, sign out, `loadMe()`. Owns `state.me`; emits `signed-in` / `signed-out`. The ONLY module that talks to `/api/session` and `/api/me`. |
| `src/fenceai/project/lifecycle.py` | `JobState`, `OPEN_STATES`, `FINISHED_STATES`, `TRANSITIONS`. Pure leaf — imports `core` only. |
| `src/fenceai/commands/model.py` | `CommandSpec`, `Rung`, `Disposition`, `CommandRefused`. Pure leaf. |
| `src/fenceai/commands/registry.py` | The closed table: `register`, `spec_for`, `all_kinds`, `parse_payload`. |
| `src/fenceai/commands/desk.py` | The six desk commands' payloads and `materialize` functions. |
| `src/fenceai/commands/run.py` | `perform(command, project, actor, capacity)` — the three checks, then the effect. |
| `src/fenceai/project/queue.py` | `QueueRow`, `QueueFilter`, `select_rows()` — the pure filter/sort/page over loaded projects. |
| `src/fenceai/web/static/js/queue.js` | The queue screen. Owns `#tab-queue`; reads nothing but `/api/projects` and `/api/projects/{id}/actions`. |
| `src/fenceai/agent/registry.py` | **Shrinks.** Keeps only the agent's `may_emit` resolution against `fenceai.commands`. |

---

## Task 1: Sign in, on screen

**Files:**
- Create: `src/fenceai/web/static/js/session.js`
- Modify: `src/fenceai/web/static/index.html` (header block, lines 18–26)
- Modify: `src/fenceai/web/static/app.js` (init order)
- Modify: `src/fenceai/web/static/js/view.js` (`initView` takes a default)
- Modify: `src/fenceai/web/static/i18n/en.json`, `he.json`
- Test: `tests/web/test_session_module.py`, `tools/ui_smoke.py`

**Interfaces:**
- Consumes: `GET /api/me` → `{user: {id, name, capacity}, view, may_choose_view}`; `POST /api/session` `{email, password}`; `DELETE /api/session`.
- Produces: `signIn(email, password)`, `signOut()`, `loadMe()`, `currentUser()` from `session.js`; `state.me` (`null` when signed out); events `signed-in`, `signed-out`.

- [ ] **Step 1: Write the failing node test**

`tests/web/test_session_module.py` — follow `tests/web/test_view_module.py`'s harness exactly (it builds a fake `state.js` and runs the module under node).

```python
SCRIPT = """
import { applyMe, signedOutState } from "./js/session.js";
const out = {};
out.sales = applyMe({user:{id:"u1",name:"Dana",capacity:"sales"}, view:"sales", may_choose_view:false});
out.admin = applyMe({user:{id:"u2",name:"Root",capacity:"admin"}, view:"all", may_choose_view:true});
out.out   = signedOutState();
console.log(JSON.stringify(out));
"""

def test_an_account_opens_on_its_own_view_and_only_admin_is_offered_the_selector(out):
    assert out["sales"]["view"] == "sales"
    assert out["sales"]["selector"] is False
    assert out["admin"]["view"] == "all"
    assert out["admin"]["selector"] is True

def test_signed_out_is_todays_app_and_not_a_locked_door(out):
    """428 browser checks and every existing user are signed out. Signed out must
    stay the full app on the `all` view, or accounts are a breaking change."""
    assert out["out"]["view"] == "all"
    assert out["out"]["selector"] is True
    assert out["out"]["user"] is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/web/test_session_module.py -q`
Expected: FAIL — `Cannot find module './js/session.js'`

- [ ] **Step 3: Write `session.js`**

```javascript
// Who is signed in. The ONE module that talks to /api/session and /api/me —
// everything else reads `state.me` or listens for `signed-in`.
//
// Signed OUT is not a locked door: it is today's app on the `all` view. Every
// existing browser check runs that way, and accounts had to be an addition
// rather than a breaking change wearing one.
import { emit, state } from "./state.js";

/** What a `/api/me` answer means for the screen. Pure, so node can test it. */
export function applyMe(me) {
  return { user: me.user, view: me.view, selector: me.may_choose_view };
}

/** Nobody signed in — the full app, and the selector everybody has today. */
export function signedOutState() {
  return { user: null, view: "all", selector: true };
}

async function apply(shape) {
  state.me = shape.user;
  state.mayChooseView = shape.selector;
  const { setView } = await import("./view.js");
  setView(shape.view);
  emit(shape.user ? "signed-in" : "signed-out", shape.user);
}

export async function loadMe() {
  const r = await fetch("/api/me");
  await apply(r.ok ? applyMe(await r.json()) : signedOutState());
}

export async function signIn(email, password) {
  const r = await fetch("/api/session", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) return false;
  await apply(applyMe(await r.json()));
  return true;
}

export async function signOut() {
  await fetch("/api/session", { method: "DELETE" });
  await apply(signedOutState());
}

export const currentUser = () => state.me;
```

- [ ] **Step 4: Run the node test and watch it pass**

Run: `uv run pytest tests/web/test_session_module.py -q`
Expected: PASS

- [ ] **Step 5: Put it in the header**

In `index.html`, replace the `#view-select` block with a container holding both
states. Keep `#view-select` — it is only hidden, and `test_view_module.py` resolves
every hide-list selector against the real page.

```html
<div id="identity">
  <form id="sign-in" hidden>
    <input id="sign-in-email" type="email" data-i18n-placeholder="signin.email" autocomplete="username">
    <input id="sign-in-password" type="password" data-i18n-placeholder="signin.password" autocomplete="current-password">
    <button type="submit" class="primary" data-i18n="signin.submit">Sign in</button>
    <span id="sign-in-error" class="warning error" hidden data-i18n="error.sign_in_failed"></span>
  </form>
  <div id="signed-in-as" hidden>
    <span id="me-name"></span>
    <span id="me-capacity" class="badge"></span>
    <button id="sign-out" data-i18n="signin.out">Sign out</button>
  </div>
</div>
```

- [ ] **Step 6: Hide the selector for everybody but an admin**

In `style.css`, beside the existing `html[data-view=…]` rules:

```css
html[data-selector="no"] #view-select { display: none; }
```

and in `session.js`'s `apply`, before `setView`:

```javascript
  document.documentElement.dataset.selector = shape.selector ? "yes" : "no";
```

- [ ] **Step 7: Call it at startup, after the view is initialised**

In `app.js`, after the existing `initView();` line:

```javascript
  import("./js/session.js").then((s) => s.loadMe());
```

`loadMe` deliberately runs AFTER `initView()` rather than replacing it: a signed-out
browser must reach today's app without waiting on a network round trip, and a
signed-in one then corrects the view. The same ordering `initRole` already needed
against `initI18n`.

- [ ] **Step 8: Add the four locale keys to BOTH bundles**

`signin.email`, `signin.password`, `signin.submit`, `signin.out` —
en: `"Email"`, `"Password"`, `"Sign in"`, `"Sign out"`;
he: `"אימייל"`, `"סיסמה"`, `"התחברות"`, `"התנתקות"`.
`error.sign_in_failed` already exists from `3707be4`.

- [ ] **Step 9: Seed two demo accounts so the screen has something to sign in as**

In `api/app.py`'s startup seed, beside the demo knowledge seed:

```python
    if not state.store.list_users():
        for uid, name, email, capacity in [
            ("u_dana", "Dana", "dana@example.com", "sales"),
            ("u_yossi", "Yossi", "yossi@example.com", "backoffice"),
            ("u_admin", "Admin", "admin@example.com", "admin"),
        ]:
            u = User(id=uid, name=name, email=email, capacity=capacity)
            u.set_password("demo")
            state.store.save_user(u)
```

- [ ] **Step 10: Add a browser smoke case**

In `tools/ui_smoke.py`, a new `_smoke_sign_in(c)` registered in the case list:

```python
def _smoke_sign_in(c):
    c.js("""document.getElementById('sign-in-email').value = 'dana@example.com';
            document.getElementById('sign-in-password').value = 'demo';
            document.getElementById('sign-in').requestSubmit(); 'ok'""")
    wait_for(c, "document.documentElement.dataset.view === 'sales'", timeout=10)
    check("signing in as a salesperson lands on the sales view",
          c.js("document.documentElement.dataset.view") == "sales")
    check("a salesperson is not offered the view selector",
          c.js("getComputedStyle(document.getElementById('view-select')).display") == "none")
    c.js("document.getElementById('sign-out').click(); 'ok'")
    wait_for(c, "document.documentElement.dataset.view === 'all'", timeout=10)
    check("signing out is today's app again",
          c.js("getComputedStyle(document.getElementById('view-select')).display") != "none")
```

- [ ] **Step 11: Run both tiers**

Run: `uv run pytest -q` — expected 3054 + 2 new, all passing.
Run: `uv run --with websocket-client python tools/ui_smoke.py` — expected 431/431.

- [ ] **Step 12: Commit**

```bash
git add src/fenceai/web/static/js/session.js src/fenceai/web/static/index.html \
        src/fenceai/web/static/app.js src/fenceai/web/static/style.css \
        src/fenceai/web/static/i18n/en.json src/fenceai/web/static/i18n/he.json \
        src/fenceai/api/app.py tests/web/test_session_module.py tools/ui_smoke.py
git commit -m "feat(web): sign in, and the view opens from the account"
```

**STOP. This is the first checkpoint the product owner can judge.** Do not start
Task 2 until they have signed in as Dana and as Yossi and said whether it is right.

---

## Task 2: A job has a state and an owner

**Files:**
- Create: `src/fenceai/project/lifecycle.py`
- Modify: `src/fenceai/project/model.py` (the `Project` class)
- Test: `tests/project/test_lifecycle.py`

**Interfaces:**
- Produces: `JobState` (`Literal`), `OPEN_STATES`, `FINISHED_STATES`, `TRANSITIONS: dict[str, set[str]]`, `is_open(state)`; `Project.status`, `Project.assignee`, `Project.submitted_at`, `Project.created_by`.

- [ ] **Step 1: Write the failing test**

```python
from fenceai.project.lifecycle import (
    FINISHED_STATES, OPEN_STATES, TRANSITIONS, is_open,
)
from fenceai.project.model import Project


def test_the_eight_states_partition_into_the_two_views():
    """The product owner asked for two lists. Eight states exist underneath
    because a job waiting to be picked up and one somebody is halfway through
    are not the same problem — but every one of them is in exactly one view."""
    assert OPEN_STATES | FINISHED_STATES == set(TRANSITIONS) | {"delivered", "cancelled"}
    assert not (OPEN_STATES & FINISHED_STATES)
    assert FINISHED_STATES == {"delivered", "cancelled"}


def test_there_is_no_won_or_lost():
    """The fence was sold at the kitchen table before the job existed, and
    `Quote.status` has no rejected either. Deals that never became jobs are lost
    before a job exists — the salesperson's screen, not this one."""
    every = OPEN_STATES | FINISHED_STATES
    assert "won" not in every and "lost" not in every


def test_a_new_project_is_drafting_and_belongs_to_nobody():
    p = Project(id="p1", name="x")
    assert p.status == "drafting"
    assert p.assignee is None
    assert p.submitted_at == ""


def test_the_four_new_fields_do_not_touch_the_topology_revision():
    """They are project state. A fact that changes no quantity must not 409
    every derived view — the rule `/job`, `/context` and `/stated` already set."""
    p = Project(id="p1", name="x")
    before = p.topology.revision
    p.status, p.assignee, p.created_by = "waiting", "u_yossi", "u_dana"
    assert p.topology.revision == before


def test_a_transition_nobody_allowed_is_not_in_the_table():
    assert "planning" in TRANSITIONS["waiting"]
    assert "delivered" not in TRANSITIONS["waiting"]
    assert TRANSITIONS["delivered"] == set()


def test_is_open_answers_for_every_state_and_guesses_for_none():
    for s in OPEN_STATES:
        assert is_open(s) is True
    for s in FINISHED_STATES:
        assert is_open(s) is False
    with pytest.raises(KeyError):
        is_open("nonsense")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/project/test_lifecycle.py -q`
Expected: FAIL — `No module named 'fenceai.project.lifecycle'`

- [ ] **Step 3: Write `lifecycle.py`**

```python
"""Whose desk a job is on.

Eight states, and the product owner asked for two LISTS — open and finished. Both
are true: the views are two, and eight states live underneath them because a job
waiting to be picked up and a job somebody is halfway through planning are not the
same problem to whoever is choosing what to work on next.

There is deliberately no `won` / `lost`. The fence was sold at the customer's
kitchen table before this job existed — the sales MVP's own sentence is that the
app's number "is never what wins the deal" — and `Quote.status` carries no
"rejected" either. A deal that never became a job is lost before a job exists.
"""

from __future__ import annotations

from typing import Literal

JobState = Literal[
    "drafting", "waiting", "planning", "planned", "quoted", "returned",
    "delivered", "cancelled",
]

#: What each state may become. A closed table rather than scattered `if`s, so
#: "can this job be taken?" has one answer in one place.
TRANSITIONS: dict[str, set[str]] = {
    "drafting":  {"waiting", "cancelled"},
    "waiting":   {"planning", "returned", "cancelled"},
    "planning":  {"planned", "returned", "cancelled"},
    "planned":   {"quoted", "planning", "cancelled"},
    "quoted":    {"delivered", "planning", "cancelled"},
    "returned":  {"waiting", "cancelled"},
    "delivered": set(),
    "cancelled": {"waiting"},
}

FINISHED_STATES: frozenset[str] = frozenset({"delivered", "cancelled"})
OPEN_STATES: frozenset[str] = frozenset(set(TRANSITIONS) - FINISHED_STATES)


def is_open(state: str) -> bool:
    """Which of the two lists this job is on.

    Raises on an unknown state rather than answering. A state nobody declared is
    a bug, and defaulting it into `open` would hide the job in the list somebody
    is actually reading.
    """
    if state not in TRANSITIONS:
        raise KeyError(f"unknown job state: {state!r}")
    return state not in FINISHED_STATES
```

- [ ] **Step 4: Add the four fields to `Project`**

In `project/model.py`, after `stated`:

```python
    # Whose desk this is on. Project state, NOT topology: a job changing hands
    # changes no quantity, so it must not bump `topology.revision` and 409 every
    # derived view — the rule `/job`, `/context` and `/stated` already follow.
    status: JobState = "drafting"
    # The backoffice account that took it. `None` is a real state, not a blank:
    # "nobody has taken this" is the whole reason a queue exists.
    assignee: str | None = None
    # When it reached the queue. Drives the service-promise sort, which is a
    # different question from when the sale happened (`job.sold_on`).
    submitted_at: str = ""
    created_by: str = ""
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest tests/project/test_lifecycle.py -q`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full suite — stored projects must still load**

Run: `uv run pytest -q`
Expected: all passing. Every field has a default, so a project stored before this
commit validates unchanged and reads as `drafting`.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/project/lifecycle.py src/fenceai/project/model.py tests/project/test_lifecycle.py
git commit -m "feat(project): a job has a state and an owner"
```

---

## Task 3: The command table leaves `fenceai/agent/`

**Files:**
- Create: `src/fenceai/commands/__init__.py`, `model.py`, `registry.py`
- Modify: `src/fenceai/agent/registry.py` (keeps only the agent's subset)
- Modify: `tests/architecture/test_fitness.py` (`DOMAIN` gains `commands`)
- Test: `tests/commands/test_registry.py`

**Interfaces:**
- Produces: `CommandSpec(kind, payload_model, rung, capacities, from_states, disposition, i18n_key, materialize)`, `register(spec)`, `spec_for(kind)`, `all_kinds()`, `parse_payload(kind, data)`, `CommandRefused(code, **params)`.
- Consumes: nothing. Pure leaf.

- [ ] **Step 1: Write the failing test**

```python
def test_the_table_is_closed_and_a_kind_nobody_registered_has_no_word():
    """`knowledge/ast.py`'s FnCall whitelist is the same instinct: a closed
    vocabulary resolved in code, no eval of strings, ever."""
    with pytest.raises(KeyError):
        spec_for("drop_all_tables")


def test_a_spec_names_which_capacities_may_perform_it():
    """The permission lives on the command, not in the handler. One table rather
    than a check scattered across handlers, half of which get added later by
    somebody who did not know."""
    spec = spec_for("claim_job")
    assert "backoffice" in spec.capacities
    assert "sales" not in spec.capacities


def test_a_spec_names_which_states_it_may_run_from():
    assert "waiting" in spec_for("claim_job").from_states
    assert "delivered" not in spec_for("claim_job").from_states


def test_registering_a_kind_twice_is_refused():
    """Two rows for one word is a table with no answer. It fails where the
    second one is written."""
    with pytest.raises(ValueError):
        register(spec_for("claim_job"))


def test_every_registered_kind_has_a_locale_key_in_both_bundles():
    """The activity log renders per language from what happened, never from a
    stored sentence — the rule the warning registry already lives by."""
    en, he = _bundles()
    for kind in all_kinds():
        assert f"command.{kind}" in en, kind
        assert f"command.{kind}" in he, kind
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/commands -q`
Expected: FAIL — `No module named 'fenceai.commands'`

- [ ] **Step 3: Write `commands/model.py`**

```python
"""What may be DONE to a job — the closed table, and nothing about who is asking.

**Extracted from `fenceai/agent/registry.py`, which was never the agent's table.**
It held one row and the agent was its only caller, so it lived there; but the list
of things that may be done to a job belongs to the job. An agent has a SUBSET of
it that it may propose, which is `TaskSpec.may_emit` and stays in `agent/`.

That direction matters: a human pressing a button and an agent proposing one must
reach the same row, or the second implementation drifts from the first — and the
drift is where an untraceable change comes from.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

Rung = Literal["note", "selection", "directive", "rule"]
#: How much a command may do on its own. The dial an agent is turned up on, and
#: the reason `commit_plan` can be pinned at `ask` for ever.
Disposition = Literal["ask", "suggest", "auto"]


class CommandRefused(Exception):
    """A command that may not run, as `code + params` like every other refusal
    here — the English message is a fallback and the sentence lives in both
    bundles."""

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class CommandSpec:
    kind: str
    payload_model: type[BaseModel]
    rung: Rung
    #: Which capacities may perform it. On the COMMAND rather than in a handler.
    capacities: frozenset[str]
    #: Which job states it may run from. Empty means "any state".
    from_states: frozenset[str]
    disposition: Disposition
    i18n_key: str
    #: payload + project -> the changed project. Pure; the caller persists.
    materialize: Callable = field(repr=False)
```

- [ ] **Step 4: Write `commands/registry.py`**

```python
"""The table itself. Growth is additive: adding a row never invalidates a stored
run, because a run stamps only the inputs it actually had."""

from __future__ import annotations

from fenceai.commands.model import CommandSpec

_TABLE: dict[str, CommandSpec] = {}


def register(spec: CommandSpec) -> CommandSpec:
    if spec.kind in _TABLE:
        raise ValueError(f"command already registered: {spec.kind}")
    _TABLE[spec.kind] = spec
    return spec


def spec_for(kind: str) -> CommandSpec:
    if kind not in _TABLE:
        raise KeyError(f"no such command: {kind}")
    return _TABLE[kind]


def all_kinds() -> list[str]:
    return sorted(_TABLE)


def parse_payload(kind: str, data: dict):
    """Validate against the kind's own model. A free-form dict is inexpressible
    under `additionalProperties:false` and silently arrives empty — the lesson
    `ai/claude.py` already carries in a comment."""
    return spec_for(kind).payload_model.model_validate(data)
```

- [ ] **Step 5: Shrink `agent/registry.py` to the agent's subset**

Replace its table with a re-export, keeping its header's reasoning and adding one
paragraph recording the move:

```python
from fenceai.commands.registry import parse_payload, spec_for  # noqa: F401
```

Keep `SelectChoicePoint` where it is until Task 4 moves it beside the other
payloads; `tests/agent/` must stay green through this step.

- [ ] **Step 6: Add `commands` to `DOMAIN` in the fitness test**

```python
DOMAIN = (
    "catalog", "commands", "core", "decisions", "demand", "fencemodel",
    "fulfillment", "identity", "knowledge", "learning", "parts", "project",
    "report", "strategy", "topology",
)
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: all passing, including `tests/agent/` unchanged.

- [ ] **Step 8: Commit**

```bash
git add src/fenceai/commands tests/commands src/fenceai/agent/registry.py tests/architecture/test_fitness.py
git commit -m "refactor(commands): the command table was never the agent's"
```

---

## Task 4: The six desk commands, and the one door

**Files:**
- Create: `src/fenceai/commands/desk.py`, `src/fenceai/commands/run.py`
- Modify: `src/fenceai/api/app.py` (one new route)
- Modify: `docs/architecture/04-backend.md` (count 68 → 69, and the table)
- Modify: `src/fenceai/web/static/i18n/en.json`, `he.json`
- Modify: `tests/web/test_locale_bundles.py` (`REFUSAL_CODES`)
- Test: `tests/commands/test_desk.py`, `tests/api/test_command_route.py`

**Interfaces:**
- Consumes: `CommandSpec`, `register`, `spec_for`, `parse_payload`, `CommandRefused` (Task 3); `TRANSITIONS`, `Project.status/assignee` (Task 2); `_signed_in`, `_actor` (`api/app.py`, from `3707be4`).
- Produces: `perform(kind, data, project, actor, capacity, now) -> Project`; route `POST /api/projects/{project_id}/actions`.

- [ ] **Step 1: Write the failing test for the three checks**

```python
def test_a_capacity_that_may_not_do_it_is_refused_before_anything_changes():
    p = Project(id="p1", name="x", status="waiting")
    with pytest.raises(CommandRefused) as e:
        perform("claim_job", {}, p, actor="user:u_dana", capacity="sales", now=NOW)
    assert e.value.code == "command_not_permitted"
    assert p.status == "waiting" and p.assignee is None


def test_a_job_in_the_wrong_state_is_refused_and_says_which_state_it_is_in():
    p = Project(id="p1", name="x", status="delivered")
    with pytest.raises(CommandRefused) as e:
        perform("claim_job", {}, p, actor="user:u_y", capacity="backoffice", now=NOW)
    assert e.value.code == "command_wrong_state"
    assert e.value.params["status"] == "delivered"


def test_taking_a_job_does_two_things_in_one_act():
    """It becomes yours AND moves waiting -> planning, because in the office
    those are one gesture."""
    p = Project(id="p1", name="x", status="waiting")
    out = perform("claim_job", {}, p, actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.assignee == "u_y"
    assert out.status == "planning"


def test_submitting_is_never_gated_on_completeness():
    """`blocking` withholds the ESTIMATE, not the handover. A sheet that refused
    an incomplete handover would be worked around within a week."""
    p = Project(id="p1", name="x", status="drafting")   # nothing drawn at all
    out = perform("submit_job", {}, p, actor="user:u_dana", capacity="sales", now=NOW)
    assert out.status == "waiting"
    assert out.submitted_at == NOW


def test_returning_to_sales_takes_the_job_off_the_backoffice_desk():
    """Or the queue stops meaning "work I can do"."""
    p = Project(id="p1", name="x", status="planning", assignee="u_y")
    out = perform("return_to_sales", {"reason": "wall height?"}, p,
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.status == "returned"
    assert out.assignee is None


def test_the_reason_a_job_was_returned_is_kept_verbatim():
    """Never a code. Whoever reads it has to see the question in the words
    somebody actually wrote."""
    p = Project(id="p1", name="x", status="planning", assignee="u_y")
    out = perform("return_to_sales", {"reason": "  is the wall 600 or 900?  "}, p,
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.annotations[-1].text == "is the wall 600 or 900?"
    assert out.annotations[-1].author == "user:u_y"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/commands/test_desk.py -q`
Expected: FAIL — `No module named 'fenceai.commands.desk'`

- [ ] **Step 3: Write `commands/desk.py`**

One `register(CommandSpec(...))` per kind. `submit_job` (sales, from `drafting`
and `returned`), `claim_job` (backoffice/admin, from `waiting`), `assign_job`
(backoffice/admin, from `waiting`/`planning`, payload `{user_id}`),
`return_to_sales` (backoffice/admin, from `planning`/`waiting`, payload
`{reason: str}`), `cancel_job` (backoffice/admin, any open state),
`reopen_job` (backoffice/admin, from `cancelled`).

Each `materialize(payload, project, actor, now) -> Project` sets the fields the
test above asserts. `return_to_sales` appends an `Annotation` with
`target_ref="job"`, `text=payload.reason.strip()`, `author=actor`.

- [ ] **Step 4: Write `commands/run.py`**

```python
def perform(kind, data, project, *, actor, capacity, now):
    """The three questions, then the effect.

    Order matters: capacity first, so a refusal never leaks whether the job was
    in a state that would have allowed it.
    """
    spec = spec_for(kind)
    if capacity not in spec.capacities:
        raise CommandRefused("command_not_permitted", kind=kind, capacity=capacity)
    if spec.from_states and project.status not in spec.from_states:
        raise CommandRefused("command_wrong_state", kind=kind, status=project.status)
    payload = parse_payload(kind, data)
    return spec.materialize(payload, project, actor=actor, now=now)
```

- [ ] **Step 5: Run the desk tests and watch them pass**

Run: `uv run pytest tests/commands -q`
Expected: PASS

- [ ] **Step 6: Write the failing route test**

```python
def test_performing_a_command_needs_a_session(client):
    """The FIRST gated route in the app. Everything else stays as open as it was
    — retrofitting 68 routes in the slice that introduces the mechanism is how a
    feature ran away here before."""
    client.cookies.clear()
    p = client.post("/api/projects", json={"name": "x"}).json()
    r = client.post(f"/api/projects/{p['id']}/actions",
                    json={"kind": "claim_job", "payload": {}})
    assert r.status_code == 401


def test_a_refusal_is_typed_and_localisable(client):
    _sign_in_as(client, "sales")
    p = client.post("/api/projects", json={"name": "x"}).json()
    r = client.post(f"/api/projects/{p['id']}/actions",
                    json={"kind": "claim_job", "payload": {}})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "command_not_permitted"


def test_performing_a_command_writes_one_activity_row_naming_the_session(client):
    _sign_in_as(client, "backoffice", user_id="u_yossi")
    p = _a_waiting_job(client)
    client.post(f"/api/projects/{p['id']}/actions",
                json={"kind": "claim_job", "payload": {}})
    rows = [e for e in state.store.audit_entries(50) if e["action"] == "command:claim_job"]
    assert rows and rows[0]["actor"] == "user:u_yossi"
```

- [ ] **Step 7: Add the route**

```python
class CommandBody(BaseModel):
    kind: str
    payload: dict = {}
    #: Who PROPOSED it, when that is not who performed it. `actor` is always the
    #: session. Two names, because "Yossi accepted the agent's suggestion" and
    #: "Yossi decided this himself" must stay different rows.
    origin: str = ""


@app.post("/api/projects/{project_id}/actions")
def perform_command(request: Request, project_id: str, body: CommandBody) -> Project:
    user = _require_user(request)
    project = _project(project_id)
    try:
        changed = commands.perform(body.kind, body.payload, project,
                                   actor=actor_ref(user), capacity=user.capacity,
                                   now=_now_iso())
    except KeyError:
        raise HTTPException(404, {"code": "command_unknown", "kind": body.kind})
    except CommandRefused as e:
        raise HTTPException(403, {"code": e.code, **e.params})
    state.store.save_project(changed, actor=actor_ref(user))
    state.store._audit(actor_ref(user), f"command:{body.kind}",
                       f"{project_id}|{body.origin}")
    return changed
```

- [ ] **Step 8: Update the doc and the bundles**

`04-backend.md`: `68 routes.` → `69 routes.`, and a table row under a new
**Commands** group. Add `error.command_not_permitted`,
`error.command_wrong_state`, `error.command_unknown` to both bundles and to
`REFUSAL_CODES`. Add `command.<kind>` × 6 to both bundles.

- [ ] **Step 9: Run both tiers**

Run: `uv run pytest -q` then the smoke.
Expected: both green; the smoke is unchanged at 431.

- [ ] **Step 10: Commit**

```bash
git add src/fenceai/commands src/fenceai/api/app.py tests/commands tests/api/test_command_route.py \
        docs/architecture/04-backend.md src/fenceai/web/static/i18n tests/web/test_locale_bundles.py
git commit -m "feat(commands): six desk commands through one door"
```

---

## Task 5: The queue query

**Files:**
- Create: `src/fenceai/project/queue.py`
- Modify: `src/fenceai/api/app.py` (`GET /api/projects` rebuilt)
- Modify: `docs/architecture/04-backend.md` (the Projects row)
- Test: `tests/project/test_queue.py`, `tests/api/test_queue_route.py`

**Interfaces:**
- Consumes: `is_open`, `OPEN_STATES` (Task 2); `handover_gaps` (`report/handover.py`).
- Produces: `QueueRow`, `QueueFilter`, `select_rows(projects, filter, now) -> tuple[list[QueueRow], str | None]` where the second element is the next cursor.

- [ ] **Step 1: Write the failing test**

```python
def test_the_two_buckets_are_the_two_lists_and_nothing_falls_between():
    rows, _ = select_rows(EVERY_STATE, QueueFilter(bucket="open"), now=NOW)
    assert {r.status for r in rows} == set(OPEN_STATES)
    rows, _ = select_rows(EVERY_STATE, QueueFilter(bucket="finished"), now=NOW)
    assert {r.status for r in rows} == {"delivered", "cancelled"}


def test_drafting_jobs_are_the_salespersons_and_not_on_the_backoffice_queue():
    """A job she has not submitted is not work anybody else can pick up."""
    rows, _ = select_rows(EVERY_STATE, QueueFilter(bucket="open", for_capacity="backoffice"), now=NOW)
    assert "drafting" not in {r.status for r in rows}


def test_assignee_me_and_assignee_none_are_different_questions():
    rows, _ = select_rows(JOBS, QueueFilter(assignee="u_yossi"), now=NOW)
    assert all(r.assignee == "u_yossi" for r in rows)
    rows, _ = select_rows(JOBS, QueueFilter(assignee="none"), now=NOW)
    assert all(r.assignee is None for r in rows)


def test_the_open_question_count_is_the_handover_sheet_and_nothing_else():
    """Not the office's own work. A fresh job has a bay width to choose and a
    plan to commit BY DEFINITION, so counting those would make every row read
    the same and tell the reader nothing."""
    p = _job_with_no_height_stated()
    rows, _ = select_rows([p], QueueFilter(), now=NOW)
    assert rows[0].open_questions == len(handover_gaps(p))


def test_the_default_sort_is_longest_waiting_first():
    rows, _ = select_rows(JOBS, QueueFilter(), now=NOW)
    waited = [r.waiting_seconds for r in rows]
    assert waited == sorted(waited, reverse=True)


def test_a_page_is_bounded_and_hands_back_a_cursor():
    """Paging is a correctness requirement: the open-question count is DERIVED,
    and deriving it for an unbounded list is what would make the rule 'read
    models are derived, never stored' unaffordable."""
    rows, cursor = select_rows(JOBS_60, QueueFilter(limit=25), now=NOW)
    assert len(rows) == 25 and cursor is not None
    rest, nxt = select_rows(JOBS_60, QueueFilter(limit=25, cursor=cursor), now=NOW)
    assert len(rest) == 25 and nxt is not None
    assert {r.id for r in rows} & {r.id for r in rest} == set()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/project/test_queue.py -q`
Expected: FAIL — `No module named 'fenceai.project.queue'`

- [ ] **Step 3: Write `queue.py`** — a pure function over already-loaded projects,
no store import (the fitness test forbids it). `QueueRow` carries `id`, `label`,
`town`, `sold_by`, `status`, `assignee`, `submitted_at`, `waiting_seconds`,
`open_questions`, and for the finished bucket `closed_at`, `quote_total_cents`.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/project/test_queue.py -q`

- [ ] **Step 5: Rebuild `GET /api/projects`**

Keep `id`, `name`, `label` on every row — the picker is not the only caller and
something keyed on them must not silently start reading something else.

- [ ] **Step 6: Both tiers, then commit**

```bash
git add src/fenceai/project/queue.py tests/project/test_queue.py \
        src/fenceai/api/app.py tests/api/test_queue_route.py docs/architecture/04-backend.md
git commit -m "feat(queue): the job list answers what to work on next"
```

---

## Task 6: The queue screen

**Files:**
- Create: `src/fenceai/web/static/js/queue.js`
- Modify: `index.html` (a `#tab-queue` panel and its tab button), `style.css`,
  `js/view.js` (the queue tab is hidden from `sales`), both bundles
- Test: `tests/web/test_queue_module.py`, `tools/ui_smoke.py`

- [ ] **Step 1: Write the failing node test** for the pure half — `rowLabel(row)`,
`waitedWord(seconds)`, `bucketFor(status)` — following `test_view_module.py`'s harness.

- [ ] **Step 2: Run it and watch it fail.**

- [ ] **Step 3: Write `queue.js`.** Every interpolated customer name and town goes
through `esc()`. Every string through `t()`. The `With` cell renders the three
states from spec §5, and `Take it` posts `claim_job` to the command route.

- [ ] **Step 4: Add the smoke case** — sign in as backoffice, filter to waiting,
press Take it, assert the row now names you and the status reads `planning`.

- [ ] **Step 5: Run both tiers.** Expected: pytest green; smoke 431 + 4 new.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static/js/queue.js src/fenceai/web/static/index.html \
        src/fenceai/web/static/style.css src/fenceai/web/static/js/view.js \
        src/fenceai/web/static/i18n tests/web/test_queue_module.py tools/ui_smoke.py
git commit -m "feat(web): the backoffice queue"
```

**STOP. This is the plan's checkpoint.** The product owner signs in as Yossi,
filters to waiting this week, takes a job, signs in as Dana, and sees it has left
her desk.

---

## Self-review against the spec

| Spec section | Task |
|---|---|
| §3 identity — view from capacity, admin-only selector | 1 |
| §4 lifecycle — eight states, no won/lost, submit never gated | 2, 4 |
| §5 assignee — three states, taking does two things, not a lock | 2, 4, 6 |
| §6 the queue — filters, paging, open questions from the handover sheet | 5, 6 |
| §10 one door — closed table, three checks, two names in the log | 3, 4 |
| §7 commit_plan · §8 the road · §9 by hand · §11 the agent | **deliberately out of scope** — see Scope above |

**Not covered by any task, and named rather than dropped:** enforcing capacity on
the 68 existing routes; the `origin` column is written but nothing reads it until
the agent slice; and `spec_for` raising `KeyError` is mapped to a 404 at the route
rather than being a typed `CommandRefused` — acceptable because an unknown kind is
a caller bug, not a user-facing refusal, and it is the only refusal in this plan
with no locale entry.
