# Current status

Updated: 2026-08-09 — **V1 COMPLETE**

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
(mutation-verified: fails against the pre-fix code). 257 pytest + 43/43 smoke. Dispositions:
docs/reviews/units-review-response.md.
