# Agent framework — slice 1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agent that reads an open choice set, recommends one of the layouts the engine already offered, shows its reasoning as checkable claims, and is visible in the app — with everything it produced and everything that was refused counted from the first run.

**Architecture:** A new `fenceai/agent/` package holding four leaf modules and a dispatcher. A task declares which action kinds it may emit; that list becomes the model's output schema, so an agent physically cannot name an action it was not given. Proposals are validated against what the view handed the agent before a person sees anything. Nothing outside the API layer imports the package, and no AI call goes near `generate()`.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest. Frontend: vanilla ES modules + SVG, no build step.

**Spec:** `docs/superpowers/specs/2026-09-08-agent-framework-design.md` (how), with `docs/superpowers/specs/2026-09-08-advisory-agent-design.md` (what, and why). Read both.

## Scope, and what is deliberately not here

This slice ends with **the product owner opening the app and seeing the agent recommend a bay layout, with its reasoning, beside the existing choice panel.** That is the checkpoint. Green tests are not.

**In scope:** the framework, one task, the deterministic stub, the three checks, the API route, the UI, and the `produced` / `dropped` / `evaluated` half of reach.

**Out of scope, with the reason:** persistence of proposals, the keep/reverse action, the five rejection types, and the `shown` / `kept` / `reversed` half of reach. All four need a store and a mutation path, they are one coherent second slice, and spec §8b is satisfied in spirit here — nothing is deferred to "a dashboard later", because a task that examined nothing already reports `evaluated: false` and a refused proposal is already counted as an agent defect. *Trigger for slice 2: this slice's checkpoint passing.*

**Also out of scope:** the Claude adapter. The stub exercises every path, and a second implementation before the first one is seen is how the choice-set feature ran away on 2026-09-03.

## Global Constraints

- **Integer millimetres and cents at rest; float only transient** (ADR-0002).
- **No AI inside `generate()`, `derive_requirements()` or `fulfill()`** (ADR-0009). The dispatcher runs after a generation the user asked for, never during one.
- **Nothing imports `fenceai/agent/` except `fenceai/api/`.** Task 8 pins it.
- **Every user-visible string goes through `t("key")` or `data-i18n`**, and `i18n/he.json` and `i18n/en.json` must keep identical key sets.
- **Any user or agent text interpolated into `innerHTML` goes through `esc()`.**
- **A new route needs `docs/architecture/04-backend.md` updated** — both the count on line 46 and the table. `tests/architecture/test_fitness.py` fails otherwise, and only in the full `pytest -q`, not in the scenarios gate.
- **The full suite must stay green:** `uv run pytest -q`. The scenarios gate `uv run pytest tests/scenarios -q` must not move — this slice adds no behaviour to `generate()`.
- Run everything with `uv run`.

## File Structure

| File | Responsibility |
|---|---|
| `src/fenceai/agent/__init__.py` | empty, package marker |
| `src/fenceai/agent/proposal.py` | `Claim`, `ViewDigest`, `Declined`, `NoStanding`, `Proposal`, `TaskResult`, `proposal_id()`. Pure leaf — no imports from other agent modules. |
| `src/fenceai/agent/registry.py` | `ActionSpec`, the action table, `SelectChoicePoint` payload, `register` / `spec_for` / `parse_payload` |
| `src/fenceai/agent/view.py` | `AgentView` — read-only access to layout, open choice sets and refs |
| `src/fenceai/agent/tasks.py` | `TaskSpec` and the `rank_choice_set` task |
| `src/fenceai/agent/run.py` | `run_task()` — dispatch, the three checks, the counters |
| `src/fenceai/ai/ports.py` | gains `TaskRunner` protocol (modify) |
| `src/fenceai/ai/stub.py` | gains `StubAgent` (modify) |
| `src/fenceai/api/app.py` | one GET route, one composition-root line (modify) |
| `src/fenceai/web/static/js/agent-advice.js` | renders advice; owns only its own container |
| `src/fenceai/web/static/index.html` | one container div (modify) |
| `src/fenceai/web/static/i18n/{en,he}.json` | new keys (modify) |
| `docs/architecture/04-backend.md` | route count + table row (modify) |

Tests mirror the source: `tests/agent/test_proposal.py`, `test_registry.py`, `test_view.py`, `test_run.py`; `tests/ai/test_stub_agent.py`; `tests/api/test_advice_route.py`; `tests/architecture/test_fitness.py` (modify).

---

### Task 1: `Claim` — a rationale is evidence, not prose

**Files:**
- Create: `src/fenceai/agent/__init__.py` (empty)
- Create: `src/fenceai/agent/proposal.py`
- Test: `tests/agent/__init__.py` (empty), `tests/agent/test_proposal.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Claim(marker: Literal["measured","read","inferred"], text: str, evidence: str | None)`. Construction raises `ValidationError` when the marker and evidence disagree.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_proposal.py
"""The rationale types. Spec §5.1.

A marker without its evidence is the failure `conversation.md` ground rule 2
exists to prevent: one side asserted from memory that a table read `NON HVHZ`
and it did not, and the only difference a reader could see when it was later
true was that the second claim arrived with a query attached.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.agent.proposal import Claim


def test_a_measured_claim_carries_the_query_that_produced_it():
    claim = Claim(marker="measured", text="window spans 2200-2900 mm",
                  evidence="landmark:lm_7.extent_mm")
    assert claim.evidence == "landmark:lm_7.extent_mm"


def test_a_measured_claim_without_evidence_is_refused():
    with pytest.raises(ValidationError, match="must carry its evidence"):
        Claim(marker="measured", text="window spans 2200-2900 mm")


def test_a_read_claim_without_evidence_is_refused():
    with pytest.raises(ValidationError, match="must carry its evidence"):
        Claim(marker="read", text="600 mm clear of a window")


def test_an_inferred_claim_carries_none_and_says_so():
    claim = Claim(marker="inferred", text="a centred bay looks better")
    assert claim.evidence is None


def test_an_inferred_claim_carrying_evidence_is_refused():
    """Forbidden rather than optional. A citation on a reasoning claim reads as
    observed, and nothing downstream can tell that it supports the reasoning
    rather than the fact."""
    with pytest.raises(ValidationError, match="carries no evidence"):
        Claim(marker="inferred", text="looks better", evidence="landmark:lm_7")


def test_empty_string_evidence_is_not_evidence():
    with pytest.raises(ValidationError, match="must carry its evidence"):
        Claim(marker="measured", text="window at 2200", evidence="")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/agent/test_proposal.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.agent'`

- [ ] **Step 3: Write the minimal implementation**

```python
# src/fenceai/agent/proposal.py
"""What an agent task produces, and how it must justify it.

A rationale is never prose. Every claim carries HOW it is known — the
convention `docs/integration-contract/conversation.md` ground rule 2 adopted
after one side asserted from memory that a table read `NON HVHZ` and it did
not: "the only difference a reader can see is that the second one arrives with
a query attached. Make that difference visible by construction rather than by
trust."

It pays for itself twice. A `measured` claim can be re-checked before a person
sees the proposal (`run.py`); an `inferred` one cannot, so it renders as
reasoning. The agent can neither advise on a number it invented nor pass an
opinion off as an observation.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §5.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

Marker = Literal["measured", "read", "inferred"]


class Claim(BaseModel):
    """One statement, and how it is known.

    `evidence` is REQUIRED for `measured` and `read` and FORBIDDEN for
    `inferred`. Forbidden rather than merely absent: a citation on a reasoning
    claim reads as observed, and nothing downstream can tell that it supports
    the reasoning rather than the fact.
    """

    marker: Marker
    text: str
    evidence: str | None = None

    @model_validator(mode="after")
    def _evidence_matches_marker(self) -> "Claim":
        if self.marker == "inferred":
            if self.evidence is not None:
                raise ValueError("an inferred claim carries no evidence")
        elif not self.evidence:
            raise ValueError(f"a {self.marker} claim must carry its evidence")
        return self
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/agent/test_proposal.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/agent/__init__.py src/fenceai/agent/proposal.py tests/agent/__init__.py tests/agent/test_proposal.py
git commit -m "feat(agent): a claim carries how it is known, or it does not construct"
```

---

### Task 2: `Proposal` and `TaskResult` — a content-derived id, and a ledger

**Files:**
- Modify: `src/fenceai/agent/proposal.py`
- Test: `tests/agent/test_proposal.py` (append)

**Interfaces:**
- Consumes: `Claim` from Task 1.
- Produces: `proposal_id(task_id, kind, payload, scope) -> str`; `ViewDigest`, `Declined`, `NoStanding`, `Proposal`, `TaskResult`. `Proposal.source_class` is the literal `"ai_proposal"`. `TaskResult.evaluated: bool` is separate from an empty `proposals` list.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_proposal.py  (append)
from fenceai.agent.proposal import (
    Declined, NoStanding, Proposal, TaskResult, ViewDigest, proposal_id,
)


def test_the_same_proposal_gets_the_same_id_every_run():
    """Random ids break the rejection record: "a rejection suppresses
    re-proposal" needs the system to recognise a re-proposal as the SAME
    proposal. `conversation.md` T46 §8 is the measured cost of getting identity
    wrong — 0 of 67 gap ids survived a cut and a consumer saw total churn."""
    a = proposal_id("rank_choice_set", "select_choice_point",
                    {"choice_set": "bay_layout", "scope": "gap:run1:0", "point_id": "p2"},
                    "gap:run1:0")
    b = proposal_id("rank_choice_set", "select_choice_point",
                    {"scope": "gap:run1:0", "point_id": "p2", "choice_set": "bay_layout"},
                    "gap:run1:0")
    assert a == b, "key order must not change the id"
    assert a.startswith("prop_")


def test_a_different_answer_is_a_different_proposal():
    a = proposal_id("rank_choice_set", "select_choice_point", {"point_id": "p2"}, "s")
    b = proposal_id("rank_choice_set", "select_choice_point", {"point_id": "p3"}, "s")
    assert a != b


def test_a_proposal_is_always_an_ai_proposal():
    """`ai_proposal` is a SourceClass in the integration contract's closed
    registry, and §1.4's BINDING block makes it proposal-only on every task. We
    do not invent provenance for agent output."""
    p = Proposal(id="prop_x", task_id="t", project_id="pr",
                 kind="select_choice_point", payload={}, scope="s")
    assert p.source_class == "ai_proposal"
    assert p.status == "proposed"


def test_a_task_that_looked_and_found_nothing_is_not_a_task_that_did_not_look():
    """Vacuous green. This repo shipped the other bug once — audit B01, a cached
    null painting a clean bill of health — and the eight-step road makes it a
    rule: unknown is never folded into done."""
    looked = TaskResult(task_id="t", evaluated=True)
    did_not = TaskResult(task_id="t", evaluated=False)
    assert looked.proposals == did_not.proposals == []
    assert looked.evaluated is not did_not.evaluated


def test_a_declined_action_carries_the_claims_that_ruled_it_out():
    d = Declined(kind="select_choice_point",
                 claims=[Claim(marker="inferred", text="costs one more post")])
    assert d.claims[0].marker == "inferred"


def test_no_standing_is_not_the_same_as_needing_information():
    """T54 §2: the Knowledge team left DECLARED_ASSOCIATIONS deliberately empty
    rather than assert a product identity they do not hold. `needs` means "I
    lack information"; `no_standing` means "I have the answer and it is not
    mine to state"."""
    r = TaskResult(
        task_id="t", evaluated=True,
        needs=["the window position is not recorded"],
        no_standing=[NoStanding(about="this fence is a CertainTeed Chesterfield",
                                whose="whoever sets the job up",
                                claims=[Claim(marker="inferred", text="the slat pitch matches")])],
    )
    assert r.needs and r.no_standing
    assert r.no_standing[0].whose


def test_a_view_digest_records_identity_not_payload():
    d = ViewDigest(slices=["choice_sets"], run_id="run_1",
                   topology_revision=4, knowledge_hash="abc123")
    assert d.topology_revision == 4
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/agent/test_proposal.py -q`
Expected: FAIL — `ImportError: cannot import name 'proposal_id'`

- [ ] **Step 3: Write the minimal implementation**

```python
# src/fenceai/agent/proposal.py  (append; add `hashlib` and `json` to the imports)
import hashlib
import json


def proposal_id(task_id: str, kind: str, payload: dict, scope: str) -> str:
    """Content-derived, never random — `core/ids.py`'s existing distinction.

    Two things break under a random id, and the second is not obvious. A re-run
    shows a person "all new suggestions" when nothing changed; and
    `advisory-agent-design.md` §3's "a rejection suppresses re-proposal" stops
    working entirely, because nothing can tell a re-proposal is the same
    proposal. `conversation.md` T46 §8 measured that from the other side of the
    boundary: 0 of 67 ids survived and the consumer saw 67 removed, 403 added,
    when "the gaps themselves did not all change; their identity did."
    """
    body = json.dumps(
        {"task": task_id, "kind": kind, "payload": payload, "scope": scope},
        sort_keys=True, separators=(",", ":"),
    )
    return "prop_" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


class ViewDigest(BaseModel):
    """What a task read, by IDENTITY rather than by payload.

    The same identity a `GenerationRun` already stamps. A replay against a
    matching digest is provably the same situation; against a copy of the
    payload it would only be a similar one.
    """

    slices: list[str] = []
    run_id: str | None = None
    topology_revision: int | None = None
    knowledge_hash: str = ""


class Declined(BaseModel):
    """An action considered and not proposed, with the claims that ruled it out.

    Evidenced exactly as a proposal is — a rejection nobody can check is not a
    reason. It is also the record that stops the same idea arriving next week.
    """

    kind: str
    claims: list[Claim] = []


class NoStanding(BaseModel):
    """Something the task could assert and may not.

    NOT a variant of `needs`. `needs` means *I lack information*; this means *I
    have the answer and it is not mine to state*. T54 §2 is the case: the
    Knowledge team could see which of our fence models their product family
    mapped to, and left the table empty rather than "assert a product identity
    we do not hold". An agent will always be able to produce a plausible
    mapping, so it needs somewhere to put one that is not a proposal.
    """

    about: str
    whose: str
    claims: list[Claim] = []


class Proposal(BaseModel):
    """One thing the agent suggests, and everything needed to check it."""

    id: str
    task_id: str
    project_id: str
    kind: str
    payload: dict = {}
    scope: str = ""
    claims: list[Claim] = []
    saw: ViewDigest = ViewDigest()
    # Fixed. `SourceClass` is a closed registry vocabulary in the integration
    # contract, and §1.4's BINDING block states `ai_proposal` is proposal-only
    # on every task — so `knowledge/source_policy.py` refuses it as authority
    # everywhere, independently of our own review gate.
    source_class: Literal["ai_proposal"] = "ai_proposal"
    agent_id: str = "stub"
    status: Literal["proposed", "kept", "reversed"] = "proposed"
    created_at: str = ""


class TaskResult(BaseModel):
    """Ledger-shaped, from `conversation.md` ground rule 3: no decision may live
    only in prose.

    `evaluated` is separate from an empty `proposals` list, and the separation
    is the point — "I did not look" is not "nothing to report".
    """

    task_id: str
    evaluated: bool
    proposals: list[Proposal] = []
    declined: list[Declined] = []
    measured: list[Claim] = []
    needs: list[str] = []
    no_standing: list[NoStanding] = []
    # Counted from the first run, never added later (spec §8b): an agent whose
    # proposals nobody keeps looks exactly like an agent that is working.
    produced: int = 0
    dropped: int = 0
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/agent/test_proposal.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/agent/proposal.py tests/agent/test_proposal.py
git commit -m "feat(agent): proposals get content-derived ids and a ledger-shaped result"
```

---

### Task 3: The action registry — the permission list that becomes a grammar

**Files:**
- Create: `src/fenceai/agent/registry.py`
- Test: `tests/agent/test_registry.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SelectChoicePoint(choice_set: str, scope: str, point_id: str)`; `ActionSpec` dataclass with `kind`, `payload_model`, `rung`, `disposition`, `i18n_key`; `register(spec)`, `spec_for(kind) -> ActionSpec`, `parse_payload(kind, payload) -> BaseModel`, `KINDS -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_registry.py
"""The action registry. Spec §2.

A code-registered table, the same instinct as `knowledge/ast.py`'s FnCall
whitelist: a closed vocabulary resolved in code, never an eval of strings.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.agent.registry import KINDS, SelectChoicePoint, parse_payload, spec_for


def test_the_one_action_this_slice_ships_is_registered():
    spec = spec_for("select_choice_point")
    assert spec.rung == "selection"
    assert spec.payload_model is SelectChoicePoint
    assert spec.i18n_key == "agent.action.select_choice_point"


def test_an_unregistered_kind_is_refused_by_name():
    with pytest.raises(KeyError, match="move_post"):
        spec_for("move_post")


def test_a_payload_is_parsed_into_its_typed_model():
    payload = parse_payload("select_choice_point", {
        "choice_set": "bay_layout", "scope": "gap:run1:0", "point_id": "p2"})
    assert isinstance(payload, SelectChoicePoint)
    assert payload.point_id == "p2"


def test_a_payload_missing_a_field_is_refused():
    with pytest.raises(ValidationError):
        parse_payload("select_choice_point", {"choice_set": "bay_layout"})


def test_a_payload_with_an_unknown_field_is_refused():
    """Structured outputs require additionalProperties:false, so a free-form
    dict is inexpressible in the schema and silently stays empty
    (`ai/claude.py`). The payload models are explicit and closed for the same
    reason, in the other direction."""
    with pytest.raises(ValidationError):
        parse_payload("select_choice_point", {
            "choice_set": "bay_layout", "scope": "s", "point_id": "p2",
            "and_also": "move a post"})


def test_kinds_is_the_whole_vocabulary():
    assert KINDS == ("select_choice_point",)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/agent/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.agent.registry'`

- [ ] **Step 3: Write the minimal implementation**

```python
# src/fenceai/agent/registry.py
"""What an agent may propose — a code-registered table, not a config file.

`knowledge/ast.py`'s FnCall whitelist is the same instinct: a closed vocabulary
resolved in code, no eval of strings, ever. A task's permission list is
compiled into the model's output schema (spec §1), so an action absent from
this table has no word in any grammar an agent is ever handed. Narrow run stops
being a policy somebody must enforce and becomes a type.

**Growth is additive.** A run stamps only the inputs it actually had, so adding
an entry never invalidates a stored run. But a finding that fits no entry
becomes a COUNTER before it becomes a row here — T54 §2, where the Knowledge
team wanted a ninth Gap kind, found none of the eight fitted, and declined to
add one "for something we can measure on our own side". Without that restraint
the table accumulates one-off kinds and the grammar is only as good as the
judgement of whoever last extended it.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


class SelectChoicePoint(BaseModel):
    """Answer an open choice set by naming one of the points it offered.

    Explicit fields, never a dict: a free-form params dict is inexpressible
    under `additionalProperties:false` and silently arrives empty — the lesson
    `ai/claude.py` already carries in a comment.
    """

    model_config = {"extra": "forbid"}

    choice_set: str
    scope: str
    point_id: str


@dataclass(frozen=True)
class ActionSpec:
    """One thing an agent may propose.

    A dataclass rather than a model: `payload_model` is a TYPE, and a registry
    row is code rather than data on the wire.
    """

    kind: str
    payload_model: type[BaseModel]
    rung: Literal["note", "selection", "directive", "rule"]
    i18n_key: str
    # Backend policy, and deliberately not the agent's business (spec §7): an
    # agent told which of its proposals get applied automatically will learn to
    # phrase things to get applied, and every check would still pass.
    disposition: Literal["show", "hold_pending", "auto"] = "show"


_REGISTRY: dict[str, ActionSpec] = {}


def register(spec: ActionSpec) -> ActionSpec:
    if spec.kind in _REGISTRY:
        raise ValueError(f"action kind already registered: {spec.kind}")
    _REGISTRY[spec.kind] = spec
    return spec


def spec_for(kind: str) -> ActionSpec:
    if kind not in _REGISTRY:
        raise KeyError(f"no registered action kind: {kind}")
    return _REGISTRY[kind]


def parse_payload(kind: str, payload: dict) -> BaseModel:
    """The typed model is authoritative; a stored `Proposal.payload` is its
    serialised form, and this is the only way to read one back."""
    return spec_for(kind).payload_model.model_validate(payload)


SELECT_CHOICE_POINT = register(ActionSpec(
    kind="select_choice_point",
    payload_model=SelectChoicePoint,
    rung="selection",
    i18n_key="agent.action.select_choice_point",
))

KINDS: tuple[str, ...] = tuple(_REGISTRY)
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/agent/test_registry.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/agent/registry.py tests/agent/test_registry.py
git commit -m "feat(agent): the action registry, and it is the grammar not a checker"
```

---

### Task 4: `AgentView` — broad read, and it remembers what it handed over

**Files:**
- Create: `src/fenceai/agent/view.py`
- Test: `tests/agent/test_view.py`

**Interfaces:**
- Consumes: `ViewDigest` from Task 2.
- Produces: `AgentView(project, result)` with `open_choice_sets() -> list[ChoiceSet]`, `point_ids(choice_set, scope) -> set[str]`, `refs_handed_over() -> set[str]`, `has(slice_name) -> bool`, `digest(slices) -> ViewDigest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_view.py
"""The read interface. Spec §4.

Breadth is in what may be looked at; narrowness is in what is asked and what
may be emitted. `ai/ports.py` refuses an ambient context object because "an
adapter that wanted more would be reaching for state the deterministic side
owns" — this class is the read half of that, with no mutators to reach with.
"""
from __future__ import annotations

from fenceai.agent.view import AgentView
from fenceai.project.model import Project, Selection
from fenceai.strategy.choices import ChoiceSet, DesignPoint
from fenceai.strategy.model import GenerationResult


def _result(*sets: ChoiceSet) -> GenerationResult:
    from fenceai.strategy.model import GenerationRun, Strategy
    from fenceai.decisions.graph import DecisionGraph
    return GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=4,
                          knowledge_hash="kh_abc"),
        strategy=Strategy(), graph=DecisionGraph(), choice_sets=list(sets))


def _set(scope: str = "gap:run1:0") -> ChoiceSet:
    return ChoiceSet(
        id="bay_layout", scope=scope, question="choices.question.bay_widths",
        points=[DesignPoint(id="p1", label="2 x 2500", widths=[2500, 2500],
                            axes={"posts": 3}, is_default=True),
                DesignPoint(id="p2", label="1800 + 1400 + 1800",
                            widths=[1800, 1400, 1800], axes={"posts": 4})])


def test_an_unanswered_choice_set_is_open():
    view = AgentView(Project(id="pr_1"), _result(_set()))
    assert [c.scope for c in view.open_choice_sets()] == ["gap:run1:0"]


def test_a_choice_set_the_person_already_answered_is_not_open():
    """The agent advises on questions that are still questions. Re-advising on
    a settled one is the alarm that always rings."""
    project = Project(id="pr_1", choices=[
        Selection(choice_set="bay_layout", scope="gap:run1:0", widths=[1800, 1400, 1800])])
    view = AgentView(project, _result(_set()))
    assert view.open_choice_sets() == []


def test_the_view_reports_whether_a_slice_has_anything_in_it():
    """`has()` is what separates "I looked and found nothing" from "I never
    looked" one layer up."""
    assert AgentView(Project(id="pr_1"), _result(_set())).has("choice_sets")
    assert not AgentView(Project(id="pr_1"), _result()).has("choice_sets")


def test_the_view_records_which_point_ids_it_handed_over():
    """The grounding check compares a claim's evidence against this. An agent
    can echo a citation and never invent one."""
    view = AgentView(Project(id="pr_1"), _result(_set()))
    view.open_choice_sets()
    assert view.point_ids("bay_layout", "gap:run1:0") == {"p1", "p2"}
    assert "point:p2" in view.refs_handed_over()


def test_nothing_is_handed_over_until_it_is_read():
    view = AgentView(Project(id="pr_1"), _result(_set()))
    assert view.refs_handed_over() == set()


def test_the_digest_is_identity_not_payload():
    view = AgentView(Project(id="pr_1"), _result(_set()))
    digest = view.digest(["choice_sets"])
    assert digest.run_id == "run_1"
    assert digest.topology_revision == 4
    assert digest.knowledge_hash == "kh_abc"
    assert digest.slices == ["choice_sets"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/agent/test_view.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.agent.view'`

If `GenerationRun` rejects the keyword arguments above, open `src/fenceai/strategy/model.py`, read the real field names, and fix the helper — do not change the production code to fit the test.

- [ ] **Step 3: Write the minimal implementation**

```python
# src/fenceai/agent/view.py
"""What a task may look at — read-only, and it remembers what it handed over.

Broad read, narrow run (spec §4). There are no mutators here on purpose: an
adapter cannot reach for state the deterministic side owns if the object it
holds cannot write.

**Never cached across runs.** A view is constructed per task run and thrown
away. `conversation.md` T53 §1 is the worst form of the alternative — a team
telling the other side twice that a cut was blocked for a reason false when
written: "Ours was worse than a stale comment — we asserted the stale state as
a current reason." A cached view is an agent doing exactly that.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §4.
"""

from __future__ import annotations

from fenceai.agent.proposal import ViewDigest
from fenceai.project.model import Project
from fenceai.strategy.choices import ChoiceSet
from fenceai.strategy.model import GenerationResult


class AgentView:
    def __init__(self, project: Project, result: GenerationResult) -> None:
        self._project = project
        self._result = result
        self._handed_over: set[str] = set()

    # -- slices ---------------------------------------------------------------

    def open_choice_sets(self) -> list[ChoiceSet]:
        """Questions still open — a set the person has already answered is not
        one. Reading it records every point id as handed over."""
        answered = {(c.choice_set, c.scope) for c in self._project.choices}
        out = [c for c in self._result.choice_sets
               if (c.id, c.scope) not in answered]
        for choice_set in out:
            for point in choice_set.points:
                self._handed_over.add(f"point:{point.id}")
        return out

    def point_ids(self, choice_set: str, scope: str) -> set[str]:
        return {p.id for c in self._result.choice_sets
                if c.id == choice_set and c.scope == scope for p in c.points}

    # -- accounting -----------------------------------------------------------

    def refs_handed_over(self) -> set[str]:
        """Every reference this run's view actually returned.

        The grounding check matches a claim's evidence against this set, which
        is why it is accumulated rather than recomputed: an agent may only cite
        what it was handed, so it can echo a citation and never invent one.
        """
        return set(self._handed_over)

    def has(self, slice_name: str) -> bool:
        if slice_name == "choice_sets":
            return bool(self._result.choice_sets)
        raise KeyError(f"no such view slice: {slice_name}")

    def digest(self, slices: list[str]) -> ViewDigest:
        run = self._result.run
        return ViewDigest(
            slices=list(slices),
            run_id=run.id,
            topology_revision=run.topology_revision,
            knowledge_hash=run.knowledge_hash,
        )
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/agent/test_view.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/agent/view.py tests/agent/test_view.py
git commit -m "feat(agent): a read-only view that remembers what it handed over"
```

---

### Task 5: `TaskSpec` and the one task

**Files:**
- Create: `src/fenceai/agent/tasks.py`
- Test: `tests/agent/test_tasks.py`

**Interfaces:**
- Consumes: `KINDS` from Task 3.
- Produces: `TaskSpec(id, goal, reads, may_emit, max_proposals)` dataclass; `RANK_CHOICE_SET: TaskSpec`; `task_for(id) -> TaskSpec`.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_tasks.py
"""Task declarations. Spec §3."""
from __future__ import annotations

import pytest

from fenceai.agent.registry import KINDS
from fenceai.agent.tasks import RANK_CHOICE_SET, task_for


def test_the_task_may_only_emit_registered_kinds():
    """The permission list becomes the output schema, so a kind that is not in
    the registry has no word in the grammar the agent is handed."""
    assert set(RANK_CHOICE_SET.may_emit) <= set(KINDS)


def test_the_task_declares_what_it_reads():
    assert RANK_CHOICE_SET.reads == ["choice_sets"]


def test_the_goal_says_what_the_task_is_for_and_never_what_is_true():
    """`conversation.md` T49 §6c found three stale claims in one day: "every one
    of them was true when written, load-bearing for a real decision, and left
    behind by the boundary moving." Domain facts come from the view at run
    time, never from prose that ages."""
    goal = RANK_CHOICE_SET.goal.lower()
    for stale in ("1800", "2500", "mm", "certainteed", "m-vinyl", "window"):
        assert stale not in goal, f"the goal states a domain fact: {stale!r}"


def test_a_cap_exists_and_is_not_a_target():
    assert RANK_CHOICE_SET.max_proposals >= 1


def test_an_unknown_task_is_refused_by_name():
    with pytest.raises(KeyError, match="place_posts"):
        task_for("place_posts")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/agent/test_tasks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.agent.tasks'`

- [ ] **Step 3: Write the minimal implementation**

```python
# src/fenceai/agent/tasks.py
"""Tasks are data, not code. Adding a capability is adding a row.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskSpec:
    """One goal, one output shape, one permission list.

    `goal` says what the task is FOR. It must never say what is TRUE: facts in
    prose go stale in the direction that keeps sounding right, and what is true
    comes from the view at run time.
    """

    id: str
    goal: str
    reads: list[str]
    may_emit: list[str]
    # A cap, not a target. "A guard that always fails is a guard everybody
    # learns to ignore" (conversation.md T55 §8) — an agent that comments on
    # everything is the same alarm.
    max_proposals: int = 1
    triggers: list[str] = field(default_factory=list)


RANK_CHOICE_SET = TaskSpec(
    id="rank_choice_set",
    goal=(
        "A question the data left open has more than one admissible answer and "
        "nothing prefers one. Recommend the answer you would pick, and give the "
        "reason as claims a reader can check. Recommend nothing if none is "
        "better than the one the engine already builds."
    ),
    reads=["choice_sets"],
    may_emit=["select_choice_point"],
    max_proposals=1,
    triggers=["choice_set_open"],
)

_TASKS = {RANK_CHOICE_SET.id: RANK_CHOICE_SET}


def task_for(task_id: str) -> TaskSpec:
    if task_id not in _TASKS:
        raise KeyError(f"no such task: {task_id}")
    return _TASKS[task_id]
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/agent/test_tasks.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/agent/tasks.py tests/agent/test_tasks.py
git commit -m "feat(agent): tasks are data, and a goal never states a domain fact"
```

---

### Task 6: The port and the deterministic stub

**Files:**
- Modify: `src/fenceai/ai/ports.py`
- Modify: `src/fenceai/ai/stub.py`
- Test: `tests/ai/test_stub_agent.py`

**Interfaces:**
- Consumes: `TaskSpec`, `AgentView`, `TaskResult`, `Proposal`, `Claim`, `proposal_id`.
- Produces: `TaskRunner` protocol with `interpreter_id: str` and `run(task, view, project_id) -> TaskResult`; `StubAgent` implementing it.

- [ ] **Step 1: Write the failing test**

```python
# tests/ai/test_stub_agent.py
"""The deterministic stub for the agent port.

`test_every_ai_port_has_a_stub` requires one, and it must be capped: the stub
answers the demo vocabulary and must never become a second rule engine.
"""
from __future__ import annotations

from fenceai.agent.tasks import RANK_CHOICE_SET
from fenceai.agent.view import AgentView
from fenceai.ai.stub import StubAgent
from fenceai.project.model import Project
from fenceai.strategy.choices import ChoiceSet, DesignPoint
from fenceai.decisions.graph import DecisionGraph
from fenceai.strategy.model import GenerationResult, GenerationRun, Strategy


def _view(*points: DesignPoint) -> AgentView:
    result = GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=1,
                          knowledge_hash="kh"),
        strategy=Strategy(), graph=DecisionGraph(),
        choice_sets=[ChoiceSet(id="bay_layout", scope="gap:run1:0",
                               question="choices.question.bay_widths",
                               points=list(points))])
    return AgentView(Project(id="pr_1"), result)


DEFAULT = DesignPoint(id="p1", label="2 x 2500", widths=[2500, 2500],
                      axes={"posts": 3}, is_default=True)
ALT = DesignPoint(id="p2", label="1800 + 1400 + 1800", widths=[1800, 1400, 1800],
                  axes={"posts": 4})


def test_the_stub_actually_produces_a_proposal():
    """A framework test whose stub returns nothing passes and proves nothing —
    the same family as vacuous green. `conversation.md` T49 §9: an entire suite
    "reports green by not running"."""
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    assert result.evaluated is True
    assert len(result.proposals) == 1
    assert result.proposals[0].kind == "select_choice_point"
    assert result.proposals[0].payload["point_id"] == "p2"


def test_every_claim_the_stub_makes_cites_a_point_it_was_handed():
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    for claim in result.proposals[0].claims:
        if claim.marker != "inferred":
            assert claim.evidence.startswith("point:")


def test_the_stub_is_honest_about_being_a_stub():
    """It has no judgement and must not pretend to. Every claim it makes about
    WHY is `inferred`."""
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    assert any(c.marker == "inferred" for c in result.proposals[0].claims)


def test_one_admissible_answer_is_not_a_question():
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT), project_id="pr_1")
    assert result.evaluated is True
    assert result.proposals == []


def test_the_stub_is_deterministic():
    a = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    b = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    assert a.proposals[0].id == b.proposals[0].id
    assert a.model_dump() == b.model_dump()


def test_the_stub_stamps_its_identity():
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    assert result.proposals[0].agent_id == "stub"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/ai/test_stub_agent.py -q`
Expected: FAIL — `ImportError: cannot import name 'StubAgent'`

- [ ] **Step 3: Write the minimal implementation**

Append the protocol to `src/fenceai/ai/ports.py`, inside the existing `TYPE_CHECKING` block for the imports:

```python
# src/fenceai/ai/ports.py  — add to the TYPE_CHECKING block
    from fenceai.agent.proposal import TaskResult
    from fenceai.agent.tasks import TaskSpec
    from fenceai.agent.view import AgentView


# ...and at the end of the file:
class TaskRunner(Protocol):
    """Runs ONE goal-scoped agent task. Broad read via the view, narrow run via
    the task's own permission list (ADR-0009, agent-framework-design §4)."""

    interpreter_id: str

    def run(self, task: "TaskSpec", view: "AgentView", project_id: str) -> "TaskResult": ...
```

Append to `src/fenceai/ai/stub.py`:

```python
# src/fenceai/ai/stub.py  — add these imports at the top
from fenceai.agent.proposal import Claim, Proposal, TaskResult, proposal_id
from fenceai.agent.tasks import TaskSpec
from fenceai.agent.view import AgentView


class StubAgent:
    """Deterministic agent for offline development and every unit test.

    Capped on purpose and must not grow: it picks the first non-default point
    the engine offered and says, as an `inferred` claim, that this is exactly
    what it did. It has no judgement, so it claims none — which still exercises
    the whole framework: registry, permission list, claims, the grounding
    check, the ledger and the counters.
    """

    interpreter_id = "stub"

    def run(self, task: TaskSpec, view: AgentView, project_id: str) -> TaskResult:
        if task.id != "rank_choice_set":
            return TaskResult(task_id=task.id, evaluated=False)

        proposals = []
        for choice_set in view.open_choice_sets():
            if len(proposals) >= task.max_proposals:
                break
            alternative = next((p for p in choice_set.points if not p.is_default), None)
            if alternative is None:
                continue  # one admissible answer is not a question
            payload = {"choice_set": choice_set.id, "scope": choice_set.scope,
                       "point_id": alternative.id}
            proposals.append(Proposal(
                id=proposal_id(task.id, "select_choice_point", payload, choice_set.scope),
                task_id=task.id, project_id=project_id,
                kind="select_choice_point", payload=payload, scope=choice_set.scope,
                claims=[
                    Claim(marker="read", text=alternative.label,
                          evidence=f"point:{alternative.id}"),
                    Claim(marker="inferred",
                          text="the stub picks the first alternative the engine "
                               "offered; it is not a judgement about this fence"),
                ],
                saw=view.digest(task.reads),
                agent_id=self.interpreter_id,
            ))
        return TaskResult(task_id=task.id, evaluated=True, proposals=proposals,
                          produced=len(proposals))
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/ai/test_stub_agent.py tests/architecture/test_fitness.py -q`
Expected: PASS. `test_every_ai_port_has_a_stub` must still pass — it matches each protocol to a conforming stub.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/ai/ports.py src/fenceai/ai/stub.py tests/ai/test_stub_agent.py
git commit -m "feat(ai): a task-runner port and a capped deterministic stub"
```

---

### Task 7: `run_task` — the three checks, and the counters

**Files:**
- Create: `src/fenceai/agent/run.py`
- Test: `tests/agent/test_run.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `run_task(task, view, runner, project_id) -> TaskResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_run.py
"""Dispatch and the three checks. Spec §6 and §8.

Nothing a person sees has skipped a check, and a proposal that fails one is
DROPPED and counted as an agent defect — never shown. A user must never be
offered something impossible.
"""
from __future__ import annotations

from fenceai.agent.proposal import Claim, Proposal, TaskResult, proposal_id
from fenceai.agent.run import run_task
from fenceai.agent.tasks import RANK_CHOICE_SET
from fenceai.agent.view import AgentView
from fenceai.decisions.graph import DecisionGraph
from fenceai.project.model import Project
from fenceai.strategy.choices import ChoiceSet, DesignPoint
from fenceai.strategy.model import GenerationResult, GenerationRun, Strategy

DEFAULT = DesignPoint(id="p1", label="2 x 2500", widths=[2500, 2500],
                      axes={"posts": 3}, is_default=True)
ALT = DesignPoint(id="p2", label="1800 + 1400 + 1800", widths=[1800, 1400, 1800],
                  axes={"posts": 4})


def _view(*points: DesignPoint) -> AgentView:
    sets = [ChoiceSet(id="bay_layout", scope="gap:run1:0",
                      question="q", points=list(points))] if points else []
    return AgentView(Project(id="pr_1"), GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=1,
                          knowledge_hash="kh"),
        strategy=Strategy(), graph=DecisionGraph(), choice_sets=sets))


class _Runner:
    """A runner under test control — the point is what the CHECKS do with it."""

    interpreter_id = "fake"

    def __init__(self, *proposals: Proposal):
        self._proposals = list(proposals)

    def run(self, task, view, project_id) -> TaskResult:
        return TaskResult(task_id=task.id, evaluated=True,
                          proposals=self._proposals, produced=len(self._proposals))


def _proposal(point_id="p2", kind="select_choice_point", claims=None,
              scope="gap:run1:0") -> Proposal:
    payload = {"choice_set": "bay_layout", "scope": scope, "point_id": point_id}
    return Proposal(id=proposal_id("rank_choice_set", kind, payload, scope),
                    task_id="rank_choice_set", project_id="pr_1", kind=kind,
                    payload=payload, scope=scope,
                    claims=claims if claims is not None
                    else [Claim(marker="read", text="x", evidence=f"point:{point_id}")])


def test_a_good_proposal_survives_every_check():
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _Runner(_proposal()),
                   project_id="pr_1")
    assert out.evaluated is True
    assert len(out.proposals) == 1
    assert out.produced == 1 and out.dropped == 0


def test_an_action_the_task_may_not_emit_is_dropped():
    """Check 1. The permission list is the grammar, and this is the belt to its
    braces — a runner that emitted an unpermitted kind is broken, not creative."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(kind="pin_post")), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_claim_citing_something_the_view_never_handed_over_is_dropped():
    """Check 2, and it is the one that stops fabrication. A `ref_id` the view
    did not return is refused whether or not it would have resolved —
    conversation.md T58 §2 and T59 §2."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[
                       Claim(marker="read", text="page 17",
                             evidence="ref:sha256-nobody-handed-this-over")])),
                   project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_an_inferred_claim_needs_no_evidence_and_is_not_dropped():
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[
                       Claim(marker="inferred", text="it looks better")])),
                   project_id="pr_1")
    assert len(out.proposals) == 1


def test_a_point_that_is_not_in_the_offered_set_is_dropped():
    """Check 3. A user must never be offered something impossible."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(point_id="p9")), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_task_with_an_empty_slice_reports_that_it_did_not_look():
    """Vacuous green. "I did not look" is never "nothing to report"."""
    out = run_task(RANK_CHOICE_SET, _view(), _Runner(_proposal()), project_id="pr_1")
    assert out.evaluated is False
    assert out.proposals == []


def test_the_runner_is_not_called_when_there_is_nothing_to_look_at():
    class _Exploding:
        interpreter_id = "boom"

        def run(self, task, view, project_id):
            raise AssertionError("must not be called on an empty slice")

    assert run_task(RANK_CHOICE_SET, _view(), _Exploding(),
                    project_id="pr_1").evaluated is False


def test_more_proposals_than_the_cap_are_trimmed_not_dropped():
    """A cap is a cap. Trimming is not a defect, so it does not count as one."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(), _proposal(point_id="p1")), project_id="pr_1")
    assert len(out.proposals) == RANK_CHOICE_SET.max_proposals
    assert out.dropped == 0


def test_a_runner_that_raises_reports_not_evaluated_rather_than_nothing_found():
    class _Broken:
        interpreter_id = "broken"

        def run(self, task, view, project_id):
            raise RuntimeError("adapter exploded")

    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _Broken(), project_id="pr_1")
    assert out.evaluated is False
    assert out.proposals == []
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/agent/test_run.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.agent.run'`

- [ ] **Step 3: Write the minimal implementation**

```python
# src/fenceai/agent/run.py
"""Dispatch: task + view + runner -> a checked TaskResult.

Three checks stand between a runner's output and a person, and a proposal that
fails one is DROPPED and counted as an agent defect rather than shown. A user
must never be offered something impossible.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §6, §8, §8b.
"""

from __future__ import annotations

from pydantic import ValidationError

from fenceai.agent.proposal import Proposal, TaskResult
from fenceai.agent.registry import parse_payload
from fenceai.agent.tasks import TaskSpec
from fenceai.agent.view import AgentView


def run_task(task: TaskSpec, view: AgentView, runner, project_id: str) -> TaskResult:
    """Run one task and return only what survived the checks.

    A task whose slices are all empty, or whose runner raises, reports
    `evaluated=False` — never an empty result that reads as "nothing to
    report". That distinction is the vacuous-green rule: a check with nothing
    to check must not report success.
    """
    if not any(view.has(name) for name in task.reads):
        return TaskResult(task_id=task.id, evaluated=False)

    try:
        raw = runner.run(task, view, project_id)
    except Exception:  # an adapter failure is not a finding about the fence
        return TaskResult(task_id=task.id, evaluated=False)

    kept, dropped = [], 0
    for proposal in raw.proposals:
        if _admissible(proposal, task, view):
            kept.append(proposal)
        else:
            dropped += 1

    return raw.model_copy(update={
        "proposals": kept[: task.max_proposals],
        "produced": len(kept),
        "dropped": dropped,
    })


def _admissible(proposal: Proposal, task: TaskSpec, view: AgentView) -> bool:
    # 1 — the permission list. Belt to the grammar's braces: a runner that
    # emitted an unpermitted kind is broken, not creative.
    if proposal.kind not in task.may_emit:
        return False

    # 2 — grounding. Every non-inferred claim must cite something THIS run's
    # view handed over. Not "does it resolve" — a real ref the agent produced
    # from nowhere would resolve. The property is that a citation can only ever
    # be echoed (conversation.md T58 §2, accepted at T59 §2).
    handed_over = view.refs_handed_over()
    for claim in proposal.claims:
        if claim.marker != "inferred" and claim.evidence not in handed_over:
            return False

    # 3 — referential. The payload must parse into its typed model and name
    # something that exists.
    try:
        payload = parse_payload(proposal.kind, proposal.payload)
    except (ValidationError, KeyError):
        return False
    if proposal.kind == "select_choice_point":
        if payload.point_id not in view.point_ids(payload.choice_set, payload.scope):
            return False
    return True
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/agent -q`
Expected: PASS, all agent tests.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/agent/run.py tests/agent/test_run.py
git commit -m "feat(agent): three checks before a person sees anything, and the counters"
```

---

### Task 8: The dependency rule, pinned

**Files:**
- Modify: `tests/architecture/test_fitness.py`

**Interfaces:**
- Consumes: the `fenceai.agent` package.
- Produces: `test_only_the_api_layer_imports_the_agent()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/architecture/test_fitness.py`:

```python
def test_only_the_api_layer_imports_the_agent():
    """A framework the pipeline CAN import is one that eventually WILL be, and
    an AI call reachable from `generate()` ends the traceability of every
    number downstream of it (ADR-0009). `agent` is a delivery-side package like
    `api` and `web`: it may depend on the domain, and nothing in the domain may
    depend on it."""
    offenders = [
        f"{path.relative_to(SRC)} imports {bad}"
        for package in DOMAIN for path in _modules(package)
        for bad in sorted(m for m in _imports(path) if m.startswith("fenceai.agent"))
    ]
    assert not offenders, offenders


def test_the_agent_never_reaches_the_store_or_the_generator():
    """The view takes what it is given. An agent module that imported
    `generate` could re-decide rather than re-read, which is the same defect
    `test_a_read_model_never_reaches_for_the_things_that_decide` prevents in
    `report`."""
    offenders = [
        f"{path.relative_to(SRC)} imports fenceai.{bad}"
        for path in _modules("agent")
        for bad in sorted(_packages(path) & {"api", "store"})
    ]
    assert not offenders, offenders
```

- [ ] **Step 2: Run it and watch it pass immediately**

Run: `uv run pytest tests/architecture/test_fitness.py -q`
Expected: PASS. **This test is a guard, not a red-green cycle** — it should be green the moment it is written, and the value is that it fails later. Prove it can fail: temporarily add `from fenceai.agent.run import run_task` to the top of `src/fenceai/strategy/generator.py`, re-run, confirm it FAILS, then remove the import and confirm it passes again.

- [ ] **Step 3: Commit**

```bash
git add tests/architecture/test_fitness.py
git commit -m "test(architecture): nothing but the API layer may import the agent"
```

---

### Task 9: The route, its words, and the documents that count it

**Files:**
- Modify: `src/fenceai/api/app.py`
- Modify: `src/fenceai/web/static/i18n/en.json`, `src/fenceai/web/static/i18n/he.json`
- Modify: `docs/architecture/04-backend.md`
- Test: `tests/api/test_advice_route.py`

**Interfaces:**
- Consumes: `run_task`, `RANK_CHOICE_SET`, `AgentView`, `StubAgent`.
- Produces: `GET /api/runs/{run_id}/advice` returning a serialised `TaskResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_advice_route.py
"""The advice route. It reads; it changes nothing."""
from __future__ import annotations


def test_advice_on_a_run_with_an_open_question(client, seeded_run):
    r = client.get(f"/api/runs/{seeded_run}/advice")
    assert r.status_code == 200
    body = r.json()
    assert body["evaluated"] is True
    assert body["task_id"] == "rank_choice_set"
    for proposal in body["proposals"]:
        assert proposal["source_class"] == "ai_proposal"
        assert proposal["claims"], "a proposal with no rationale is not a proposal"


def test_advice_never_mutates_the_project(client, seeded_run, project_id):
    before = client.get(f"/api/projects/{project_id}").json()
    client.get(f"/api/runs/{seeded_run}/advice")
    assert client.get(f"/api/projects/{project_id}").json() == before


def test_advice_is_the_same_on_two_calls(client, seeded_run):
    a = client.get(f"/api/runs/{seeded_run}/advice").json()
    b = client.get(f"/api/runs/{seeded_run}/advice").json()
    assert [p["id"] for p in a["proposals"]] == [p["id"] for p in b["proposals"]]


def test_advice_refuses_a_run_whose_topology_moved(client, seeded_run, moved_topology):
    r = client.get(f"/api/runs/{seeded_run}/advice")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "topology_changed"
```

Reuse the fixtures in `tests/api/` — read `tests/api/test_snapshot_routes.py` for the established `client` / project-seeding pattern and follow it rather than inventing one. If no `moved_topology` fixture exists, write it by PUTting the project's topology once to bump its revision.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/api/test_advice_route.py -q`
Expected: FAIL — 404, the route does not exist.

- [ ] **Step 3: Write the minimal implementation**

Add to `AppState` and `lifespan` in `src/fenceai/api/app.py`:

```python
class AppState:
    ...
    agent = None

# in lifespan(), beside the other three:
    state.agent = StubAgent()
```

Add the route, next to the other run-reading routes:

```python
@app.get("/api/runs/{run_id}/advice")
def get_advice(run_id: str):
    """What the agent would suggest about this run's open questions.

    Read-only and derived: nothing is stored, and a second call on unchanged
    inputs returns the same proposal ids because they are content-derived.
    """
    result = _run(run_id)
    project = _project(result.run.project_id)
    # Same refusal as `/structure`: advice about a layout laid over an edited
    # drawing is advice about a fence nobody drew.
    if project.topology.revision != result.run.topology_revision:
        raise HTTPException(409, {
            "code": "topology_changed",
            "run_topology_revision": result.run.topology_revision,
            "project_topology_revision": project.topology.revision,
        })
    view = AgentView(project, result)
    return run_task(RANK_CHOICE_SET, view, state.agent,
                    project_id=result.run.project_id)
```

...with these imports at the top of `app.py`:

```python
from fenceai.agent.run import run_task
from fenceai.agent.tasks import RANK_CHOICE_SET
from fenceai.agent.view import AgentView
from fenceai.ai.stub import StubAgent  # add to the existing stub import line
```

Add to **both** `i18n/en.json` and `i18n/he.json`, keeping the key sets identical:

```json
"agent.action.select_choice_point": "Use this layout",
"agent.title": "Suggestion",
"agent.marker.measured": "measured",
"agent.marker.read": "from your rules",
"agent.marker.inferred": "reasoning",
"agent.none": "Nothing to suggest here",
"agent.not_evaluated": "Could not check",
"agent.stub_notice": "Offline suggestion — no judgement behind it"
```

Hebrew values (the plan states them so the executor does not invent them):

```json
"agent.action.select_choice_point": "השתמש בפריסה הזו",
"agent.title": "הצעה",
"agent.marker.measured": "נמדד",
"agent.marker.read": "מהכללים שלך",
"agent.marker.inferred": "הסקה",
"agent.none": "אין מה להציע כאן",
"agent.not_evaluated": "לא ניתן היה לבדוק",
"agent.stub_notice": "הצעה במצב לא־מקוון — אין מאחוריה שיפוט"
```

Update `docs/architecture/04-backend.md`: change `63 routes.` on line 46 to `64 routes.`, and add `advice` to the run-reading group in the table.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/api/test_advice_route.py tests/architecture/test_fitness.py tests/web/test_locale_bundles.py -q`
Expected: PASS. The fitness tests check the route count and that every path appears in the doc; the locale test checks key parity.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/api/app.py src/fenceai/web/static/i18n/en.json src/fenceai/web/static/i18n/he.json docs/architecture/04-backend.md tests/api/test_advice_route.py
git commit -m "feat(api): GET /api/runs/{id}/advice, with both bundles and the doc table"
```

---

### Task 10: The screen — advice beside the question, never instead of it

**Files:**
- Create: `src/fenceai/web/static/js/agent-advice.js`
- Modify: `src/fenceai/web/static/index.html`
- Test: `tests/web/test_agent_advice_module.py`

**Interfaces:**
- Consumes: `GET /api/runs/{run_id}/advice`.
- Produces: an ES module owning `#agent-advice` and nothing else.

- [ ] **Step 1: Read before writing**

Open `src/fenceai/web/static/js/state.js` and one existing module that fetches per run (`js/runview.js` is the closest). Match how they subscribe to run changes and how they call `t()`. **Do not** touch the choices panel's DOM — this module owns `#agent-advice` only.

- [ ] **Step 2: Write the failing test**

```python
# tests/web/test_agent_advice_module.py
"""The advice module, as source. Mirrors `tests/web/test_base_top_module.py`.

The rules here are the frontend contract's, and each has a defect behind it:
esc() on interpolated text, `t()` on every visible string, and a suggestion
that is added BESIDE what it concerns rather than replacing it.
"""
from __future__ import annotations

from pathlib import Path

MODULE = Path("src/fenceai/web/static/js/agent-advice.js")


def test_the_module_exists_and_owns_one_container():
    src = MODULE.read_text()
    assert "#agent-advice" in src or "agent-advice" in src
    assert "#choices" not in src, "no module touches another module's DOM subtree"


def test_every_interpolated_value_is_escaped():
    """Claim text and point labels are agent- and data-authored."""
    src = MODULE.read_text()
    assert "esc(" in src
    assert "${claim.text}" not in src, "unescaped agent text in innerHTML"


def test_no_literal_user_facing_string():
    """Every visible string goes through t(). A literal here is a string that
    exists in one language."""
    src = MODULE.read_text()
    for literal in ("Suggestion", "Nothing to suggest", "Could not check"):
        assert f'"{literal}"' not in src and f"'{literal}'" not in src


def test_not_evaluated_and_no_proposals_render_differently():
    """"I did not look" is never "nothing to report" — audit B01 in miniature."""
    src = MODULE.read_text()
    assert "agent.not_evaluated" in src
    assert "agent.none" in src


def test_the_module_never_writes_project_state():
    """Slice 1 advises and does not act. A keep/reverse path arrives in slice 2
    with the record that makes a refusal mean something."""
    src = MODULE.read_text()
    for mutator in ("saveTopology", "pushSnapshot", "method: \"PUT\"", "method: 'PUT'"):
        assert mutator not in src
```

- [ ] **Step 3: Run it and watch it fail**

Run: `uv run pytest tests/web/test_agent_advice_module.py -q`
Expected: FAIL — the file does not exist.

- [ ] **Step 4: Write the module**

```javascript
// src/fenceai/web/static/js/agent-advice.js
// The agent's suggestions for the current run.
//
// It renders BESIDE the question it concerns and never replaces anything —
// spec §5.3. A suggestion that replaced a warning would let a wrong guess cost
// a record instead of a dismissal.
//
// Slice 1 advises only. There is no keep/reverse here on purpose: a refusal
// that leaves no record lets the agent re-propose what was already refused,
// and the record arrives with slice 2.
import { state, on, t, esc } from "./state.js";

const MARKER_KEY = {
  measured: "agent.marker.measured",
  read: "agent.marker.read",
  inferred: "agent.marker.inferred",
};

function claimRow(claim) {
  const marker = t(MARKER_KEY[claim.marker] || "agent.marker.inferred");
  return `<li class="agent-claim agent-claim--${esc(claim.marker)}">
    <span class="agent-claim__marker">${esc(marker)}</span>
    <span class="agent-claim__text">${esc(claim.text)}</span>
  </li>`;
}

function proposalCard(proposal) {
  return `<article class="agent-proposal">
    <h4>${esc(t("agent.title"))}</h4>
    <ul class="agent-claims">${proposal.claims.map(claimRow).join("")}</ul>
    <p class="agent-note">${esc(t("agent.stub_notice"))}</p>
  </article>`;
}

export function renderAdvice(result, host) {
  if (!host) return;
  if (!result || result.evaluated !== true) {
    host.innerHTML = `<p class="agent-empty">${esc(t("agent.not_evaluated"))}</p>`;
    return;
  }
  if (!result.proposals.length) {
    host.innerHTML = `<p class="agent-empty">${esc(t("agent.none"))}</p>`;
    return;
  }
  host.innerHTML = result.proposals.map(proposalCard).join("");
}

export async function loadAdvice(runId, host) {
  if (!runId) return renderAdvice(null, host);
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/advice`);
    if (!response.ok) return renderAdvice(null, host);
    renderAdvice(await response.json(), host);
  } catch {
    // A failed fetch is "could not check", never "nothing to suggest".
    renderAdvice(null, host);
  }
}

on("run:changed", () => loadAdvice(state.runId, document.getElementById("agent-advice")));
```

Add the container to `index.html`, immediately after the element that closes `#choices`:

```html
<section id="agent-advice" class="agent-advice" aria-live="polite"></section>
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest tests/web -q`
Expected: PASS, including the locale-bundle parity tests.

- [ ] **Step 6: Run the whole suite and the smoke**

```bash
uv run pytest -q
uv run pytest tests/scenarios -q     # must not move
uv run --with websocket-client python tools/ui_smoke.py
```

Expected: the full suite green, the scenarios gate unchanged, the smoke suite passing. `on("run:changed", ...)` must match the real event name in `state.js` — if it does not, use the real one; do not add a new event.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/web/static/js/agent-advice.js src/fenceai/web/static/index.html tests/web/test_agent_advice_module.py
git commit -m "feat(web): the agent's suggestion, beside the question and never instead of it"
```

---

## THE CHECKPOINT — stop here

Do not start slice 2. Do not add the Claude adapter. Do not extend the registry.

```bash
uv run uvicorn fenceai.api.app:app --reload
```

Open `http://localhost:8000`, draw a run long enough to leave a real choice — a 5 m stretch produces one — press **Generate**, and look at the panel beside the choices.

**The product owner must see this and say whether it is right or wrong before anything else is written.** Green tests are not the checkpoint. The failure this prevents is on the record: on 2026-09-03 a feature landed correctly, every test passed, and the verdict was *"we took a bigger task then we could chew."*

Then update `plan/current-status.md` with what was built and what building it found.

## Self-review

**Spec coverage.** §1 permission-list-as-grammar → Tasks 3, 5, 7 (check 1). §2 registry → Task 3. §3 task, and a goal that states no domain fact → Task 5. §4 view, never cached → Task 4. §5.0 content-derived ids → Task 2. §5.1 tagged claims → Task 1. §5.2 `ai_proposal` → Task 2. §5.3 beside-never-instead → Task 10. §5.4 ledger, `no_standing` → Task 2. §6 three checks → Task 7. §7 disposition not the agent's business → Task 3 (field exists, never passed to a runner). §8 silence, `evaluated` → Tasks 2, 7, 10. §8b reach → Task 7's counters, with `shown`/`kept`/`reversed` scoped out above and the reason given. §9 stub, and its test asserting a proposal was produced → Task 6. §10 module layout and the dependency rule → Task 8. §11 seams — untouched, correctly. §12 refusals — each has a test.

**Not covered, deliberately:** `materialize` on `ActionSpec` (nothing is materialised in an advise-only slice), and the Claude adapter. Both are named in Scope with their trigger.

**Type consistency.** `TaskResult` fields are identical in Tasks 2, 6 and 7. `Proposal.scope` is used by `proposal_id` in Task 2 and by check 3 in Task 7. `AgentView.refs_handed_over()` is spelled the same in Tasks 4 and 7. `run(task, view, project_id)` has the same signature in the port, the stub and `_Runner`.

**Known risk, stated rather than hidden.** Tasks 4, 6, 7 and 9 construct `GenerationRun` and `Project` in fixtures from field names read at planning time. If any differ, fix the fixture, never the production model — and if `state.js` has no `run:changed` event, use the real one.
