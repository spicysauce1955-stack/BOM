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

### Display units are presentation only (2026-08-11)
The UI offers a millimetre/centimetre toggle (`web/static/js/units.js`, persisted in
`localStorage`). It converts at the presentation boundary ONLY: mm → rendered field/label
on the way out, field → int mm on the way in, so a round trip is lossless at 1 mm
(`toMm(toDisplayValue(x)) === x`, pinned in `tests/web/test_units_module.py`). Nothing
below the boundary changes: the API, the store, the rule data, and the raw-JSON editors
(knowledge actions, inventory JSON) stay int mm — those editors show the storage
representation deliberately. Locale strings carry `{u}` plus `*_mm` placeholders instead
of a hardcoded unit; `units.tu()`/`unitParams()` supply both, and backend warning params
convert by name (`*_mm`). Decision-graph prose is server-rendered, so `/explain` takes a
`units` query param alongside `lang` and `decisions/explain.py` applies the same two rules
(`*_mm` → display value, `{u}` → unit word) to its templates; the stored graph is never
touched by how it was read. Raw payload dicts inside `input_fact` lines stay verbatim mm —
they are the record, not a sentence.

### Half a face, per member (2026-08-14)
`between_frame` (`fencemodel/resolve.py`) measures a member against the frame members it
runs between, and a placement gives a CENTRELINE, so half of each frame member's face
height stands between the two centrelines and the opening. The halving is integer
division **per member** — `top//2 + base//2`, never `(top + base)//2` — and the difference
is real: two 45 mm faces halve to 22 each, where the sum halves to 45. Same discipline as
the slope-length rounding above: one named point, stated in the code and pinned by a
hand-derived literal (`tests/fencemodel/test_joint_geometry.py`), because the number lands
on a cut list where a millimetre is a piece that does not fit.

The placement itself is NOT rounded a second time: `_between_frame_extent` reads the
positions off the frame slots the same panel already resolved rather than calling
`placement_positions` again. Two calls would be two implementations of one rounding point.
