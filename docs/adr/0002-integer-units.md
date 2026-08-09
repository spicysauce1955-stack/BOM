# ADR-0002: Integer millimeters and integer cents; no floats at rest

Status: accepted · 2026-08-09

## Decision
All lengths/stations/coordinates are integer millimeters; money integer cents; quantities
integers; UoM conversions integer ratios (`Fraction`). float64 is permitted transiently
(slope %, interpolation) but every persisted or compared value is int mm. Exactly two named
tolerances: `SNAP_TOLERANCE_MM = 25` (same-point/loop closure, construction-scale) and
`NUMERIC_TOLERANCE_MM = 1` (derived-geometry comparison after rounding).

## Rationale
Research A (JTS/GEOS snap-rounding lesson, Clipper integer model: quantization beats epsilons;
exact equality, lossless serialization) and C (float kerf accumulation produces saw-infeasible
plans; hashable, reproducible plans). int32 covers ±2147 km.

## Consequences
Slope-length of a span uses `round(hypot(dx_mm, dz_mm))` — documented single rounding point.
Chord (plan) vs slope length must be named explicitly on every quantity (A pitfall 4).
