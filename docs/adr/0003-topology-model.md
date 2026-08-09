# ADR-0003: Topology = node/run-edge graph + station-addressed events; 2.5D split

Status: accepted · 2026-08-09

## Decision
- `Node`: junction/terminal points with identity (shared corner posts). `Run`: ordered int-mm
  vertex polyline between two nodes; interior vertices are geometry with derived corner
  classification, not graph nodes.
- Arc-length stationing derived per run; all varying properties are events addressed by
  station: point events (gate, obstacle, elevation sample (s,z)) and interval events (base
  type, height intent, top-line mode). Events are never baked into geometry.
- Vertical: `ground(s)` piecewise-linear from elevation samples; fence top-line derived
  (`ground + height intent`, quantized by strategy), never stored as primary data.
- Event anchoring under geometry edits: stored internally as (segment_index, fraction) —
  proportional within originating segment; stations are a derived view. Documented product
  rule (Research A pitfall 1).
- Polyline-only horizontal geometry in V1; `segment_kind` slot reserved for arcs.
- No geometry library in the core: straight-segment station math is exact integer arithmetic
  (~10 lines). Shapely adoption deferred until arcs/offsets/polygons appear.

## Rationale
Research A: ISO 19148 linear referencing / dynamic segmentation is the converged industry
pattern; splitting geometry at attribute boundaries is the classic failure; IFC4x3 alignment
confirms the horizontal/vertical split.
