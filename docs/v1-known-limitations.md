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
- **Layout is blind to the cut plan.** The two never speak, so nobody is told when a
  small layout change would buy far less material. S07 is the standing example: two
  1500 mm bays need four 3 m bars (1500+3+1500 > 3000, so one rail per bar and a
  1497 mm offcut each — 12 m of stock for 6 m of rail), while 1498 mm bays fit two per
  bar, and three 1000 mm bays need six rails but only **three** bars. More rails, less
  aluminium, one more post. The planner already computes the waste and `layout_segment`
  already emits a rejected alternative; nothing joins them up. This is an *advisory*,
  never an automatic relayout — span width is the user's design decision, and material
  cost is one input to it. Trigger: the first job where a customer is quoted materially
  more than a neighbouring layout would have cost.
- **No workshop model.** The system knows what a fence is made of but not what the shop
  can *do* to make it — the operations available (cut, drill, splice, weld, bend,
  coat), their rules (max handled length, minimum offcut, which joins are permitted
  where), their costs (setup plus per-unit) and their consequences. Today the one piece
  of process knowledge in the system, `DivisibleLinear.kerf_mm`, sits on the *product*,
  when a kerf is a property of the **saw**. Until this exists, "fabricate it" can never
  be an alternative to "buy it", labour is invisible in every comparison, and a rule
  like "we never splice a rail under 2 m" has nowhere to live. Trigger: the first
  decision that turns on shop capability rather than on catalogue contents — most
  likely a made-to-measure panel the shop could either buy or build. See the extension
  seam in `docs/superpowers/specs/2026-08-12-fence-model-design.md`, which is written so
  this can be added without reworking eligibility.
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
