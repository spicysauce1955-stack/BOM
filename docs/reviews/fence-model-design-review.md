# Fence model design review — findings and dispositions (2026-08-12)

`architecture-critic` on the proposed design at
`docs/superpowers/specs/2026-08-12-fence-model-design.md`, run before any code was written.
Verdict: **SOUND-WITH-FIXES** — the shape was right, but the spec repeated the structure
review's characteristic failure mode: it asserted that existing machinery "already survives"
the new design in four places where the code says otherwise, and it deferred the one thing
that would have tested its central claim.

24 findings: 7 blockers, 8 major, 9 minor. All are dispositioned; the spec has been revised
in place rather than annotated. Five of the load-bearing claims were verified independently
against the code before being accepted.

## Blockers — fixed in the spec

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | **A SKU-free requirement line breaks the parts ledger.** The ledger keys on `(sku, unit)` from `RequirementLine.sku` (`report/structure.py:180`) and `BomLine.sku` (`191-193`), and `fulfill()` groups by `r.sku` (`fulfillment/fulfill.py:71-75`). A 40-slat panel would report 40 cuts unassigned *and* 40 from stock, print a blank SKU column, and satisfy A3's both-directions property vacuously. The spec never said how the chosen SKU flows back. | The write-back is now the mechanism the section turns on: demand emits `sku=""` + eligibility, `fulfill()` returns `resolved_requirements` with the chosen member, and `build_structure` is called with those. Ledger keys, `Part.sku` and `_merge_parts` are untouched because every line has a SKU by then. |
| 2 | **`run.id` cannot see a model change.** It hashes `[topology, knowledge_snapshot, overrides, policy]` (`generator.py:145-151`) and `save_run` is `INSERT OR IGNORE` (`store/db.py:180`). Edit a slat gap, regenerate: identical id, the old document is kept, and the POST response and `/bom` disagree permanently. | Verified. The digest gains the model snapshot, option values, selection preset and a catalog content hash. Called out that a field on `GenerationRun` is not an input to the hash. |
| 3 | **"Frozen into the snapshot" was a hash nobody compares** — A2 verbatim. `inventory_hash` is stamped (`app.py:313-315`) and checked nowhere; `/bom`, `/structure`, `/quote` all recompute against today's catalog. Also: the spec's claim that accepted quotes silently change is **false** — `Quote` persists `requirements` and `bom` (`quote.py:31-32`). | Verified, both halves. The resolved member list is frozen into the persisted strategy, not hashed; `/structure` and `/bom` gain a `catalog_changed` 409 shaped like `topology_changed`. The false quote claim is corrected in the spec text rather than deleted, so the next reader sees the correction. |
| 4 | **Category conflation.** Safety hard constraints were demoted to warnings although ADR-0005 makes a violated hard constraint a generation failure; and `LayoutPolicy` was emitted "at manufacturer authority" while claiming company rules could outrank it — impossible when `hard_constraint`=1 and `company_rule`=3 (`knowledge/model.py:19-27`). | The tier now decides the consequence: the same check fails generation under a `hard_constraint` and warns under a `company_rule`/preference. `LayoutPolicy` becomes a list of contributions, each declaring its own `knowledge_type`. |
| 5 | **`post_role_by_height` is unimplementable in the current order.** Posts are built before spans (`generator.py:111-113`, `627-712`; spans at `886-940`), and `_make_post` guarantees no post-hoc mutation (`generator.py:332-333`). | Dropped from phases 1–2, with the trigger for revisiting it named. |
| 6 | **A model change mid-run creates no structural boundary.** Model stations are absent from the `fixed` set (`generator.py:620-621`) and span properties sample the mid-point, so a bay straddles two models silently. `max_span_mm` also resolves once per run (`generator.py:490`), so a per-interval model cannot be honoured at all. | Model-change stations join `fixed`, as base transitions do; layout params resolve per segment; a two-model disagreement at a shared post surfaces as `knowledge_conflict`. |
| 7 | **Rail count would move from defeasible knowledge into authored model data**, so a company rule scoped to a project would bind to nothing and lose with no contest and no `defeated` edge — regressing behaviour pinned by `tests/strategy/test_scope_binding.py`. | `distributed()` placements name a knowledge param (`count_param="rails_per_span"`) instead of an integer; the model contributes the default as a `fact`. Structure is the model's, the count stays knowledge's. |

## Major — fixed in the spec

| # | Finding | Disposition |
|---|---------|-------------|
| 8 | A single `actual_gap_mm` cannot express an integer-mm fit; 2000/100/20 gives 23.5 mm gaps, really 24×6 and 23×11, so `clear_gap_exceeded` compares a rounded 23 and never fires while six openings exceed the limit | `FitResult.gaps_mm` is a list; spreading mirrors `layout.py:22-23`; the check runs on `max()` |
| 9 | `length_rule` needs a catalog face-width attribute that does not exist and a span↔flanking-post link that no object owns (asymmetric on S05) — and it silently decides the live disagreement between `golden-scenarios.md:23` ("clear width") and `derive.py:63` (centre-to-centre) | `attrs.face_width_mm` named; `resolve_panel` receives both resolved flanking posts; M-LEGACY declares `centre_to_centre` so nothing moves, and the scenario text is a separate task through the `golden-scenarios` skill. The numeric stake (S07 rails 1500→1420 halves the rail BOM) is recorded |
| 10 | The locale guarantee is false: the scanner regexes two files only (`test_locale_bundles.py:60-70`), so every new code ships untranslated with the test green — and fulfillment warnings have no home (`Bom` has no warnings field) | Scanner extension is part of the slice that adds the first code; `Bom` gains `warnings: list[StrategyWarning]` |
| 11 | `AreaPrice`/`BandPrice` are unrepresentable: `BomLine` has one `unit_price_cents` and `fulfill()` emits one line per SKU, so two panel sizes collapse into one line with no correct unit price. "Only change outside the new module" was false | Phase 2 scoped to `FlatPrice` + `LinearPrice`; area/band deferred behind a named prerequisite (grouping per `(sku, price_basis, size)`); the real blast radius is listed |
| 12 | The presets were specified against a dead field — `objective_preset` (`generator.py:57`) is read by nothing, and `fulfill()` receives no policy or knowledge; the `DefaultComponent` fallback would have put a knowledge lookup inside fulfillment | Preset resolved at generation, recorded on the run, in the digest, passed to `fulfill()` explicitly; the fallback is frozen onto the requirement as a member at generation time |
| 13 | An approved substitution is unrepresentable — the override vocabulary is closed and post-centric (`overrides.py:44-47`) — so `substitute_needs_approval` would fire forever, reproducing the inert `SubstitutionRule.policy` | Three new ADR-0004-anchored directives: `approve_substitute`, `force_slot_item`, `set_slot_count` |
| 14 | No anchoring vocabulary for panel-level corrections ("nine slats here, not ten"), although foundation §9 makes expert correction the premise | Covered by the same directives; `slot_key` is a new anchor dimension and a stale one orphans through the existing mechanism |
| 15 | **The phasing deferred the only part that tests the design.** One-member groups leave requirement SKUs, `fulfill()` grouping, the ledger and the read model all untouched, so phase 1's acceptance test proves the legacy path still works and nothing about eligibility | Phase 1 now carries one two-member group end to end — the 2 m/3 m kerf fixture — so the SKU-identity, ledger and read-model consequences are settled before `M-SLAT` |

## Minor — fixed in the spec

- **16** The waste-factor claim was false for linear products (engineering qty counts cuts, not bars, so extra bars are invisible on both sides of the ledger). Deferred explicitly, with the ambiguity named instead of guessed.
- **17** `conversion: Ratio` encoded exactly the nominal division the spec spends a paragraph disproving — deleted. `supply` duplicated `Consumption` — deleted, replaced by load-time validation that a member's consumption can satisfy the requirement.
- **18** `Variant` precedence said "specificity", which is undefined for a bare `Expr` — now authored order, first satisfied condition wins. Also noted that variant/axis/eligibility predicates evaluate outside the knowledge evaluator and therefore produce no firing/defeated events.
- **19** "Byte-identical" was literally false — restated as identical requirements and BOM. Field removal now needs a migration, because a stored run re-read without `rail_count` silently defaults to 2.
- **20** Five frontend contracts stated: the elevation is a field on `StructureReport` (not a second endpoint, which would reintroduce A7), display-unit round-tripping, `swatch` validated at load rather than escaped at render, the never-mirrored rule, and `_ENUM_WORDS` for the new enums.
- **21** `_merge_parts` would collapse a shadowbox panel's front and back members into one row, making the click-a-slat promise unimplementable — `Part` gains `slot_key` and merging keys on it; pegs stay element-level.
- **22** Catalog-side models do not inherit `preview-impact`; `learning/impact.py` gains model-version cases in the slice that makes models editable.
- **23** `exact_span_mm`, discrete-height warnings and "minimal relaxations" were three unspecified behaviours treated as decided — all three now defined, including per-section aggregation and a typed `relaxations` field instead of stringified params.
- **24** Raked member lengths interpolate a float datum with no named rounding point — now `member_length_mm()`, the single place that rounds.

## Judged sound, not relitigated

Eligibility on the slot rather than the product; rejecting SAP usage probability; the closed
`FixingRule.basis` vocabulary instead of a scripting language; product choice as a fulfillment
objective coupled to the cut plan, with the kerf arithmetic correct against
`cutplan.py:98`; model selection as an interval event rather than a reference to a generated
element; `ResolvedSlot` as fit parameters with geometry derived server-side; `M-LEGACY` as the
compatibility path; and the out-of-scope list.

## Note on method

Five claims were checked against the source before acceptance rather than taken on trust:
the run-id digest and `INSERT OR IGNORE`, the read-path recomputation and the quote
immutability counter-claim, the locale scanner's file list, and the golden-scenario clear-width
disagreement. All five held. The quote finding in particular corrected an error in the spec
that the review's own summary had half-inverted, which is why it is written out in full above.
