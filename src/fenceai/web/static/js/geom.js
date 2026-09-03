// Pure geometry + SVG helpers. Int mm world coordinates; px only at the boundary.
// The plan canvas is NEVER mirrored in RTL (spec §4).

import { state } from "./state.js";

export const SCALE = 0.045;      // px per mm
export const OX = 60, OY = 260;  // world origin in canvas px
export const SNAP_MM = 100;      // drawing grid snap

export const toPx = (p) => [OX + p[0] * SCALE, OY - p[1] * SCALE];
export const toMmRaw = (x, y) => [Math.round((x - OX) / SCALE), Math.round((OY - y) / SCALE)];
export const toMm = (x, y) => {
  const [mx, my] = toMmRaw(x, y);
  return [Math.round(mx / SNAP_MM) * SNAP_MM, Math.round(my / SNAP_MM) * SNAP_MM];
};

export function nodeById(id) {
  return state.project.topology.nodes.find((n) => n.id === id);
}

export function runById(runId) {
  return state.project.topology.runs.find((r) => r.id === runId);
}

export function runPoints(run) {
  const a = nodeById(run.start_node_id), b = nodeById(run.end_node_id);
  return [[a.x_mm, a.y_mm], ...(run.interior_vertices || []), [b.x_mm, b.y_mm]];
}

export function runLength(run) {
  const pts = runPoints(run);
  let total = 0;
  for (let i = 0; i + 1 < pts.length; i++)
    total += Math.round(Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]));
  return total;
}

export function pointAtStation(runId, stationMm) {
  const run = runById(runId);
  if (!run) return null;
  const pts = runPoints(run);
  let s = Math.max(0, stationMm);
  for (let i = 0; i + 1 < pts.length; i++) {
    const seg = Math.round(Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]));
    if (s <= seg || i === pts.length - 2) {
      const t = seg ? Math.min(s / seg, 1) : 0;
      return [
        Math.round(pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t),
        Math.round(pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t),
      ];
    }
    s -= seg;
  }
  return pts[pts.length - 1];
}

export function stationAtPoint(run, xMm, yMm) {
  // nearest station on the run to a world point (projection per segment)
  const pts = runPoints(run);
  let best = { station: 0, dist: Infinity };
  let acc = 0;
  for (let i = 0; i + 1 < pts.length; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const dx = bx - ax, dy = by - ay;
    const seg = Math.round(Math.hypot(dx, dy));
    const t = seg ? Math.max(0, Math.min(1, ((xMm - ax) * dx + (yMm - ay) * dy) / (dx * dx + dy * dy))) : 0;
    const px = ax + dx * t, py = ay + dy * t;
    const dist = Math.hypot(xMm - px, yMm - py);
    if (dist < best.dist) best = { station: Math.round(acc + seg * t), dist };
    acc += seg;
  }
  return best;
}

// Pointer tolerance for "this pixel belongs to that run", in world mm. It mirrors
// HALF of .run-hit's stroke-width (style.css) so the band whose cursor a user can
// see, the status readout and every click agree on one answer.
export const RUN_HIT_PX = 8;
export const RUN_HIT_MM = Math.round(RUN_HIT_PX / SCALE); // 178 mm

// THE run resolver: nearest run to a world point, or null beyond tolMm. Paint
// order must never decide which run a pixel belongs to — that is what made the
// corner of an L record a slope on the wrong leg (persona-lab B4). Distances are
// geometric, so an end-cap cannot swallow a neighbour's stations; exact ties fall
// to the run that comes first in topology order, deterministically.
export function runAtPoint(xMm, yMm, tolMm = RUN_HIT_MM) {
  let best = null;
  for (const run of state.project?.topology.runs || []) {
    const hit = stationAtPoint(run, xMm, yMm);
    if (hit.dist <= tolMm && (best === null || hit.dist < best.dist))
      best = { run, station: hit.station, dist: hit.dist };
  }
  return best;
}

// The endpoint NODE a station falls on, or null for an interior station. A run
// end is a shared corner: its elevation belongs to the node, not to one leg.
export function endpointNodeAt(run, station, tolMm = RUN_HIT_MM) {
  const L = runLength(run);
  const tol = Math.min(tolMm, Math.max(Math.floor(L / 2), 0));
  if (station <= tol) return nodeById(run.start_node_id);
  if (station >= L - tol) return nodeById(run.end_node_id);
  return null;
}

export function nearestNode(xMm, yMm, radiusMm, excludeId) {
  let best = null, bestD = radiusMm;
  for (const n of state.project.topology.nodes) {
    if (n.id === excludeId) continue;
    const d = Math.hypot(n.x_mm - xMm, n.y_mm - yMm);
    if (d <= bestD) { best = n; bestD = d; }
  }
  return best;
}

// Snapping (draw + drag) — plan Task 7, implemented exactly:
//   1. dot snap: nearest existing node within 150 mm -> that node
//   2. angle snap: if angle to anchor within 6 deg of k*45 deg -> project onto ray
//   3. grid snap: round each coord to 100 mm
// Alt (opts.alt) bypasses 2+3. Grid rounding after a 45-degree projection keeps
// the angle exact when the anchor is on-grid (|dx| == |dy| rounds equally).
export function snapPoint(xMm, yMm, anchor, opts = {}) {
  const node = nearestNode(xMm, yMm, 150, opts.excludeNodeId);
  if (node) return { p: [node.x_mm, node.y_mm], kind: "dot", node };
  if (opts.alt) return { p: [Math.round(xMm), Math.round(yMm)], kind: null };
  let p = [xMm, yMm], kind = "grid";
  if (anchor) {
    const dx = xMm - anchor[0], dy = yMm - anchor[1];
    if (Math.hypot(dx, dy) > 1) {
      const step = Math.PI / 4;
      const ang = Math.atan2(dy, dx);
      const k = Math.round(ang / step);
      if (Math.abs(ang - k * step) <= (6 * Math.PI) / 180) {
        const ux = Math.cos(k * step), uy = Math.sin(k * step);
        const along = dx * ux + dy * uy;
        p = [anchor[0] + ux * along, anchor[1] + uy * along];
        kind = "angle";
      }
    }
  }
  p = [Math.round(p[0] / SNAP_MM) * SNAP_MM, Math.round(p[1] / SNAP_MM) * SNAP_MM];
  return { p, kind };
}

function segmentLengths(run) {
  const pts = runPoints(run);
  const lens = [];
  for (let i = 0; i + 1 < pts.length; i++)
    lens.push(Math.round(Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])));
  return lens;
}

export function anchorFor(runId, station) {
  // per-segment anchor matching backend make_anchor() (station.py): find the
  // containing segment; offset/authored-length are SEGMENT-local. Whole-run
  // anchors silently re-anchor wrong on multi-segment runs (final UI-v2 review #1).
  const run = runById(runId);
  const lens = segmentLengths(run);
  const total = lens.reduce((a, b) => a + b, 0);
  let s = Math.max(0, Math.min(station, total));
  for (let i = 0; i < lens.length; i++) {
    if (s <= lens[i] || i === lens.length - 1)
      return { segment_index: i, offset_mm: Math.min(s, lens[i]), seg_len_at_authoring_mm: lens[i] };
    s -= lens[i];
  }
  return { segment_index: 0, offset_mm: 0, seg_len_at_authoring_mm: total || 1 };
}

export function stationOfAnchor(run, anchor) {
  // resolve an anchor to a current station exactly like backend anchor_station(),
  // honouring the anchor's own `reanchor` policy — the ONE branch, mirrored:
  //   proportional (the default) — an elevation sample a third of the way along a
  //     wall stays a third of the way along when the wall is stretched (ADR-0003);
  //   rigid — the OFFSET is what a person measured, so it survives the edit; a
  //     post 800 mm past a corner stays 800 mm past that corner.
  // Absent means proportional: no anchor stored in any existing project carries
  // the field, and their behaviour may not change.
  // Both the clamp and the scaling are segment-local, exactly like the anchor.
  const lens = segmentLengths(run);
  const i = Math.max(0, Math.min(anchor.segment_index, lens.length - 1));
  const segLen = lens[i];
  const offset = anchor.reanchor === "rigid" || anchor.seg_len_at_authoring_mm === segLen
    ? Math.min(anchor.offset_mm, segLen)
    : Math.round((anchor.offset_mm * segLen) / Math.max(anchor.seg_len_at_authoring_mm, 1));
  return lens.slice(0, i).reduce((a, b) => a + b, 0) + offset;
}

// ---------- elevation model (mirrors backend ground_samples()) ----------
export const GROUND_TOL_MM = 1; // NUMERIC_TOLERANCE_MM (units.py)

// [{station, z, ev?, node?}] sorted by station: NODE elevations anchor the
// endpoints — a shared corner is single-valued fence-wide — with interior
// elevation_sample events between. An explicit event within GROUND_TOL_MM of an
// endpoint overrides the node value (backwards compatible with event-only runs).
export function groundSamplesFor(run, L = runLength(run)) {
  const events = run.point_events
    .filter((ev) => ev.payload.kind === "elevation_sample")
    .map((ev) => ({
      ev, station: Math.min(stationOfAnchor(run, ev.anchor), L), z: ev.payload.z_mm,
    }))
    .sort((a, b) => a.station - b.station);
  const samples = [...events];
  if (!events.some((e) => e.station <= GROUND_TOL_MM)) {
    const n = nodeById(run.start_node_id);
    samples.unshift({ node: n, station: 0, z: n?.z_mm ?? 0 });
  }
  if (!events.some((e) => Math.abs(e.station - L) <= GROUND_TOL_MM)) {
    const n = nodeById(run.end_node_id);
    samples.push({ node: n, station: L, z: n?.z_mm ?? 0 });
  }
  return samples.sort((a, b) => a.station - b.station);
}

// piecewise-linear ground, matching backend ground_z() (endpoints always present)
export function groundZAt(samples, station) {
  const last = samples[samples.length - 1];
  const s = Math.max(samples[0].station, Math.min(station, last.station));
  for (let i = 0; i + 1 < samples.length; i++) {
    const a = samples[i], b = samples[i + 1];
    if (a.station <= s && s <= b.station)
      return b.station === a.station
        ? a.z : Math.round(a.z + ((b.z - a.z) * (s - a.station)) / (b.station - a.station));
  }
  return last.z;
}

// ---------- SVG helpers ----------
export function el(tag, attrs, parent) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

export function clearGroup(id) {
  const g = document.getElementById(id);
  while (g.firstChild) g.removeChild(g.firstChild);
  return g;
}
