# Material requirements & fulfillment

Plane: **Engine** — see [00-overview.md](00-overview.md#three-planes).

Demand and supply, strictly separated (foundation §10): strategy → engineering demand;
demand + catalog + inventory + objective → a chosen product per line → fulfillment
(allocation, cuts, packages, purchase BOM).
Decisions: ADR-0007, ADR-0011. Research: optimization-fulfillment.md.

## The pipeline

`fulfillment/pipeline.py: price_strategy(strategy, catalog, inventory, demand_skus,
preset)` runs a declared list of three phases (`fulfillment/phases.py: PIPELINE`) and
returns a `PricedRun{requirements, unresolved, warnings, decisions, bom}`:

| Phase | Function | Reads → writes |
|---|---|---|
| `derive_demand` | `demand/derive.py: derive_requirements` | strategy, catalog, demand_skus → `demand` |
| `resolve_supply` | `fulfillment/supply.py: resolve_supply` | demand, catalog, inventory, preset → `requirements`, `unresolved`, `warnings`, `decisions` |
| `fulfil` | `fulfillment/fulfill.py: fulfill` | requirements, catalog, inventory, warnings → `bom` (which carries the supply warnings) |

Each `Phase(name, fn, reads, writes)` works on one shared `PipelineState`, and
`check_order` runs at import: a phase that reads a field no earlier phase writes is
refused, so a step inserted in the wrong place fails a test instead of quietly pricing
an empty list. It is not a workflow engine and has no registry — `PIPELINE` is one
declared tuple a reader can see whole. Every priced read (`/bom`, `/structure`,
`/quote`, `/explain`, section decisions, readiness and flags), the panel preview and
the impact preview run this one function; four hand-copied versions of it had
already diverged once.

Pure over an inventory snapshot; soft allocation only (reservation deferred).

## Demand derivation (`demand` module)

Pure function `derive_requirements(strategy, catalog, policy=None) -> list[DemandLine]`;
the pipeline passes the run's `demand_skus` as `policy`, merged over
`DEMAND_POLICY_DEFAULTS`.

A `DemandLine` is what the fence NEEDS: `id` (`req0001`, … — positional),
`engineering_qty`, `cut_length_mm`, `length_basis`, `pegs` (strategy element ids),
`role`, `slot_key` and `eligibility`. It carries **no sku and no unit**. A product
generation already chose arrives as a one-member eligibility, so every line takes the
one path through supply.

- posts → for every post, a `post` line, a `cap` line (the model's `cap_sku`, else the
  company default) and, iff `mounting == "ground"`, one `concrete` application — each
  pegged to the post;
- spans → one line per **resolved panel slot** (`Span.panel`, from the fence model), each
  carrying `slot_key` and the slot's `eligibility` — pegs carry `cut_length_mm`. Behind
  `M-LEGACY` that is exactly the old two rails and eight screws. A span with no panel is a
  run stored before fence models existed and is refused (`run_predates_fence_model`), never
  silently back-filled from the legacy `rail_count`/`screws_count`. A `contained` slot
  produces no line (its container's line already bought it), nor does a slot with
  `qty ≤ 0`;
- **members the run derived continuous → ONE line per `Strategy.member_run`**, pegged to
  every bay it crosses, with the group's cut length and the slot's own `qty` — NOT the
  slot's qty times the bays. The per-bay lines for those bays are suppressed, or the same
  rail would be ordered twice. Demand does not decide continuity and does not re-derive it
  (see below);
- gates → one `gate_kit` line iff the strategy chose a kit; a kit is bought whole
  ([below](#fulfillment-fulfillment-module)).

Length basis is `width | slope` — `slope` iff the bay is raked — chosen per bay during
generation and carried on the line (Research A pitfall 4).

**No demand line names a sku or a unit.** `resolve_supply` turns a line into a
`ResolvedSupplyLine(DemandLine)` through `ResolvedSupplyLine.of(line, sku, unit)`, which
adds both as required, non-empty fields in one statement; the unit comes from
`fulfill.engineering_unit_for`, the same function that stamps `BomLine.engineering_unit`.
The parts ledger balances asked-vs-purchased per `(sku, unit)` and reads the purchased
side from `BomLine.engineering_unit`, so a unit demand guessed for itself can disagree
with what `fulfill()` did and report one demand as unassigned *and* from stock at once.
`fulfill()` accepts only the resolved type, so a blank sku cannot reach it.

### Continuity (`strategy/continuity.py`, boundary contract obligation 14)

Whether a member runs continuously through an intermediate post is **derived** from the
product's manufactured `stock_length` against the RESOLVED bay spacing — never authored.
It is derived during generation, once per run, after the run is laid out, because:

- it needs the spacing, so it cannot be a property of the part;
- a second derivation downstream could disagree with the first, and then the drawing and
  the cut list disagree about whether a rail is one piece or three. Foundation §15 —
  a read model never recomputes a quantity — makes that a defect, not a nuisance.

The answer is recorded as `Strategy.member_runs`. Demand reads it, `plan_cuts` sees the
group's length as one piece, and the structure sheet inverts the line's pegs the way it
inverts every other line's — carrying `shared_with` so a piece listed under each bay it
crosses does not read as one piece per bay.

Inputs, in the order they are asked:

1. **The capability.** `FrameSlot.post_joint` — `unstated | lands | through`. Only
   `through` puts a member on the table, and it is not the answer: the same `through` rail
   is two bays per piece in 16 ft stock and one in 12 ft. It is its own field rather than a
   `JointKind`, because `joint` names the housing a frame member gives the INFILL and is
   validated and drawn against `channel_depth_mm`. `unstated` is the default and resolves
   to per bay — what every fence authored before this was priced to — without claiming the
   model said `lands`.
2. **What ends a chain**, whatever the stock length is: a post that is not a `line` post
   (a corner, a gate, a junction, a transition — or no post at all), a bay that climbs or
   steps at the post, a different panel, a different candidate set, a different rail count.
3. **The stock length**, taken as the SHORTEST every candidate product can be bought in;
   the longest is recorded beside it on the decision node, so a reader can see that a
   longer bar was on the table and that adding a short one to the catalog is what would
   shorten every piece on the next run.
   Which product fills the slot is `resolve_supply`'s answer, so a slot with several
   candidates has not decided its own stock length; the shortest claims continuity only
   where every candidate could make the piece, and `plan_cuts` refuses a piece longer than
   its stock.
4. **The join**, per length rule (`CONTINUITY_JOINS` in `fencemodel/lengths.py`): how the
   per-bay lengths a bay already resolved combine into one piece. A rule with no registered
   join is not continuable.

`FrameSlot.continuity` / `Member.continuity` is the authored override the contract keeps
for a guide that states the behaviour outright and gives no length. It wins, and a
disagreement with the derived answer is reported (`warning.continuity_override_disagrees`)
rather than settled in silence. The one thing it cannot win against is the length of a bar
(`warning.continuity_override_unbuildable`). The stock length is **unknown** when any
candidate states none or is missing from the catalog: the derivation then abstains (the
member is cut per bay), an authored `continuous` runs the whole chain, and — unless the
author said `per_bay` — `warning.continuity_stock_length_unknown` says that nothing bounded
it. The chain is a real limit (a corner, a gate, a grade ends it) but not one anybody
chose, and `plan_cuts`' length guard only covers divisible stock.

## Fulfillment (`fulfillment` module)

There is no explode stage and no substitute stage. Netting, cutting, packaging and
pricing all happen inside `fulfill()`, one branch per consumption kind, over the
resolved lines grouped by sku:

| `Consumption.kind` | Engineering unit | Netted against | Bought as |
|---|---|---|---|
| `divisible_linear` | `cut` | the yard's `remnant` items, as bins opened before the cut plan starts; full bars in stock are not netted | new bars from the cut plan |
| `packaged_discrete` | its own `engineering_unit` | `opened_package` items | whole packages |
| `coverage_based` | its own `engineering_unit` | nothing | `ceil(applications × num / den)` purchase units |
| `indivisible_discrete`, `assembly_kit` | `each` | `full_stock` items, in id order | whole units |

**An assembly kit is bought whole**, with a note listing what it includes. Nothing
explodes it into components, and crediting a kit against a panel's own demand was
deliberately kept out of the pipeline: a phase after supply could only credit by reading
the chosen product's components, which credits parts nobody asked that panel to place.
Containment is authored instead (`Part.contains`) and resolved upstream, where the
panel's members are settled (`phases.py`; engine-architecture spec §7).

`Catalog.substitutions` / `SubstitutionRule` exist and nothing reads them. The approval
gate that does exist sits on the fence model's eligibility: a member marked
`approval = "suggest_only"` is usable only when its sku is in `resolve_supply`'s
`approvals`, and `price_strategy` never passes any. So on every read path a line whose
only eligible members are suggest-only is `unresolved`, with `substitute_needs_approval`.

A sku the catalog does not have is billed as a zero-priced `UNKNOWN: <sku>` line, counted
in eaches and flagged — never a KeyError, never a silent drop. It reaches `fulfill()`
only as a group's sole candidate ([below](#objectives)).

### Cut planner (per linear SKU)
`plan_cuts(sku, semantics, pieces, remnants)`, a plain function. Kerf-aware capacity:
piece cost `len + kerf`, bar capacity `stock_len + kerf`. Pieces are taken in FFD order
(length desc, requirement id); each goes to the open bin it leaves the smallest residual
in — the yard's remnants are bins opened before the first piece, and win ties — and a new
bar opens only when no open bin fits. A piece longer than its stock raises, and
`resolve_supply` keeps one from ever arriving.
Leftover ≥ `min_reusable_remnant_mm` ⇒ recorded reusable, listed on
`Bom.projected_remnants` and shown on the BOM tab; below ⇒ waste. **`projected_remnants` is
a projection attached to this BOM/quote — it is deliberately not written back into the
project's stored inventory** (that would mutate a user-owned record from a pure function,
and inventory has no warehouse scope to carry offcuts between projects yet).

Two lower bounds on new bars are computed and the **stronger one certifies the plan**:
- the LP relaxation `ceil((Σ(len+kerf) − used remnant capacity) / (stock+kerf))`, where
  the used remnant capacity is the cost of the pieces the plan placed on remnants —
  reported as `lp_lower_bound`, unattainable whenever pieces do not tile the stock;
- a counting bound: for the *m* longest pieces, no bin holds more of them than fit when
  filled with the smallest of those *m* (each remnant credited its own such count), so
  `ceil((m − credited) / per_new_bar)` new bars are unavoidable; valid for every *m*.

`lower_bound = max(...)`, and `certified_optimal = new_bar_count ≤ lower_bound`. Certifying
against the relaxation alone labelled provably optimal plans "heuristic" (4×1500 from
3000 mm stock: relaxation 3, truth 4) — persona-lab readers took that as an admission the
tool pads orders. Deterministic ordering (length desc, requirement id).
There is no planner Protocol: `fulfill()` and supply's cost and waste tiers call
`plan_cuts` directly, so a CP-SAT implementation (triggers in ADR-0007) would first have
to introduce that seam.

### Packages
`net = max(0, demand − Σ opened_package.qty)`, `purchase_qty = ceil(net / qty_per_package)`,
and the overage `packages × qty_per_package − net` is recorded on the line. Opened packages
are always used first — `PackagedDiscrete` has only `engineering_unit` and
`qty_per_package`, so there is no reuse policy to honour. Each opened package's
`Allocation` is `min(its qty, demand)` and is not decremented across packages, so two
opened packages can together allocate more than the demand. **Gap (not implemented):**
package overage is *not* added to `projected_remnants` — only cut leftovers are. Either
`fulfill()` starts emitting an `opened_package` projection for the overage, or this
sentence stays a known gap; it must not read as shipped behaviour.

### Span layout (lives in `strategy`, documented here with its math)
Per free segment between fixed posts (nodes, corners, gate posts, pinned posts, base
transitions when rules demand a boundary): `n = ceil(L / max_span)`, widths `L//n` with
`L mod n` distributed one mm to the first spans (fixed rule). Preferences do not adjust
`n`; they choose between two layouts. `layout_segment` computes the equal layout and the
nominal one (`prefer_span_width`'s width, clamped to the maximum); `prefer_equal_spans`
— the default — takes the first, `prefer_span_width` the second, a tie between them is
resolved like any other, and the loser is recorded as the rejected alternative on the
`layout_spans` node, which cites the winning preference. A manufactured width
(`exact_mm`, from the model) wins outright. Nothing merges or steals from a neighbour: a
bay under `prefer_min_span_width` stands, because merging would break the maximum, and
the caller reports a `sliver_span` conflict citing the preference
(`test_sliver_span_warning_cites_preference`).

**The count divides by the PUBLISHED limit; the widths stay integer millimetres.**
`contract.md:112-117` is binding that arithmetic multiplying a published value consumes its
thousandths, and `n = ceil(L / max_span)` is the clause's own worked example — so
`equal_layout_milli` divides by `max_span_milli` (`SetParam.value_milli`, defaulting to
`max_span * 1000` for any authored rule). `n` is a count, so "rounds only its output" is
satisfied by integer ceiling division; the widths it splits are lengths at rest and stay in
whole millimetres (ADR-0002).

That leaves a residue, and the residue is REPORTED rather than absorbed. Where the
published limit falls between whole millimetres — five of the six real span magnitudes do,
`56"` being 1422.4 mm — the remainder spread can put one bay a fraction over it: a 4267 mm
run is three bays of 1422.333 mm, stored as `[1423, 1422, 1422]`, one of them 0.6 mm over.
The alternative is a fourth post, footing and pour, which is the harm the clause exists to
prevent, so the three-bay layout stands (`_SegmentModel.admits()` is the bound — the
remainder ceiling `ceil(limit)` AND the minimum bay count, both required: exactly
`max_span` for a whole-millimetre limit, so nothing authored can reach this). The segment
then carries `warning.span_rounded_over_published_limit` at `info` severity and a
`conflict` node with action `span_rounded_over_published_limit`, scoped to the bays
carrying the fraction, `input_from` the `layout_spans` node and `governed_by` the limit
that chose the count — never `defeated` by it, because the rule was honoured, not beaten.
The sentence shows the limit at published precision (a `*_milli` param, the one length the
display layer does not round to the millimetre grid): printing `1422` would report our
unit's problem as the customer's. Worst case over the first hundred metres is 0.8 mm, on
roughly one run length in a hundred; anything `admits()` refuses — wider than the ceiling,
or the right width with too few bays — is a layout bug, a wrong rule or a stale stored
answer, and still fails the run.

## Objectives
Lexicographic tiers with **named presets** (ADR-0007) — never a raw tier list and never
user-facing weights. Two presets exist, because a company with an own-brand policy and a
company chasing margin want opposite answers.

Before any preset runs, two filters decide who may compete. They are not a tier of the
preset, and no preset can reorder them:

1. **approval** (`_usable`): a member is usable if its `approval` is `auto` or its sku is
   in `approvals` (none are passed today, above);
2. **feasibility** (`_can_supply`): the sku is in the catalog and no piece is longer than
   its stock.

A preset is then a sort key over `RankInputs{sku, priority, cost_cents, waste_mm}`,
lowest wins, registered in `fulfillment/presets.py: PRESETS` — an open registry, so a new
preset is a registration rather than an edit to a type and a branch:

| Rank | `least_cost` (default) | `honour_priority` |
|---|---|---|
| 1 | purchase cost | member priority |
| 2 | waste | purchase cost |
| 3 | member priority | waste |
| 4 | sku (deterministic) | sku (deterministic) |

Cost is the planned new bars × bar price for linear stock (cuts planned against the
yard's remnants), price × quantity otherwise; waste is the cut plan's waste without
remnants, and 0 for anything not linear.

Feasibility is resolved *before* ranking **and before the number of candidates is looked
at**: a candidate whose piece is longer than its stock loses under every preset rather
than winning on priority, and a group with exactly one member is no exception. It used to
be — with one candidate there is no choice to make, so the gate was skipped — and the line
then reached `plan_cuts`, which raises, which is how a saved run became permanently
unreadable behind a raw English 400 on `/bom`, `/structure` and `/quote` at once. There is
no choice at group size one, but there is still a question.

A sku missing from the catalog loses the same way **whenever it has rivals** — a product
that does not exist cannot be priced, and a candidate costing nothing would beat every one
that does. A group whose only candidate is an unknown sku is the exception: there is no
rival to protect, so the line resolves to it and `fulfill()` bills the flagged `UNKNOWN:`
line. That is how a post pointing at a deleted product still shows on the BOM instead of
vanishing into a warnings panel.

When **no** candidate can be used there is no answer — the line is routed to `unresolved`
and reported, never silently picked. Three codes, because they send the reader to
different places to go fix it:

| Code | Severity | Means | Go look at |
|---|---|---|---|
| `no_eligible_item` | error | the eligibility set is empty — or names no product at all, as for a post standing with `sku = ""` because knowledge named no default | the fence model, or the knowledge default |
| `no_feasible_item` | error | candidates were tried and not one fits | the catalog's stock lengths |
| `substitute_needs_approval` | warning | every eligible member is `suggest_only` and none was approved | the model's eligibility — no approval path exists yet |

All three carry the requirement's pegs, in `params` (for the sentence) and `element_refs`
(for the reader that can map an element id to a bay tag). `role` + `slot_key` alone name a
KIND of part, so a 60-bay fence emitted sixty identical warnings naming no bay between
them.

Feasibility is a catalog + geometry predicate — `sku in catalog` and `piece <= stock`, the
same comparison `plan_cuts` makes before it raises — and NOT a cut plan. That is what makes
it affordable at group size one; cuts are planned only when two or more feasible candidates
have to be ranked against each other.

There is no separate path for a product generation already chose — a post, a cap, the
concrete, a gate kit. It arrives as a one-member eligibility and takes the same grouping,
the same filters and the same `_choose`, so "`fulfill()` never sees a piece longer than its
stock" is a property of the one path into `fulfill()`. Lines are grouped by eligibility
signature — the `(sku, priority, approval)` of their usable members — so one demand is
answered by one product; a `SupplyDecision` is recorded per group whenever more than one
candidate was considered, and the output is re-sorted into demand order.

**The preset is a supply input, not part of the design.** It is resolved at generation
from the project policy and recorded on `GenerationRun.objective_preset`, but it left the
run-id digest in `digest-v3` (ADR-0011): a design is what it is regardless of how it will
be bought, and switching the preset used to mint a new run id every time. Because an
unchanged fence regenerates to the same id and the first stored document is kept, the
run's recorded preset is frozen at its first generation — so every read route, and the
panel preview, passes `_live_preset(project_id)`, the project's policy NOW, never the
run's value. The preset actually used is recorded on the `SupplyRun` and is part of its
id. It is stored as a plain string and validated against `PRESETS` inside
`resolve_supply`, so an unrecognised value is a loud `ValueError` (a 400 on the read
routes), not a quiet reinterpretation as the default.

*(Earlier drafts of this document named a default of `["fewest_new_stock",
"prefer_remnant_use", "fewest_cuts"]`. Those are not preset names and `resolve_supply` now
raises on them; the tiers they described are folded into `least_cost`'s cost and waste
tiers, which are computed by planning the cuts rather than counted nominally.)*

## SupplyRun — what a design costs from one yard

A `GenerationRun` is the design; a `SupplyRun` (`fulfillment/supply_run.py`, ADR-0011) is
that design priced against one inventory, one catalog and one objective — the persisted,
named form of a `PricedRun`.

* **Identity:** `"sup_" + sha256(json([design_id, inventory_hash, catalog_hash,
  objective_preset, SUPPLY_BEHAVIOR_VERSION]))[:12]`, with `inventory_hash` the first 16
  hex characters of a sha256 over the inventory's JSON and `catalog_hash` the run's own
  stamp (the read path has already refused a catalog that moved). Bump
  `SUPPLY_BEHAVIOR_VERSION` when what a strategy costs changes for unchanged inputs.
* **Storage:** `supply_runs(id, design_id, created_at, doc)`, written `ON CONFLICT DO
  NOTHING`. `save_supply_run` returns the STORED row, so a repeat read reports the first
  `created_at` rather than its own, and two reads of an unchanged fence are identical.
* **Written by** `GET /api/runs/{id}/bom`, `GET /api/runs/{id}/structure` and
  `POST /api/runs/{id}/quote` — every read that shows money or cut pieces names the supply
  run it was priced as, so one run id can no longer print two BOMs with nothing to tell
  them apart. It holds `requirements`, `unresolved` and the `bom` (whose `warnings` are the
  supply warnings). The supply decisions are not stored; they are re-derived into the
  graph at read time ([`decision-model.md`](decision-model.md#supply-decisions-are-added-at-read-time)).

## Quote — a supply run somebody stands behind

`fulfillment/quote.py: Quote` is an immutable snapshot of `requirements` + `bom` and
`total_cents`, stamped with `inventory_hash`, `knowledge_snapshot_hash` (the run's
`snapshot_hash`), `catalog_hash` and `supply_id`. Only its `status` ever changes:
`draft → accepted → superseded`.

* `POST /api/runs/{id}/quote` refuses 409 `site_conditions_changed` — the quote is the one
  money view that refuses a moved site, because it is the one that freezes a commercial
  document; `/bom` and `/structure` are working views — and 400 `unresolved_supply`,
  listing every line that could not be supplied, because a quote must not under-price the
  job. It takes the catalog guards below too, and saves the supply run it froze.
* `POST /api/quotes/{id}/accept` accepts a draft and, in one transaction, supersedes the
  project's previously accepted quote; any other transition is a 400.
* **Accepting a quote changes no job state.** `Project.status` does not move to `quoted` —
  that edge is declared and unreachable; the job lifecycle belongs to
  [`people-and-work.md`](people-and-work.md).

## Read-path guards

Every priced read goes through `api/app.py: _priced`, which guards before it computes:

* `_fresh_catalog` — 409 `catalog_schema_changed` when the run was stamped under another
  `CATALOG_SCHEMA_VERSION`, and 409 `catalog_changed` when today's catalog, hashed over the
  skus the run named, differs from the run's `catalog_hash`. A stored run is never
  silently re-supplied against a different catalog.
* `ReadRefused` from demand — 400 with `code + params`: `run_predates_fence_model` (a span
  with no panel) and `member_run_unreadable` (a member run naming a bay or slot the
  strategy does not have). Both say: regenerate.
* An unknown preset — a `ValueError`, a plain 400.

`/explain` and section decisions swallow these refusals and render the graph without supply
nodes. `/structure` and section decisions also refuse a moved drawing or site (409
`topology_changed`, `site_conditions_changed`); `/quote` refuses a moved site; `/bom`
refuses neither — it describes the run, not the drawing.

## Invariants (tested)
- Per bar, `Σ len + kerf × (pieces − 1) ≤ stock` — equivalently `Σ(len + kerf) ≤ stock +
  kerf`; piece conservation (every demanded cut appears exactly once across bars); a
  reusable leftover is at least `min_reusable_remnant_mm`.
- Packaged SKUs: `purchase_qty × qty_per_package + allocated ≥ engineering_qty`. Coverage
  SKUs: `purchase_qty × den ≥ applications × num`.
- Every requirement pegs ≥1 strategy element, each with ≥1 decision node; BOM lines and
  allocations together peg exactly the set of requirement ids.
- Every projected remnant meets its threshold — below it never re-enters inventory as
  reusable.
- Regenerating from the same inputs yields an identical strategy, graph, run id,
  requirements and BOM.
- `fulfill()` never receives a requirement whose piece exceeds its product's stock, at any
  group size and by any path — `resolve_supply` routes it to `unresolved` first
  (`tests/fulfillment/test_supply.py`).
