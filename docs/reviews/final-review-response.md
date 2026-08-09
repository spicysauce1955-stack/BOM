# Final V1 review response

Architecture-critic verdict: **SOUND-WITH-FIXES** (all five prior blocker-class fixes
verified as genuinely holding). Test-reviewer verdict: **GAPS**. Disposition of every
finding; all fixes landed in commit a13ee54; suite 153 passing.

## Architecture critic (new-surface findings)

| # | Finding | Disposition |
|---|---|---|
| 1 (high) | Duplicate node/run ids possible after page reload; no server-side validation | **Fixed.** `Topology` model validator rejects duplicate node/run/event ids and dangling node refs (PUT → 422); client derives id counters from the loaded project. |
| 2 (med) | `scope_restrict` could retarget scope values, not just narrow | **Fixed.** Existing dimensions must keep their values and at least one dimension must be added; API test covers the 400. |
| 3 (med) | Intent ids collide across re-interpretations; confirmation resolves oldest | **Fixed.** Record ordinal in every intent id (stub + claude); `confirm_intent` raises descriptive ValueError instead of StopIteration; collision test added. |
| 4 (med) | Verbatim text interpolated into innerHTML (script injection) | **Fixed.** `esc()` applied to all interpolated user/expert text (annotations, comments, knowledge source_text, candidates, overrides, BOM notes). |
| 5 (med) | BOM recomputed against current inventory with no record | **Fixed (smallest form).** BOM responses carry an inventory content hash; each fulfill is audit-logged. Full persisted BOM snapshots recorded as a known limitation. |
| 6 (low-med) | Knowledge lifecycle logic in composition root; non-atomic transitions | **Fixed.** `Store.replace_active_version` and `Store.apply_review_outcome` do retire+insert in one transaction; API routes now call them. |
| 7 (low) | `update_knowledge_status` accepted any string/transition | **Fixed.** Allowed-transition map (draft→active/retired, active→retired, proposed→retired/rejected) + Literal re-validation; illegal transitions → 400. |
| 8 (low) | BOM recomputed on every render; project-targeted intent silently lands on runs[0] | **Fixed.** BOM render gated behind the active tab; project-targeted confirmations prompt for the target run. |

## Test reviewer

| # | Finding | Disposition |
|---|---|---|
| 1 (major) | Vacuous determinism assertion in invariants | **Fixed.** Real double-generate `rerun` fixture across all seven spine shapes, comparing strategy/graph/run-id/requirements/BOM dumps. |
| 2 (major) | Coverage-based SKU (CONC-25) numerically untested, excluded from undersupply invariant | **Fixed.** Invariant extended to coverage semantics; S01 pins 5 applications → 3 bags (odd round-up boundary). |
| 3 (major) | POST-CAP documented but never demanded | **Fixed.** 1 cap per post in demand derivation (policy `cap_sku`); pinned to post count in tests. |
| 4 | Sliver/K-SLIVER path uncovered | **Fixed.** 400 mm run test asserts warning + K-SLIVER citation. |
| 5 | S10 gate decisions didn't cite the gate topology event | **Fixed** in generator (gate fact nodes created before posts; flanking posts cite them) + asserted. |
| 6 | Fallback test admitted both outcomes | **Fixed.** Client construction stubbed to fail; asserts exactly `stub`. |
| 7 | knowledge_ref → snapshot integrity unasserted | **Fixed.** New invariant test across all fixtures. |
| 8 | API coverage gaps (list/get, delete-override workflow, reject/scope-restrict, catalog, audit, 404s, invalid payload) | **Fixed.** Six new API tests including the scope-widening 400 and duplicate-id 422. |
| 9 | Slope-threshold boundary (exactly 150‰) | **Fixed.** Counterexample at 150‰ added to K-STEP-SLOPE's executable examples. |

Post-fix verification: full suite 153 passing; fresh clone installs, tests green,
boots, and serves the UI (`uv sync && uv run pytest -q && uvicorn ...`).
