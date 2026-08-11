# Display-units review — findings and dispositions (2026-08-11)

Two adversarial reviews of the mm/cm display-unit feature (commit 5d1735b) plus the
follow-up that took units and enum words into the decision prose (dc3f20f):
`architecture-critic` on the domain/frontend contracts, `test-reviewer` on the tests.

## Fixed

| # | Finding | Fix |
|---|---------|-----|
| A1 | `fieldMm()` returns `null` for a blank field (the old code returned `0`), and every popover save wrote it straight into a topology payload — `height_mm: null` → 422 after the local mutation, and `anchorFor(runId, null)` silently collapsed the interval to station 0. | `save()` now reads every required length first, marks unreadable fields `.invalid`, focuses the first one and refuses the save **before** `pushSnapshot`. `editor.js` |
| A2 | Rule builder: `paramIsLength` was computed at render time and captured in the `change` closure, but the free-text param box commits on `input` without re-rendering — typing `max_gap_mm` then `40` in cm mode stored **40 mm instead of 400 mm** in persisted rule data. | length-ness is now a thunk (`lengthNow()`) re-evaluated at commit time. `tabs.js`. Pinned by a smoke check that drives the freehand param box in cm mode and reads the stored action back out of the raw-JSON view; verified to FAIL against the pre-fix code. |
| A3 | `t("action.param." + p)` rendered the `{u}` placeholder literally in the known-params dropdown (dynamic key, so both new guards were blind to it). | `tu(...)`; a source guard now covers the other dynamic-key renderer (`localizedByCode`). |
| A4 | Decision prose stayed in mm under a cm header — and the ADR justified it while the working tree was already contradicting it. | Resolved by dc3f20f: `/explain` takes `units`, `explain.py` applies the same two rules, ADR-0002 addendum rewritten to match. |
| A5 | The "bare number < 100 is metres" shortcut is a trap in cm mode: `90` meaning 90 cm became a 90-metre segment. | The shortcut now applies only in mm mode; in cm a bare number is centimetres. New `hint.draw_cm` states the rule. The parser moved out of `editor.js` into `units.js` as `parseTypedLength(buf, unit)` — pure and unit-explicit, so the whole boundary matrix is pinned in node, plus a smoke check that types `90` on the canvas in cm mode. Mutation-verified at both layers. |
| T1 | `toMm` `trunc`/`floor` mutants survive the integer round trip (demonstrated by the reviewer). | `parse_sub` vector pins half-up rounding on sub-millimetre entry. |
| T2 | `inputStep`/`snapStep` untested — a regression to `step="1"` would coarsen every cm field to whole centimetres. | pinned: `{mm: "1", cm: "0.1"}` and `snapStep(10) → 1` in cm. |
| T3 | `unitParams` mutant converting *all* numerics survives (counts, degrees would be divided by 10). | fixture now carries `posts`/`tilt_deg`; both directions (`params_mm` and `params`) asserted. |
| T4 | Whole stateful half of `units.js` untested. | node harness stubs `localStorage`/`document`: corrupt stored unit → default, unknown unit → no event, two toggles → exactly two events. |
| T5 | Both locale guards trivially defeated: gershayim (`מ״מ`) slipped past the regex, and `t("key", {…})` without `u` slipped past the call-site guard. | regex covers `[מס]["״]מ` case-insensitively; the call-site guard now inspects *every* call of a `{u}` key and accepts only `tu(` or an explicit `u:`. |
| T6 | Smoke gaps: placeholder sweep ran before generation (so warnings were never covered) and read `innerText` (hidden panels excluded); "remembered per browser" only read localStorage; BOM check asserted a header word, not a converted number; `str(run_len/10)` was float-format-fragile. | sweep repeated after generation over `documentElement.innerHTML`; real reload check; converted cut-plan number; raw-JSON-stays-mm check; blank-field check; `:g` formatting. 42/42 checks. |

## Accepted, not changed

- **`toMm(...) ?? 0` in the rule builder and inventory rows** (T: "contradicts the module contract"): those two fields legitimately mean "unset = 0 / null" and behave exactly as before the feature. The contract that matters — *never write `null` into a payload* — is now enforced where it was actually violated (A1).
- **`fmtLen()` output inside `.num`** (bidi isolation): renders correctly today; `bomHtml` keeps the unit word outside the span. Worth unifying, not worth churn now.
- **Bare stations rendered without a unit** in the inspector event list: deliberate density in a two-column list; the unit is in the panel's other rows.
- **`btn-units` localized imperatively** rather than via `data-i18n`: the label is `Units: {u}`, i.e. a parameterized string; `applyStatic` only handles static keys.

## Known gaps (next round)

- `input_fact` decision lines still print the raw payload dict (mm, English keys) — readable as a record, ugly as a sentence.
- No CI: `tests/web/test_units_module.py` silently skips where node is absent. An
  opt-in `FENCEAI_REQUIRE_NODE` strictness flag was suggested and is not implemented.
