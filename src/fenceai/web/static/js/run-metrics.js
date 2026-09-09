// Run geometry — pure functions, no DOM, no state, no imports.
//
// A street landmark can be typed: select it and its angle, length and width are
// number fields (`landmark-shape.js: rectMetrics` / `rectFromMetrics`). The
// FENCE could not be. A stretch could only be dragged until the label happened
// to read about right, which is a strange thing to ask of a salesperson who has
// just measured the job and knows it is "12.4 m, turning 30 degrees". This
// module is the fence's half of that surface: read a run's length and bearing
// off its geometry, and write them back.
//
// It is the gate's half too. A gate is its own short run between two nodes, so
// typing a gate's opening and the angle it hangs at is the same operation on the
// same code — there is no second implementation to keep in step.
//
// **Two pairs of functions, because there are two kinds of run.** A run with
// exactly two points has ONE length and ONE angle, and those are the two numbers
// a person means when they say "this stretch". A run with a corner in it has one
// of each PER LEG, and offering a single "angle" for the whole thing would
// silently straighten a shape somebody drew the moment they touched the field.
// So `runMetrics` refuses anything but a straight run and `segmentMetrics` serves
// the legs one at a time — the same refusal `landmark-shape.js: metricsKind`
// makes when it gives a click-built house no angle field at all. `shapeOf` is how
// a panel asks which of the two it is looking at before it draws a single row.
//
// World coordinates are integer millimetres (ADR-0002) and y-UP (`geom.js: toPx`
// does `OY - y*SCALE`), so angles are degrees counter-clockwise from +x — the way
// a person reads a bearing off this drawing. The plan canvas is never mirrored in
// RTL, so the direction a positive angle turns is the same in both languages and
// the number in the field means one thing.

/** A run with exactly two points: one length, one angle, both typeable. */
export const STRAIGHT = "straight";

/** A run with at least one corner: one length and one angle PER LEG. */
export const POLYLINE = "polyline";

const rnd = (v) => Math.round(v);
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const isPoint = (p) => Array.isArray(p) && p.length >= 2 && isNum(p[0]) && isNum(p[1]);
const isPointList = (pts) => Array.isArray(pts) && pts.length >= 2 && pts.every(isPoint);

/** The length of one leg, rounded EXACTLY the way `geom.js: runLength` rounds it.
 *
 *  `runLength` rounds each segment to a whole millimetre and then sums, so the
 *  only way this module's number and the app's cannot differ is to round per leg
 *  here as well. Rounding the total instead would show 12402 in the panel beside
 *  a 12401 on the canvas, and a salesperson would be right to distrust both. */
const legLength = (a, b) => rnd(Math.hypot(b[0] - a[0], b[1] - a[1]));

/** Degrees counter-clockwise from +x, normalised into (-180, 180].
 *
 *  `Math.atan2` is already in that range for every input this module sees, but
 *  the normalisation is written out because the SAME range has to hold for an
 *  angle a user typed and handed back: 190 and -170 are one bearing, and the
 *  field must not flip between them across an edit that changed nothing. Due
 *  west lands on +180, not -180 — a positive number is what a person writes. */
function normDeg(deg) {
  let a = deg % 360;
  if (a <= -180) a += 360;
  if (a > 180) a -= 360;
  return a === 0 ? 0 : a;   // fold -0 so an eastward run reads 0, never "-0"
}

/** Which pair of functions this point list is for: STRAIGHT, POLYLINE, or null
 *  for something that is not a run at all (fewer than two points, a malformed
 *  point). A panel asks this FIRST — see the header for why the two are not one
 *  interchangeable case. */
export function shapeOf(points) {
  if (!isPointList(points)) return null;
  return points.length === 2 ? STRAIGHT : POLYLINE;
}

/** Read a straight run back as the numbers a person would type:
 *  `{length_mm, angle_deg, start, end}` — or null when the run has a corner in
 *  it, which is `segmentMetrics`'s job instead.
 *
 *  `angle_deg` is a float and is NOT rounded. A whole-degree field looks like a
 *  harmless display nicety and moves the far end of a 20 m run by about 17 cm,
 *  which is enough to open a visible gap at the corner the next stretch starts
 *  from — and it would make the round trip below fail where anyone can see it.
 *  Formatting for a field is the panel's job, at the field boundary.
 *
 *  A zero-length run gets null rather than `{length_mm: 0, angle_deg: 0}`: it has
 *  no bearing to report, and serving one would break the round trip (writing a
 *  zero length back is refused). Two nodes on one spot are fixed by dragging,
 *  not by typing. */
export function runMetrics(points) {
  if (shapeOf(points) !== STRAIGHT) return null;
  const start = [rnd(points[0][0]), rnd(points[0][1])];
  const end = [rnd(points[1][0]), rnd(points[1][1])];
  const length_mm = legLength(start, end);
  if (length_mm <= 0) return null;
  return {
    length_mm,
    angle_deg: normDeg((Math.atan2(end[1] - start[1], end[0] - start[0]) * 180) / Math.PI),
    start,
    end,
  };
}

/** Write a straight run's length and/or angle back: `{start, end}`, integer mm.
 *
 *  **The start is the anchor and the end is what moves.** A person typing a
 *  length is saying "this stretch is 12.4 m", not "centre a 12.4 m stretch on
 *  where this one was" — moving both ends would slide the fence off the corner
 *  it was drawn from and quietly detach it from the run before it.
 *
 *  Either figure may be omitted, and then it keeps its current value. Typing only
 *  an angle therefore PIVOTS the run about its start at its present length, which
 *  is exactly what "change the angle of the fence" means; typing only a length
 *  slides the end along the bearing it already had. An edit that supplies neither
 *  is the identity edit and gives the run back unchanged.
 *
 *  Null for a run that is not straight, a figure that is present but not finite,
 *  or a length of zero or less — a run with no length has no direction, and
 *  storing one would hand every consumer downstream a degenerate segment. */
export function runFromMetrics(points, metrics) {
  const current = runMetrics(points);
  if (!current) return null;
  const built = rebuild(current.start, current, metrics);
  return built ? { start: current.start, end: built } : null;
}

/** Read leg `index` of a run — `points[index]` to `points[index+1]` — as the same
 *  `{length_mm, angle_deg, start, end}` object.
 *
 *  This is what a run WITH corners offers instead of one angle for the whole
 *  shape: one row per leg. It works on a straight run too (leg 0 is the run),
 *  so a panel that has already decided to render rows does not need a second code
 *  path for the two-point case. Null for an index that is not a leg. */
export function segmentMetrics(points, index) {
  if (!isPointList(points)) return null;
  if (!Number.isInteger(index) || index < 0 || index + 1 >= points.length) return null;
  return runMetrics([points[index], points[index + 1]]);
}

/** Write leg `index` back, returning the WHOLE point list with that leg rebuilt.
 *
 *  **Every point after the leg is carried along by the same translation.**
 *  Lengthening the first leg of an L moves the corner AND the far end; it does
 *  not stretch the first leg past a corner that stayed put, which is what a naive
 *  implementation does and which turns an L into a Z on the first keystroke. The
 *  points BEFORE `index` never move, for the same reason `runFromMetrics` anchors
 *  the start: the part of the fence already drawn from a real corner stays on it.
 *
 *  The shape of the run is preserved that way — every other leg keeps its own
 *  length and bearing exactly, so editing one leg is an edit to one leg.
 *
 *  Null on the same refusals as `runFromMetrics`, plus an index that is not a
 *  leg. */
export function segmentFromMetrics(points, index, metrics) {
  const current = segmentMetrics(points, index);
  if (!current) return null;
  const moved = rebuild(current.start, current, metrics);
  if (!moved) return null;
  const dx = moved[0] - current.end[0], dy = moved[1] - current.end[1];
  return points.map((p, i) => {
    if (i <= index) return [rnd(p[0]), rnd(p[1])];
    if (i === index + 1) return [moved[0], moved[1]];
    return [rnd(p[0]) + dx, rnd(p[1]) + dy];
  });
}

/** The far end of a leg that starts at `start`, after applying whichever of
 *  `{length_mm, angle_deg}` the edit supplied over `current`. Null if what was
 *  supplied is not usable. Shared so the straight-run and per-leg paths cannot
 *  disagree about what an omitted field means. */
function rebuild(start, current, metrics) {
  const m = metrics ?? {};
  const length_mm = m.length_mm ?? current.length_mm;
  const angle_deg = m.angle_deg ?? current.angle_deg;
  if (!isNum(length_mm) || !isNum(angle_deg)) return null;
  if (length_mm <= 0) return null;
  const a = (normDeg(angle_deg) * Math.PI) / 180;
  return [rnd(start[0] + length_mm * Math.cos(a)),
          rnd(start[1] + length_mm * Math.sin(a))];
}
