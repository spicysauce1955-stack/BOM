# ADR-0004: Strategy = pure function + anchored override patches; full regeneration

Status: accepted · 2026-08-09

## Decision
`generate(topology, knowledge_snapshot, catalog, overrides, policy) -> (strategy, decision_graph, warnings)`
is pure and deterministic. Every edit fully regenerates (no incremental patching of strategy).
User overrides are a separate patch list keyed by stable semantic anchors
`(run_id, station|interval, kind)` — never generated element IDs or array indices. On
regeneration, overrides re-apply by anchor matching within tolerance; non-matching overrides
become explicit `orphaned_override` warnings.

Dependency capture during generation feeds the decision graph and impact analysis
(reverse-dependency walk → regenerate-and-diff), not an incremental recomputation engine.

## Rationale
Research A: CAD topological-naming problem — referencing generated geometry from user data is
the canonical way editable parametric systems rot. Research B (Salsa lesson): track
dependencies for invalidation; full re-runs are milliseconds at fence scale.

## Consequences
The foundation doc's "recompute only affected dependencies where possible" (§7) is satisfied
via impact *analysis* + cheap full regeneration, not partial recompute. Multiple strategies per
topology are natural (pure function + differing policies/overrides).
