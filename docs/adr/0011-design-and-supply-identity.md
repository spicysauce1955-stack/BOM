# ADR-0011: A run id names the DESIGN; a supply run names what it costs

Status: accepted · 2026-08-20

## Decision

One id was answering two questions. It now answers one.

* **`GenerationRun` (the design).** Topology, knowledge, overrides, models, parts,
  design policy, engine version. Pure, deterministic, reproducible for ever (ADR-0004).
* **`SupplyRun` (what it costs to build).** One design priced against one yard, at one
  set of catalog prices, under one objective preset. A statement about a moment, and
  legitimately different tomorrow.

`objective_preset` leaves the design digest and `RUN_DIGEST_VERSION` goes to `digest-v3`.
`SUPPLY_BEHAVIOR_VERSION` is introduced in `fulfillment/supply_run.py`. `/bom` stops being
a pure read and returns the `SupplyRun` it stored, idempotent by digest. `Quote` gains
`supply_id`.

Relations: one design has many supply runs; a `Quote` is a supply run somebody decided to
stand behind. A `SupplyRun` is the persisted, identified form of the in-memory `PricedRun`
that `fulfillment/pipeline.py` already returned.

## Rationale

The defect was demonstrable, not theoretical. `run_81da35f5f2a9` printed a BOM of 40 700
agorot, then 27 200 after three posts arrived in the yard, with `GET /api/runs/{id}`
**byte-identical** between the two. `/bom` read live inventory; the `inventory_hash` that
would have explained the difference was computed on every read and written only to the
audit log, entering no identity, no stored document and no quote. Two printouts could not
be told apart — by a reader or by the system. `Quote` already froze the numbers without
being able to name what produced them.

`objective_preset` was the mirror image: it sat in the DESIGN digest and was read by
nothing in `generate()` — only by `resolve_supply`, the panel preview and the impact
preview. So the design id moved for a supply reason while supply identity did not move at
all.

The boundary is not arbitrary. `derive_requirements(strategy, catalog)` is pure; a
`DemandLine` says what the fence NEEDS and deliberately carries no sku and no unit.
`resolve_supply(requirements, catalog, inventory, preset)` is the first stage that takes
the yard and the objective, and `ResolvedSupplyLine(DemandLine)` adds exactly those two
fields. That signature is where reproducibility ends, so that is where the second identity
begins.

`SUPPLY_BEHAVIOR_VERSION` is the half `PLANNING_BEHAVIOR_VERSION` left out: nothing
versioned cut planning, supply resolution or allocation, so a change to the FFD packer
would have made a stored quote silently mean something else.

## Consequences

**One deliberate discontinuity, taken knowingly.** The digest bump means a regeneration of
an unchanged project mints a new id once. Stored runs keep their ids and stay readable.
Digest stability is a property WITHIN a version and is not weakened; what the bump strands
is comments anchored to already-persisted run ids, once, at the boundary. Against that,
switching the preset used to strand a thread EVERY time it was switched — the bump trades
one bounded discontinuity for the removal of a recurring one.

**`GenerationRun.objective_preset` is now reported, never read for a decision.** This is
the non-obvious part and the main reason this ADR exists. `save_run` is `INSERT OR IGNORE`,
and the preset is no longer a digest input — so an unchanged fence regenerates to the same
id and the stored document is the FIRST one for ever. Its `objective_preset` is frozen at
first generation. Anything reading it for a decision would price under an objective the
user had already changed, silently. Read paths take the live preset from the project's
policy (`api/app.py::_live_preset`). A poisoned preset on a stored run is now inert, where
it used to 400 every read of that run with no user action able to repair it.

**`/bom` writes.** Safe because the id is the content: the same design against the same
inventory, catalog and preset digests to the same `supply_id`, and `INSERT OR IGNORE` does
not write twice. Growth tracks real changes to the yard, not read volume. `save_supply_run`
returns the STORED row rather than the caller's object, because `created_at` is the one
field two otherwise-identical supply runs can differ by, and echoing the argument made two
reads of an unchanged fence differ by a timestamp the database did not have.

**Not decided here**, and deliberately: no retention policy for supply runs (append-only,
idempotency already collapses repeated reads); the impact preview still compares designs
rather than supply runs; no BOM arithmetic moved — the compatibility gate is byte-identical
across the whole change, which is the evidence that this was an identity change and not a
costing one.

Spec: `docs/superpowers/specs/2026-08-19-design-run-material-run.md` (which names the
entity `MaterialRun`; `material` was already a catalog product attribute — vinyl, steel,
cedar — that a part's spec declares as a CONSTRAINT on an item, so the entity is built as
`SupplyRun`). Plan: `docs/superpowers/plans/2026-08-20-design-run-supply-run.md`.
