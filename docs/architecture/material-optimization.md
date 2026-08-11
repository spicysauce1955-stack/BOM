# Material requirements & fulfillment

Two stages, strictly separated (foundation §10): strategy → engineering demand;
demand + inventory + policies → fulfillment (allocation, cuts, packages, purchase BOM).
Decisions: ADR-0007. Research: optimization-fulfillment.md.

## Demand derivation (`demand` module)

Pure function `derive_requirements(strategy, catalog) -> [RequirementLine]`:
- posts → 1 × post sku each (+ cap facts if rule says so) — pegs to post ids;
- spans → `rail_count` rails cut to span slope-length (racked) or width (level/stepped)
  — pegs carry `cut_length_mm`; screws per connection from knowledge facts;
- soil posts → concrete coverage applications;
- gates → kit sku (exploded later).
Length basis (chord vs slope) is chosen per vertical mode and named in the line payload
(Research A pitfall 4).

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
Lexicographic tiers (policy presets): default `["fewest_new_stock", "prefer_remnant_use",
"fewest_cuts"]`. Implemented as deterministic tie-break order in V1 planners; a tier list is
part of `policy` and recorded in the GenerationRun.

## Invariants (tested)
- Σ(pieces + kerf) ≤ stock + kerf per bar; piece conservation (every demanded cut appears
  exactly once across bars).
- purchase_qty × package ≥ engineering demand for packaged SKUs.
- Every BOM line pegs to ≥1 requirement; every requirement to ≥1 element.
- Remnant below threshold never re-enters inventory as reusable.
- Same demand + inventory + policy ⇒ byte-identical plan.
