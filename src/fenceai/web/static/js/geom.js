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

export function anchorFor(runId, station) {
  // UI-authored runs are single-segment; segment 0, offset = station (clamped)
  const run = runById(runId);
  const L = runLength(run);
  return { segment_index: 0, offset_mm: Math.min(station, L), seg_len_at_authoring_mm: L };
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
