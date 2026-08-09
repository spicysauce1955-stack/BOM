# Spike review response (Slice 0 checkpoint)

Architecture-critic verdict: **SOUND-WITH-FIXES**. Test-reviewer verdict: **GAPS**.
Both reviews evaluated commit 926b0da..spike. Disposition of every finding:

## Architecture critic

| # | Finding | Disposition |
|---|---|---|
| 1 (blocker) | Preferences cited but causally inert; vertical loop-overwrite let weakest firing win | **Fixed.** Layout preference (equal vs span-width) resolved through `evaluator.resolve` with surfaced ties (S13); vertical mode slot-resolved the same way; `PreferSpanWidth` drives `nominal_mm`. |
| 2 | generate() mutated override status; confirm_intent didn't bump revision | **Fixed.** Orphans reported via `GenerationResult.orphaned_overrides`; revision bumped on event materialization. |
| 3 | Override matching exact-integer; node/line posts unreachable; ForceVertical interval ignored | **Fixed.** `SNAP_TOLERANCE_MM` matching everywhere; force sku/mounting apply to node, fixed, and line posts; ForceVertical applies per span interval. |
| 4 | Hardcoded product literals; element mutated after decision recorded | **Fixed.** `DefaultComponent` knowledge action (K-POST-DEFAULT); mounting/reinforcement skus come from the rules; all selection resolved before the decision node; no post-hoc mutation. |
| 5 | Wrong slot granularity in resolve_actions | **Fixed.** `resolve_actions(..., match=)` narrows to the slot (per-surface mounting, per-context reinforcement, per-role defaults). |
| 6 | GraphBuilder knowledge edges violated ordinal acyclicity | **Fixed.** Knowledge input nodes materialized before their consumer; single `_edge` path enforces ordering. |
| 7 | demand imported knowledge; quantities untraced | **Fixed.** Rails/screws resolved in generate() with a `quantity` node citing K-RAILS/K-SCREWS; `Span.screws_count`; demand depends on strategy+catalog only. |
| 8 | Base interval boundary order-dependent | **Fixed.** Half-open `[start, end)` with end-inclusive-at-run-end rule, documented in `base_surface_at`. |
| 9 | Node posts ignored cross-run context | **Fixed.** Per-node pass over all incident runs: surface disagreement surfaced as conflict+warning (masonry wins deterministically), gate-edge adjacency reinforces, overrides reach node posts. |
| 10 | Hard-tier ties didn't fail generation | **Fixed.** `resolve()` raises GenerationFailure for tied hard-authority contenders with disagreeing outputs; DMN-ANY agreement handled via `values_agree`. |
| 11 | Stepped/wall verticality unrepresentable | **Fixed** (extension): wall_profile + top_line events consumed; per-span `step_mm`/bottom-z in decision payloads; S04/S06 tests pin it. |
| 12 | Module map drift; ai↔project | **Accepted, documented.** `project` added to map; `ai/records` is dependency-free; adapters (stub/claude) may import domain models. |
| 13 | Cut planner dead code; weak LP credit | **Fixed.** Dead line removed; bound credits only consumed remnant capacity. |
| 14 | K-REMNANT citation impossible | **Accepted.** Remnant policy is catalog data; scenario doc reworded (allocation cites catalog policy, not a KB object). Revisit if remnant policy becomes company-configurable knowledge. |
| 15 | Fabricated gate kit sku | **Fixed.** Unknown catalog SKU → `unknown_product` warning at generation; fulfillment prices unknown SKUs at zero with a note instead of KeyError. |
| 16 | Float slope in payloads; endpoint-only slope | **Fixed.** Integer `slope_permille`; steepest consecutive-sample grade; ground_z docstring corrected. |
| 17 | Coarse pegging; gates lacked structural node | **Partially fixed.** Gates get `place_gate` structural nodes. Per-SKU (not per-connection) allocation pegging kept for V1 — recorded in known limitations. Substitution/assembly-explosion stages remain V1-deferred. |

## Test reviewer

Findings 1–3 (station/anchor, evaluator precedence, cut-planner boundaries): **fixed** —
`tests/topology/test_station.py`, `tests/knowledge/test_evaluator.py`,
`tests/fulfillment/test_cutplan.py`. Findings 4–8 (kerf-binding assertion, layout
boundaries, package boundary, reverse traceability, post positions): **fixed** in
`tests/strategy/test_layout.py` and strengthened spike tests. Hard-tier tie behavior
changed by critic finding 10; evaluator tests updated to match (preference ties surface,
hard ties raise).

Suite after fixes: 118 passing.
