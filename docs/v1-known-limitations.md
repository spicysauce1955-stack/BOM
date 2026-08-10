# V1 known limitations

Deliberate deferrals and honest weaknesses, with the trigger that should revisit each.

## Domain

- **Interior run vertices are supported by the model but not the UI** — the editor
  creates straight runs between nodes; corners are shared nodes (which covers S03).
  Multi-segment runs with mid-run corners work through the API only.
- **Raked vs stepped is per-run resolved, per-span overridable** — no automatic mixed
  mode along one run based on local grade.
- **Gate anchored at its start station**; gates crossing run boundaries unsupported.
- **2D sheet/area cutting** (panel ripping) not implemented — only linear cutting.
  Trigger: first product with sheet semantics.
- **Substitution rules are data but not applied** during netting (suggest-only records
  exist; no automatic substitution pass). Trigger: first real substitution policy.
- **Assembly kits purchase whole**; component explosion is informational (BOM note).
- **Remnant policy lives on the catalog item**, not as a knowledge object (see
  docs/reviews/spike-review-response.md finding 14).
- **Allocation pegging is per-SKU**, not per-connection (critic finding 17) —
  every allocation lists all requirement ids of its SKU.
- **Cut-plan optimality**: FFD + LP bound; when the bound is not met the plan is
  flagged, not escalated. Trigger: real jobs where FFD misses (then CP-SAT extra,
  ADR-0007).
- ~~Impact analysis is per-run only~~ **Done (2026-08-10)**: cross-project rule impact
  preview (`POST /api/knowledge/preview-impact`, `POST /api/candidates/{id}/{v}/preview`
  + UI buttons in the review queue and knowledge editor) — regenerate-and-diff across
  all projects; previews persist nothing. Remaining refinement: diff against *historical*
  accepted quotes once BOM snapshots exist (see below).

## Learning / AI

- **Stub proposer recognizes one demo pattern** (existing-foundation corrections);
  the Claude proposer port exists but only the interpreter has a Claude adapter.
- **Candidate rules carry an AddNote action** (advisory) rather than a structured
  condition — structuring happens at review-edit time; the review UI supports
  approve/reject/scope-restrict but not condition editing.
- **Tier-2 LLM explanation polish not implemented** — Tier-1 templates only (the
  architecture reserves the port; ADR-0009).
- **Claude adapter untested against the live API** in this environment (no key);
  contract tests cover the wire schema and fallback behavior.

## Platform

- **Single-tenant, no auth, no concurrent-writer support** (SQLite WAL, one process).
  Trigger for Postgres swap: multi-tenant or concurrent editing (ADR-0008).
- **Full topology replacement on edit** (PUT) — no fine-grained topology PATCH ops;
  event re-anchoring code exists but the UI path always rewrites whole topology.
- **Strategy statuses** (accepted/superseded) are persisted but there is no
  accept/compare-alternatives workflow in the UI.
- ~~BOMs recomputed, not snapshotted~~ **Done (2026-08-10)**: persisted quotes —
  `POST /api/runs/{id}/quote` freezes requirements+BOM with inventory + knowledge
  snapshot hashes; draft→accepted→superseded lifecycle (accept supersedes the
  project's prior accepted quote, atomically); quotes panel in the BOM tab; impact
  preview now also reports the delta vs each project's accepted quote. The live
  `/bom` endpoint still recomputes (by design — it's the working view).
- **The UI is pragmatic** (mission §13). UI v2 added direct canvas manipulation,
  undo/redo, the elevation side view, and Hebrew-first RTL; still missing: touch-optimized gestures beyond big targets,
  and interior-vertex drawing in one stroke (corners are made by chaining runs or
  inserting via midpoint handles). Zoom/pan/fit added 2026-08-10 (wheel zoom,
  middle/Ctrl-drag pan, ⤢ fit).
