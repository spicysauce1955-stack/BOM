# ADR-0007: Closed-form layout; FFD cut planning with certificate; no solver dependency

Status: accepted · 2026-08-09

## Decision
- Span layout: closed-form `n = ceil(L/max_span)`, integer remainder spreading, rule-based
  gate/corner sub-run handling. Deterministic.
- Cut planning: FFD/BFD with kerf-aware capacity (piece+kerf against stock+kerf), remnant-
  first best-fit allocation, min_reusable_length waste threshold, LP lower-bound optimality
  certificate reported on every plan; deterministic tie-breaks (length desc, stable id).
- BOM lines carry dual quantities (engineering + purchase) with integer-ratio UoM conversion
  and per-item rounding policy; every allocation/purchase line pegs back to demand lines.
- Planning is pure over an inventory snapshot (soft allocation); reservation is a separate
  step (out of V1 scope beyond the flag).
- Objectives: lexicographic tiers with named presets; no raw user-facing weights.
- `LayoutPlanner`/`CutPlanner` are Protocols; OR-Tools CP-SAT (Apache-2.0) may be added as an
  optional extra when triggers fire (FFD misses LP bound on real jobs; coupled objectives;
  batch cutting; combinatorial layout). Not a V1 dependency (~25 MB wheel, no current need).

## Rationale
Research C: fence instances are tiny; FFD + certificate gives exactness where free; the
integration (cutting + remnants + packaging + pegging) is the value, the kernel is commodity.
