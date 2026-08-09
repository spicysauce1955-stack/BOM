# Research A — Geometry & topology representation

*Researcher A report, 2026-08-09. Decision-oriented; synthesized into ADR-0003/0004.*

## Key findings

### Linear referencing (LRS) is the right mental model
Every mature "properties vary along a line" system (ISO 19148, Esri dynamic segmentation,
PostGIS `ST_LocateAlong`, civil stationing/chainage, IFC4x3 `IfcAlignment`, OpenDRIVE `s`)
converges on: geometry stored once as ordered vertices; a derived arc-length measure `s`;
varying attributes **never baked into geometry** but held in separate event tables — point
events (gate at s=12400) and linear events (base=concrete for s∈[8000,22500]). The overlay of
geometry × events is computed on demand. Splitting polylines at attribute boundaries (the
naive approach) causes segment proliferation and couples attribute edits to geometry surgery.

Civil wrinkle worth stealing: **station equations / re-stationing rules** — when geometry is
edited mid-run, downstream stations shift; the anchoring policy for events must be an explicit
product decision (see pitfalls).

### Vertex storage + arc-length addressing — both, layered
Store ordered vertices (user-drawn corners are semantically meaningful); derive cumulative
arc-length per vertex (cached); address everything else (attribute ranges, generated posts,
gates) by station `s`, converting via `line_interpolate_point`/`line_locate_point`
(Shapely; JTS `LengthIndexedLine`). Pure arc-length-native (baked XY endpoints) goes stale on
vertex drags; pure vertex-index addressing is too coarse (base can change mid-segment).

### 2.5D: horizontal alignment + vertical profile
Never model the 3D curve directly. Plan polyline (2D, stationed) + `ground(s)` piecewise-linear
elevation profile (point events (s,z), interpolated). Fence top-line is **derived**:
`top(s) = ground(s) + height_intent(s)` as ideal, quantized by panel strategy (racked vs
stepped is a per-interval attribute like any other). Allow elevation samples at stations that
are not plan vertices.

### Graph vs sequence: shallow graph of nodes + run-edges
Pure run lists break on T-junctions (shared posts double-counted), closed loops, and gates at
run boundaries. Use: `Node` (junction/terminal; XY, identity, post-role hints) +
`RunEdge` (ordered interior vertices between nodes). Interior vertices are geometry, not graph
nodes; corner classification is derived from turn angle with per-vertex override. networkx or
hand-rolled dict adjacency both fine at this scale.

### Regeneration: pure function + override patches, NOT a feature tree
CAD feature-trees suffer the **topological naming problem** (derived features referencing
unstable generated IDs break on upstream edits; FreeCAD spent years on it). Do not build a
dependency-graph regeneration engine. Instead:
- `strategy = generate(topology, events, rules)` — pure, deterministic, fully regenerated
  per edit (hundreds of posts → microseconds).
- User overrides = separate patch list keyed by **stable semantic anchors**
  `(run_id, station, kind)` — never generated array index or regenerated UUID. Re-apply by
  anchor matching with tolerance; non-matching overrides become explicit "orphaned override"
  warnings, not silent corruption.

**This is the single most important finding**: it is the difference between an editable
strategy that survives edits and one that resets on every drag.

### Precision: int mm at rest, float64 in flight
- JTS/GEOS answer to robustness was quantization (snap-rounding/OverlayNG), not epsilons.
  Clipper/VLSI use 64-bit ints and are essentially unbreakable.
- Sites ≤ hundreds of meters → representation precision is not the risk; equality, snapping,
  drift are.
- **Canonical stored coordinates & stations: integer millimeters** (int32 spans ±2147 km).
  Exact equality, lossless diff-able serialization, trivial hashing.
- Compute in float64 (mm-as-double exact to 2^53), round back at the boundary.
- Exactly two named tolerances: snap tolerance (~25 mm, construction-scale: same-point/loop
  closure) and numeric tolerance (~0.5 mm, derived-geometry comparisons). No scattered 1e-6s.

## Library verdicts (Python 3.12)

| Library | License | Verdict |
|---|---|---|
| Shapely 2.x (GEOS) | BSD-3 (GEOS LGPL-2.1 dyn-linked, safe) | **Adopt** — `line_locate_point`/`interpolate`/`substring` are the whole LRS math. 2D-only; fine given 2.5D split. |
| JTS | EPL/EDL | Borrow concepts (LengthIndexedLine, PrecisionModel docs), not code (JVM). |
| PostGIS LRS | GPL-2 (server-side) | Optional later; keep LRS logic in Python regardless. |
| networkx | BSD-3 | Adopt or hand-roll (graph is tiny). |
| CGAL | mostly GPL | **Reject** — license risk, overkill. |
| Open CASCADE / pythonocc | LGPL-2.1+exc | **Reject for core**; revisit only for 3D/STEP export. |
| IfcOpenShell | LGPL-3 | Roadmap export adapter only; borrow `IfcAlignment` schema shape. |
| Clipper2 | Boost-1.0 | Not needed now; precedent for int coords. |

Bottom line: **Shapely + (optional) networkx is the whole geometry stack**; the valuable
imports from heavyweight systems are schemas and disciplines, not code.

## Pitfalls
1. Unspecified re-stationing semantics for events under vertex edits (#1 latent-bug source in
   LRS systems). Recommendation: anchor events proportionally within their originating segment
   (internally (segment index, fraction); stations as derived view).
2. Baking attributes into geometry.
3. Referencing generated geometry from user data (topological naming problem).
4. Chord-length vs slope-length confusion: panels cut to *slope* length on racked runs; posts
   stationed in *plan*. BOMs wrong by cos(grade) otherwise (~1.5% at 10°).
5. Mixed-unit epsilons.
6. Shapely silently ignoring Z.
7. Float coordinates in persistence/undo.

## Open trade-offs
- Arcs in plan: polyline-only for V1, reserve a `segment_type` slot in the schema.
- Event anchoring: proportional-within-segment (drawn) vs absolute-station (typed values);
  could differ per event source at cost of complexity.
- Overrides as patch-list-over-regeneration (recommended) vs strategy as first-class editable
  document with suggested regeneration.
- Persistence: Postgres M-geometries vs plain JSON int-mm (JSON keeps one brain).
