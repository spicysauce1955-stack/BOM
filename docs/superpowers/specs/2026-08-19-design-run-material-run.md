# DesignRun and MaterialRun — design

Date: 2026-08-19. Status: **proposed, not implemented.** It changes persisted
identity, so it gets the brainstorm → spec → review → plan treatment the
part-spec design got, and it is written for a decision rather than for a commit.

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

**Recommendation: (a).** The discontinuity is one-time and legible; the
conflation is permanent and keeps producing the confusion in §1. But it is the
user's call, because it invalidates the "regenerate and get the same id" property
that `test_regenerating_the_same_drawing_keeps_the_conversation` now depends on —
comments anchored to a design run would be stranded by the bump exactly as they
are by an edited drawing.

---

## 6. What this is NOT

* Not a pricing change, a currency change, or a quote-lifecycle change.
* Not persisted BOM snapshots for their own sake — `Quote` already does that for
  the commercial document. This is about being able to NAME the thing a quote
  froze.
* Not multi-warehouse inventory. `inventory_hash` names one yard's state; scoping
  inventory is a separate question the audit did not raise.

---

## 7. Open questions for the reader

1. **(a) or (b) in §5.** The one real decision.
2. Should a MaterialRun be **garbage-collected**? A project priced daily
   accumulates one row per read. Suggested answer: keep those referenced by a
   quote for ever, and let the rest expire — but that is a retention policy, not
   a modelling question, and it should not hold this up.
3. Does the **impact preview** compare designs or materializations? It
   regenerates and diffs, so it is a design question today; with prices in it, a
   reader would reasonably expect the money to move too.
