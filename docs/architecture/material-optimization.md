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
- **members the run derived continuous → ONE line per `Strategy.member_run`**, pegged to
  every bay it crosses, with the group's cut length and the slot's own `qty` — NOT the
  slot's qty times the bays. The per-bay lines for those bays are suppressed, or the same
  rail would be ordered twice. Demand does not decide continuity and does not re-derive it
  (see below);
- gates → kit sku (exploded later).
Length basis (chord vs slope) is chosen per vertical mode and named in the line payload
(Research A pitfall 4).

A span line names **no sku and no unit**. Both are written by `resolve_supply` from the
eligibility set and the chosen product's `Consumption`, in one statement — the parts ledger
balances asked-vs-purchased per `(sku, unit)` and reads the purchased side from
`BomLine.engineering_unit`, so a unit demand guessed for itself can disagree with what
`fulfill()` did and report one demand as unassigned *and* from stock at once.

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
(`warning.continuity_override_unbuildable`). Where no candidate states a stock length at
all, the assertion runs the whole chain and `warning.continuity_stock_length_unknown` says
that nothing bounded it — the chain is a real limit (a corner, a gate, a grade ends it) but
not one anybody chose, and `plan_cuts`' length guard only covers divisible stock.

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

Feasibility is resolved *before* tier 2 **and before the number of candidates is looked
at**: a candidate whose piece is longer than its stock, or whose sku is not in the catalog,
loses under every preset rather than winning on priority, and a group with exactly one
member is no exception. It used to be — with one candidate there is no choice to make, so
the gate was skipped — and the line then reached `plan_cuts`, which raises, which is how a
saved run became permanently unreadable behind a raw English 400 on `/bom`, `/structure`
and `/quote` at once. There is no choice at group size one, but there is still a question.

When **no** candidate is feasible there is no answer — the line is routed to `unresolved`
and reported, never silently picked. Two codes, because they send the reader to different
places to go fix it:

| Code | Means | Go look at |
|---|---|---|
| `no_eligible_item` | the eligibility set is empty — nothing is a candidate | the fence model |
| `no_feasible_item` | candidates were tried and not one fits | the catalog's stock lengths |

Both carry the requirement's pegs, in `params` (for the sentence) and `element_refs` (for
the reader that can map an element id to a bay tag). `role` + `slot_key` alone name a KIND
of part, so a 60-bay fence emitted sixty identical warnings naming no bay between them.

Feasibility is a catalog + geometry predicate — `sku in catalog` and `piece <= stock`, the
same comparison `plan_cuts` makes before it raises — and NOT a cut plan. That is what makes
it affordable at group size one; cuts are planned only when two or more feasible candidates
have to be ranked against each other.

An authored sku (a post, a cap, a gate kit — a line that arrives already naming its
product) skips the choice, because there is nothing to choose, but takes the same
feasibility guard. No shipped demand line carries both a sku and a cut length, so that
guard fires for nothing today; it is there so "`fulfill()` never sees a piece longer than
its stock" is a property of every path into `fulfill()` rather than of one of them.

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
- `fulfill()` never receives a requirement whose piece exceeds its product's stock, at any
  group size and by any path — `resolve_supply` routes it to `unresolved` first.
