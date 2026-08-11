// Base-top profile geometry — pure functions, no DOM and no state.
//
// A base_top payload is a list of {pos_permille, z_mm} points along a section's
// interval, where z_mm is the top's height ABOVE LOCAL GROUND (backend
// base_top_at semantics). Two consecutive points at the same pos = a vertical
// STEP, and the right side wins at the boundary.
//
// Everything a user asks for in the side view — "make it that height", "make it
// horizontal", "meet the next section", "put a step here" — is one of these
// transforms, so they are written once here and tested without a browser.

export const STEP_RISE_MM = 200;   // default rise of a newly added step

// height above ground at a permille position — mirrors backend base_top_at()
export function topZAt(points, pos) {
  if (!points.length) return 0;
  if (pos <= points[0].pos_permille) return points[0].z_mm;
  for (let i = 0; i + 1 < points.length; i++) {
    const a = points[i], b = points[i + 1];
    if (a.pos_permille === b.pos_permille) {
      if (pos === a.pos_permille) return b.z_mm;   // right side of the step wins
      continue;
    }
    if (a.pos_permille <= pos && pos <= b.pos_permille) {
      if (pos === b.pos_permille) continue;        // a following step may claim it
      return Math.round(a.z_mm + ((b.z_mm - a.z_mm) * (pos - a.pos_permille))
        / (b.pos_permille - a.pos_permille));
    }
  }
  return points[points.length - 1].z_mm;
}

// A constant height above the ground: the top follows every rise and dip.
export function flatPoints(zAboveGroundMm) {
  const z = Math.max(0, Math.round(zAboveGroundMm));
  return [{ pos_permille: 0, z_mm: z }, { pos_permille: 1000, z_mm: z }];
}

// A HORIZONTAL top at one absolute elevation. Because z_mm is stored above local
// ground, a level top needs a point wherever the ground changes slope — with
// only two end points the top would follow the ground's interior breaks.
// `stations` are the ground breakpoints (absolute run stations, ascending);
// `groundAt(station)` gives the ground elevation there.
export function levelPoints(stations, groundAt, s0, s1, absZ) {
  const span = s1 - s0;
  if (span <= 0) return flatPoints(Math.max(0, absZ - groundAt(s0)));
  const inside = stations.filter((s) => s > s0 && s < s1);
  const out = [];
  let last = null;
  for (const s of [s0, ...inside, s1]) {
    const pos = Math.round(((s - s0) * 1000) / span);
    if (pos === last) continue;                       // one point per position
    last = pos;
    out.push({ pos_permille: pos, z_mm: Math.max(0, Math.round(absZ - groundAt(s))) });
  }
  return out;
}

// Insert a step at `pos`: the top keeps its shape on the way in, jumps by
// `riseMm`, and everything after the step moves with it (that is what "add a
// step" means — a plateau, not a ramp back down).
export function withStep(points, pos, riseMm = STEP_RISE_MM) {
  if (!points.length) return points;
  const p = Math.max(0, Math.min(Math.round(pos), 1000));
  const zBefore = topZAt(points, p);
  const out = [];
  for (const pt of points) if (pt.pos_permille < p) out.push({ ...pt });
  out.push({ pos_permille: p, z_mm: zBefore });
  out.push({ pos_permille: p, z_mm: Math.max(0, zBefore + Math.round(riseMm)) });
  for (const pt of points) {
    if (pt.pos_permille <= p) continue;
    out.push({ ...pt, z_mm: Math.max(0, pt.z_mm + Math.round(riseMm)) });
  }
  return out;
}

// Move an end point so the top meets a neighbouring section at their shared
// node. `targets` carry ABSOLUTE elevations; ground elevations at this section's
// own ends convert them back to heights above ground. Ends with no neighbour (or
// a neighbour with no base top) are left exactly as they were.
export function matchEnds(points, { startAbs, endAbs, groundStart, groundEnd }) {
  if (!points.length) return points;
  const out = points.map((p) => ({ ...p }));
  if (startAbs != null)
    out[0].z_mm = Math.max(0, Math.round(startAbs - groundStart));
  if (endAbs != null)
    out[out.length - 1].z_mm = Math.max(0, Math.round(endAbs - groundEnd));
  return out;
}

// The step positions of a profile (two points sharing a position), for hinting.
export function stepPositions(points) {
  const out = [];
  for (let i = 0; i + 1 < points.length; i++)
    if (points[i].pos_permille === points[i + 1].pos_permille)
      out.push(points[i].pos_permille);
  return out;
}
