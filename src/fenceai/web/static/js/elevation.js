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
const CALLOUT_STEP = 30;     // one lane out for a second callout on the same side
const MARGIN_ROW = 22;       // the edge-margin row, under the panel
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
      seat: seatRect(m, height),
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

/** The housed part of a drawn member, flipped into SVG y, or null.
 *
 * `seat_start_mm`/`seat_end_mm` are stated along the member's OWN axis, and the
 * wire does not say which axis that is — a tall thin rectangle and a long flat
 * one are the same shape here. So the pair has to prove it: the range is taken
 * as the axis it actually falls inside. A range that fits neither is drawn as
 * nothing rather than as a band across the wrong dimension.
 *
 * Nothing is derived. The seat is where the read model said the member enters
 * its housing, which is the same integer that shortened it on the cut list. */
export function seatRect(m, height) {
  const start = m?.seat_start_mm;
  const end = m?.seat_end_mm;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  const inY = start >= m.y_mm && end <= m.y_mm + m.h_mm;
  const inX = start >= m.x_mm && end <= m.x_mm + m.w_mm;
  if (inY && (m.h_mm >= m.w_mm || !inX))
    return { x_mm: m.x_mm, y_mm: height - end, w_mm: m.w_mm, h_mm: end - start };
  if (inX)
    return { x_mm: start, y_mm: height - (m.y_mm + m.h_mm), w_mm: end - start,
             h_mm: m.h_mm };
  return null;
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
  return (elev?.members || []).some((m) => m.declared === false)
    || (elev?.posts || []).some((p) => p.declared === false || p.cap_declared === false);
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

/** The pattern's PITCH — member plus the gap after it — or null.
 *
 * The number a slat fence is specified by ("100 at 150 centres"), and the one
 * neither the member width nor the gap states on its own. Measured between two
 * consecutive members' leading edges, which is a placement fact both rectangles
 * already carry.
 *
 * Emitted only when the pitch is CONSTANT across the whole placed sequence. A
 * `spread_to_fit` pattern absorbs its remainder into the gaps, so its members
 * are not evenly pitched, and one pitch quoted over an uneven pattern is a
 * number an installer would set out from and get wrong by the last bay. The gap
 * line beside the drawing already says the honest thing there ("20–21 mm"). */

/** The members of the fitted PATTERN, keyed by slot.
 *
 * `kind` is on the wire ("frame" | "infill") precisely so a client does not have
 * to guess: a two-rail frame slot and a two-slat pattern are the same shape here,
 * and calling out an "edge margin" between the opening and a rail would dimension
 * something nobody set out. A run generated before `kind` existed carries "" for
 * every member, and there the old behaviour (consider them all) is the only
 * option — better a dimension derived from every member than none at all. */
function patternSlots(elev) {
  const members = elev?.members || [];
  const typed = members.some((m) => m.kind);
  const bySlot = new Map();
  for (const m of members) {
    if (typed && m.kind !== "infill") continue;
    if (!bySlot.has(m.slot_key)) bySlot.set(m.slot_key, []);
    bySlot.get(m.slot_key).push(m);
  }
  return bySlot;
}

export function pitchDimension(elev) {
  for (const list of patternSlots(elev).values()) {
    if (list.length < 3) continue;      // two members show a gap, not a rhythm
    const seq = [...list].sort((a, b) => a.index - b.index);
    const vertical = seq.every((m, i) => i === 0 || m.y_mm === seq[0].y_mm);
    const axis = vertical ? "x" : "y";
    const at = (m) => (axis === "x" ? m.x_mm : m.y_mm);
    const pitches = seq.slice(1).map((m, i) => at(m) - at(seq[i]));
    if (!pitches.length || pitches.some((p) => p !== pitches[0] || p <= 0)) continue;
    const a = seq[0];
    const b = seq[1];
    return {
      axis, value_mm: pitches[0], from_mm: at(a), to_mm: at(b),
      cross_mm: axis === "x" ? a.y_mm + a.h_mm : a.x_mm + a.w_mm,
      slot_key: a.slot_key,
    };
  }
  return null;
}

/** What is left clear at each end of the pattern, or null.
 *
 * `edge_margin_mm` is authored on the infill and the fit spends it; on the wire
 * it survives as the distance between the opening edge and the outermost
 * member, which is what the drawing measures — the same two rectangles the
 * renderer is already placing. Reported as a PAIR because the two ends differ
 * under `start`/`end` justification, and one figure would name the wrong end. */
export function edgeMargins(elev) {
  // The FIT's own answer when the wire carries it. The margin is a number the
  // fit produced and spent; measuring it back off the drawn rectangles was a
  // client-side re-derivation of it, and the two diverge exactly where it
  // matters — `start`/`spread_to_fit` leave the residual BEYOND the end margin,
  // so the honest far-end clearance is `edge_margin_end_mm + residual_mm`.
  if (Number.isFinite(elev?.edge_margin_start_mm)
      && Number.isFinite(elev?.edge_margin_end_mm)) {
    const start = elev.edge_margin_start_mm;
    const end = elev.edge_margin_end_mm + (elev.residual_mm || 0);
    if (start > 0 || end > 0) {
      const first = (elev.members || []).find((m) => !m.kind || m.kind === "infill");
      const vertical = !first || first.h_mm >= first.w_mm;
      return { axis: vertical ? "x" : "y", start_mm: start, end_mm: end,
               slot_key: first?.slot_key || "",
               cross_mm: first
                 ? (vertical ? first.y_mm + first.h_mm : first.x_mm + first.w_mm) : 0 };
    }
    return null;
  }
  // a run generated before the fit put its margins on the wire: measured off the
  // outermost rectangles, which is honest as a DRAWN clearance and is all there is
  const width = elev?.width_mm || 0;
  const height = elev?.height_mm || 0;
  for (const list of patternSlots(elev).values()) {
    if (list.length < 2) continue;
    const seq = [...list].sort((a, b) => a.index - b.index);
    const vertical = seq.every((m) => m.y_mm === seq[0].y_mm && m.h_mm === seq[0].h_mm);
    const first = seq[0];
    const last = seq[seq.length - 1];
    const start = vertical ? first.x_mm : first.y_mm;
    const end = vertical ? width - (last.x_mm + last.w_mm)
                         : height - (last.y_mm + last.h_mm);
    if (start <= 0 && end <= 0) continue;   // flush both ends: nothing to call out
    return { axis: vertical ? "x" : "y", start_mm: Math.max(start, 0),
             end_mm: Math.max(end, 0), slot_key: first.slot_key,
             cross_mm: vertical ? first.y_mm + first.h_mm : first.x_mm + first.w_mm };
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

/** The drawing's box and scale, in viewBox units — the ONE transform.
 *
 * `renderElevation` computed this inline until the canvas needed to put drag
 * handles on the very same rectangles. Two copies of a scale is a handle three
 * pixels from the board it moves, so it is computed here and called from both.
 * `null` when there is nothing to draw, which is the same condition the renderer
 * refuses on.
 *
 * `annotations` changes the padding — a fitted-gap callout takes a lane above
 * the panel — so a caller overlaying handles must pass the SAME options it
 * renders with, and must read `y0` rather than assume `PAD_TOP`. */
export function elevationLayout(elev, { annotations = true, posts = false } = {}) {
  const w = elev?.width_mm || 0;
  const h = elev?.height_mm || 0;
  if (!(w > 0) || !(h > 0) || !(elev?.members || []).length) return null;
  // The posts stand OUTSIDE the opening — the start one at a negative x — so the
  // box has to grow to hold them, or they are drawn over the height dimension.
  // Their width is in millimetres like everything else, so it scales with the
  // drawing rather than being a fixed inset.
  const flanking = posts ? (elev.posts || []) : [];
  const postMm = flanking.reduce((most, p) => Math.max(most, p.w_mm || 0), 0);
  const capMm = flanking.reduce((most, p) => Math.max(most, p.cap_h_mm || 0), 0);
  const dim = annotations ? gapDimension(elev) : null;
  const pitch = annotations ? pitchDimension(elev) : null;
  const margins = annotations ? edgeMargins(elev) : null;
  // the gap callout is drawn clear of the panel, so it needs the room: above a
  // vertical pattern, beyond the end edge of a horizontal one — and the pitch
  // sits one line beyond the gap on the same side, because they measure the
  // same rhythm and reading them apart is reading them twice
  const above = [dim, pitch].filter((d) => d?.axis === "x").length;
  const beside = [dim, pitch].filter((d) => d?.axis === "y").length;
  const padTop = above ? PAD_TOP_GAP + (above - 1) * CALLOUT_STEP : PAD_TOP;
  const padEnd = beside ? PAD_END_GAP + (beside - 1) * CALLOUT_STEP : PAD_END;
  // the edge margins take their own row under the panel, and push the overall
  // width dimension down rather than sharing a line with it
  const padBottom = PAD_BOTTOM + (margins ? MARGIN_ROW : 0);
  // one scale for both axes: a drawing that stretched to fill its box would
  // make a 100 mm slat and a 20 mm gap look like the same thing
  // one scale over the WHOLE drawing, posts included, so a bay does not change
  // scale the moment its posts are shown
  const s = Math.min(MAX_DRAW_W / (w + 2 * postMm), MAX_DRAW_H / (h + capMm));
  const postPad = postMm * s;
  const capPad = capMm * s;
  return {
    s, x0: PAD_START + postPad, y0: padTop + capPad, w_mm: w, h_mm: h,
    dw: w * s, dh: h * s, padBottom, postPad, capPad,
    vw: PAD_START + postPad + w * s + postPad + padEnd,
    vh: padTop + capPad + h * s + padBottom,
    dim, pitch, margins,
  };
}

/** Panel millimetres -> viewBox units. Panel y counts UP from the bottom, so
 *  this flips; `renderElevation`'s own `py` takes an already-flipped value from
 *  `elevationRects` and does not. */
export const layoutPx = (L, x_mm, y_mm) =>
  [L.x0 + x_mm * L.s, L.y0 + (L.h_mm - y_mm) * L.s];

/** ... and back, for a pointer landing on the drawing. */
export const layoutMm = (L, x, y) =>
  [Math.round((x - L.x0) / L.s), Math.round(L.h_mm - (y - L.y0) / L.s)];

/** A `PanelElevation` as an `<svg>` element, or null when there is nothing to
 *  draw (a model with no members, or a bay from a run that predates panels).
 *
 *  `onSelect(slotKey)` fires when a member is clicked. The renderer never
 *  reaches out of its own SVG: which row that highlights is the CALLER's table
 *  and the caller's business.
 *
 *  `fixings` draws the fastener places, and is OFF by default: the Panel and
 *  Structure tabs answer "what is this panel made of", where a screw is a BOM
 *  line; the canvas answers "what does per-member-crossing MEAN", where the
 *  places are the only way to see it. */
export function renderElevation(elev, {
  onSelect, annotations = true, joints = true, fixings = false, posts = false,
} = {}) {
  const L = elevationLayout(elev, { annotations, posts });
  const rects = elevationRects(elev);
  if (!L || !rects.length) return null;

  const { s, x0, y0, dw, dh, vw, vh, dim, pitch, margins } = L;
  const w = L.w_mm;
  const h = L.h_mm;
  const px = (mm) => x0 + mm * s;
  const py = (mm) => y0 + mm * s;

  const svg = el("svg", {
    viewBox: `0 0 ${r(vw)} ${r(vh)}`,
    class: "elevation-svg",
    preserveAspectRatio: "xMidYMid meet",
  });
  // The posts FIRST, so the opening and everything fitted into it paints over
  // them — a post is behind the panel it carries, not in front of it.
  if (posts) drawPosts(svg, L, elev);
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

  // The housed ends, hatched over the members they belong to. This is the one
  // thing the elevation can honestly say about a joint at this scale — "that
  // part of it is inside something" — and it is worth saying, because a seated
  // member and a butted one are otherwise the same rectangle and 135 mm apart
  // on the cut list. HOW it is housed is the section inset's job (joint.js).
  if (joints) {
    const seats = el("g", { class: "elev-seats" }, svg);
    for (const m of rects) {
      if (!m.seat) continue;
      el("rect", {
        class: "elev-seat", "data-slot": m.slot_key,
        x: r(px(m.seat.x_mm)), y: r(py(m.seat.y_mm)),
        width: r(Math.max(m.seat.w_mm * s, 0.5)),
        height: r(Math.max(m.seat.h_mm * s, 0.5)),
      }, seats);
    }
  }

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

  // The fastener PLACES, when the caller wants them. Each carries its own count
  // (`report/elevation.py`), so a panel taking 96 screws is 32 dots reading ×3
  // rather than a rash — "a dot per screw would bury the panel" is still true,
  // and this is not that.
  if (fixings) {
    const group = el("g", { class: "elev-fixings" }, svg);
    for (const f of elev.fixings || []) {
      const [fx, fy] = layoutPx(L, f.x_mm, f.y_mm);
      const dot = el("circle", {
        class: "elev-fixing", cx: r(fx), cy: r(fy), r: 5,
        "data-slot": f.slot_key, "data-index": String(f.index),
      }, group);
      // identifiers and a count, set as TEXT — a slot key never becomes markup
      el("title", {}, dot).textContent = `${f.slot_key} ×${f.qty}`;
    }
  }

  if (annotations) {
    const widthRow = y0 + dh + 22 + (margins ? MARGIN_ROW : 0);
    dimension(svg, "x", x0, widthRow, x0 + dw, widthRow,
              tu("elevation.length", { len_mm: w }));
    dimension(svg, "y", x0 - 26, y0, x0 - 26, y0 + dh,
              tu("elevation.length", { len_mm: h }));
    if (dim) drawGap(svg, dim, { px, py, w, h, y0, lane: 0 });
    // the pitch goes one lane out from the gap when both are on the same side
    if (pitch)
      drawGap(svg, { ...pitch, gap_mm: pitch.value_mm,
                     start_mm: pitch.from_mm, end_mm: pitch.to_mm },
              { px, py, w, h, y0, lane: dim?.axis === pitch.axis ? 1 : 0,
                cls: "elev-pitch-dim" });
    if (margins) drawMargins(svg, margins, { px, py, w, h, x0, y0, dw, dh });
  }

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
function drawGap(svg, dim, { px, py, w, h, y0, lane = 0, cls = "elev-gap-dim" }) {
  const g = el("g", { class: `elev-dim ${cls}` }, svg);
  const label = tu("elevation.length", { len_mm: dim.gap_mm });
  if (dim.axis === "x") {
    const x1 = px(dim.start_mm);
    const x2 = px(dim.end_mm);
    const y = y0 - 22 - lane * CALLOUT_STEP;
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
  const x = px(w) + 20 + lane * CALLOUT_STEP;
  el("line", { x1: r(x), y1: r(y1), x2: r(x), y2: r(y2) }, g);
  for (const y of [y1, y2])
    el("line", { class: "elev-leader", x1: r(px(dim.cross_mm)), y1: r(y), x2: r(x), y2: r(y) }, g);
  const cy = (y1 + y2) / 2;
  el("text", { class: "elev-dim-label", x: r(x + 16), y: r(cy), "text-anchor": "middle",
               transform: `rotate(-90 ${r(x + 16)} ${r(cy)})` }, g).textContent = label;
}

/** The posts the bay stands between, and their caps.
 *
 * `x_mm` is negative on the start side and that is the contract — the post
 * occupies the millimetres BEFORE the opening. Clamping it to zero would draw
 * the post over the first board and shift the whole bay a post-width across.
 *
 * A post is selectable like any member (`data-slot`), because the two parts of
 * a fence that had no editor were exactly the two with nowhere to click. */
function drawPosts(svg, L, elev) {
  const group = el("g", { class: "elev-posts" }, svg);
  for (const post of elev.posts || []) {
    const [x, y] = layoutPx(L, post.x_mm, post.h_mm + (post.cap_h_mm || 0));
    const [, base] = layoutPx(L, post.x_mm, 0);
    const rect = el("rect", {
      class: `elev-post${post.declared === false ? " elev-nominal" : ""}`,
      x: r(x), y: r(y + (post.cap_h_mm || 0) * L.s),
      width: r(Math.max(post.w_mm * L.s, 0.5)),
      height: r(Math.max(base - y - (post.cap_h_mm || 0) * L.s, 0.5)),
      "data-slot": post.sku ? `post:${post.side}` : "post",
      "data-side": post.side,
    }, group);
    // identifiers only, and as TEXT — a sku never becomes markup or paint
    el("title", {}, rect).textContent =
      [post.kind, post.sku].filter(Boolean).join(" \u00b7 ") || "post";
    if (post.cap_h_mm > 0) {
      const cap = el("rect", {
        // the catalog carries no cap height, so the one drawn is invented — and
        // a drawing that paints an invented size exactly like a measured one is
        // claiming a precision it does not have
        class: `elev-cap${post.cap_declared === false ? " elev-nominal" : ""}`,
        x: r(x), y: r(y),
        width: r(Math.max(post.w_mm * L.s, 0.5)),
        height: r(Math.max(post.cap_h_mm * L.s, 0.5)),
        "data-slot": "cap", "data-side": post.side,
      }, group);
      el("title", {}, cap).textContent = post.cap_sku || "cap";
    }
  }
}

const r = (n) => Math.round(n * 10) / 10;

/** What is left clear at each end of the pattern, dimensioned under the panel.
 *
 * On its own row rather than sharing the width dimension's line: the two answer
 * different questions ("how wide is the opening" against "how far in does the
 * infill start"), and a reader who has to work out which tick belongs to which
 * has been given a puzzle instead of a dimension. A zero margin is drawn as
 * nothing at all — a dimension line of length zero is a tick with a 0 beside it,
 * which reads as a mistake. */
function drawMargins(svg, margins, { px, py, w, h, x0, y0, dw, dh }) {
  const g = el("g", { class: "elev-dim elev-margin-dim" }, svg);
  if (margins.axis === "x") {
    const y = y0 + dh + 14;
    if (margins.start_mm > 0) marginSpan(g, x0, px(margins.start_mm), y, margins.start_mm);
    if (margins.end_mm > 0)
      marginSpan(g, px(w - margins.end_mm), x0 + dw, y, margins.end_mm);
    return;
  }
  // a horizontal pattern's margins run up the panel, so they are called out on
  // the start edge beside the height dimension
  const x = x0 - 14;
  if (margins.start_mm > 0)
    marginSpan(g, x, x, y0 + dh, margins.start_mm, py(h - margins.start_mm));
  if (margins.end_mm > 0)
    marginSpan(g, x, x, y0, margins.end_mm, py(margins.end_mm));
}

function marginSpan(g, x1, x2, y, value_mm, yEnd) {
  const vertical = yEnd !== undefined;
  el("line", vertical
    ? { x1: r(x1), y1: r(x2), x2: r(x1), y2: r(yEnd) }
    : { x1: r(x1), y1: r(y), x2: r(x2), y2: r(y) }, g);
  const label = el("text", {
    class: "elev-dim-label elev-margin-label",
    x: r(vertical ? x1 - 4 : (x1 + x2) / 2),
    y: r(vertical ? (x2 + yEnd) / 2 : y - 4),
    "text-anchor": "middle",
  }, g);
  if (vertical)
    label.setAttribute("transform",
      `rotate(-90 ${r(x1 - 4)} ${r((x2 + yEnd) / 2)})`);
  label.textContent = tu("elevation.length", { len_mm: value_mm });
}
