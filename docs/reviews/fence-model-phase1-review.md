# Fence model phase 1 — review findings and dispositions (2026-08-12)

Three independent final reviews of `765310c..4bd0ba5`, run before the branch was offered
for merge: the project's `architecture-critic`, a whole-branch code review, and the
project's `test-reviewer`. Then one fix wave and one scoped re-review of it.

Verdicts: **SOUND-WITH-FIXES**, **READY WITH FIXES**, **GAPS**. They converged on the same
defects from three different angles, which is the useful part.

## What the reviews confirmed

The compatibility gate is real. Three parties verified independently that S01–S14 produce
identical requirement lines and an identical BOM behind `M-LEGACY`: the implementer by a
worktree JSON diff, the whole-branch reviewer by rebuilding it from scratch over four
topology lengths, and the re-reviewer by running the *pre-fix* spine at `cc19a44` against
the committed gate fixtures — all seven identical, so the artifact is not merely blessing
post-fix behaviour.

Also confirmed sound: all eight golden-scenario invariants have a failing-if-broken test;
determinism is covered twice and genuinely; LLM isolation is clean; `fit.py`'s
`_assert_accounts_for_axis` is a real conservation invariant applied to every case.

## Fixed in the wave

| # | Finding | Disposition |
|---|---------|-------------|
| A | **`fit_pattern` never terminated** on a member whose gap cancels its width — verified by hanging at exit 124, inside `generate()`. Negative gaps are a documented feature (board-on-board) and nothing bounded them. | Per-cycle advance check in `_count_members` plus `validate_model` rejecting `width_mm <= 0` and `width_mm + gap_after_mm <= 0`. A latent `ZeroDivisionError` on an empty gap list closed with it. |
| B | **The ledger unit was guessed for the third time.** Asked keys on `(sku, unit)` from demand; purchased keys on the product's `Consumption`. An indivisible product carrying `attrs.length_mm` — a combination `validate_model` explicitly blesses — double-booked six items as *both* unassigned and from stock. | One function, `engineering_unit_for(catalog, sku)`, is now the only answer, called by `fulfill()` for the purchased side and by `_name_product` for the asked side. Disagreement now requires editing one function, rather than being merely absent today. |
| C | **The pipeline was copy-pasted at four sites**, and the duplication had already caused a divergence: `create_quote` was the one endpoint calling `load_catalog()` directly, so the only endpoint that freezes an immutable commercial document was the only one exempt from the staleness check. | `fulfillment/pipeline.py`; `derive_requirements` and `fulfill` now have exactly one production caller each. Quote gets the check and stamps `catalog_hash`. `fulfill()` refuses a blank SKU, and caller-level assertions make the three-word reintroduction fail. |
| D | **All-candidates-infeasible was a silent wrong answer, then an unhandled 500** — the fallback picked one anyway with no warning, and `fulfill()` raised from outside the routes' `try`. | Returns no candidate; emits `no_eligible_item` plus an `unresolved` line. |
| E | **The compatibility gate did not exist in the repository.** It was a throwaway diff of two pytest runs. Two one-line mutations left the suite green: raked rails cut to plan width instead of slope length (511 passed), and the knowledge-resolved SKUs ignored entirely (509 passed). No test in the suite generated a raked span at all. | Eight committed JSON fixtures with a parametrized regression, plus the raked fixture the suite lacked. Re-verified by re-running the slope mutation: 2 failed. A guard test prevents a new fixture silently skipping the gate. |
| F | **Two vacuous tests** — one asserted a value it had assigned two lines earlier; the other asserted a SKU identical to the hardcoded default, so it could not detect whether the mechanism it named existed. | First deleted, with a comment naming the test that genuinely covers the route. Second rebuilt around a `DefaultComponent` that changes the answer. |
| G | **Six features validated at load and ignored at resolve** — variants, option axes, height support, eligibility predicates, and two `Excess` policies. Blessing data then ignoring it turns a deferral into a wrong answer with a green light. | `validate_model` rejects them by name. Docstrings describing unbuilt behaviour as working were corrected. **Partially addressed — see below.** |
| H | **Docs.** `material-optimization.md` documented a default preset the code now raises on. The pre-branch-run refusal surfaced as a raw English string. | Doc rewritten around the two real presets; refusal carries `code + params` with both locale bundles and a JS branch replacing a false "no structure yet". |

## Open, and why they are open rather than fixed

The process allows one fix wave and one scoped re-review. These two survived it and are
surfaced rather than silently carried.

- **A saved run can become permanently unreadable through the UI alone, with a false
  message.** Point a rail's `DefaultComponent` at a stock shorter than the cut and every
  read route returns a raw English 400 from the cut planner. The structure tab matches
  none of its known refusal reasons and renders *"Generate a strategy to see how it is laid
  out"* — the exact false message H was written to eliminate, reached by a different door —
  while the BOM tab throws into an unhandled rejection and renders nothing. The fix wave
  believed this unreachable with the shipped model; the re-reviewer disproved that using
  only the catalog and knowledge editors. Not a regression (it was a 500 before), and the
  fix is small: a coded `ReadRefused` from the planner's failure plus two JS branches.

- **`InfillSpec.supply` is still blessed-then-ignored.** `"assembly"` means the infill is
  bought as one pre-made unit; `resolve_panel` unconditionally emits per-member component
  slots and nothing reads the field, so authoring it silently produces a different set of
  purchased SKUs. It fails the criterion the G fix set for itself. Zero impact today — no
  shipped model sets it — but it is exactly the defect class G exists to close.

## Parked deliberately, with triggers in `v1-known-limitations.md`

A chosen SKU has no traceable decision-graph node once a group has more than one member;
`catalog_hash` is whole-catalog so any product edit 409s every prior run's read views;
`model_snapshot` is `(id, version)` rather than a content hash and `legacy_model()` mints
different models under one ref; and runs predating this branch cannot be read at all.

Also parked: coverage for the `FixingRule` bases, the justification × excess matrix, and
supply's waste and remnant tiers. All three are unreachable by any shipped model and are
the first thing phase 2 must close.

## One thing worth knowing before phase 2

`validate_model` has **no production caller**. Models are only ever built by
`legacy_model()`, which bypasses it. Every load-time gate on this branch — G's feature
refusals, A's per-member bound, the SKU and length checks — is enforced by tests only,
until a model-loading route exists. Pre-existing rather than introduced here, but it means
those gates protect phase-2 authors, not today's users.

## Note on method

Five implementer reports on this branch stated causal mechanisms that turned out false when
a reviewer reproduced them — a wrong explanation for a right conclusion, a latent bug that
could not occur, a smoke suite that never touched the code it was said to cover, an
"established precedent" the plan itself contradicted, and an unreachability claim reached in
two API calls. The shipped code was correct in every case. Reviewers caught all five only
because they re-ran the claim instead of reading it. That is the practice worth keeping.
