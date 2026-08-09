# Research C — Cutting stock, span layout, packaging, fulfillment

*Researcher C report, 2026-08-09. Synthesized into ADR-0007 and docs/architecture/material-optimization.md.*

## 1D cutting stock

- Fence jobs are tiny instances: tens of pieces, 1–3 stock lengths + a few remnants. Column
  generation / branch-and-price targets industrial scale; overkill here.
- **FFD/BFD**: worst case 11/9·OPT + 6/9; in practice optimal or within one bar at this scale.
- **Optimality certificate**: LP lower bound `ceil(Σ(piece+kerf)/stock)` (kerf-corrected); if
  FFD hits it, provably optimal — which happens most of the time on fence-like demand (many
  identical rail lengths). When missed by ≥1 bar, escalate to bounded branch-and-bound
  (trivial ≤ ~40 pieces) or CP-SAT. "Heuristic + certificate + escalation" gives exactness
  where free, speed everywhere.
- **Kerf**: bar with pieces p1..pk consumes Σp + (k−1)·kerf (or k·kerf with trailing offcut).
  Simplest safe model: each piece costs `piece + kerf`, capacity `stock + kerf` (credits back
  the final kerf). Kerf configurable per material/tool.
- **Remnants**: industry practice distinguishes *waste* (< min_reusable_length, scrapped,
  counted) from *usable remnant* (≥ threshold, returned to inventory with provenance).
  Secondary objective some optimizers offer: concentrate waste into one long remnant.
  Consumption: remnant-first, best-fit (smallest that fits, preserve long ones), but never at
  the cost of extra bars.
- Deterministic tie-breaking (length desc, then stable ID) → reproducible plans.

## Solver landscape

| Option | License | Verdict |
|---|---|---|
| OR-Tools CP-SAT | Apache-2.0 (v9.15, Jan 2026; ~22–30 MB wheel) | Best free discrete optimizer; integer-native; hard+soft in one model; deterministic w/ workers=1+seed. **Not in V1** — behind interface as optional extra when triggers fire. |
| PuLP + CBC | BSD-ish / EPL | MIP-only, CBC aging. Skip. |
| python-mip | EPL | Maintenance/packaging friction. Skip. |
| MiniZinc | MPL-2.0 | External toolchain; wrong shape for embedding. Skip. |
| HiGHS (highspy) | MIT | Only if MIP without OR-Tools ever wanted. |

CP-SAT triggers: FFD misses LP bound on real jobs more than rarely; coupled objectives
(min bars → remnant use → max largest leftover → min distinct patterns); multi-job batch
cutting; combinatorial layout (obstacles, gates pinned to posts, discrete panel catalogs,
slope steps).

## Span layout — closed form, deterministic

```
n = ceil(L / max_span);  base = L // n;  (L mod n) spans get base+1
```
Provably optimal for fewest-posts + equal-width preference; integer mm throughout;
remainder spread by fixed rule (ends or center). Gates/openings: subtract opening, solve
sub-runs independently; terminal span < min_span → adjust n rule-based. "Nice widths"
(match stock panel w): k = round(L/w) full + one cut panel at least-visible end by policy.
Same inputs → same layout → same BOM is essential (quoting, caching, testing, trust). Even
CP-SAT variant effectively deterministic (workers=1, fixed seed) but per-version — snapshot
plans in tests.

## Package rounding, UoM, MRP concepts to borrow

- **Dual quantities per BOM line**: `engineering_qty` (each/mm) and `purchase_qty` (box/bar)
  linked by explicit integer-ratio UoM conversion (never bare float). Demand 47 screws →
  3 boxes of 20 → overage 13. Always keep both numbers.
- **Rounding policy as catalog data** (SAP rounding profiles): round_up_to_multiple(pack),
  optional min_order_qty.
- **Pipeline = MRP**: BOM explosion → netting (against inventory) → lot-sizing. Name stages
  this way to keep module boundaries honest.
- **Demand pegging**: every allocation/purchase line carries references back to the demand
  lines it serves (purchase ← cut pieces ← spans). Cheap at plan time, impossible to
  reconstruct later; powers "why am I buying this?" — a differentiator here.
- **Soft allocation vs hard reservation** (ATP pattern): planning is pure over an inventory
  snapshot; reservation is a separate transactional step. Makes replanning trivial.
- **Substitutions**: ordered alternate-item rules on catalog with policy flag (auto |
  suggest_only), applied during netting, recorded in pegging.

## Multi-objective

- **Lexicographic tiers** are the domain-correct default (no weight tuning, no unit
  commensurability): e.g. [purchase_cost] → [remnant_value_consumed] → [num_cuts].
  Heuristics implement tiers as tie-break order; CP-SAT as sequential solves.
- Weighted sum acceptable *within* a tier once converted to money (cut ≈ labor cost).
- Expose named presets ("cheapest", "least waste", "fastest install"), not raw weights.
- Pitfall: weighted sums across incommensurable units flip plans under small weight changes.

## Existing tools

- **CutList Optimizer** (commercial, closed): UX benchmark — kerf setting, stock/remnant
  lists, waste %, printable per-bar cut diagrams. Emulate its output format.
- **cut-optimizer-1d** (Rust, MIT/Apache): evidence heuristics suffice commercially; read,
  don't bind.
- **opcut** (Python, GPL-family): read-only inspiration, no code reuse (copyleft).
- OR-Tools ships bin-packing/cutting examples — starting point when CP-SAT path opens.
- **No OSS combines cutting + remnant inventory + package rounding + pegging — that
  integration is the moat; the cutting kernel is commodity.**

## Concrete V1 recommendations

1. **Int mm, int cents, int counts. Never float** (kerf accumulation in float produces
   saw-infeasible plans). `Fraction`/int-pairs for UoM ratios.
2. CutPlanner = pure function `(demand_pieces, stock, remnants, policy) → CutPlan`; FFD/BFD,
   kerf-aware capacity, remnant-first best-fit, min_reusable_length, LP-bound certificate,
   deterministic tie-breaks. ~200 lines, no deps, property-testable (piece conservation, no
   overfill, kerf accounting).
3. Span layout closed-form; no solver.
4. CutPlanner/LayoutPlanner as protocols; CP-SAT optional extra later.
5. Dual-quantity BOM lines, int-ratio UoM, per-item rounding policy, pegging everywhere,
   soft-allocation planning + separate reservation.
6. Lexicographic objective tiers, shipped presets.
7. Test guards: kerf off-by-one on last cut; sub-threshold remnants leaking into inventory;
   nondeterministic iteration order; overage feed-back to inventory (decide explicitly; MRP
   says yes — V1: yes, flagged).

## Open trade-offs
(a) remnant value zero vs discounted pro-rata (affects eagerness to spend remnants);
(b) staged cut-plan→purchase vs joint (staged near-optimal; "try each stock length, pick
cheapest" loop covers the gap); (c) how much layout preference is user-visible config vs
opinionated default.
