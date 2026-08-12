# Material requirements & fulfillment

Two stages, strictly separated (foundation §10): strategy → engineering demand;
demand + inventory + policies → fulfillment (allocation, cuts, packages, purchase BOM).
Decisions: ADR-0007. Research: optimization-fulfillment.md.

## Demand derivation (`demand` module)

Pure function `derive_requirements(strategy, catalog, demand_skus) -> [RequirementLine]`:
- posts → 1 × post sku each (+ cap facts if rule says so) — pegs to post ids;
- spans → one line per **resolved panel slot** (`Span.panel`, from the fence model), each
  carrying `slot_key` and the slot's `eligibility` — pegs carry `cut_length_mm`. Behind
  `M-LEGACY` that is exactly the old two rails and eight screws. A span with no panel is a
  run stored before fence models existed and is refused (`run_predates_fence_model`), never
  silently back-filled from the legacy `rail_count`/`screws_count`;
- soil posts → concrete coverage applications;
- gates → kit sku (exploded later).
Length basis (chord vs slope) is chosen per vertical mode and named in the line payload
(Research A pitfall 4).

A span line names **no sku and no unit**. Both are written by `resolve_supply` from the
eligibility set and the chosen product's `Consumption`, in one statement — the parts ledger
balances asked-vs-purchased per `(sku, unit)` and reads the purchased side from
`BomLine.engineering_unit`, so a unit demand guessed for itself can disagree with what
`fulfill()` did and report one demand as unassigned *and* from stock at once.

## Fulfillment pipeline (`fulfillment` module)

```
explode assemblies → substitute (policy-gated) → net against inventory
  → cut-plan divisible linear SKUs → round packages → price → BOM + allocations
```
Pure over an inventory snapshot; soft allocation only (reservation deferred).

### Cut planner (per linear SKU)
FFD with kerf-aware capacity: piece cost `len + kerf`, bar capacity `stock_len + kerf`.
Remnant-first best-fit (smallest remnant that fits; remnants never increase bar count).
Leftover ≥ `min_reusable_remnant_mm` ⇒ recorded reusable, listed on
`Bom.projected_remnants` and shown on the BOM tab; below ⇒ waste. **`projected_remnants` is
a projection attached to this BOM/quote — it is deliberately not written back into the
project's stored inventory** (that would mutate a user-owned record from a pure function,
and inventory has no warehouse scope to carry offcuts between projects yet).

Two lower bounds on new bars are computed and the **stronger one certifies the plan**:
- the LP relaxation `ceil(Σ(len+kerf) / (stock+kerf))` — reported as `lp_lower_bound`,
  unattainable whenever pieces do not tile the stock;
- a counting bound: for the *m* longest pieces, no bin holds more of them than fit when
  filled with the smallest of those *m* (each remnant credited its own such count), so
  `ceil((m − credited) / per_new_bar)` new bars are unavoidable; valid for every *m*.

`lower_bound = max(...)`, and `certified_optimal = new_bar_count ≤ lower_bound`. Certifying
against the relaxation alone labelled provably optimal plans "heuristic" (4×1500 from
3000 mm stock: relaxation 3, truth 4) — persona-lab readers took that as an admission the
tool pads orders. Deterministic ordering (length desc, requirement id).
`CutPlanner` is a Protocol — CP-SAT implementation is a later optional extra (triggers in
ADR-0007).

### Packages
`purchase_qty = ceil(engineering_qty / qty_per_package)`; overage recorded on the line.
Opened-package reuse honors catalog policy. **Gap (not implemented):** package overage is
*not* added to `projected_remnants` — only cut leftovers are. Either `fulfill()` starts
emitting an `opened_package` projection for the overage, or this sentence stays a known
gap; it must not read as shipped behaviour.

### Span layout (lives in `strategy`, documented here with its math)
Per free segment between fixed posts (nodes, corners, gate posts, pinned posts, base
transitions when rules demand a boundary): `n = ceil(L / max_span)`, widths `L//n` with
`L mod n` distributed one mm to the first spans (fixed rule). Preferences may adjust n
(e.g. sliver avoidance merges/steals from neighbors) — every adjustment is a decision node
citing the preference.

## Objectives
Lexicographic tiers with **named presets** (ADR-0007) — never a raw tier list and never
user-facing weights. Two presets exist, because a company with an own-brand policy and a
company chasing margin want opposite answers:

| Tier | `least_cost` (default) | `honour_priority` |
|---|---|---|
| 1 | eligibility + approval policy (hard) | eligibility + approval policy (hard) |
| 2 | purchase cost | member priority |
| 3 | waste | purchase cost |
| 4 | member priority | waste |
| 5 | deterministic sku order | deterministic sku order |

Feasibility is resolved *before* tier 2 and filters the field: a candidate whose piece is
longer than its stock, or whose sku is not in the catalog, loses under every preset rather
than winning on priority. When **no** candidate is feasible there is no answer — the line is
reported as `no_eligible_item` and routed to `unresolved`, never silently picked.

The preset name is resolved at generation, recorded on `GenerationRun.objective_preset`,
included in the run-id digest, and passed to `resolve_supply()` explicitly. It is stored as
a plain string, so an unrecognised value is a loud `ValueError` at that one boundary, not a
quiet reinterpretation as the default.

*(Earlier drafts of this document named a default of `["fewest_new_stock",
"prefer_remnant_use", "fewest_cuts"]`. Those are not preset names and `resolve_supply` now
raises on them; the tiers they described are folded into `least_cost`'s cost and waste
tiers, which are computed by planning the cuts rather than counted nominally.)*

## Invariants (tested)
- Σ(pieces + kerf) ≤ stock + kerf per bar; piece conservation (every demanded cut appears
  exactly once across bars).
- purchase_qty × package ≥ engineering demand for packaged SKUs.
- Every BOM line pegs to ≥1 requirement; every requirement to ≥1 element.
- Remnant below threshold never re-enters inventory as reusable.
- Same demand + inventory + policy ⇒ byte-identical plan.
