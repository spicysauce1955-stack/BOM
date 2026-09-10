// Gate geometry — pure functions, no DOM, no state, no imports.
//
// A gate on the plan is a station and a width, and until Generate runs the
// drawing shows neither: a plain segment with no opening in it and no hint of
// which way it swings. The user's complaint was exactly that — "gate placement
// should be shown on the map layout (with its width and open direction — the
// placement is not sufficient for an opening fence)" — and the fix is that the
// plan draws the HOLE and the SWING live from the topology event, before any
// generation, for single-swing, double-swing and sliding gates alike.
//
// All of that is coordinate arithmetic with an inverse, so it lives here and is
// tested in node rather than by aiming a mouse at an SVG.
//
// THE ONE CONVENTION EVERYTHING HERE DEPENDS ON
// ---------------------------------------------
// World coordinates are integer millimetres (ADR-0002) and y-UP (`geom.js:
// toPx` does `OY - y*SCALE`). A run is a polyline `[[x,y], ...]` from its start
// node through its interior vertices to its end node, and a STATION is arc
// length in mm from the start of that polyline.
//
// "left" and "right" are relative to the run's OWN DIRECTION OF TRAVEL. With
// the unit direction `d = (ux, uy)`:
//
//     left  = (-uy,  ux)        right = ( uy, -ux)
//
// That is why the stored fact is run-relative — `side: "left"` — and not a
// sentence. "Opens toward the house" is not storable: the house can move, the
// run can be redrawn end-for-end, and the sentence has to be re-derived either
// way. So the topology stores the side, and READING it out is a separate act:
// `sideProbe` hands a point to a landmark hit test to get "toward the house",
// and `screenSideOf` gives the honest fallback ("toward the top of the
// drawing") when there is no landmark on that side. The plan canvas is never
// mirrored in RTL (CLAUDE.md), so that fallback is a description the reader can
// verify by looking, in either language.
//
// Positions come back as integer millimetres; DIRECTIONS come back as floats.
// Rounding a unit vector to integers would collapse it to one of nine values
// and quantise every angle on the drawing. Every function returns `null` rather
// than throwing, because these run inside a render loop driven by a topology
// event: a half-drawn gate must leave the rest of the plan on the screen.
//
// `pointAtStationOn` is `geom.js: pointAtStation` with the `state` lookup
// removed — it takes the point list instead of a run id. Duplicating those ten
// lines is the price of this module importing nothing, and it is worth paying:
// a module that reaches into `state` cannot be run in node, and the whole
// reason this file exists is that it can be.

// The sweep of a leaf, in degrees. A gate is drawn CLOSED with an arc showing
// where it goes, and the arc is a quarter circle: that is the convention on
// every architectural plan, and 90 degrees is what a leaf that clears its own
// opening actually does.
export const SWING_DEG = 90;

// Points along that quarter circle, endpoints included. Eight 11.25-degree
// steps read as a curve at every zoom this canvas offers and stay small enough
// to be a sane thing to put in an SVG `points` attribute.
export const ARC_POINTS = 9;

const rnd = (v) => Math.round(v);
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const isPoint = (p) => Array.isArray(p) && p.length >= 2 && isNum(p[0]) && isNum(p[1]);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi));

/** The polyline, or null when it is not one. Two valid points is the minimum:
 *  one point is a node, not a run. */
function polyline(points) {
  if (!Array.isArray(points) || points.length < 2) return null;
  return points.every(isPoint) ? points : null;
}

/** Per-segment lengths, each ROUNDED — mirroring `geom.js: runLength` and
 *  `anchorFor` exactly. Stations are compared against these numbers all over
 *  the app; summing raw hypotenuses here would put this module a millimetre or
 *  two out of step with the anchors it is drawing. */
function segLengths(points) {
  const lens = [];
  for (let i = 0; i + 1 < points.length; i++)
    lens.push(rnd(Math.hypot(points[i + 1][0] - points[i][0],
                             points[i + 1][1] - points[i][1])));
  return lens;
}

const totalOf = (lens) => lens.reduce((a, b) => a + b, 0);

/** The point at `stationMm` along the polyline, integer mm, or null.
 *
 *  A station past either end is CLAMPED to that end rather than extrapolated —
 *  same as `geom.js: pointAtStation`, and for the same reason the opening is
 *  clamped below: the drawing may not show fence where there is none. */
export function pointAtStationOn(points, stationMm) {
  const pts = polyline(points);
  if (!pts || !isNum(stationMm)) return null;
  const lens = segLengths(pts);
  let s = Math.max(0, stationMm);
  for (let i = 0; i < lens.length; i++) {
    if (s <= lens[i] || i === lens.length - 1) {
      const t = lens[i] ? Math.min(s / lens[i], 1) : 0;
      return [rnd(pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t),
              rnd(pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)];
    }
    s -= lens[i];
  }
  return [rnd(pts[pts.length - 1][0]), rnd(pts[pts.length - 1][1])];
}

/** The UNIT direction `[ux, uy]` of the segment the station falls on, or null
 *  for a polyline with no length at all.
 *
 *  Floats, deliberately: this is a direction, not a position (see the header).
 *
 *  At a vertex the answer is the segment the station ENTERS — the one ahead of
 *  it. Dragging a gate along an L then reads the near leg right up to the
 *  corner and the far leg from the corner onward, with no station at which the
 *  swing symbol belongs to the segment behind. Zero-length segments are skipped
 *  rather than divided by. */
export function directionAtStationOn(points, stationMm) {
  const pts = polyline(points);
  if (!pts || !isNum(stationMm)) return null;
  const lens = segLengths(pts);
  const total = totalOf(lens);
  if (total <= 0) return null;
  let s = clamp(stationMm, 0, total);
  let last = -1;
  for (let i = 0; i < lens.length; i++) {
    if (lens[i] <= 0) continue;
    last = i;
    if (s < lens[i]) return unitOfSegment(pts, i);
    s -= lens[i];
  }
  return last < 0 ? null : unitOfSegment(pts, last);
}

/** Segment `i`'s unit direction, from the RAW hypotenuse — the rounded length
 *  is for comparing stations, not for normalising a vector. */
function unitOfSegment(points, i) {
  const dx = points[i + 1][0] - points[i][0];
  const dy = points[i + 1][1] - points[i][1];
  const len = Math.hypot(dx, dy);
  return len > 0 ? [dx / len, dy / len] : null;
}

/** The opening: `{a, b, aStation, bStation}`, or null for a non-positive width
 *  or a polyline that is not one.
 *
 *  `a` is the point at the start station, `b` the point at `start + width`,
 *  both integer mm, and BOTH STATIONS ARE CLAMPED TO THE RUN.
 *
 *  The clamp is not cosmetic. `strategy/generator.py` already does exactly this
 *  — `ge = min(gs + opening, length)` — and raises `gate_past_run_end` when it
 *  bites. A drawing that did not clamp would show an opening the generator
 *  refuses to build, and the salesperson would be looking at a hole that is not
 *  in the plan. The picture and the plan agree about where the hole is, and
 *  when the hole is too small for the gate, the warning is what says so.
 *
 *  A gate placed at or past the very end therefore comes back with `a` equal to
 *  `b` — a zero-width opening, which is the truth about that placement, and
 *  which the swing and slide symbols below refuse rather than draw. */
export function openingEdges(points, startStationMm, widthMm) {
  const pts = polyline(points);
  if (!pts || !isNum(startStationMm) || !isNum(widthMm) || widthMm <= 0) return null;
  const total = totalOf(segLengths(pts));
  const aStation = clamp(rnd(startStationMm), 0, total);
  const bStation = clamp(aStation + rnd(widthMm), 0, total);
  const a = pointAtStationOn(pts, aStation);
  const b = pointAtStationOn(pts, bStation);
  if (!a || !b) return null;
  return { a, b, aStation, bStation };
}

/** The unit normal of `direction` on `side`: `[-uy, ux]` for "left" and
 *  `[uy, -ux]` for "right" (the header's one convention). Null for a direction
 *  that is not a finite non-zero vector, or a side that is not one of the two.
 *
 *  The input is normalised first, so a caller may hand in any vector along the
 *  line — a chord, a raw delta — and still get a unit normal back. */
export function normalOf(direction, side) {
  if (!isPoint(direction)) return null;
  const len = Math.hypot(direction[0], direction[1]);
  if (!(len > 0)) return null;
  const ux = direction[0] / len, uy = direction[1] / len;
  if (side === "left") return [-uy, ux];
  if (side === "right") return [uy, -ux];
  return null;
}

/** The direction the OPENING is drawn in: the unit chord `a -> b`.
 *
 *  Every symbol in this module hangs off this rather than off the run direction
 *  at the start station, and the difference only shows on a gate that spans a
 *  corner. There the chord cuts across the corner, which is where the leaf and
 *  the probe belong: a normal taken from the incoming leg would put the leaf at
 *  right angles to one half of an opening it has to clear, and could swing it
 *  into the other leg. On a straight run — every gate a salesperson actually
 *  places — the chord IS the run direction, exactly.
 *
 *  A zero-length opening has no chord, so it falls back to the run direction,
 *  and the callers that need a real leaf refuse it anyway. */
function openingDirection(points, edges) {
  const dx = edges.b[0] - edges.a[0], dy = edges.b[1] - edges.a[1];
  const len = Math.hypot(dx, dy);
  if (len > 0) return [dx / len, dy / len];
  return directionAtStationOn(points, edges.aStation);
}

/** A point `distMm` off the middle of the opening on `side`, integer mm, or
 *  null on bad input.
 *
 *  This is what turns a stored `left` into a sentence. The caller hands the
 *  point to a point-in-polygon test over the landmarks and finds out what is on
 *  that side of the fence — the house, the pool, nothing — so the gate reads as
 *  "opens toward the house" without the topology ever having stored a claim
 *  about a house that may since have moved. Nothing on that side is not a
 *  failure: it is `screenSideOf`'s cue. */
export function sideProbe(points, startStationMm, widthMm, side, distMm) {
  const pts = polyline(points);
  if (!pts || !isNum(distMm)) return null;
  const edges = openingEdges(pts, startStationMm, widthMm);
  if (!edges) return null;
  const n = normalOf(openingDirection(pts, edges), side);
  if (!n) return null;
  const mx = (edges.a[0] + edges.b[0]) / 2, my = (edges.a[1] + edges.b[1]) / 2;
  return [rnd(mx + n[0] * distMm), rnd(my + n[1] * distMm)];
}

/** The architectural swing symbol as pure geometry, or null.
 *
 *      { pivot,   // [x,y] the hinged edge: "start" -> a, "end" -> b
 *        free,    // [x,y] the other edge of the opening
 *        tip,     // [x,y] pivot + the opening's length along the side normal
 *        arc }    // [[x,y], ...] ARC_POINTS along the quarter circle
 *                 //       free -> tip, centred on pivot
 *
 *  The renderer draws the leaf CLOSED (`pivot` -> `free`) and the arc shows
 *  where it goes. That is the convention on every architectural plan and it is
 *  what makes "which way does this open?" answerable at a glance — a leaf drawn
 *  open instead hides the opening it came out of.
 *
 *  The radius is the leaf's own length, `|pivot - free|`, so the arc starts
 *  exactly at `free` and ends exactly at `tip`; both endpoints are pinned to
 *  those two points rather than recomputed, so no rounding can open a gap
 *  between the leaf and its arc.
 *
 *  A DOUBLE gate is TWO CALLS to this function, each over its OWN HALF of the
 *  opening and both with the same `side`:
 *
 *      swingLeaf(pts, start,       width / 2, "start", side)
 *      swingLeaf(pts, start + w/2, width / 2, "end",   side)
 *
 *  Half, not the full width twice: each leaf of a double gate spans half the
 *  hole, and two full-width leaves would be drawn straight through each other
 *  and swing a metre past the posts. Called this way the two free edges land on
 *  the same point — the middle of the opening, which is where the leaves meet
 *  when the gate is shut.
 *
 *  There is deliberately no `doubleSwingLeaves`: two leaves are two leaves, the
 *  caller already loops over what it draws, and a second function would only be
 *  a second place for the side convention to drift. */
export function swingLeaf(points, startStationMm, widthMm, hinge, side) {
  const pts = polyline(points);
  if (!pts) return null;
  if (hinge !== "start" && hinge !== "end") return null;
  const edges = openingEdges(pts, startStationMm, widthMm);
  if (!edges) return null;
  const pivot = hinge === "start" ? edges.a : edges.b;
  const free = hinge === "start" ? edges.b : edges.a;
  const radius = Math.hypot(free[0] - pivot[0], free[1] - pivot[1]);
  if (!(radius > 0)) return null;          // a clamped-away opening has no leaf
  const n = normalOf(openingDirection(pts, edges), side);
  if (!n) return null;
  const tip = [rnd(pivot[0] + n[0] * radius), rnd(pivot[1] + n[1] * radius)];
  // Sweep the SHORT way from the closed leaf to the open one. `tip - pivot` is
  // perpendicular to `free - pivot` by construction, so this is +90 degrees for
  // one hinge and -90 for the other, and the arc always lies on the side the
  // gate opens toward.
  const a0 = Math.atan2(free[1] - pivot[1], free[0] - pivot[0]);
  const a1 = Math.atan2(tip[1] - pivot[1], tip[0] - pivot[0]);
  let d = a1 - a0;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d <= -Math.PI) d += 2 * Math.PI;
  const arc = [];
  for (let i = 0; i < ARC_POINTS; i++) {
    const a = a0 + (d * i) / (ARC_POINTS - 1);
    arc.push([rnd(pivot[0] + radius * Math.cos(a)),
              rnd(pivot[1] + radius * Math.sin(a))]);
  }
  arc[0] = [free[0], free[1]];
  arc[ARC_POINTS - 1] = [tip[0], tip[1]];
  return { pivot: [pivot[0], pivot[1]], free: [free[0], free[1]], tip, arc };
}

/** The retraction arrow for a sliding or cantilever gate: `{from, to}`, integer
 *  mm, or null.
 *
 *  `from` is the opening edge the leaf retracts past ("start" -> `a`,
 *  "end" -> `b`) and `to` is that point carried a further `widthMm` ALONG THE
 *  RUN in that direction — along the polyline, so an arrow that reaches a
 *  corner turns with the fence instead of leaving it.
 *
 *  It is drawn at its TRUE length, and it is clamped to the run's own ends. A
 *  sliding gate needs a clear span of fence to retract into; when there is not
 *  enough, the arrow comes back visibly short of its own opening, and that is
 *  the point. Shortening it to a token stub would hide the one thing this
 *  symbol exists to show. */
export function slideArrow(points, startStationMm, widthMm, slidesTo) {
  const pts = polyline(points);
  if (!pts) return null;
  if (slidesTo !== "start" && slidesTo !== "end") return null;
  const edges = openingEdges(pts, startStationMm, widthMm);
  if (!edges) return null;
  const reach = rnd(widthMm);
  const from = slidesTo === "start" ? edges.a : edges.b;
  const toStation = slidesTo === "start"
    ? edges.aStation - reach
    : edges.bStation + reach;
  const to = pointAtStationOn(pts, toStation);   // clamps at both ends
  if (!to) return null;
  return { from: [from[0], from[1]], to };
}

/** Which way that side points ON THE DRAWING: "up" | "down" | "left" | "right",
 *  or null for bad input.
 *
 *  The world is y-up and the canvas draws y down, so a normal with a POSITIVE y
 *  points toward the TOP of the drawing. Getting that backwards is a one-word
 *  error that survives every test that only checks the vector.
 *
 *  This is the honest fallback for naming a side when `sideProbe` found no
 *  landmark there. It is a weaker sentence than "toward the house" and it is
 *  deliberately preferred to "left"/"right", which would be a claim about the
 *  run's direction of travel that no reader of the drawing can see. The plan
 *  canvas is never mirrored in RTL, so "toward the top of the drawing" means
 *  the same thing in Hebrew and in English.
 *
 *  A normal at exactly 45 degrees is named by its horizontal component. The tie
 *  has to break somewhere; breaking it consistently means a gate does not flip
 *  its description as a run is nudged through the diagonal. */
export function screenSideOf(direction, side) {
  const n = normalOf(direction, side);
  if (!n) return null;
  if (Math.abs(n[0]) >= Math.abs(n[1])) return n[0] > 0 ? "right" : "left";
  return n[1] > 0 ? "up" : "down";
}
