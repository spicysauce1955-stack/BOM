# Current status

Updated: 2026-08-12 — V1 complete; fence models phase 1 landed (phases 2–3 remain)

- [x] Research (4 parallel researcher reports, synthesis, ADRs 0001–0010)
- [x] Architecture (docs/architecture/*, golden scenarios S01–S14 defined)
- [x] Slice 0: spike + review cycle (docs/reviews/spike-review-response.md)
- [x] Slices 1–8: core domain — all S01–S14 scenarios passing
- [x] Slice 9: SQLite store + FastAPI API
- [x] Slice 10: SVG topology editor + strategy overlay UI (headless-Chrome verified)
- [x] Slice 11: hardening, V1 docs, fresh-clone verification
- [x] Final review pass: architecture-critic SOUND-WITH-FIXES + test-reviewer GAPS —
      every finding fixed (docs/reviews/final-review-response.md); 153 tests passing

V1 completion definition (docs/input/plan.md §20): satisfied — integrated app runs,
golden scenarios pass, strategy generation + decision provenance + material semantics
+ BOM + cutting/packages/remnants + annotations/interpretations + correction/candidate
workflow all work, architecture docs match implementation, automated tests pass, fresh
developer can run from docs/v1-runbook.md.

Next (V2 candidates): see docs/v1-known-limitations.md triggers — persisted BOM
snapshots, cross-project impact preview, CP-SAT escalation, substitution netting,
Claude proposer/critic adapters, Tier-2 explanation polish, multi-tenant Postgres.

## UI v2 (2026-08-10) — COMPLETE
Spec docs/superpowers/specs/2026-08-10-ui-v2-design.md; plan .../plans/2026-08-10-ui-v2.md.
Delivered by 4 worktree agents + integrator: module scaffold; backend i18n (warning
codes+params, he/en explanation templates, Hebrew stub interpretation, bilingual names);
editor (undo/redo, select/draw grammar, snapping, typed lengths, canvas event popovers
incl. height tool); profile side view (ground/wall editing, synced selection); Hebrew-first
RTL (153-key parity, Noto Sans Hebrew, logical-properties CSS, localized dynamic content).
Verified: 174 pytest + 14/14 tools/ui_smoke.py checks + inspected screenshots.

## Rule impact preview (2026-08-10) — COMPLETE
"This change would affect N of your projects" before approving/saving knowledge —
Research D's highest-value review feature. learning/impact.py (pure regenerate-and-diff),
2 API endpoints, UI in review queue + knowledge editor (he/en). 202 pytest + 21/21 smoke.

## Canvas zoom/pan/fit (2026-08-10) — COMPLETE
Wheel zoom anchored at cursor (0.25x-6x), middle/Ctrl-drag pan (screen-space math),
fit-view button, world-aligned grid re-rendered per view (5 m spacing when zoomed out).
202 pytest + 24/24 smoke.

## Persisted quotes (2026-08-10) — COMPLETE
Immutable BOM snapshots with lifecycle (draft/accepted/superseded, atomic supersede),
quotes panel in the BOM tab (he/en), impact preview reports vs-accepted-quote deltas.
Smoke hardened: aborts if a stale server holds the port. 208 pytest + 26/26 smoke.

## Base top-line editing UI (2026-08-10) — COMPLETE
Side-view editing for the base_top event (backend efc49e7): filled band whose top edge
follows the point profile (vertical jumps at steps, concrete/wall tones), draggable
diamond dots (10 mm z snap; horizontal drag moves pos_permille, snapping onto a
neighbour makes a STEP), dbl-click edge inserts an interpolated point, dbl-click the
dashed hint line gives a bare built base a top line, dot popover types/deletes points,
band popover edits first/last and converts legacy wall_profile into a 2-point base_top.
Inspector lists base_top with a localized point count. 8 he/en keys added.
217 pytest + 26/26 smoke + 28/28 dedicated CDP drive (step -> K-STEP-POST transition
post verified in plan AND profile) + inspected screenshots.

## UI ease-of-use round (2026-08-10) — COMPLETE (#2-#4 of research menu; #1 auto-compute rejected by user)
Type-while-drawing exact lengths (SketchUp mechanic, unit-tolerant, angle-snap on
direction only); gate catalog picker (components excluded); seeded sample project +
getting-started checklist + empty-canvas CTA + labeled toolbar; zero prompt()/JSON
UIs left: inline quote/reject/scope/run forms, sentence-style knowledge rule builder
with Advanced-JSON toggle, inventory table editor. 220 pytest + 27/27 smoke,
272-key he/en parity. Research report menu retained for next rounds (#5-#10:
adaptive UI, wizard spine, dimension pad, spatial warnings, segment table, aerial).

## Persona-lab run 2 batch A: frontend + fulfillment (2026-08-11) — COMPLETE
**One resolver decides which run a pointer means** (`geom.runAtPoint`): hover used array
order, clicks used SVG paint order, and `.run-hit`'s round cap put a 178 mm disc over the
neighbouring leg — the status bar said one station and the click recorded another, so a
climb was authored on the wrong leg and priced level, and the first leg's last 200 mm were
unreachable. Linecap is butt; the strategy overlay can no longer swallow a click. A ground
click at a run end writes the shared node's z, so two legs cannot contradict each other
about one corner. `.run-label` opens the length editor only for the select tool; popover
fields select on focus (`1000` had been reaching the DB as `10000`); the height popover
spans the whole run; the gate picker reads `attrs.opening_width_mm` instead of parsing a SKU.
**Cut plans are certified honestly**: added a counting lower bound, so `lower_bound =
max(lp, counting)` and a provably optimal plan is no longer called "heuristic" — and no
solver vocabulary reaches a BOM line (two S07 assertions had encoded the defect; the doc
never promised the certificate, so the code was wrong). **The rule editor no longer traps
you** — the escape hatch was gated on parsing the broken JSON. Impact failures, api.js
alerts and the inventory back-label now honour `code + params`; projected remnants render.
Documented rather than papered over: package overage is never projected, and inventory has
no warehouse scope, so offcuts cannot reach the next job.
382 pytest + 50/50 smoke.

Note for archaeology: commit `0c100a6` ("bind rule scope") also carries `cutplan.py`,
`test_cutplan.py` and `test_locale_bundles.py` changes from a concurrent agent, swept in by
a `git add -A`. Nothing was lost; the message is just narrower than the diff.

## Persona-lab run 2 backend fixes: B1/B2/B3 (2026-08-11) — COMPLETE
Four defects, TDD, one commit each. **Rule scope now binds** — `bind_scope()` derives
dimensions generically from generation facts (`project_id` run-wide; `surface`/`context`
at the post-level slots), so restricted approvals and stub-proposed candidates can fire and
specificity finally breaks ties; the impact preview binds each case's project. **A gate kit
must fit its opening** — fit is catalog DATA (`Product.attrs["opening_width_mm"]`, like
`length_mm` on posts), never parsed from a SKU: mismatch → `gate_kit_width_mismatch`, no
`kit_sku` → selected from the catalog by declared width, nothing fits → `no_gate_kit` and no
BOM line. **Gate-kit provenance is the gate event**, not K-GATE-REINF (which governs only the
post upgrade); `governed_by` = "this rule decided this value" is now written down.
**The stub proposer reads יסוד as well as "foundation"**, and promotion drops the
"(candidate)" marker in every language.
Refused as hardcoding: nothing — the two blocked dimensions (`series`, soil type) need a
topology-model field, and gate-kit width needed a catalog attribute, which is data, not code.
382 pytest + 49/49 smoke.

## Persona lab RUN 2 (2026-08-11) — COMPLETE, supersedes run 1
Run 1's study was wrong: personas came from market research, not the architecture, so the
central user (the expert correcting proposals, foundation §9) was never simulated and S11–S14
went untested. Run 2 uses five roles from the architecture, each doing a real job twice, with
the status bar visible, a `move` verb, 60 actions (look free), no checklists, no quit framing,
and taxonomy assigned by the refuter instead of the persona.
Report: `docs/reviews/persona-lab-run2-2026-08-11.md`. 31 confirmed / 13 refuted / 3 positives.
**Works, verified:** immutable accepted quotes + supersede; impact preview across the portfolio;
cut plans and typed lengths. `fulfillment` finished both jobs (site 2 in six actions).
**Severity-4 blockers:** gate kit ignores opening width (`generator.py:431` — a 3500 mm gate
priced as GATE-KIT-1000, accepted against a customer, and the decision graph attributes the SKU
to a rule); rule `scope` accepted then dropped (`ctx["scope"] = {}` at generator.py 131/182/406/941
— restricted approval and every stub-proposed candidate are no-ops); the expert loop is inert
end-to-end (obstacle/foundation payloads exist but nothing authors them — S12 ⇄ code disagreement;
`ai/stub.py:116` matches the English "foundation" only; `AddNote` has no consumers); status-bar
station vs click hit-test disagree on an L (`.run-hit` round cap ≈178 mm disc at the corner) so a
6 m climb is priced level. Cheapest real fix: `editor.js:541` needs `.select()` (3 personas,
`1000` → `10000` reaches the DB).
Eight harness defects found and fixed across both runs; one known-unfixed (native `<select>`
needs keyboard driving). 346 pytest + 44/44 smoke.

## Persona lab (2026-08-11) — RUN 1, SUPERSEDED (study design was wrong)
`tools/persona_lab/` — six real-role personas (5 he + 1 en control, from Israeli fence-trade
research) drive the live app over CDP perceiving only rendered UI (visible labels, opaque
handles, no ids/API/DB/repo). Independent refuters reproduce every finding and assign severity.
First run: **0 of 6 completed their job**; 64 raw findings → 51 confirmed, 13 refuted.
Report: `docs/reviews/persona-lab-2026-08-11.md`.
Top blocker: `editor.js:541` focuses popover number fields without `.select()`, so typed digits
prefix the prefilled value (1000+3500 → 35001000) and a bad `z_mm=-4000` persists unvalidated —
hit by 5 of 6 personas. Then: no export, € hardcoded, no customer-facing price, no metre unit.
The run also found 5 defects in the harness itself (all fixed, `5d08262` + `b720a2f`, regression
-tested) which had manufactured 13 false findings — including a fake "app froze, data lost".
302 pytest + 44/44 smoke.

## Display-unit toggle: mm / cm (2026-08-11) — COMPLETE
User-selectable display unit in the header (persisted per browser, Hebrew מ"מ / ס"מ).
New `js/units.js` is the only converter: `toDisplayValue`/`toMm` at every field boundary,
`tu()`/`unitParams()` render `{…_mm} {u}` locale strings (backend warning params convert
by name). Covers canvas labels + cursor readout + typed lengths (a bare number ≥100 now
reads in the active unit), every popover field, the side-view z editors/tooltips/ticks,
inspector events + overrides, BOM cut plans/allocations/engineering demand, inventory
lengths, and `*_mm` rule-builder fields. Storage stays int mm everywhere (ADR-0002
addendum); raw-JSON editors and server-rendered decision prose deliberately stay mm.
244 pytest (incl. node-run round-trip tests for units.js + two bundle guards) +
34/34 smoke (210 cm → 2100 mm verified end-to-end) + screenshot inspected.

## Explanations follow language AND unit; enum words localized (2026-08-11) — COMPLETE
`/api/runs/{id}/explain/{element}` gained a `units` param beside `lang`; explain.py renders
`*_mm` values in the reader's unit with a `{u}` token (same two rules as units.js). Enum
VALUES (post kind, mounting, base surface, vertical mode, post orientation) now render as
words in both the prose (`_ENUM_WORDS`) and the UI (`enum.*` bundle keys + units.enumWord),
so Hebrew no longer carries raw "line"/"soil"/"perpendicular" — this also fixes the
tilted_stepped warning's raw-enum param. inspect() takes key+params and replays the last
inspection on language/unit change. Tests pin: cm rendering without float noise, Hebrew
enum prose, every domain Literal has a Hebrew word, the two lexicons agree, `?units=inch`
is a 422, and reading never mutates the graph. 251 pytest + 37/37 smoke (decision trail
verified in cm with Hebrew enums; screenshot 09).

## Units review round (2026-08-11) — COMPLETE
architecture-critic + test-reviewer on the units work. Three real defects fixed: blank
popover length fields wrote `null` into topology payloads (422 + a zero-length interval at
station 0); the rule builder stored a cm value as mm when the param name was typed into the
free-text box (10x, in persisted rule data); `{u}` rendered literally in the known-params
dropdown. Also removed the cm-mode "bare number < 100 = metres" trap (90 → 90 m) with a
per-unit draw hint. Tests hardened: sub-mm rounding, field steps, both param directions,
the stateful half of units.js (stubbed localStorage/DOM), gershayim-proof unit-literal
guard, inverted call-site guard, and a source guard for the dynamic warning renderer.
Smoke: blank-field refusal, real reload, converted BOM numbers, raw-JSON-stays-mm,
post-generation placeholder sweep, and a freehand `*_mm` rule param driven in cm mode
(mutation-verified: fails against the pre-fix code). The typed-length parser moved from
editor.js into units.js as `parseTypedLength(buf, unit)`, so its unit-dependent boundary
matrix is pinned in node as well as through a canvas keystroke check — both layers
mutation-verified. 260 pytest + 44/44 smoke. Dispositions:
docs/reviews/units-review-response.md.

## Side view: scope switch + base-top actions (2026-08-11) — COMPLETE
User feedback: aligning two sections' bases, changing a base height at all, making one
horizontal and creating steps were all hard, and the whole fence competed for one strip.
The side view now has a SCOPE switch (whole fence | one section, remembered) with a section
picker that keeps the plan selection in step; a focused section fills a taller panel, so the
drag targets are far bigger. New `js/base-top.js` holds the geometry as pure transforms —
`flatPoints` (a height above ground), `levelPoints` (ONE absolute elevation, with a point at
every ground break, since z is stored above local ground), `matchEnds` (meet the neighbour's
top at a shared node), `withStep` (a plateau: everything past the step rises with it) — plus
`topZAt`, moved out of profile.js. A base bar drives them by number instead of by aim, and
says plainly when a section is on soil (base_top only affects BUILT_BASES). 395 pytest
(13 new node-run geometry tests) + 58/58 smoke, incl. two adjacent sections aligned
end-to-end. Level is exact to NUMERIC_TOLERANCE_MM — permille point positions quantize it.

## Base-top segment rules + neighbour elevation (2026-08-11) — COMPLETE
Follow-up to the side-view round. A step is now what the word means on site: a VERTICAL
riser followed by a HORIZONTAL tread. Both are `lock` values on the new
`BaseTopPoint.lock` field (level|step|null, an authoring constraint on the segment that
starts at that point) — `enforceLocks` re-imposes them after every edit (drag, typed z,
height, level, match, step), propagating outward from the point the user actually moved.
Clicking any segment of the top line opens a rule popover (אופקי / אנכי / חופשי); locked
segments render distinctly. "Horizontal" now locks every segment, and a corner match that
would contradict a standing horizontal rule is REFUSED with a note pointing at the new
"≡ גובה השכן" action, which levels the whole section at the neighbour's elevation (the
second reading of "align two sections", per user confirmation). 401 pytest (6 new lock
tests) + 62/62 smoke, incl. lock persistence through the API and the refusal path.

## Map panning, side-view scale, fence-on-base, strategy summary (2026-08-11) — COMPLETE
Four pieces of user feedback. (1) The plan canvas pans by dragging empty space with the
primary button (any tool; grab/grabbing cursors), alongside the existing middle- and
Ctrl-drag; a press that never moves is still a click, so nothing edits by accident.
(2) The side view gained an elevation scale — "nice" 1/2/5 tick steps, labels in the
display unit, and the axis names its unit AND the vertical exaggeration that distorts it.
(3) REAL MODEL FIX: posts on a built base were recorded at ground level while the panels
already rested on the base top, so the post-length check measured through the wall and
charged embedment on top. New `Post.base_z_mm` (the elevation a post stands on; None =
ground) — the check measures exposure from it and only `ground`-mounted posts pay
embedment. The profile draws posts from base_z to the adjacent panel tops. (4) A strategy
summary above the warnings: counts, fence length, span width range, height, panel mode,
post SKUs, note count, a link to the priced BOM and the "click anything to see why" hint.
406 pytest (5 new built-base tests) + 74/74 smoke, screenshots inspected. Follow-up: the
map's `grab` leaked onto everything drawn on it (a CSS rule on the <svg> beats the
elements' presentation attributes) — every cursor role is now spelled out: map=grab,
draw=crosshair, event tools aim (crosshair) at a run, runs=pointer, vertices=move,
ghosts=copy, generated elements=help, and an active pan forces `grabbing` over every
element under the pointer so it never flickers mid-drag.

## Structure & parts: layout and the items it consists of (2026-08-11) — COMPLETE
Researched (fence estimating vendors, contractor spacing guides, permit-drawing rules, AIA
dimensioning) and built in five tasks; spec + plan in docs/superpowers/.
`fenceai/report/structure.py` is a pure read model over a run: sections/posts/bays/gates
tagged (A, P1, B1, G1 — derived, never stored), setting out as running stations with
centre-to-centre spacings, and per-element parts obtained by INVERTING existing pegs
(element → RequirementLine → BomLine, plus cut-piece bar provenance). Its governing property
is Σ(parts) ≡ BOM, with unpegged demand reported as `unassigned`. `RequirementLine.role`
(post|cap|concrete|rail|screw|gate_kit) rides to `Part.role` so the customer sheet can
describe fixings instead of counting them — trade practice, not a guess from SKU strings.
GET /api/runs/{id}/structure serves it; the Structure tab renders both detail levels;
`js/structure-data.js` is the single tag source for the tab AND both drawings; the side view
gained a chained centre-to-centre dimension string with one overall per section and the
CLOSING bay marked; printing yields the site sheet (drawings + schedules, title block, plan
auto-framed). 424 pytest (16 new) + 88/88 smoke.

## Structure & parts review round (2026-08-11) — COMPLETE
architecture-critic + test-reviewer before calling the milestone done; both earned it.
The layout half was sound; the parts half was not. Fixed: a stored run laid out over an
EDITED topology (invented stations — now 409 + "the drawing changed"); the report being a
function of mutable inventory with nothing recording it (inventory_hash + cache
invalidation); Σ(parts) ≡ BOM holding in only one direction (fulfilment emits no line when
stock covers demand → new `from_stock` bucket); `unassigned` summing across units and
printing negatives; a shared corner post carrying TWO tags while the drawing prints one
(tags now unique per element, `A/P1`, totals count elements not rows); the dimension chain
starring a GATE opening as the tolerance-absorbing bay; a stale in-flight fetch labelling
one run's drawing with another's schedule; and a gate clamped past its section end keeping
a kit that cannot fit (new `gate_past_run_end` warning). Tests: four demonstrated mutations
(concrete on the wrong post, screws on the wrong bay, every rail claiming bar #1, a cap
labelled a post) now die; the vacuous `32 + 0 == 32` unassigned test became the real
fitted-vs-bought relationship; browser checks assert identity rather than existence.
440 pytest + 99/99 smoke. Dispositions: docs/reviews/structure-review-response.md.

## Fence models, phase 1 (2026-08-12) — COMPLETE
Spec docs/superpowers/specs/2026-08-12-fence-model-design.md (revised after adversarial
review, 7 blockers / 8 major / 9 minor dispositioned); plan
.../plans/2026-08-12-fence-model-phase1.md. The structure of a fence panel stops being two
integers on `Span`. A new pure module `fenceai/fencemodel/` owns the schema (`model.py`
with load-time `validate_model`), the 1-D pattern fit (`fit.py`), and per-span resolution
(`resolve.py`); `Span.panel` carries a `ResolvedPanel`, `derive_requirements` expands its
slots instead of reading `rail_count`/`screws_count`, and a new
`fenceai/fulfillment/supply.py` resolves each line's ELIGIBILITY to a concrete SKU before
`fulfill()` runs, so the parts ledger keeps keying on `(sku, unit)`. Choosing among eligible
items is an objective coupled to the cut plan, not a lookup — named lexicographic presets
(`least_cost`, `honour_priority`, ADR-0007), with feasibility filtered first. The run-id
digest gains the model snapshot, the catalog hash and the preset, and `/bom`, `/structure`
and `/quote` refuse a run re-read against a moved catalog (409 `catalog_changed`). All of it
lands behind a built-in `M-LEGACY`, whose acceptance gate is that every existing shape
produces identical requirement lines and an identical BOM.

## Fence models phase 1 review round (2026-08-12) — COMPLETE
architecture-critic (SOUND-WITH-FIXES) + whole-branch code review (WITH-FIXES) +
test-reviewer (GAPS), converging on the same defects; all fixed in one wave.
`fit_pattern` HUNG on a non-advancing pattern (`gap_after_mm` may be negative and nothing
bounded it) — guarded in `fit.py` per pattern cycle and rejected per member in
`validate_model`. Demand had guessed the parts-ledger unit three times and was still wrong
(an indivisible product with `attrs.length_mm` legitimately backs a length slot, and is
still bought in eaches — the same six items appeared in `unassigned` AND `from_stock`);
demand now emits no unit at all and `resolve_supply` writes sku and unit together from the
one function `fulfill()` uses. The four copy-pasted `derive → resolve → fulfill` sites
became `fulfillment/pipeline.py`, which closed the divergence that duplication had already
caused: `create_quote` loaded the catalog directly, so the one endpoint freezing an
immutable commercial document was the only one exempt from the staleness check (BOM 409,
structure 409, quote 200). `fulfill()` now REFUSES a blank sku instead of trusting its
callers. All-candidates-infeasible was a silent pick followed by an unhandled 500; it is a
`no_eligible_item` warning plus an `unresolved` line. Features validated at load and then
ignored at resolve (`variants`, `option_axes`, `layout_policy`, `height_support`,
`Eligibility.predicate`, `excess` of trim_last/extension_clip) are now REJECTED by
`validate_model` rather than blessed and dropped — a deferral must not read as a working
feature. The compatibility gate became a committed artifact (per-fixture requirement lines
+ BOM as JSON), and the fixture set gained the RAKED shape the suite entirely lacked: two
mutations that previously left the suite green (deleting the slope-length branch; ignoring
the resolved `demand_skus`) now fail. Two vacuous tests deleted/replaced. 555 pytest
(+46) · 126 golden scenarios (+18) · 101/101 smoke. Dispositions and the fix wave:
.superpowers/sdd/2026-08-12-fence-model-phase1/fix-wave-report.md.

## Fence models phase 1 — closing the open findings (2026-08-12) — COMPLETE
The four gaps `docs/reviews/fence-model-phase1-review.md` left open (two "Open", one
"worth knowing", one raised there as a suspicion) are closed on
`fix/fence-model-open-findings`; that document's new "How they were closed" section is the
record. **A saved run could be made permanently unreadable through the UI alone** — an
800 mm rail stock plus a `DefaultComponent` aimed at it, two API calls — after which /bom,
/structure and /quote all returned a raw English 400 from the cut planner and the structure
tab said *"generate a strategy to see how it is laid out"*, which is false. Not fixed by
catching the planner: `resolve_supply` skipped its feasibility gate for a ONE-member group,
so the gate now runs before the candidate count is looked at (and on the authored-sku path
too), and `fulfill()` cannot be handed a piece longer than its stock by any route.
Feasibility became a catalog+geometry predicate instead of a cut plan, so it is free at
group size one. **The gap was then computed, localized and rendered nowhere** —
`Bom.warnings`, `StructureReport.warnings`/`unresolved` were read by no JS at all, so the
200 would have been a BOM silently one line short; `js/warnings.js` now owns the single
`code + params` → sentence path and both money views render it, naming the BAY via the
structure report's tags. `no_feasible_item` splits "candidates were tried and none fits"
from `no_eligible_item`'s "nothing is a candidate". **`InfillSpec.supply` and
`Eligibility.group`** join the rejected-feature table — `group` after verifying both that
nothing reads it and that it would change the chosen SKU (grouping decides which lines are
costed together, and cut planning is not additive). **`validate_model` gained its
production caller**: `generate()` validates the resolved model, `GenerationFailure`/422 if
it fails, 2.1 us against a 0.85 ms four-bay generation, once per topology run — no caching.
That gate found a real hole on its first run (a test catalog missing the rail its panels
were eligible for). Compatibility-gate fixtures untouched.

A second review of that round found five more, all fixed. **One of the new smoke checks was
vacuous** — it read the whole structure body for `A/B1`, which the ordinary bays table
already prints, so it passed with the feature deleted; every assertion is now scoped to the
`.supply-problems` panel and the bay-naming one to the warning rows inside it (re-verified
by deletion). **The Hebrew sentence printed raw English identifiers**: a `role.*` lexicon
and a `roleWord()` beside `enumWord()` — its own namespace, because `concrete` is both a
base surface and a role — plus `{slot_key}` suppressed when it equals `{role}`. **The 422
told the user nothing and also threw**: `GenerationFailure` carries optional `code + params`
like `ReadRefused`, `fence_model_unknown_sku` names the SKU a knowledge rule got wrong,
`api.js` renders any `error.<code>`, and `btn-generate` no longer hands an async function
to `addEventListener`. **The customer sheet was getting an itemised screw count** — the
panel now follows that sheet's own describe-don't-itemise rule. **And the false "generate a
strategy" message's CLASS is closed**, not just this round's cause: an unrecognised refusal
in `structure-data.js` was mapped to "no attempt yet", and is now `"unknown"` naming its
code. 580 pytest (+25) · 126 golden scenarios (unchanged) · 106/106 smoke (+5).

**Phases 2 and 3 remain.** Phase 2: `M-SLAT`, variants, option axes, the pricing union,
the elevation read model, the panel warning codes, and multi-member eligibility selected by
running the FFD planner per candidate — plus the `select_supply` decision node, without
which a multi-member choice has no explanation (docs/v1-known-limitations.md). Phase 3:
arc-flow over multiple stock lengths and sources with remnants, via OR-Tools.
