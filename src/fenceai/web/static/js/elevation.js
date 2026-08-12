// The panel, drawn: the server's `PanelElevation` as SVG rectangles.
//
// One renderer, two callers (the Panel tab's preview and the Structure tab's
// selected bay), because the two drawings are the same drawing — a picture that
// differed by which endpoint it came from would be a second answer to "what does
// this panel look like".
//
// What this module does NOT do, deliberately:
//   * it does not fetch. Both callers already hold the elevation (the preview
//     response, and the structure report cache), and a renderer with a fetch in
//     it would race the caller that has the newer copy;
//   * it does not compute geometry. Every rectangle here is a rectangle
//     `fenceai/report/elevation.py` placed. The fit that decides where a slat
//     sits is an algorithm with a justification x excess matrix behind it, and a
//     JS copy of it would eventually disagree with the cut list the same numbers
//     produced — which is the whole reason the elevation is a read model.
//
// The ONE transform it owns is the axis flip: the panel frame has y = 0 at the
// bottom of the opening, SVG has y growing downward.
//
// This SVG is NEVER mirrored in RTL — it joins the plan canvas and the side view
// in that rule (`.elevation-svg` is `direction: ltr` in CSS). Mirroring it would
// reverse the slat order against the plan drawn one tab over.

import { el } from "./geom.js";
import { t } from "./i18n.js";
import { tu } from "./units.js";

// viewBox geometry, in viewBox units (the SVG scales to its container width).
// The viewBox is fitted to the DRAWING rather than fixed, so a wide panel does
// not sit letterboxed inside a square box while the label text shrinks with it.
const MAX_DRAW_W = 940;
const MAX_DRAW_H = 620;      // a tall narrow bay must not become a tower
const PAD_START = 58;        // room for the height dimension
const PAD_END = 16;
const PAD_BOTTOM = 54;       // room for the width dimension
const PAD_TOP = 18;
const PAD_TOP_GAP = 60;      // …and for the fitted-gap dimension, when there is one
const PAD_END_GAP = 76;      // (a horizontal pattern's gap is called out beside it)
const TICK = 7;              // dimension tick half-length

// Fill and edge come from the stylesheet, keyed by a role from a CLOSED set —
// never from a sku, a swatch or any other server string. A colour is a style
// context: `esc()` does not make an arbitrary string safe to hand to `fill`.
const ROLES = new Set(["infill", "rail", "post", "cap", "spacer", "gate_kit"]);
const roleClass = (role) => (ROLES.has(role) ? `elev-${role}` : "elev-other");

// ---------------------------------------------------------------- pure parts

/** The members as drawn: panel y flipped into SVG y, back faces first.
 *
 * Sorting by face is the shadowbox case — a member set behind the frame has to
 * be painted before the ones in front of it, or the panel reads inside out. */
export function elevationRects(elev) {
  const height = elev?.height_mm || 0;
  return (elev?.members || [])
    .map((m, order) => ({
      key: `${m.slot_key}#${m.index}`,
      slot_key: m.slot_key || "",
      role: m.role || "",
      index: m.index,
      x_mm: m.x_mm,
      y_mm: height - (m.y_mm + m.h_mm),   // SVG y grows downward
      w_mm: m.w_mm,
      h_mm: m.h_mm,
      declared: m.declared !== false,
      face: m.face === "back" ? "back" : "front",
      sku: m.sku || "",
      order,
    }))
    .sort((a, b) => (a.face === b.face ? a.order - b.order
      : a.face === "back" ? -1 : 1));
}

/** The fitted gaps as one fact: how many, and the range they cover.
 *
 * `gaps_mm` is a LIST rather than a rounded number on purpose — a pattern that
 * cannot divide evenly spreads the remainder across the gaps, and "20–21 mm" is
 * the honest statement of that where "20 mm" is not. */
export function gapSummary(elev) {
  const gaps = (elev?.gaps_mm || []).filter((g) => Number.isFinite(g));
  if (!gaps.length) return null;
  return { count: gaps.length, min_mm: Math.min(...gaps), max_mm: Math.max(...gaps) };
}

/** True when any drawn member's face size is a nominal the read model invented.
 *  The drawing has to say so, or it claims a precision the catalog does not have. */
export function hasNominal(elev) {
  return (elev?.members || []).some((m) => m.declared === false);
}

/** One gap to dimension on the drawing, in PANEL coordinates, or null.
 *
 * `gaps_mm[i]` is the gap after placed member `i` of the fitted pattern, and a
 * member carries that same `i` as its `index` — so the dimension is a lookup,
 * not a measurement. The wire does not say WHICH slot the fitted list belongs
 * to (a frame slot and an infill slot are the same shape here), so the pair has
 * to prove it: a gap is dimensioned only where two consecutive members already
 * sit exactly the listed distance apart. Nothing is re-derived, and a pattern
 * this cannot confirm gets no dimension line rather than a wrong one. */
export function gapDimension(elev) {
  const gaps = elev?.gaps_mm || [];
  if (!gaps.length) return null;
  const bySlot = new Map();
  for (const m of elev.members || []) {
    if (!bySlot.has(m.slot_key)) bySlot.set(m.slot_key, []);
    bySlot.get(m.slot_key).push(m);
  }
  for (const list of bySlot.values()) {
    const seq = [...list].sort((a, b) => a.index - b.index);
    for (let i = 0; i + 1 < seq.length; i += 1) {
      const a = seq[i];
      const b = seq[i + 1];
      const gap = gaps[a.index];
      if (b.index !== a.index + 1 || !(gap > 0)) continue;
      if (a.y_mm === b.y_mm && a.h_mm === b.h_mm && b.x_mm - (a.x_mm + a.w_mm) === gap)
        return { axis: "x", gap_mm: gap, start_mm: a.x_mm + a.w_mm, end_mm: b.x_mm,
                 cross_mm: a.y_mm + a.h_mm, slot_key: a.slot_key };
      if (a.x_mm === b.x_mm && a.w_mm === b.w_mm && b.y_mm - (a.y_mm + a.h_mm) === gap)
        return { axis: "y", gap_mm: gap, start_mm: a.y_mm + a.h_mm, end_mm: b.y_mm,
                 cross_mm: a.x_mm + a.w_mm, slot_key: a.slot_key };
    }
  }
  return null;
}

/** The sentence that goes beside the drawing: the gaps, in the display unit. */
export function gapLine(elev) {
  const g = gapSummary(elev);
  if (!g) return "";
  return g.min_mm === g.max_mm
    ? tu("elevation.gaps_one", { n: g.count, gap_mm: g.min_mm })
    : tu("elevation.gaps_range", { n: g.count, min_mm: g.min_mm, max_mm: g.max_mm });
}

// -------------------------------------------------------------- the drawing

/** A `PanelElevation` as an `<svg>` element, or null when there is nothing to
 *  draw (a model with no members, or a bay from a run that predates panels).
 *
 *  `onSelect(slotKey)` fires when a member is clicked. The renderer never
 *  reaches out of its own SVG: which row that highlights is the CALLER's table
 *  and the caller's business. */
export function renderElevation(elev, { onSelect } = {}) {
  const w = elev?.width_mm || 0;
  const h = elev?.height_mm || 0;
  const rects = elevationRects(elev);
  if (!(w > 0) || !(h > 0) || !rects.length) return null;

  const dim = gapDimension(elev);
  // the gap callout is drawn clear of the panel, so it needs the room: above a
  // vertical pattern, beyond the end edge of a horizontal one
  const padTop = dim?.axis === "x" ? PAD_TOP_GAP : PAD_TOP;
  const padEnd = dim?.axis === "y" ? PAD_END_GAP : PAD_END;
  // one scale for both axes: a drawing that stretched to fill its box would
  // make a 100 mm slat and a 20 mm gap look like the same thing
  const s = Math.min(MAX_DRAW_W / w, MAX_DRAW_H / h);
  const dw = w * s;
  const dh = h * s;
  const x0 = PAD_START;
  const y0 = padTop;
  const vw = PAD_START + dw + padEnd;
  const vh = padTop + dh + PAD_BOTTOM;
  const px = (mm) => x0 + mm * s;
  const py = (mm) => y0 + mm * s;

  const svg = el("svg", {
    viewBox: `0 0 ${r(vw)} ${r(vh)}`,
    class: "elevation-svg",
    preserveAspectRatio: "xMidYMid meet",
  });
  el("rect", { class: "elev-opening", x: r(x0), y: r(y0), width: r(dw), height: r(dh) }, svg);

  const body = el("g", { class: "elev-members" }, svg);
  rects.forEach((m, order) => {
    const rect = el("rect", {
      class: `elev-member ${roleClass(m.role)}${m.declared ? "" : " elev-nominal"}`,
      x: r(px(m.x_mm)), y: r(py(m.y_mm)),
      width: r(Math.max(m.w_mm * s, 0.5)), height: r(Math.max(m.h_mm * s, 0.5)),
      "data-slot": m.slot_key, "data-index": String(m.index),
      "data-order": String(order),   // paint order, so a raised member can go back
    }, body);
    // identifiers only, and set as TEXT — a sku never becomes markup or paint
    el("title", {}, rect).textContent = m.sku ? `${m.slot_key} · ${m.sku}` : m.slot_key;
  });

  // Hidden edges, drawn over the infill. A rail on a slat panel is genuinely
  // behind the slats, so occlusion alone leaves a two-rail panel and a
  // three-rail panel looking identical — which is the one comparison this
  // drawing exists to make. Outlines only: they add no rectangle to count, and
  // they carry no fill, so nothing here overstates what is in front of what.
  const edges = el("g", { class: "elev-edges" }, svg);
  for (const m of rects)
    el("rect", {
      class: `elev-edge${m.declared ? "" : " elev-nominal"}`,
      x: r(px(m.x_mm)), y: r(py(m.y_mm)),
      width: r(Math.max(m.w_mm * s, 0.5)), height: r(Math.max(m.h_mm * s, 0.5)),
    }, edges);

  dimension(svg, "x", x0, y0 + dh + 22, x0 + dw, y0 + dh + 22,
            tu("elevation.length", { len_mm: w }));
  dimension(svg, "y", x0 - 26, y0, x0 - 26, y0 + dh,
            tu("elevation.length", { len_mm: h }));
  if (dim) drawGap(svg, dim, { px, py, w, h, y0 });

  if (onSelect) {
    svg.addEventListener("click", (ev) => {
      const hit = ev.target.closest?.("[data-slot]");
      if (hit) onSelect(hit.getAttribute("data-slot"));
    });
    svg.classList.add("elev-clickable");
  }
  return svg;
}

/** Mark every member of one slot as selected; pass null to clear.
 *
 * Selected members are RAISED to the top of the group. A rail on a slat panel
 * is genuinely behind the slats — which is what the drawing should show — but a
 * highlight nobody can see is the same as no highlight, and the point of the
 * click is to answer "which of these is the rail". SVG has no z-index, so paint
 * order is the only lever; `data-order` puts them back where they were. */
export function highlightSlot(svg, slotKey) {
  if (!svg) return;
  const group = svg.querySelector(".elev-members");
  if (!group) return;
  const rects = [...group.querySelectorAll(".elev-member")]
    .sort((a, b) => +a.getAttribute("data-order") - +b.getAttribute("data-order"));
  const chosen = (rect) => slotKey !== null && rect.getAttribute("data-slot") === slotKey;
  for (const rect of rects) rect.classList.toggle("selected", chosen(rect));
  // back to the server's order, then the selected slot on top of it
  for (const rect of [...rects.filter((x) => !chosen(x)), ...rects.filter(chosen)])
    group.appendChild(rect);
}

function dimension(svg, axis, x1, y1, x2, y2, label) {
  const g = el("g", { class: "elev-dim" }, svg);
  el("line", { x1: r(x1), y1: r(y1), x2: r(x2), y2: r(y2) }, g);
  for (const [x, y] of [[x1, y1], [x2, y2]])
    el("line", axis === "x"
      ? { x1: r(x), y1: r(y - TICK), x2: r(x), y2: r(y + TICK) }
      : { x1: r(x - TICK), y1: r(y), x2: r(x + TICK), y2: r(y) }, g);
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const text = el("text", axis === "x"
    ? { class: "elev-dim-label", x: r(cx), y: r(cy + 20), "text-anchor": "middle" }
    : { class: "elev-dim-label", x: r(cx), y: r(cy), "text-anchor": "middle",
        transform: `rotate(-90 ${r(cx)} ${r(cy)})`, dy: "-8" }, g);
  text.textContent = label;      // textContent, never innerHTML
}

// The fitted gap, called out clear of the panel: above it for a vertical
// pattern, beside it for a horizontal one, because a 20 mm label drawn INSIDE a
// 20 mm gap is a label nobody can read.
function drawGap(svg, dim, { px, py, w, h, y0 }) {
  const g = el("g", { class: "elev-dim elev-gap-dim" }, svg);
  const label = tu("elevation.length", { len_mm: dim.gap_mm });
  if (dim.axis === "x") {
    const x1 = px(dim.start_mm);
    const x2 = px(dim.end_mm);
    const y = y0 - 22;
    el("line", { x1: r(x1), y1: r(y), x2: r(x2), y2: r(y) }, g);
    for (const x of [x1, x2])
      el("line", { class: "elev-leader", x1: r(x), y1: r(y), x2: r(x),
                   y2: r(py(h - dim.cross_mm)) }, g);
    el("text", { class: "elev-dim-label", x: r((x1 + x2) / 2), y: r(y - 9),
                 "text-anchor": "middle" }, g).textContent = label;
    return;
  }
  // horizontal pattern: the gap runs up the panel, so the callout goes beside it
  const y1 = py(h - dim.start_mm);
  const y2 = py(h - dim.end_mm);
  const x = px(w) + 20;
  el("line", { x1: r(x), y1: r(y1), x2: r(x), y2: r(y2) }, g);
  for (const y of [y1, y2])
    el("line", { class: "elev-leader", x1: r(px(dim.cross_mm)), y1: r(y), x2: r(x), y2: r(y) }, g);
  const cy = (y1 + y2) / 2;
  el("text", { class: "elev-dim-label", x: r(x + 16), y: r(cy), "text-anchor": "middle",
               transform: `rotate(-90 ${r(x + 16)} ${r(cy)})` }, g).textContent = label;
}

const r = (n) => Math.round(n * 10) / 10;
