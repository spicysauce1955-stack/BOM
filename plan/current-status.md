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
