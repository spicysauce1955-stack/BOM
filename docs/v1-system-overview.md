# Fence AI — V1 system overview

Working V1 of the system described in `docs/product/architecture-foundation-v0.1.md`:
visual construction topology → explainable strategy generation → engineering demand →
fulfillment (cuts, packages, remnants, inventory) → purchase BOM, with a persisted
decision graph, typed/versioned knowledge, and an expert correction → knowledge-candidate
review loop. Python 3.12 modular monolith, FastAPI, SQLite, static SVG/JS frontend.

## What exists

| Capability | Where | Verified by |
|---|---|---|
| Topology: nodes/runs, station events (gates, base intervals, elevation samples, height intents, wall profiles, corner overrides), proportional re-anchoring | `fenceai/topology` | `tests/topology` |
| Product catalog with 6 consumption semantics + substitution records | `fenceai/catalog` | `tests/catalog` via scenarios |
| Typed knowledge (fact/hard/company/preference/heuristic/override/candidate), closed condition ASTs, owned evaluator, authority→specificity→recency precedence, surfaced conflicts, hard-tie generation failure, immutable versions, snapshot stamping, executable rule examples | `fenceai/knowledge` | `tests/knowledge` |
| Pure deterministic `generate()`: node context pass, fixed posts (corners, base transitions, gate edges, pins), closed-form span layout with preference resolution and recorded alternatives, vertical-mode resolution, wall-profile/top-line heights, knowledge-driven product selection | `fenceai/strategy` | `tests/scenarios` S01–S06, S10–S13 |
| Decision graph: append-only, acyclic by ordinal, dynamic dependency capture, per-element explanation templates, knowledge impact analysis | `fenceai/decisions` | scenario citation asserts; `/explain`, `/impact` API tests |
| Demand derivation with pegging; fulfillment: FFD cut planner (kerf, remnant-first, LP certificate), package rounding, coverage, kits, inventory allocation | `fenceai/demand`, `fenceai/fulfillment` | S07–S09, `tests/fulfillment` |
| Overrides: pin/suppress/force sku/mounting/vertical, tolerance-matched anchors, orphan surfacing | `fenceai/strategy/overrides` | S11 |
| Annotations → AI interpretation (stub default, Claude adapter opt-in) → human confirmation → first-class events with provenance | `fenceai/ai`, `fenceai/project` | S14, `tests/ai` |
| Corrections → knowledge candidates (never auto-active) → review (approve/edit/scope-restrict/reject) | `fenceai/learning` | S12 |
| Persistence: SQLite, append-only versions/runs/corrections/audit | `fenceai/store` | `tests/api` |
| REST API + SVG topology editor with strategy overlay, inspector, knowledge/review/BOM/annotation/inventory tabs | `fenceai/api`, `fenceai/web` | `tests/api`; headless-Chrome screenshots |

## Decision trail example (live output)

```
Post at station 2000 mm (gate, ground mount, POST-S-HD) on soil base. Governed by K-GATE-REINF@v1.
  ← Input fact: run_geometry {'run_id': 'run1', 'length_mm': 5000, 'slope_permille': 0}
  ← Input fact: knowledge_version {'knowledge_ref': 'K-GATE-REINF@v1'}
```

## Where the docs are

Architecture: `docs/architecture/` (module map in `01-domains.md`). Decisions:
`docs/adr/0001–0010`. Research: `docs/research/`. Behavioral contract:
`docs/scenarios/golden-scenarios.md` ⇄ `tests/scenarios/`. Review history:
`docs/reviews/`. Run instructions: `docs/v1-runbook.md`. Limits:
`docs/v1-known-limitations.md`.
