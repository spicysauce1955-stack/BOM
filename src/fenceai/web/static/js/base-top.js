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
    // every segment is LOCKED level: "make it horizontal" is an intent that
    // must survive the next edit, not a one-off arrangement of points
    out.push({ pos_permille: pos, z_mm: Math.max(0, Math.round(absZ - groundAt(s))),
      lock: "level" });
  }
  if (out.length) out[out.length - 1].lock = null;    // no segment starts here
  return out;
}

// ---------- segment locks -------------------------------------------------
// A lock lives on the point that STARTS a segment and says what that segment is:
// "level" (one absolute elevation) or "step" (vertical). Locks are the user's
// intent, so they SURVIVE later edits — every mutation re-runs enforceLocks.

// Re-impose the locks after an edit at `fromIndex`, propagating outward: the
// point the user just moved is the one that wins, and locked neighbours follow
// it. `groundAtPos(pos)` gives the ground elevation at a permille position.
export function enforceLocks(points, groundAtPos, fromIndex = 0) {
  const out = points.map((p) => ({ ...p }));
  const absOf = (pt) => groundAtPos(pt.pos_permille) + pt.z_mm;
  const start = Math.max(0, Math.min(fromIndex, out.length - 1));
  // forward: each locked segment drags its RIGHT end into line
  for (let i = start; i + 1 < out.length; i++) {
    const a = out[i], b = out[i + 1];
    if (a.lock === "level") b.z_mm = Math.max(0, Math.round(absOf(a) - groundAtPos(b.pos_permille)));
    else if (a.lock === "step") b.pos_permille = a.pos_permille;
  }
  // backward: locked segments before the edit drag their LEFT end instead
  for (let i = start - 1; i >= 0; i--) {
    const a = out[i], b = out[i + 1];
    if (a.lock === "level") a.z_mm = Math.max(0, Math.round(absOf(b) - groundAtPos(a.pos_permille)));
    else if (a.lock === "step") a.pos_permille = b.pos_permille;
  }
  return out;
}

// Set (or clear) the lock on the segment starting at `index`, then enforce it.
// Locking a segment vertical IS how a step is made by hand.
export function setLock(points, index, lock, groundAtPos) {
  if (index < 0 || index + 1 >= points.length) return points;
  const out = points.map((p, i) => (i === index ? { ...p, lock: lock || null } : { ...p }));
  return enforceLocks(out, groundAtPos, index);
}

export function lockOf(points, index) {
  return points[index]?.lock ?? null;
}

// Insert a step at `pos`: the top keeps its shape on the way in, rises
// VERTICALLY, and continues HORIZONTALLY after it — a stepped wall, which is
// what the word means on site. Both of those are locks, so they hold.
export function withStep(points, pos, riseMm = STEP_RISE_MM, groundAtPos = null) {
  if (!points.length) return points;
  const p = Math.max(0, Math.min(Math.round(pos), 1000));
  const zBefore = topZAt(points, p);
  const out = [];
  for (const pt of points) if (pt.pos_permille < p) out.push({ ...pt });
  const riser = out.length;
  out.push({ pos_permille: p, z_mm: zBefore, lock: "step" });     // the riser
  out.push({ pos_permille: p, z_mm: Math.max(0, zBefore + Math.round(riseMm)),
    lock: "level" });                                             // the tread
  for (const pt of points) {
    if (pt.pos_permille <= p) continue;
    out.push({ ...pt, z_mm: Math.max(0, pt.z_mm + Math.round(riseMm)) });
  }
  // enforce FORWARD from the riser: the new step is what the user just asked
  // for, so the tread's far end follows it, not the other way round
  return groundAtPos ? enforceLocks(out, groundAtPos, riser) : out;
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
