// Landmark geometry — pure functions, no DOM, no state, no imports.
//
// "The property" step asks the salesperson for the things that are NOT the
// fence: the house, the street it faces, a tree in the way, the pool nobody
// wants a gate next to. Each of those is drawn with a different GESTURE — a
// house is walked corner by corner, a street is dragged along its centre line,
// a tree is dragged out from its trunk — and each of those gestures is a
// coordinate transform with an inverse. Both live here, so the whole edit
// surface is testable in node rather than by aiming a mouse at an SVG.
//
// **There is only ONE shape in the storage model.** `project/model.py: Landmark`
// is a point list with a `closed` flag, and that is deliberate: a second
// geometry type would buy nothing but a second set of edge cases in every
// renderer, every hit test and every serialiser. So a street is a RECTANGLE
// (a road has width) and a tree is a POLYGON that reads as a circle. The
// "metrics" functions below are how that stays editable anyway: they INVERT a
// point list back into the numbers a person would type — angle, length, width,
// radius — and rebuild the points from them. Nothing is stored twice, so
// nothing can disagree.
//
// Everything is integer millimetres (ADR-0002). World coordinates are y-UP
// (`geom.js: toPx` does `OY - y*SCALE`), so a positive angle turns
// counter-clockwise the way a person expects it to on the drawing.

// The registry, mirroring the backend's LANDMARK_KINDS. Adding a kind is a
// one-line change in three places (here, GESTURE, the backend tuple) and needs
// no schema discussion — that seam is the point of the single shape type.
export const LANDMARK_KINDS = ["house", "street", "sidewalk", "pool", "tree",
                              "boundary", "other"];

// A toolbar with seven buttons is a toolbar nobody reads. The two things every
// job has get a button; the rest live behind "Other…", which is a statement
// about frequency and not about importance.
export const PRIMARY_KINDS = ["house", "street"];
export const OTHER_KINDS = ["sidewalk", "pool", "tree", "boundary", "other"];

// How each kind is DRAWN. Four gestures, because four is how many distinct
// things a person is actually doing:
//   polygon — click corner, corner, corner: a building has as many corners as
//             it has, and a drag can only ever describe four of them
//   band    — drag along the road's centre line, at any angle; the width and
//             both ends are grips on the drawing afterwards
//   rect    — drag a box, the oldest gesture on the canvas
//   circle  — drag from the middle outward, which is where a tree's trunk is
export const GESTURE = {
  house: "polygon", street: "band", sidewalk: "band",
  pool: "rect", tree: "circle", boundary: "rect", other: "rect",
};

// A band's width when the drag gave no width to use — i.e. when the gesture was
// a straight line ALONG the road rather than a box around it. A residential
// street is about 4 m of carriageway and a pavement about 1.5 m; being roughly
// right beats being zero, because a zero-width street draws as a line and then
// the width field has nothing to edit. It is never imposed on a drag that
// stated a width of its own, which was the complaint that produced the box
// gesture above.
export const DEFAULT_WIDTH_MM = { street: 4000, sidewalk: 1500 };

// A tree at 16 sides reads as round at every zoom this canvas offers and stays
// small enough to be a sane thing to store, drag and diff.
export const TREE_SIDES = 16;

// Below this, a gesture was not deliberate. A stray click with a tool active
// must not leave an invisible 3 mm building on the drawing that the office
// person then has to ask about.
export const MIN_MM = 300;

const rnd = (v) => Math.round(v);
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const isPoint = (p) => Array.isArray(p) && p.length >= 2 && isNum(p[0]) && isNum(p[1]);

/** Which gesture draws this kind. Unknown kinds fall back to a box so a caller
 *  that has not heard of a new kind still draws SOMETHING; `shapeFor` is the
 *  one that refuses them, because that is where a bad kind would otherwise
 *  reach the API and 422 far away from the gesture that caused it. */
export function gestureFor(kind) {
  return GESTURE[kind] ?? "rect";
}

/** The shape a press-drag-release describes: `{points, closed}` or null.
 *
 *  Null means "that was not a landmark": no drag, an unknown kind, a gesture
 *  too small to be deliberate — and a POLYGON kind, because a house is built
 *  click-by-click and a drag can only describe a box. Callers hand those to
 *  `polygonFromClicks` instead. */
export function shapeFor(kind, from, to, minMm = MIN_MM) {
  if (!isPoint(from) || !isPoint(to)) return null;
  if (!LANDMARK_KINDS.includes(kind)) return null;
  const gesture = gestureFor(kind);
  if (gesture === "polygon") return null;
  const x0 = rnd(from[0]), y0 = rnd(from[1]);
  const x1 = rnd(to[0]), y1 = rnd(to[1]);
  // Per AXIS, not both at once: a street IS a long thin thing, and demanding
  // 300 mm of drift in the short direction would refuse the most ordinary
  // gesture in this tool.
  if (Math.abs(x1 - x0) < minMm && Math.abs(y1 - y0) < minMm) return null;
  if (gesture === "band") {
    // The drag IS the centre line, at whatever angle it was dragged, and the
    // band gets the default width around it. The width is then a grip on the
    // drawing (`dragBandGrip`), not a second reading of the same drag.
    //
    // This replaces a box gesture — "drag a box and that box is the street" —
    // which answered "the street has a fixed width" and created the next
    // complaint: a box is axis-aligned, so a diagonal drag drew a fat square
    // rather than a street running at that angle, and the only way to angle
    // one was to type degrees into the side panel. "Make the street placement
    // more flexible (angles and such)".
    //
    // The bearing snaps to the nearest 15° when the drag is within a few
    // degrees of one, so a street meant to run square to the page comes out
    // square without anybody holding a key, and any other angle is untouched.
    const end = snapBearing([x0, y0], [x1, y1]);
    const rect = bandRect([x0, y0], end, DEFAULT_WIDTH_MM[kind] ?? 1500);
    return rect ? { points: rect, closed: true } : null;
  }
  if (gesture === "circle") {
    // The drag starts at the trunk and pulls out to the canopy, so the
    // distance dragged is the RADIUS and the press point is the centre.
    const radius = rnd(Math.hypot(x1 - x0, y1 - y0));
    if (radius < minMm) return null;
    const pts = circlePolygon([x0, y0], radius);
    return pts ? { points: pts, closed: true } : null;
  }
  // "rect": the axis-aligned box the drag spanned. A person drags from
  // whichever corner they started at, so a backwards drag has to describe the
  // same building — the corner ORDER differs, the outline does not.
  return { points: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], closed: true };
}

// How close to a round bearing a drag has to be before it snaps onto it. Wide
// enough that "roughly along the page" lands exactly along it, narrow enough
// that a street deliberately at 20° stays at 20°.
export const BEARING_STEP_DEG = 15;
export const BEARING_SNAP_DEG = 4;

// A street narrower than this is a line again, and a line cannot be grabbed.
export const MIN_BAND_WIDTH_MM = 500;

/** `to`, turned onto the nearest multiple of `stepDeg` around `from` when it is
 *  within `tolDeg` of one — otherwise `to` unchanged. The LENGTH is kept either
 *  way: snapping the angle must not also shorten the street. Integer mm out. */
export function snapBearing(from, to, stepDeg = BEARING_STEP_DEG, tolDeg = BEARING_SNAP_DEG) {
  if (!isPoint(from) || !isPoint(to)) return to;
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const len = Math.hypot(dx, dy);
  if (len <= 0) return [rnd(to[0]), rnd(to[1])];
  const deg = (Math.atan2(dy, dx) * 180) / Math.PI;
  const nearest = Math.round(deg / stepDeg) * stepDeg;
  if (Math.abs(deg - nearest) > tolDeg) return [rnd(to[0]), rnd(to[1])];
  const a = (nearest * Math.PI) / 180;
  return [rnd(from[0] + len * Math.cos(a)), rnd(from[1] + len * Math.sin(a))];
}

/** A band read back as its CENTRE LINE: `{a, b, width_mm}`, or null when the
 *  four points are not a rectangle.
 *
 *  `a` is the middle of the `p3 -> p0` end and `b` the middle of `p1 -> p2`,
 *  which is `bandRect`'s corner contract read backwards — so
 *  `bandRect(a, b, width_mm)` rebuilds the same band. */
export function bandAxis(points) {
  if (!rectMetrics(points)) return null;
  const [p0, p1, p2, p3] = points;
  const mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
  return {
    a: mid(p0, p3),
    b: mid(p1, p2),
    width_mm: rnd(Math.hypot(p2[0] - p1[0], p2[1] - p1[1])),
  };
}

/** Where a band's three grips sit, in mm: one on each end of the centre line,
 *  and one on the middle of a long edge for the width. Null for a shape that is
 *  not a band. */
export function bandGrips(points) {
  const axis = bandAxis(points);
  if (!axis) return null;
  const [p0, p1] = points;
  return { a: axis.a, b: axis.b, width: [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2] };
}

/** `pointer`, projected onto the ray `from -> through`, when the bearing of
 *  `from -> pointer` is within `tolDeg` of that ray's — otherwise null.
 *
 *  This is what lets a street somebody TYPED at 12° be stretched without being
 *  re-snapped to 15°: pulling an end roughly along the street keeps the street's
 *  own angle exactly, and only a drag that genuinely turns it is offered the
 *  round bearings. */
function alongOwnBearing(from, through, pointer, tolDeg = BEARING_SNAP_DEG) {
  const ux = through[0] - from[0], uy = through[1] - from[1];
  const len = Math.hypot(ux, uy);
  const px = pointer[0] - from[0], py = pointer[1] - from[1];
  const plen = Math.hypot(px, py);
  if (len <= 0 || plen <= 0) return null;
  const cos = (ux * px + uy * py) / (len * plen);
  const deg = (Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI;
  if (deg > tolDeg) return null;
  const along = (ux * px + uy * py) / len;
  return [rnd(from[0] + (ux / len) * along), rnd(from[1] + (uy / len) * along)];
}

/** Which landmark kinds show their grips, for the armed `tool` on road step
 *  `step` (`null` when the view has no road — the whole app).
 *
 *    - the street or sidewalk tool: that kind, on any step that offers it;
 *    - the select tool: every band kind, but only where the property is being
 *      edited — the salesperson's `property` step, or a view with no road;
 *    - anything else: none. Grips are live hit targets, so a grip left on the
 *      side-view step would let a click meant for the ground reshape the street.
 *
 *  Decided from state, not from whether a panel happens to be laid out: the
 *  road arms a step's tool BEFORE it scopes the screen, so a layout read at
 *  `tool-changed` saw the previous step and showed the grips one step late. */
export function gripKindsFor(tool, step) {
  const bands = LANDMARK_KINDS.filter((k) => GESTURE[k] === "band");
  if (bands.includes(tool)) return [tool];
  if (tool === "select" && (step === "property" || step == null)) return bands;
  return [];
}

/** The band after dragging one grip to `pointer`, from the band as it was when
 *  the drag STARTED (`origin`) — a delta from the start, never an accumulation
 *  of rounded moves.
 *
 *    grip "a" / "b" — that end of the centre line goes to the pointer and the
 *                     other end stays put: the street swings and stretches
 *                     about its far end. Pulled roughly along the street it
 *                     keeps its own angle exactly; turned, it is
 *                     bearing-snapped like drawing one.
 *    grip "width"   — the band keeps its centre line and becomes as wide as
 *                     twice the pointer's distance from it, so it grows on
 *                     both sides at once and never drifts off the road.
 *
 *  Returns `origin` unchanged for a drag that would leave no street (ends
 *  closer than `MIN_MM`) — refusing a bad drop rather than saving a sliver. */
export function dragBandGrip(origin, grip, pointer) {
  const axis = bandAxis(origin);
  if (!axis || !isPoint(pointer)) return origin;
  let { a, b, width_mm: width } = axis;
  if (grip === "a") a = alongOwnBearing(b, a, pointer) ?? snapBearing(b, pointer);
  else if (grip === "b") b = alongOwnBearing(a, b, pointer) ?? snapBearing(a, pointer);
  else if (grip === "width") {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const len = Math.hypot(dx, dy);
    if (len <= 0) return origin;
    const off = Math.abs(((pointer[0] - a[0]) * dy - (pointer[1] - a[1]) * dx) / len);
    width = Math.max(MIN_BAND_WIDTH_MM, rnd(off * 2));
  } else return origin;
  if (Math.hypot(b[0] - a[0], b[1] - a[1]) < MIN_MM) return origin;
  return bandRect(a, b, width) ?? origin;
}

/** The rectangle of width `widthMm` centred on the segment `from -> to`.
 *
 *  The corner ORDER is a contract the rest of this module depends on:
 *  `p0 -> p1` is always the LENGTH axis and `p1 -> p2` the WIDTH axis, so
 *  `rectMetrics` can read a rectangle back without guessing which pair of
 *  sides the user thinks of as "the length of the road". */
export function bandRect(from, to, widthMm) {
  if (!isPoint(from) || !isPoint(to) || !isNum(widthMm)) return null;
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const len = Math.hypot(dx, dy);
  if (len <= 0) return null;   // a road with no length is not a road
  const half = widthMm / 2;
  // unit normal, turned counter-clockwise from the direction of travel
  const nx = (-dy / len) * half, ny = (dx / len) * half;
  return [
    [rnd(from[0] + nx), rnd(from[1] + ny)],
    [rnd(to[0] + nx), rnd(to[1] + ny)],
    [rnd(to[0] - nx), rnd(to[1] - ny)],
    [rnd(from[0] - nx), rnd(from[1] - ny)],
  ];
}

/** A regular `sides`-gon: first vertex at angle 0, going counter-clockwise.
 *  A tree is this, not a `<circle>`: see the header — one shape type. */
export function circlePolygon(center, radiusMm, sides = TREE_SIDES) {
  if (!isPoint(center) || !isNum(radiusMm) || radiusMm < 1) return null;
  const n = Math.max(3, Math.round(sides));
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = (2 * Math.PI * i) / n;
    out.push([rnd(center[0] + radiusMm * Math.cos(a)),
              rnd(center[1] + radiusMm * Math.sin(a))]);
  }
  return out;
}

/** Read a 4-corner rectangle back as the numbers a person would type:
 *  `{center, angle_deg, length_mm, width_mm}`, or null if these four points
 *  are not a rectangle.
 *
 *  The tolerance is proportional (1% of the longer side, never below
 *  NUMERIC_TOLERANCE_MM * 2) because the corners are integers: an exact test
 *  would reject nearly every rectangle this module itself produced, and then
 *  the edit panel would vanish from shapes it is supposed to edit.
 *
 *  `angle_deg` is normalised into [0, 180). A rectangle at 190 degrees and one
 *  at 10 are the same rectangle, and showing a user 190 in a field they then
 *  re-type is how a shape flips when nothing was changed. The cost is that a
 *  rectangle read "backwards" rebuilds CYCLICALLY ROTATED by two corners —
 *  same four points, same order contract, different starting corner. That is
 *  the same rectangle; a flipped one would not be. */
export function rectMetrics(points) {
  if (!Array.isArray(points) || points.length !== 4) return null;
  if (!points.every(isPoint)) return null;
  const [p0, p1, p2, p3] = points;
  const ux = p1[0] - p0[0], uy = p1[1] - p0[1];
  const vx = p2[0] - p1[0], vy = p2[1] - p1[1];
  const length = Math.hypot(ux, uy);
  const width = Math.hypot(vx, vy);
  if (length < 1 || width < 1) return null;      // a line is not a rectangle
  const tol = Math.max(2, 0.01 * Math.max(length, width));
  // opposite sides equal...
  const backLen = Math.hypot(p2[0] - p3[0], p2[1] - p3[1]);
  const backWidth = Math.hypot(p3[0] - p0[0], p3[1] - p0[1]);
  if (Math.abs(length - backLen) > tol) return null;
  if (Math.abs(width - backWidth) > tol) return null;
  // ...and one corner square. The dot product over the length is the WIDTH
  // side's drift along the length axis, in millimetres, so the tolerance
  // above compares like with like.
  if (Math.abs((ux * vx + uy * vy) / length) > tol) return null;
  let angle = (Math.atan2(uy, ux) * 180) / Math.PI;
  angle = ((angle % 360) + 360) % 360;
  if (angle >= 180) angle -= 180;
  return {
    center: [rnd((p0[0] + p1[0] + p2[0] + p3[0]) / 4),
             rnd((p0[1] + p1[1] + p2[1] + p3[1]) / 4)],
    // NOT rounded: this is the only float the module hands out. A tenth of a
    // degree looks like a harmless display nicety and moves the far corner of
    // a 20 m street by a centimetre, so the round trip would stop being one.
    // Formatting for a field is the panel's job, at the field boundary.
    angle_deg: angle,
    length_mm: rnd(length),
    width_mm: rnd(width),
  };
}

/** The exact inverse of `rectMetrics`, in the same corner order. This is what
 *  an editable "angle / length / width" panel writes back, so the round trip
 *  `rectFromMetrics(rectMetrics(pts))` has to return the rectangle it was
 *  given — the whole edit surface rests on that.
 *
 *  It rebuilds in the CANONICAL winding, the one `bandRect` lays down. Four
 *  numbers cannot say which way round a rectangle was traversed, and the
 *  numbers are what the panel edits. So the one case that does not come back
 *  corner-for-corner is a bbox drag that went UP the page: same four corners,
 *  same outline, traversed the other way. A closed path draws identically
 *  either way, and after one edit the shape is canonical for good — which is
 *  why this is a note and not a flag on the metrics. */
export function rectFromMetrics(metrics) {
  if (!metrics) return null;
  const { center, angle_deg, length_mm, width_mm } = metrics;
  if (!isPoint(center) || !isNum(angle_deg)) return null;
  if (!isNum(length_mm) || !isNum(width_mm)) return null;
  if (length_mm < 1 || width_mm < 1) return null;
  const a = (angle_deg * Math.PI) / 180;
  const ux = Math.cos(a) * (length_mm / 2), uy = Math.sin(a) * (length_mm / 2);
  const nx = -Math.sin(a) * (width_mm / 2), ny = Math.cos(a) * (width_mm / 2);
  return [
    [rnd(center[0] - ux + nx), rnd(center[1] - uy + ny)],
    [rnd(center[0] + ux + nx), rnd(center[1] + uy + ny)],
    [rnd(center[0] + ux - nx), rnd(center[1] + uy - ny)],
    [rnd(center[0] - ux - nx), rnd(center[1] - uy - ny)],
  ];
}

/** Read a polygon back as `{center, radius_mm}`, or null when it is not round.
 *  Fewer than 8 points cannot read as a circle (a hexagon is a shape somebody
 *  drew on purpose), and radii that vary by more than 5% of the mean are a
 *  polygon that happens to be roughly convex, not a tree. */
export function circleMetrics(points) {
  if (!Array.isArray(points) || points.length < 8) return null;
  if (!points.every(isPoint)) return null;
  const n = points.length;
  const cx = points.reduce((s, p) => s + p[0], 0) / n;
  const cy = points.reduce((s, p) => s + p[1], 0) / n;
  const radii = points.map((p) => Math.hypot(p[0] - cx, p[1] - cy));
  const mean = radii.reduce((s, r) => s + r, 0) / n;
  if (mean < 1) return null;
  if (radii.some((r) => Math.abs(r - mean) > 0.05 * mean)) return null;
  return { center: [rnd(cx), rnd(cy)], radius_mm: rnd(mean) };
}

/** `circlePolygon` under a name that pairs with `circleMetrics`, so an edit
 *  panel reads and writes through a matching pair rather than remembering
 *  which direction each function goes. */
export function circleFromMetrics(center, radiusMm, sides = TREE_SIDES) {
  if (!isNum(radiusMm) || radiusMm < 1) return null;
  return circlePolygon(center, radiusMm, sides);
}

/** The click list a house builder collected, as a closed shape — or null.
 *
 *  Two things get dropped. A click within `minMm` of the previous one is a
 *  double-click while placing, not a corner, and two vertices on one corner
 *  make a zero-length wall that every consumer then has to special-case. A
 *  trailing click within `minMm` of the FIRST one is the "close it" gesture,
 *  not a vertex — the shape is already closed by its flag.
 *
 *  Fewer than 3 survivors is null rather than a shape, because `Landmark`'s
 *  own validator refuses a closed shape with fewer than 3 points, and getting
 *  a 422 back after drawing a house is worse than the gesture quietly needing
 *  one more corner. */
export function polygonFromClicks(points, minMm = MIN_MM) {
  if (!Array.isArray(points)) return null;
  const out = [];
  for (const p of points) {
    if (!isPoint(p)) continue;
    const q = [rnd(p[0]), rnd(p[1])];
    const prev = out[out.length - 1];
    if (prev && Math.hypot(q[0] - prev[0], q[1] - prev[1]) < minMm) continue;
    out.push(q);
  }
  while (out.length > 1) {
    const last = out[out.length - 1], first = out[0];
    if (Math.hypot(last[0] - first[0], last[1] - first[1]) >= minMm) break;
    out.pop();
  }
  if (out.length < 3) return null;
  return { points: out, closed: true };
}

/** Which editable metrics this landmark offers: "rect", "circle" or "none".
 *
 *  "none" is the honest answer for a click-built house: a free polygon has no
 *  angle, length or width to type, and inventing a bounding box for the panel
 *  would silently square off the shape somebody drew the moment they touched
 *  a field. */
export function metricsKind(landmark) {
  const points = landmark?.points;
  if (rectMetrics(points)) return "rect";
  if (circleMetrics(points)) return "circle";
  return "none";
}
