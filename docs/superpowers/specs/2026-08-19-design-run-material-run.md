# DesignRun and MaterialRun — design

Date: 2026-08-19. Status: **decided 2026-08-20, not yet implemented.** It changes
persisted identity, so it gets the brainstorm → spec → review → plan treatment the
part-spec design got, and it was written for a decision rather than for a commit.
The decisions it asked for are recorded in §5 and §7; the plan follows from them.

**RENAMED, 2026-08-20: `MaterialRun` is built as `SupplyRun`.** This spec's name
collides with an existing domain word. `material` is a catalog product attribute
from a closed vocabulary — `attrs={"material": "vinyl"}` (`catalog/demo.py:142`) —
which a part's spec declares as a CONSTRAINT rather than a fact
(`SpecField(key="material", value="vinyl", agree="==")`, `parts/demo.py:92`,
reading `item.material == "vinyl"`), and which the UI renders in a surface called
the material drawer (`fencemodel/preview.py:79`). Under that vocabulary
"MaterialRun" reads as a run about vinyl-versus-steel. The half this entity names
is the half below the demand boundary, and the codebase already calls that
**supply**: `resolve_supply()`, `ResolvedSupplyLine`, `SupplyDecision`,
`fulfillment/supply.py`. So: `SupplyRun`, `supply_id`, `supply_runs`,
`SUPPLY_BEHAVIOR_VERSION`. Everything else in this spec stands as written; see
`docs/superpowers/plans/2026-08-20-design-run-supply-run.md`.

Source: backend audit §1.5 (`docs/reviews/backend-audit-2026-08-16-response.md`),
whose disposition was "its own spec". `plan/open-work.md` item 5.

---

## 1. The defect, demonstrated rather than described

One `run_id`, two different BOMs, with the stored run byte-identical between
them. Reproduced on the demo:

```
run_81da35f5f2a9
  BOM before:  BAR-CAP 4 · BAR-POST-LINE 4 · BAR-RAIL-8FT 6 · BAR-SCREW-SS 1 · CONC-25 2   40 700
  ... put 3 × BAR-POST-LINE into the project's inventory ...
  BOM after:   BAR-CAP 4 · BAR-POST-LINE 1 · BAR-RAIL-8FT 6 · BAR-SCREW-SS 1 · CONC-25 2   27 200
```

Nothing about the fence changed. `GET /api/runs/{id}` returns the same document
both times. What changed is what it costs to build, because `/bom` reads LIVE
inventory (`api/app.py`: `_priced(result)` → `price_strategy(..., inventory)`).

The `inventory_hash` that would explain the difference is computed on every read
and written to the **audit log** — it enters no identity, no stored document and
no quote. So a reader holding two printouts of "run_81da35f5f2a9" has no way to
tell which inventory each was priced against, and the system cannot tell them
either.

**The second half of the same confusion.** `objective_preset` is inside the
DESIGN digest (`strategy/generator.py`), and it is read by nothing in
`generate()` — only by `resolve_supply`, the panel preview and the impact
preview. Changing the preset therefore produces a different `run_id` for an
identical fence, which is the mirror image of the first defect: design identity
moving for a supply reason, while supply identity does not move at all.

---

## 2. What a run IS, said once

Two questions are being answered by one id.

* **What fence is this?** Topology, knowledge, overrides, models, parts, policy,
  engine version. Pure, deterministic, reproducible for ever
  (ADR-0004). This is the DESIGN.
* **What does it cost to build, from the stock we have, under this objective?**
  Inventory, catalog prices, objective preset, cut plans, allocations,
  projected remnants. This is the MATERIALIZATION.

The first is a statement about the world the drawing describes. The second is a
statement about a moment — a yard, a price list, a preference — and it is
legitimately different tomorrow.

```
DesignRun     1 ──── n  MaterialRun
  design_id                material_id
  (today's run_id)         (design_id + inventory_hash + catalog_hash + preset
                            + fulfilment behaviour version)
```

A `Quote` already freezes a BOM and is the proof this second thing exists: it is
a MaterialRun that somebody decided to stand behind. Today it freezes the numbers
without being able to name what produced them.

---

## 3. What changes

**`GenerationRun` loses `objective_preset`** from its digest and keeps the field
for reading old documents (`@field_validator(mode="before")`, the established
upgrader shape). A design is what it is regardless of how it will be bought.

**A new stored entity, `MaterialRun`**, in its own append-only table beside
`generation_runs` — columns only for what is queried by (`id`, `design_id`,
`created_at`), everything else in `doc`, audited on write, per `store/db.py`'s
conventions:

```python
class MaterialRun(BaseModel):
    id: str                    # digest of the fields below
    design_id: str             # the GenerationRun it prices
    inventory_hash: str        # what was in the yard
    catalog_hash: str          # narrowed, as today
    objective_preset: str
    fulfilment_version: str    # the engine constant that does NOT exist yet
    created_at: str
    bom: Bom
    requirements: list[ResolvedSupplyLine]
    unresolved: list[DemandLine]
```

`FULFILMENT_BEHAVIOR_VERSION` is new and is the point of §1.6 applied to the
half that was left out: `PLANNING_BEHAVIOR_VERSION` covers generation, and
nothing covers cut planning, supply resolution or allocation. A change to the
FFD packer must produce a different material id or a stored quote silently means
something else.

**`/bom` stops being a pure read.** It becomes "materialize this design against
today's yard, and return the MaterialRun" — idempotent by digest: the same design
against the same inventory, catalog and preset returns the same `material_id`
and does not write twice. That is the same `INSERT OR IGNORE` shape the design
run already uses, with the same reason.

---

## 4. What must NOT change

* **`generate()` stays pure and deterministic.** Nothing here reaches it.
* **No BOM arithmetic moves.** This is an identity change, not a costing change:
  the compatibility gate must stay byte-identical, and if it moves, the change is
  wrong.
* **`Σ(parts) ≡ BOM` and the read models keep working**, because they take the
  BOM they are given; they now get it from a MaterialRun rather than from a
  recomputation.
* **A quote still refuses a stale catalog.** It gains a better refusal — it can
  now say *which* materialization it froze.

---

## 5. The migration, which is the expensive half

Every stored `GenerationRun` today has an `objective_preset` inside its digest.
Removing it changes the id of every future generation of the same fence — old
runs keep their ids and remain readable, but a regeneration of an unchanged
project now produces a NEW id where it used to return the old one. That is a
visible behaviour change and the reason this needs a decision rather than a
commit: it is the "same fence, new id" case, and every quote pointing at the old
id is still valid while nothing new will ever match it again.

Two honest options:

* **(a) Bump `RUN_DIGEST_VERSION` and accept one discontinuity.** Every project
  re-generates to a new id once, deliberately, and the reason is recorded. Simple,
  loud, and irreversible.
* **(b) Keep `objective_preset` in the design digest for ever** and accept that
  the design id carries a supply field, documenting it as legacy. Cheap, and it
  leaves the conflation this spec exists to remove.

**Recommendation: (a). DECIDED: (a), 2026-08-20.** The discontinuity is one-time
and legible; the conflation is permanent and keeps producing the confusion in §1.

**A correction to this section, made when the decision was taken.** The paragraph
above used to claim the bump "invalidates the 'regenerate and get the same id'
property that `test_regenerating_the_same_drawing_keeps_the_conversation` now
depends on". That is wrong, and it overstated the cost. That test
(`tests/api/test_decision_comments.py:139`) builds a project and generates twice
against ONE digest version, so it stays green across a bump; digest stability is a
property WITHIN a version, and the bump does not weaken it. What the bump actually
strands is narrower: comments anchored to already-PERSISTED run ids stop being
claimed when those projects next regenerate, once, at the boundary. Afterwards the
property is exactly as strong as it is today.

The payoff sits on the same axis, which is why (a) wins rather than merely costing
little. Today, switching `objective_preset` mints a new design id and strands the
thread EVERY time it is switched. After the change it mints a new `material_id`
and the design thread survives. (a) trades one bounded discontinuity for the
removal of a recurring one.

---

## 6. What this is NOT

* Not a pricing change, a currency change, or a quote-lifecycle change.
* Not persisted BOM snapshots for their own sake — `Quote` already does that for
  the commercial document. This is about being able to NAME the thing a quote
  froze.
* Not multi-warehouse inventory. `inventory_hash` names one yard's state; scoping
  inventory is a separate question the audit did not raise.

---

## 7. Open questions for the reader — answered 2026-08-20

1. **(a) or (b) in §5.** The one real decision. **→ (a): bump
   `RUN_DIGEST_VERSION`** (`digest-v2` → `digest-v3`), with the reasoning and the
   correction recorded in §5.
2. Should a MaterialRun be **garbage-collected**? A project priced daily
   accumulates one row per read. Suggested answer: keep those referenced by a
   quote for ever, and let the rest expire — but that is a retention policy, not
   a modelling question, and it should not hold this up. **→ No GC in this
   change.** The table is append-only and `INSERT OR IGNORE` by digest, so
   idempotency already collapses repeated identical reads and growth tracks real
   inventory/catalog/preset changes rather than read volume. Retention stays a
   separate question, to be answered when a real yard's row count motivates it.
3. Does the **impact preview** compare designs or materializations? It
   regenerates and diffs, so it is a design question today; with prices in it, a
   reader would reasonably expect the money to move too. **→ Designs only; leave
   the preview alone.** This change is an identity refactor and must not become a
   feature (§4). Diffing money is a legitimate follow-up, and it is strictly
   easier once MaterialRun exists to be the thing diffed — which is an argument
   for doing it after, not during.
