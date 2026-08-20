# DesignRun / MaterialRun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the one `run_id` that today answers two questions into a `DesignRun`
(what fence is this — pure, deterministic, for ever) and a `MaterialRun` (what does it
cost to build from the stock we have, under this objective — true of a moment), so that
two printouts of the same run id can no longer name two different BOMs.

**Architecture:** `objective_preset` leaves the design digest and `RUN_DIGEST_VERSION`
bumps to `digest-v3`. A new `fulfillment/material.py` owns `FULFILMENT_BEHAVIOR_VERSION`,
the `inventory_hash` computation that is currently copy-pasted at three sites in
`api/app.py`, and a `MaterialRun` document whose id is a digest of
`(design_id, inventory_hash, catalog_hash, objective_preset, fulfilment_version)`. A new
append-only `material_runs` table stores it under `INSERT OR IGNORE`, exactly as
`generation_runs` is stored and for the same reason. `/bom` stops being a pure read and
becomes "materialize this design against today's yard, and return the MaterialRun",
idempotent by digest. A `Quote` gains `material_id`, so the commercial document can name
the materialization it froze.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLite (`store/db.py`), pytest. No new
dependencies.

**Spec:** `docs/superpowers/specs/2026-08-19-design-run-material-run.md` — read it before
Task 1. Its §1 demonstrates the defect, §4 lists what must NOT change, and §5/§7 carry the
three decisions this plan implements.

---

## Global Constraints

- **Integer millimetres and cents at rest; float only transient** (ADR-0002). Nothing in
  this plan does arithmetic on a quantity; if a task finds itself doing so, the task is
  wrong.
- **`generate()` stays pure and deterministic** (ADR-0004). Nothing in this plan reaches
  into it except to change what its digest is computed OVER.
- **No BOM arithmetic moves.** This is an identity change, not a costing change. The
  compatibility gate (`tests/scenarios/test_compatibility_gate.py`) must stay
  byte-identical across the whole plan. If a golden file moves, the change is wrong —
  do not regenerate the goldens.
- **Decisions taken 2026-08-20** (spec §5, §7): (a) bump `RUN_DIGEST_VERSION`; no
  garbage collection of MaterialRuns in this change; the impact preview keeps comparing
  designs and is not touched.
- **New stored documents follow `store/db.py` conventions**: columns only for what is
  queried by (`id`, `design_id`, `created_at`), everything else in `doc`, audited on write,
  append-only.
- **No new user-visible warning or refusal codes are introduced by this plan.** If a task
  finds itself needing one, it needs `warning.<code>`/`critique.<code>` entries in BOTH
  `i18n/he.json` and `i18n/en.json` (`tests/web/test_locale_bundles.py` enforces this) —
  stop and say so rather than adding an English-only string.
- **Mutation is the standard here.** Every new test must be shown failing against the
  pre-fix code before the fix lands. Two vacuous assertions were caught in the last arc by
  doing exactly this.
- Run the full suite with `uv run pytest -q`; the release gate is
  `uv run pytest tests/scenarios -q`.

## Two corrections to the spec, confirmed in the code

The spec was written before these were checked. Both change the work, and Tasks 4 and 5
exist because of them.

**A. The preset is in the digest TWICE.** `strategy/generator.py:264` puts the whole
merged `policy` dict into the digest list, and `DEFAULT_POLICY`
(`strategy/generator.py:88`) is `{"default_height_mm": 1800, "objective_preset":
"least_cost"}`, so `policy` always carries the preset. Line 267 then adds
`run_meta.objective_preset` a second time. Removing only line 267 leaves the id unmoved
and the change inert while looking done. Task 4 removes both.

**B. Once the preset leaves the digest, the STORED preset freezes for ever.** After Task 4,
regenerating an unchanged project under a different preset produces the same design id.
`save_run` is `INSERT OR IGNORE` (`store/db.py:592`), so the stored document is the FIRST
one and `result.run.objective_preset` keeps the preset of the first generation for the life
of the project. Every read that takes the preset off the stored run — `api/app.py:208`
(`_priced`, which serves /bom, /structure and /quote) and `api/app.py:1053` (the bay
preview) — would then price under a preset the user has since changed, silently. Task 5
moves those reads to the project's LIVE policy, which is what the spec's own model implies:
the preset is a materialization input, sourced from now, exactly as inventory is.

`learning/impact.py:167` also reads `result.run.objective_preset`, but its `result` comes
from a fresh in-memory `generate()` call with `policy=p.policy`, not from the store, so it
is not exposed to the freeze and is left alone (spec §7.3: the impact preview is not
touched).

## File Structure

**Created:**
- `src/fenceai/fulfillment/material.py` — the materialization identity: the behaviour
  version, the inventory hash, the material id digest, and the `MaterialRun` document.
  One responsibility: naming what a priced BOM was priced against.
- `tests/fulfillment/test_material.py` — unit tests for that module.
- `tests/api/test_material_run.py` — the endpoint behaviour, including the spec §1
  reproduction.

**Modified:**
- `src/fenceai/strategy/generator.py` — digest inputs (both preset occurrences),
  `RUN_DIGEST_VERSION` → `digest-v3`, and the comment block that currently explains why
  there is no fulfilment version.
- `src/fenceai/strategy/model.py:184` — `GenerationRun.objective_preset` becomes a
  read-only legacy field; the comment must say so.
- `src/fenceai/store/db.py` — `material_runs` table + `save_material_run` /
  `load_material_run` / `list_material_runs`.
- `src/fenceai/api/app.py` — `_priced` takes an explicit preset; `/bom` materializes;
  `create_quote` records `material_id`; the bay preview reads the live preset.
- `src/fenceai/fulfillment/quote.py` — `material_id` field.
- `tests/strategy/test_run_identity.py:39` — `test_the_preset_changes_the_run_id` inverts.
- `plan/open-work.md` — item 5 moves from SPECIFIED to done.
- `docs/architecture/` — the backend document gains the new table and routes (the
  architecture fitness tests check this; see Task 8).

---

### Task 1: The materialization identity module

The pure half, with no store and no API: a version constant, the inventory hash that three
sites in `api/app.py` currently each compute for themselves, and the digest.

**Files:**
- Create: `src/fenceai/fulfillment/material.py`
- Test: `tests/fulfillment/test_material.py`

**Interfaces:**
- Consumes: `Inventory` from `fenceai.fulfillment.fulfill`.
- Produces:
  - `FULFILMENT_BEHAVIOR_VERSION: str` (initial value `"fulfilment-v1"`)
  - `inventory_hash(inventory: Inventory) -> str` — 16 hex chars
  - `material_id(design_id: str, inventory_hash: str, catalog_hash: str, objective_preset: str) -> str`
    — returns `"mat_" + 12 hex chars`

- [ ] **Step 1: Write the failing tests**

Create `tests/fulfillment/test_material.py`:

```python
"""A MaterialRun's id names what a BOM was priced AGAINST. Every input that can
change the money has to be inside it, or a stored quote silently means something
else after the engine changes under it."""

import pytest

from fenceai.fulfillment.fulfill import Inventory
from fenceai.fulfillment.material import (
    FULFILMENT_BEHAVIOR_VERSION, inventory_hash, material_id,
)


def test_the_inventory_hash_is_stable_and_sized():
    inv = Inventory()
    assert inventory_hash(inv) == inventory_hash(Inventory())
    assert len(inventory_hash(inv)) == 16


def test_a_different_yard_hashes_differently():
    a = Inventory()
    b = Inventory(stock={"BAR-POST-LINE": 3})
    assert inventory_hash(a) != inventory_hash(b)


def test_identical_inputs_give_the_identical_material_id():
    args = ("run_abc", "inv0000000000000", "cat0000000000000", "least_cost")
    assert material_id(*args) == material_id(*args)
    assert material_id(*args).startswith("mat_")
    assert len(material_id(*args)) == len("mat_") + 12


@pytest.mark.parametrize("position", [0, 1, 2, 3])
def test_every_input_moves_the_material_id(position):
    """Each argument is load-bearing. A parametrized sweep rather than four
    hand-written cases, because the failure this guards against is one input
    being dropped from the digest and nobody noticing."""
    base = ["run_abc", "inv0000000000000", "cat0000000000000", "least_cost"]
    moved = list(base)
    moved[position] = moved[position] + "X"
    assert material_id(*base) != material_id(*moved)


def test_the_fulfilment_behaviour_version_is_part_of_the_material_id(monkeypatch):
    """The point of §1.6 applied to the half that was left out.
    PLANNING_BEHAVIOR_VERSION covers generation; nothing covered cut planning,
    supply resolution or allocation. A change to the FFD packer must produce a
    different material id or a stored quote silently means something else."""
    from fenceai.fulfillment import material

    before = material_id("run_abc", "inv0", "cat0", "least_cost")
    monkeypatch.setattr(material, "FULFILMENT_BEHAVIOR_VERSION", "fulfilment-vNEXT")
    assert material_id("run_abc", "inv0", "cat0", "least_cost") != before


def test_the_version_constant_is_named_not_blank():
    assert FULFILMENT_BEHAVIOR_VERSION.startswith("fulfilment-")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/fulfillment/test_material.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.fulfillment.material'`

- [ ] **Step 3: Write the module**

Create `src/fenceai/fulfillment/material.py`:

```python
"""What a BOM was priced AGAINST, named.

A run id answers "what fence is this" — topology, knowledge, overrides, models,
parts, policy, engine version — and is reproducible for ever (ADR-0004). It does
NOT answer "what does it cost to build, from the stock we have, under this
objective", because inventory, prices and the objective preset are statements
about a moment and are legitimately different tomorrow.

Before this module the second question had no name at all: /bom read live
inventory, computed an `inventory_hash` on every read, wrote it to the audit log,
and put it in no identity and no stored document. One run id could therefore
print two different BOMs with `GET /api/runs/{id}` byte-identical between them
(the spec reproduces it: 40 700 then 27 200 agorot after three posts arrive).

`FULFILMENT_BEHAVIOR_VERSION` is the other half of PLANNING_BEHAVIOR_VERSION.
That constant covers generation's output; nothing covered cut planning, supply
resolution or allocation. Bump this one when what a strategy COSTS changes for
unchanged inputs — a different packer, a different remnant policy, a different
allocation order — or a stored quote silently comes to mean something else.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from fenceai.demand.derive import DemandLine
from fenceai.fulfillment.fulfill import Bom, Inventory
from fenceai.fulfillment.lines import ResolvedSupplyLine

FULFILMENT_BEHAVIOR_VERSION = "fulfilment-v1"


def inventory_hash(inventory: Inventory) -> str:
    """What was in the yard, as sixteen characters.

    Three sites in `api/app.py` each computed this inline with the same
    expression; three copies of a hash are three chances for one of them to
    quietly hash something else.
    """
    return hashlib.sha256(inventory.model_dump_json().encode()).hexdigest()[:16]


def material_id(
    design_id: str,
    inventory_hash: str,
    catalog_hash: str,
    objective_preset: str,
) -> str:
    """The content address of one materialization.

    Read through the module global rather than a default argument, so
    `monkeypatch.setattr` on the constant moves the id — a default argument would
    bind the version at import time and make the guard untestable.
    """
    return "mat_" + hashlib.sha256(
        json.dumps(
            [design_id, inventory_hash, catalog_hash, objective_preset,
             FULFILMENT_BEHAVIOR_VERSION],
            sort_keys=True, default=str,
        ).encode()
    ).hexdigest()[:12]


class MaterialRun(BaseModel):
    """One design, priced against one yard, under one objective.

    `Quote` already froze this thing's numbers without being able to name what
    produced them; a quote now carries `material_id` and can.
    """

    id: str
    design_id: str            # the GenerationRun this prices
    inventory_hash: str = ""  # what was in the yard
    catalog_hash: str = ""    # narrowed to the skus the run named, as the design does
    objective_preset: str = "least_cost"
    fulfilment_version: str = ""
    created_at: str = ""
    requirements: list[ResolvedSupplyLine] = []
    # kept, never dropped, for the same reason PricedRun keeps them: a working
    # view reports the gap, and /quote refuses to freeze a document that
    # under-prices the job
    unresolved: list[DemandLine] = []
    bom: Bom
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/fulfillment/test_material.py -q`
Expected: PASS (7 tests, counting the parametrized sweep as four)

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/fulfillment/material.py tests/fulfillment/test_material.py
git commit -m "feat(material): the thing a quote freezes gets a name and a version"
```

---

### Task 2: Storing a MaterialRun

Append-only, `INSERT OR IGNORE` by digest, columns only for what is queried by. The same
shape `save_run` uses, for the same reason.

**Files:**
- Modify: `src/fenceai/store/db.py:28-52` (schema), and the generation-runs section around
  `src/fenceai/store/db.py:590-612` (add the new section directly beneath it)
- Test: `tests/store/test_material_store.py` (create)

**Interfaces:**
- Consumes: `MaterialRun` from `fenceai.fulfillment.material` (Task 1).
- Produces on `Store`:
  - `save_material_run(self, m: MaterialRun, actor: str = "system") -> None`
  - `load_material_run(self, material_id: str) -> MaterialRun | None`
  - `list_material_runs(self, design_id: str) -> list[dict]` — `[{"id", "created_at"}]`,
    oldest first

- [ ] **Step 1: Write the failing tests**

Create `tests/store/test_material_store.py`:

```python
"""A MaterialRun is append-only and idempotent by digest, exactly as a
GenerationRun is: the same design against the same yard under the same objective
is ONE fact, however many times it is read."""

from fenceai.fulfillment.fulfill import Bom
from fenceai.fulfillment.material import MaterialRun
from fenceai.store.db import Store


def _material(**kw) -> MaterialRun:
    base = dict(id="mat_aaa", design_id="run_abc", inventory_hash="inv0",
                catalog_hash="cat0", objective_preset="least_cost",
                fulfilment_version="fulfilment-v1", bom=Bom())
    return MaterialRun(**{**base, **kw})


def test_a_material_run_round_trips():
    store = Store(":memory:")
    store.save_material_run(_material())
    loaded = store.load_material_run("mat_aaa")
    assert loaded is not None
    assert loaded.design_id == "run_abc"
    assert loaded.objective_preset == "least_cost"
    assert loaded.fulfilment_version == "fulfilment-v1"


def test_an_unknown_material_run_is_none_not_an_error():
    assert Store(":memory:").load_material_run("mat_nope") is None


def test_the_store_stamps_created_at():
    store = Store(":memory:")
    store.save_material_run(_material())
    assert store.load_material_run("mat_aaa").created_at


def test_saving_the_same_id_twice_does_not_write_twice():
    """INSERT OR IGNORE, for the reason save_run uses it: /bom materializes on
    every read, and a project priced daily must not accumulate a row per read of
    an unchanged yard."""
    store = Store(":memory:")
    store.save_material_run(_material())
    store.save_material_run(_material(design_id="run_DIFFERENT"))
    assert store.load_material_run("mat_aaa").design_id == "run_abc"
    assert len(store.list_material_runs("run_abc")) == 1


def test_material_runs_are_listed_per_design():
    store = Store(":memory:")
    store.save_material_run(_material(id="mat_a", design_id="run_one"))
    store.save_material_run(_material(id="mat_b", design_id="run_one"))
    store.save_material_run(_material(id="mat_c", design_id="run_two"))
    assert {r["id"] for r in store.list_material_runs("run_one")} == {"mat_a", "mat_b"}
    assert [r["id"] for r in store.list_material_runs("run_two")] == ["mat_c"]


def test_writing_a_material_run_is_audited():
    store = Store(":memory:")
    store.save_material_run(_material(), actor="expert")
    assert any(e["action"] == "save_material_run" and e["ref"] == "mat_aaa"
               for e in store.audit_entries())
```

`Store(":memory:")` and `store.audit_entries()` are verified against `store/db.py:123` and
`store/db.py:759` — use them as written.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/store/test_material_store.py -q`
Expected: FAIL — `AttributeError: 'Store' object has no attribute 'save_material_run'`

- [ ] **Step 3: Add the table**

In `src/fenceai/store/db.py`, inside the `_SCHEMA` string, directly after the
`generation_runs` table (line 39-41), add:

```sql
CREATE TABLE IF NOT EXISTS material_runs (
    id TEXT PRIMARY KEY, design_id TEXT NOT NULL, created_at TEXT NOT NULL,
    doc TEXT NOT NULL);
```

Add the import beside the existing `GenerationResult` import at the top of the file:

```python
from fenceai.fulfillment.material import MaterialRun
```

- [ ] **Step 4: Add the three methods**

In `src/fenceai/store/db.py`, immediately after `list_runs` (which ends at line 612), add:

```python
    # -- material runs (append-only) --------------------------------------------

    def save_material_run(self, m: MaterialRun, actor: str = "system") -> None:
        """INSERT OR IGNORE, for `save_run`'s reason: the id IS the content, so a
        second write of the same id is the same fact arriving again. /bom
        materializes on every read, and an unchanged yard must not accumulate a
        row per read.

        The clock lives here, as it does for a quote and a correction, and fills
        a BLANK rather than overwriting: a caller that already established when
        this happened is not second-guessed.
        """
        m.created_at = m.created_at or _now()
        self._conn.execute(
            "INSERT OR IGNORE INTO material_runs (id, design_id, created_at, doc) "
            "VALUES (?,?,?,?)",
            (m.id, m.design_id, m.created_at, m.model_dump_json()),
        )
        self._audit(actor, "save_material_run", m.id)
        self._conn.commit()

    def load_material_run(self, material_id: str) -> MaterialRun | None:
        row = self._conn.execute(
            "SELECT doc FROM material_runs WHERE id=?", (material_id,)
        ).fetchone()
        return MaterialRun.model_validate_json(row[0]) if row else None

    def list_material_runs(self, design_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, created_at FROM material_runs WHERE design_id=? "
            "ORDER BY created_at, id",
            (design_id,),
        ).fetchall()
        return [{"id": r[0], "created_at": r[1]} for r in rows]
```

Note the `ORDER BY created_at, id`: the order must be TOTAL, or two materializations
written in the same second swap between two reads — the same defect `list_corrections`
(`store/db.py:629`) documents against itself.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/store/test_material_store.py -q`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full suite — a schema change touches every stored-state test**

Run: `uv run pytest -q`
Expected: PASS, same count as before plus the new tests.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/store/db.py tests/store/test_material_store.py
git commit -m "feat(store): material runs get their own append-only table"
```

---

### Task 3: A quote can name what it froze

Smallest possible change, taken before the digest moves so that it lands in isolation.

**Files:**
- Modify: `src/fenceai/fulfillment/quote.py:35`
- Test: `tests/fulfillment/test_quote_material_ref.py` (create)

**Interfaces:**
- Produces: `Quote.material_id: str = ""` — `""` means a quote frozen before
  materializations had names, which is exactly the population a later migration must be
  able to name.

- [ ] **Step 1: Write the failing test**

Create `tests/fulfillment/test_quote_material_ref.py`:

```python
"""A Quote was always a MaterialRun somebody decided to stand behind. It froze
the numbers without being able to name what produced them; now it can."""

from fenceai.fulfillment.fulfill import Bom
from fenceai.fulfillment.quote import Quote


def test_a_quote_carries_the_material_it_froze():
    q = Quote(id="quote_1", project_id="p", run_id="run_abc",
              material_id="mat_aaa", bom=Bom())
    assert q.material_id == "mat_aaa"


def test_a_quote_frozen_before_materializations_had_names_still_reads():
    """Quotes are stored as whole JSON documents and re-read with
    model_validate_json, so a required field would make every earlier quote
    unreadable rather than merely out of date."""
    q = Quote.model_validate({"id": "quote_old", "project_id": "p",
                              "run_id": "run_abc", "bom": {}})
    assert q.material_id == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/fulfillment/test_quote_material_ref.py -q`
Expected: FAIL — pydantic rejects the unexpected keyword `material_id`, or the attribute
does not exist.

- [ ] **Step 3: Add the field**

In `src/fenceai/fulfillment/quote.py`, directly after the `catalog_hash` field (line 35):

```python
    # WHICH materialization this document froze. A quote was always a MaterialRun
    # somebody decided to stand behind — it captured the numbers (`requirements`,
    # `bom`) without being able to name the thing that produced them, so two
    # quotes of one run against two different yards were indistinguishable except
    # by their totals. "" is a quote frozen before materializations had names.
    material_id: str = ""
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/fulfillment/test_quote_material_ref.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/fulfillment/quote.py tests/fulfillment/test_quote_material_ref.py
git commit -m "feat(quote): a frozen document can name the materialization it froze"
```

---

### Task 4: The preset leaves the design digest

The decision from spec §5. **Read correction A at the top of this plan before starting** —
the preset is in the digest twice and removing one occurrence is inert.

**Files:**
- Modify: `src/fenceai/strategy/generator.py:99-123` (the version comment block and
  `RUN_DIGEST_VERSION`), and `src/fenceai/strategy/generator.py:233-271` (the digest)
- Modify: `src/fenceai/strategy/model.py:184`
- Test: `tests/strategy/test_run_identity.py:39` (invert the existing test, add two)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `RUN_DIGEST_VERSION == "digest-v3"`. `GenerationRun.objective_preset` still
  EXISTS and is still populated by `generate()` — it is no longer a digest input, and it is
  no longer the source of truth for a read (that is Task 5).

- [ ] **Step 1: Invert the test that asserts the old behaviour**

In `tests/strategy/test_run_identity.py`, replace `test_the_preset_changes_the_run_id`
(lines 39-43) with:

```python
def test_the_preset_does_NOT_change_the_run_id():
    """A design is what it is regardless of how it will be bought.

    `objective_preset` is read by nothing in generate() — only by resolve_supply,
    the panel preview and the impact preview. Keeping it in the digest made the
    design id move for a supply reason, which is the mirror image of one run id
    printing two BOMs: design identity moving when the fence did not, while
    supply identity did not move at all.
    """
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    b = generate(topo, kb, demo_catalog(), policy={"objective_preset": "honour_priority"})
    assert a.run.id == b.run.id
    # the run still REPORTS the preset it was generated under; it simply is not
    # what the run is
    assert b.run.objective_preset == "honour_priority"


def test_a_design_policy_field_still_changes_the_run_id():
    """The guard against over-correcting. `policy` carries design inputs too, and
    the digest strips exactly ONE key from it — a change that dropped the whole
    dict would make two genuinely different fences hash the same, and this test
    is the difference between the two mistakes."""
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    b = generate(topo, kb, demo_catalog(), policy={"default_height_mm": 2100})
    assert a.run.id != b.run.id
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/strategy/test_run_identity.py -q`
Expected: FAIL on `test_the_preset_does_NOT_change_the_run_id` (`assert a.run.id == b.run.id`
is false). `test_a_design_policy_field_still_changes_the_run_id` should already PASS — it
guards the mistake, it does not drive the change.

- [ ] **Step 3: Remove BOTH occurrences from the digest**

In `src/fenceai/strategy/generator.py`, replace the comment block and digest at lines
233-271. The two changes are the `design_policy` line and the removal of
`run_meta.objective_preset` from the list:

```python
    # anything that changes what the run MEANS belongs in the digest, or
    # INSERT OR IGNORE (store/db.py) serves a stale document under a reused id:
    # - model_snapshot: which fence model(s)/versions the run actually drew from
    # - catalog_hash: the catalog content the run resolved products against
    #
    # `objective_preset` is deliberately NOT here, and it was here TWICE: once by
    # name and once inside `policy`, which DEFAULT_POLICY always populates. It is
    # read by nothing in generate() — only by resolve_supply, the panel preview
    # and the impact preview — so keeping it made the design id move for a supply
    # reason. It belongs to the materialization identity (fulfillment/material.py)
    # along with the inventory and the catalog prices.
    run_meta.model_snapshot = sorted(
        {u.sort_key(): u for u in models_used}.values(), key=ModelUse.sort_key
    )
```

Then, immediately before the `run_meta.id = ...` assignment, add:

```python
    # exactly ONE key is stripped. `policy` carries design inputs too
    # (default_height_mm), and dropping the whole dict would make two genuinely
    # different fences hash the same — the opposite mistake, and the worse one.
    design_policy = {k: v for k, v in policy.items() if k != "objective_preset"}
```

and change the digest list to use `design_policy` in place of `policy`, dropping the
`run_meta.objective_preset` line:

```python
            [project_id, topology.model_dump(), run_meta.knowledge_snapshot,
             [o.model_dump() for o in overrides], design_policy,
             [u.model_dump() for u in run_meta.model_snapshot], run_meta.catalog_hash,
             [u.model_dump() for u in run_meta.part_snapshot],
             PLANNING_BEHAVIOR_VERSION, RUN_DIGEST_VERSION],
```

Leave `run_meta.objective_preset = policy["objective_preset"]` (line 254) in place — the
run still reports what it was generated under.

- [ ] **Step 4: Bump the digest version and rewrite the comment that is now false**

In `src/fenceai/strategy/generator.py`, replace the "There is deliberately NO fulfillment
version here" paragraph (lines 105-110) — it now describes a system that exists:

```python
# The fulfilment version lives in `fulfillment/material.py`, not here. A run's
# stored document is the strategy and its graph; the BOM is a function of mutable
# inventory and is named by a MaterialRun. Putting a fulfilment version in the
# DESIGN digest would deepen exactly the conflation the split removed.
```

And bump the constant (line 123), keeping the existing v2 note above it:

```python
# v3: `objective_preset` LEFT the digest, from both places it occupied (by name,
# and inside `policy`). A design is what it is regardless of how it will be
# bought. This is the one deliberate discontinuity the spec asked for and got:
# stored runs keep their ids and stay readable, and a regeneration of an
# unchanged project mints a new id ONCE, at this boundary. Digest stability is a
# property within a version and is not weakened by the bump.
RUN_DIGEST_VERSION = "digest-v3"
```

- [ ] **Step 5: Mark the model field as no longer an identity input**

In `src/fenceai/strategy/model.py`, replace line 184:

```python
    # which supply-resolution preset this run was GENERATED under. Reported, not
    # identity: it left the digest in digest-v3 (a design is what it is
    # regardless of how it will be bought). It is also NOT the source of truth
    # for a read — `save_run` is INSERT OR IGNORE, so on an unchanged fence this
    # field is frozen at the first generation for ever. Read paths take the live
    # preset from the project's policy and record it on the MaterialRun.
    objective_preset: str = "least_cost"
```

- [ ] **Step 6: Run the identity tests to verify they pass**

Run: `uv run pytest tests/strategy/test_run_identity.py -q`
Expected: PASS (7 tests)

- [ ] **Step 7: Run the release gate — the goldens must NOT move**

Run: `uv run pytest tests/scenarios -q`
Expected: PASS, byte-identical. The compatibility gate's `_spine`
(`tests/scenarios/test_compatibility_gate.py:52`) returns only `requirements` and `bom` and
never a run id, so a digest change must move nothing here. **If a golden file moves, stop:
the change has touched costing and is wrong.**

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS. Tests that assert a run id is stable across a regeneration still pass —
`tests/api/test_decision_comments.py:139` generates twice within one digest version.

- [ ] **Step 9: Commit**

```bash
git add src/fenceai/strategy/generator.py src/fenceai/strategy/model.py \
        tests/strategy/test_run_identity.py
git commit -m "feat(identity)!: a design is what it is regardless of how it will be bought

objective_preset leaves the digest, from BOTH places it occupied — by name and
inside policy, which DEFAULT_POLICY always populates, so removing one was inert.
RUN_DIGEST_VERSION bumps to digest-v3: one deliberate discontinuity, recorded."
```

---

### Task 5: The read paths take the LIVE preset

**Read correction B at the top of this plan before starting.** After Task 4 the stored
preset is frozen by `INSERT OR IGNORE` and can never change for an unchanged fence. This
task is what stops that from becoming a silent mispricing.

**Files:**
- Modify: `src/fenceai/api/app.py:191-216` (`_priced`), and its four call sites — `get_bom`
  (line 374), `get_structure` (line 409), `create_quote` (line 440), and the bay preview
  (line 1053)
- Test: `tests/api/test_material_run.py` (create — this file grows in Task 6 too)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_priced(result, preset: str) -> tuple[Catalog, Inventory, PricedRun]` — the
  preset becomes an explicit required argument, so no caller can silently fall back to the
  stored one. A `_live_preset(project_id: str) -> str` helper reads
  `project.policy.get("objective_preset", DEFAULT_POLICY["objective_preset"])`.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_material_run.py`:

```python
"""Once the preset leaves the design digest, the STORED preset freezes: an
unchanged fence regenerates to the same id, save_run is INSERT OR IGNORE, and the
document served for ever is the first one. A read that trusts it prices under a
preset the user changed weeks ago."""

from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from tests.api.test_decision_comments import _fence  # the established project+run fixture


def test_changing_the_preset_changes_what_the_bom_is_priced_under():
    """The policy is set through the store, not through a route: there is no
    policy endpoint (verified — `policy` appears in api/app.py only at the
    generate call and the impact snapshot). Adding one for a test's convenience
    would be inventing product surface to prove a backend property.
    """
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        before = client.get(f"/api/runs/{run_id}/bom").json()

        project = state.store.load_project(pid)
        project.policy = {**project.policy, "objective_preset": "honour_priority"}
        state.store.save_project(project)

        again = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
        # the DESIGN did not move — that is digest-v3 working
        assert again == run_id
        after = client.get(f"/api/runs/{run_id}/bom").json()
        # ...and the read is nonetheless priced under the preset in force NOW,
        # not the one frozen into the stored document at first generation
        assert after["material"]["objective_preset"] == "honour_priority"
        assert before["material"]["objective_preset"] == "least_cost"
        assert after["material"]["id"] != before["material"]["id"]
```

This test asserts the `material` key that Task 6 adds. Land it here as an expected failure
if the two tasks are done by one worker; otherwise split it: assert the pricing effect here
by reading `state.store.load_run(run_id).run.objective_preset` against the preset actually
used, and move the `material` assertions to Task 6.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/api/test_material_run.py -q`
Expected: FAIL — `after["material"]` does not exist, and (the real defect) the preset in
force is the frozen one.

- [ ] **Step 3: Make the preset an explicit argument**

In `src/fenceai/api/app.py`, add the import beside the other strategy imports:

```python
from fenceai.strategy.generator import DEFAULT_POLICY
```

Add the helper immediately above `_priced` (line 191):

```python
def _live_preset(project_id: str) -> str:
    """The objective in force NOW, from the project's policy.

    NOT `result.run.objective_preset`. A stored run's preset is frozen at its
    first generation: since digest-v3 the preset is not a digest input, so an
    unchanged fence regenerates to the same id and `save_run`'s INSERT OR IGNORE
    keeps the first document for ever. Reading the preset off it would price
    every later read under an objective the user has since changed, silently and
    with no way to see it. The preset is a materialization input, sourced from
    now, exactly as inventory is.
    """
    project = state.store.load_project(project_id)
    policy = project.policy if project else {}
    return policy.get("objective_preset", DEFAULT_POLICY["objective_preset"])
```

Then change `_priced`'s signature and the one line that uses the preset (line 208):

```python
def _priced(result, preset: str) -> tuple[Catalog, Inventory, PricedRun]:
```

```python
            preset=preset,
```

Extend `_priced`'s docstring with a sentence saying why the preset is a parameter and not
read from `result`:

```python
    The preset is a REQUIRED argument rather than something this helper reads off
    the run, so that no caller can quietly fall back to the frozen stored value —
    see `_live_preset`.
```

- [ ] **Step 4: Update all four call sites**

- `get_bom` (line 374): `_, inventory, priced = _priced(result, _live_preset(result.run.project_id))`
- `get_structure` (line 409): `catalog, inventory, priced = _priced(result, _live_preset(result.run.project_id))`
- `create_quote` (line 440): `_, inventory, priced = _priced(result, _live_preset(result.run.project_id))`
- the bay preview (line 1053): replace `result.run.objective_preset` with
  `_live_preset(result.run.project_id)`

`get_structure` already loads the project as `project` above the call; use
`_live_preset(result.run.project_id)` there anyway rather than reaching into
`project.policy` inline, so all four sites read identically and there is one place the rule
lives.

Leave `learning/impact.py:167` alone: its `result` comes from a fresh in-memory
`generate()` with `policy=p.policy`, so it is not exposed to the freeze, and spec §7.3
decided the impact preview is not touched.

- [ ] **Step 5: Run the API suite**

Run: `uv run pytest tests/api -q`
Expected: PASS except the Task 6 half of the new test (`material` key missing). Fix any
call site that still passes one argument — a `TypeError: _priced() missing 1 required
positional argument` is the signature doing its job.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/api/app.py tests/api/test_material_run.py
git commit -m "fix(read): the preset comes from the project, not from the frozen run doc"
```

---

### Task 6: `/bom` materializes

The endpoint stops being a pure read and becomes "materialize this design against today's
yard, and return the MaterialRun" — idempotent by digest.

**Files:**
- Modify: `src/fenceai/api/app.py:371-391` (`get_bom`), and lines 415-416 and 457 (the two
  other inline `inventory_hash` computations)
- Test: `tests/api/test_material_run.py` (extend)

**Interfaces:**
- Consumes: `material_id`, `inventory_hash`, `MaterialRun`, `FULFILMENT_BEHAVIOR_VERSION`
  (Task 1); `save_material_run` (Task 2); `_live_preset` (Task 5).
- Produces: `GET /api/runs/{run_id}/bom` gains a `material` key —
  the serialized `MaterialRun`. `inventory_hash` stays on the response at the top level;
  it is what the frontend already reads and this is not the task to move it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_material_run.py`:

```python
def test_the_bom_names_the_materialization_that_produced_it():
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        body = client.get(f"/api/runs/{run_id}/bom").json()
        m = body["material"]
        assert m["id"].startswith("mat_")
        assert m["design_id"] == run_id
        assert m["inventory_hash"] == body["inventory_hash"]
        assert m["fulfilment_version"]
        assert m["bom"] == body["bom"]


def test_reading_the_same_bom_twice_is_ONE_materialization():
    """Idempotent by digest, which is why /bom can write at all: the same design
    against the same yard under the same objective is one fact, however many
    times it is read."""
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        first = client.get(f"/api/runs/{run_id}/bom").json()["material"]["id"]
        second = client.get(f"/api/runs/{run_id}/bom").json()["material"]["id"]
        assert first == second


def test_the_spec_defect_is_gone_one_run_id_two_boms_now_have_two_names():
    """The reproduction from the spec's §1, turned into a regression test.

    Nothing about the fence changes and GET /api/runs/{id} stays byte-identical
    — that is correct and stays correct. What was missing is that the two BOMs
    had no names, so a reader holding two printouts could not tell which
    inventory each was priced against. Now they can.
    """
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        before_run = client.get(f"/api/runs/{run_id}").json()
        before = client.get(f"/api/runs/{run_id}/bom").json()

        inv = client.get(f"/api/projects/{pid}/inventory").json()
        inv["stock"] = {**inv.get("stock", {}), "BAR-POST-LINE": 3}
        client.put(f"/api/projects/{pid}/inventory", json=inv)

        after = client.get(f"/api/runs/{run_id}/bom").json()
        # the DESIGN is unchanged, and still says so
        assert client.get(f"/api/runs/{run_id}").json() == before_run
        # the two materializations are different, and each names its own yard
        assert after["material"]["id"] != before["material"]["id"]
        assert after["material"]["inventory_hash"] != before["material"]["inventory_hash"]
        assert after["material"]["design_id"] == before["material"]["design_id"] == run_id


def test_a_materialization_is_retrievable_after_the_yard_moves_on():
    """The point of storing it: the row outlives the inventory state that
    produced it, which is what makes a printout checkable later."""
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        mat_id = client.get(f"/api/runs/{run_id}/bom").json()["material"]["id"]
        inv = client.get(f"/api/projects/{pid}/inventory").json()
        inv["stock"] = {**inv.get("stock", {}), "BAR-POST-LINE": 3}
        client.put(f"/api/projects/{pid}/inventory", json=inv)
        stored = state.store.load_material_run(mat_id)
        assert stored is not None and stored.design_id == run_id
```

`state` is already imported by the Task 5 test. The inventory routes are verified:
`GET /api/projects/{project_id}/inventory` (`api/app.py:1171`) and the matching `PUT`
(`api/app.py:1177`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/api/test_material_run.py -q`
Expected: FAIL — `KeyError: 'material'`

- [ ] **Step 3: Materialize in `get_bom`**

Add the imports beside the other fulfillment imports in `src/fenceai/api/app.py`:

```python
from fenceai.fulfillment.material import (
    FULFILMENT_BEHAVIOR_VERSION, MaterialRun, inventory_hash, material_id,
)
```

Replace the body of `get_bom` (lines 372-391):

```python
def get_bom(run_id: str):
    """Materialize this design against today's yard, and return the MaterialRun.

    This is deliberately not a pure read any more. It used to be one, and that
    was the defect: /bom read LIVE inventory, so one run id printed two
    different BOMs with `GET /api/runs/{id}` byte-identical between them, and the
    inventory_hash that would have explained the difference was computed on every
    read and written only to the audit log. It entered no identity, no stored
    document and no quote, so a reader holding two printouts could not tell which
    yard each was priced against — and neither could the system.

    Writing here is safe because the id IS the content: the same design against
    the same inventory, catalog and preset digests to the same `material_id` and
    `save_material_run`'s INSERT OR IGNORE does not write twice. Growth tracks
    real changes to the yard, not read volume, which is why no retention policy
    is needed yet (spec §7.2).
    """
    result = _run(run_id)
    preset = _live_preset(result.run.project_id)
    _, inventory, priced = _priced(result, preset)
    inv_hash = inventory_hash(inventory)
    material = MaterialRun(
        id=material_id(run_id, inv_hash, result.run.catalog_hash, preset),
        design_id=run_id,
        inventory_hash=inv_hash,
        catalog_hash=result.run.catalog_hash,
        objective_preset=preset,
        fulfilment_version=FULFILMENT_BEHAVIOR_VERSION,
        requirements=priced.requirements,
        unresolved=priced.unresolved,
        bom=priced.bom,
    )
    state.store.save_material_run(material)
    # the audit action keeps its name and gains the material id: the ref used to
    # be the only place the inventory hash was recorded, and is now a pointer to
    # a row that holds it
    state.store.log("system", "fulfill", f"{run_id}:inv={inv_hash}:{material.id}")
    # routing an unresolved line out of `requirements` (so a blank sku can never
    # reach fulfill()/the ledger) must not make it disappear from this view —
    # /bom is a working view, so it reports the gap rather than refusing.
    # The same demand, grouped by what CAUSED it. Derived here rather than in the
    # client because the pegs are a backend fact and a second inversion of them
    # in JS is how the two views would come to disagree about which bay bought a
    # rail. Deliberately NOT topology-dependent: /bom stays readable when the
    # drawing has moved on, which is why it groups by `run_ref` and leaves the
    # section TAGS to `js/structure-data.js`, the single tag source.
    return {"requirements": priced.requirements, "unresolved": priced.unresolved,
            "bom": priced.bom, "inventory_hash": inv_hash, "material": material,
            "grouped": group_bom(result.strategy, priced.requirements, priced.bom,
                                 priced.decisions, priced.unresolved)}
```

- [ ] **Step 4: Collapse the two other inline hashes**

In `get_structure`, replace lines 415-416:

```python
    report.inventory_hash = inventory_hash(inventory)
```

In `create_quote`, replace line 457:

```python
        inventory_hash=inventory_hash(inventory),
```

Remove the `import hashlib` at `api/app.py:9` **only if** nothing else in the file uses it
— grep first (`grep -n "hashlib" src/fenceai/api/app.py`) and leave it if there is another
user.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/api/test_material_run.py -q`
Expected: PASS (5 tests, including the Task 5 test that now finds its `material` key)

- [ ] **Step 6: Run the full suite and the release gate**

Run: `uv run pytest -q && uv run pytest tests/scenarios -q`
Expected: PASS. `tests/api/test_api.py:333` (the `fulfill` audit action) must still pass —
the action name was kept deliberately.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/api/app.py tests/api/test_material_run.py
git commit -m "feat(bom): /bom materializes, and the BOM it returns has a name"
```

---

### Task 7: The quote records which materialization it froze

**Files:**
- Modify: `src/fenceai/api/app.py:432-466` (`create_quote`)
- Test: `tests/api/test_material_run.py` (extend)

**Interfaces:**
- Consumes: `Quote.material_id` (Task 3); `material_id`/`MaterialRun`/`inventory_hash`
  (Task 1); `save_material_run` (Task 2); `_live_preset` (Task 5).
- Produces: `POST /api/runs/{run_id}/quote` returns a `Quote` whose `material_id` names a
  row in `material_runs`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_material_run.py`:

```python
def test_a_quote_names_a_materialization_that_actually_exists():
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        quote = client.post(f"/api/runs/{run_id}/quote", json={"label": "q1"}).json()
        assert quote["material_id"].startswith("mat_")
        stored = state.store.load_material_run(quote["material_id"])
        assert stored is not None
        assert stored.design_id == run_id
        assert stored.bom == quote["bom"] or stored.bom.model_dump() == quote["bom"]


def test_the_quote_and_the_bom_read_agree_on_the_materialization():
    """Same design, same yard, same objective — one material id, whichever route
    computed it. Two ids here would mean the two paths disagree about what they
    priced, which is the whole class of defect this change removes."""
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        from_bom = client.get(f"/api/runs/{run_id}/bom").json()["material"]["id"]
        quote = client.post(f"/api/runs/{run_id}/quote", json={"label": "q"}).json()
        assert quote["material_id"] == from_bom
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/api/test_material_run.py -q`
Expected: FAIL — `quote["material_id"]` is `""`.

- [ ] **Step 3: Materialize in `create_quote` too**

In `create_quote`, replace the `_priced` call and the `Quote(...)` construction (lines
440-464). The `unresolved` refusal in between is unchanged and must stay exactly where it
is — a quote still refuses to freeze a document that under-prices the job:

```python
    preset = _live_preset(result.run.project_id)
    _, inventory, priced = _priced(result, preset)
```

then, after the unresolved check, before building the `Quote`:

```python
    # the same digest /bom computes, from the same inputs — so a quote and the
    # BOM read that preceded it name ONE materialization rather than two. Saved
    # here as well because a quote may be the first thing a project ever asks
    # for, and the document it stands behind must exist.
    inv_hash = inventory_hash(inventory)
    material = MaterialRun(
        id=material_id(run_id, inv_hash, result.run.catalog_hash, preset),
        design_id=run_id,
        inventory_hash=inv_hash,
        catalog_hash=result.run.catalog_hash,
        objective_preset=preset,
        fulfilment_version=FULFILMENT_BEHAVIOR_VERSION,
        requirements=priced.requirements,
        unresolved=priced.unresolved,
        bom=priced.bom,
    )
    state.store.save_material_run(material, actor=body.author)
```

and add the field to the `Quote(...)` call, beside `catalog_hash`:

```python
        material_id=material.id,
        inventory_hash=inv_hash,
```

(replacing the inline `inventory_hash=hashlib.sha256(...)` from Task 6 Step 4 — the local
`inv_hash` is the same value and now has one source.)

If the two `MaterialRun` constructions in `get_bom` and `create_quote` are byte-identical
apart from the actor, extract them into one module-level helper in `api/app.py`:

```python
def _materialize(result, preset: str, priced, inventory) -> MaterialRun:
    """One construction, two callers. Two copies of a digest's inputs is how the
    quote path and the BOM path would come to name different materializations for
    the same fence."""
```

Do this extraction — the duplication is exactly the four-copies-of-a-pipeline shape
`fulfillment/pipeline.py`'s own docstring exists to warn about.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/api/test_material_run.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full suite and the release gate**

Run: `uv run pytest -q && uv run pytest tests/scenarios -q`
Expected: PASS, goldens byte-identical.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/api/app.py tests/api/test_material_run.py
git commit -m "feat(quote): the frozen document names the materialization it froze"
```

---

### Task 8: The docs change with the code, or not at all

`docs/architecture/` and `docs/adr/` are truth here, and the architecture fitness tests
check the backend document against the real tables and routes — they caught real drift on
their first run when the part-library arc added a table and two routes without touching the
doc (`plan/open-work.md`, "Smaller, known, and cheap").

**Files:**
- Modify: the backend architecture document under `docs/architecture/` — find it with
  `grep -rln "generation_runs" docs/architecture/`
- Modify: `plan/open-work.md:84-95` (item 5)
- Modify: `plan/current-status.md` — add the checkpoint entry, newest first
- Create: `docs/adr/ADR-00NN-design-and-material-identity.md` — take the next free number
  from `ls docs/adr/` and follow the shape of the existing ADRs exactly

**Interfaces:** none — documentation.

- [ ] **Step 1: Find what the fitness tests check**

Run: `uv run pytest tests/architecture -q -v`
Expected: PASS today. Read the test file to learn exactly which document and which section
the table list and the route list are read from, so Step 2 edits the right place rather
than a plausible-looking one.

- [ ] **Step 2: Update the backend architecture document**

Add `material_runs` to the table list and `material` to what `GET /api/runs/{id}/bom`
returns. Add a sentence naming the split: a design run answers what fence this is; a
material run answers what it costs to build, from the stock we have, under this objective.

- [ ] **Step 3: Write the ADR**

Record: the two questions one id was answering; the decision to bump `RUN_DIGEST_VERSION`
to `digest-v3` and the one-time discontinuity it buys; `FULFILMENT_BEHAVIOR_VERSION` as the
missing half of `PLANNING_BEHAVIOR_VERSION`; and the consequence that the stored
`objective_preset` is frozen by `INSERT OR IGNORE`, which is why reads take the live preset
from the project. That last one is the non-obvious part and is the reason the ADR is worth
writing: the next person to read `GenerationRun.objective_preset` will otherwise use it.

- [ ] **Step 4: Run the fitness tests and the full suite**

Run: `uv run pytest tests/architecture -q && uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Update the plan documents**

In `plan/open-work.md`, replace item 5's "SPECIFIED, not built" heading and body with a
`~~struck~~` DONE entry in the shape items 1-4 use, naming the commits and — following the
established convention in that file — what was **knowingly not done**:

- the frontend does not yet SHOW the material id; the BOM tab renders the BOM and the
  `inventory_hash` as before. A reader holding two printouts can now distinguish them via
  the API, not yet on the page.
- MaterialRuns are never garbage-collected (spec §7.2, decided).
- the impact preview still compares designs, not materializations (spec §7.3, decided).
- `GenerationRun.objective_preset` is still populated and still stored; it is now only a
  record of what a run was generated under, and correction B is the reason nothing may read
  it for a decision.

In `plan/current-status.md`, add the checkpoint entry.

- [ ] **Step 6: Commit**

```bash
git add docs/ plan/
git commit -m "docs(identity): the split gets its ADR, and the handoff says what it left"
```

---

## Self-Review

**Spec coverage:**
- §3 "GenerationRun loses objective_preset" → Task 4. The spec proposed a
  `@field_validator(mode="before")` upgrader; none is needed, because the field is KEPT
  (pydantic reads old documents unchanged) rather than removed. Task 4 Step 5 documents it
  instead. **This is a deliberate divergence from the spec** and the reason is that the
  spec's upgrader solves a problem the chosen shape does not have.
- §3 "a new stored entity, MaterialRun" → Tasks 1 and 2.
- §3 `FULFILMENT_BEHAVIOR_VERSION` → Task 1.
- §3 "/bom stops being a pure read", idempotent by digest → Task 6.
- §4 "generate() stays pure" / "no BOM arithmetic moves" → Global Constraints, and the
  gate is re-run at Tasks 4, 6 and 7.
- §4 "a quote still refuses a stale catalog, and gains a better refusal" → Task 7 keeps
  the `_priced` staleness check and the `unresolved` refusal exactly where they are. The
  quote can now NAME its materialization; making the refusal MESSAGE cite it would need a
  new user-visible code in both locale bundles, so it is deliberately not done here.
- §5 decision (a) → Task 4.
- §7.2 no GC → not implemented, by decision; recorded in Task 8 Step 5.
- §7.3 impact preview untouched → Task 5 Step 4 states it and leaves `learning/impact.py`
  alone.

**Placeholder scan:** no TBDs. Every API route, store method and test fixture the plan
names was verified against the code while writing it: `Store.__init__` (`db.py:123`),
`audit_entries` (`db.py:759`), `load_project` (`db.py:162`), the inventory GET/PUT
(`app.py:1171`/`1177`), `_fence` (`tests/api/test_decision_comments.py:22`), and the
absence of any project-policy route (hence the store-level write in Task 5). One place
still says "read before writing" — the architecture document in Task 8 — because which
document and section the fitness tests read is a thing the tests themselves should be
allowed to say.

**Type consistency:** `material_id()` takes `(design_id, inventory_hash, catalog_hash,
objective_preset)` in Task 1 and is called with exactly those four, in that order, in Tasks
6 and 7. `inventory_hash` is a function in Task 1 and a field name on `MaterialRun` and
`Quote` — this shadowing is real and is why `get_bom` and `create_quote` bind the local as
`inv_hash`. `_priced(result, preset)` is defined in Task 5 and called with two arguments at
all four sites.

**Scope check:** one subsystem, one plan. The frontend is deliberately out of scope — no JS
reads `objective_preset` today (verified) and nothing in the BOM tab needs to change for
the API to stop lying.
