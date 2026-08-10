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
  // resolve an anchor to a current station exactly like backend anchor_station():
  // proportional re-anchoring within the (possibly resized) originating segment
  const lens = segmentLengths(run);
  const i = Math.max(0, Math.min(anchor.segment_index, lens.length - 1));
  const segLen = lens[i];
  const offset = anchor.seg_len_at_authoring_mm === segLen
    ? Math.min(anchor.offset_mm, segLen)
    : Math.round((anchor.offset_mm * segLen) / Math.max(anchor.seg_len_at_authoring_mm, 1));
  return lens.slice(0, i).reduce((a, b) => a + b, 0) + offset;
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
