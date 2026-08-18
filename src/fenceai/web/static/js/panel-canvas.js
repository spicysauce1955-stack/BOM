// The panel canvas: the drawing IS the editor.
//
// It draws nothing of its own. `renderElevation` paints the rectangles the
// server placed (`report/elevation.py`), and this module lays an interaction
// layer over them in the same coordinates — `elevationLayout` is shared for
// exactly that reason, because a second copy of the transform is a handle three
// pixels from the board it moves.
//
// The canvas is NEVER mirrored in RTL. It joins the plan canvas, the profile and
// the macro elevation in that standing rule: the first board of a panel is the
// first board in every language, and mirroring would reverse it against the
// plan drawn one tab over.
//
// A drag does NOT re-price per frame. Pricing is a request and the fit runs on
// the server, so a drawing rebuilt under the pointer would fight the hand
// holding it — the handle and a dashed ghost move locally with a live numeric
// readout, and the commit on pointerup is what writes the document and asks for
// the new panel. `isDragging()` is how the caller knows not to repaint.
//
// DOM: only the host it is handed, exactly like `renderInspector`.

import {
  elevationLayout, highlightSlot, layoutMm, layoutPx, renderElevation,
} from "./elevation.js";
// the SVG element builder (createElementNS), not builder-ui's HTML one — an
// HTML <circle> in an SVG is a node the browser lays out and never draws
import { el } from "./geom.js";
import { t } from "./i18n.js";
import {
  gapFromDrag, handlesFor, marginFromDrag, placementFromDrag, widthFromDrag,
} from "./panel-canvas-geom.js";
import { tu } from "./units.js";

// A drag in progress, or null. Module state rather than a closure because the
// CALLER has to see it: a re-price landing mid-drag would rebuild the SVG the
// pointer is captured on, and the capture would go with it.
let drag = null;

export const isDragging = () => drag !== null;

/** Draw the panel and everything a pointer can do to it.
 *
 * `elev` is the server's `PanelElevation`; `spec` the AUTHORED `PanelSpec` the
 * drag writes into. Both are needed and neither is derivable from the other:
 * the drawing says where a board ended up, the spec says which number put it
 * there.
 *
 * Callbacks: `onSelect(selection)` when something is clicked (including the
 * empty opening, which selects the panel itself); `onCommit(handle, value)` on
 * pointerup, with the authored value the drag produced. There is deliberately
 * no per-move callback into the document — a drag is one edit, not sixty. */
export function renderCanvas(host, { elev, spec, selection } = {}, {
  onSelect = () => {}, onCommit = () => {},
} = {}) {
  if (!host) return null;
  // A repaint replaces the SVG the pointer was captured on, so a drag in
  // progress is over whether or not its pointerup ever arrives. Not clearing it
  // left `isDragging()` true for the rest of the session, and the caller — which
  // uses it to decide whether to repaint — stopped repainting for good.
  drag = null;
  host.innerHTML = "";
  const svg = renderElevation(elev, { fixings: true, posts: true });
  if (!svg) {
    host.appendChild(emptyOpening());
    return null;
  }
  svg.classList.add("panel-canvas-svg");
  host.appendChild(svg);

  // the SAME options the drawing was rendered with — the posts change the
  // padding, and a layout that disagreed would put every handle off its board
  const layout = elevationLayout(elev, { posts: true });
  mountHandles(svg, layout, elev, spec, onCommit);
  wireSelection(svg, spec, onSelect);
  applySelection(svg, selection);
  return svg;
}

/** What a model with nothing in it yet looks like: an opening, and what to do.
 *
 * `renderElevation` returns null there — correctly, it has no rectangles to
 * draw — and an empty box with no explanation is where a new author stops. */
function emptyOpening() {
  const svg = el("svg", { class: "elevation-svg panel-canvas-svg",
                          viewBox: "0 0 400 260", preserveAspectRatio: "xMidYMid meet" });
  el("rect", { class: "elev-opening", x: "20", y: "20",
               width: "360", height: "220" }, svg);
  el("text", { class: "canvas-empty", x: "200", y: "130",
               "text-anchor": "middle" }, svg).textContent = t("canvas.empty_hint");
  return svg;
}

// --- selection ---------------------------------------------------------------

/** Which authored thing a drawn rectangle or fastener dot belongs to.
 *
 * `data-slot` is the AUTHORED key — `resolve_panel` builds every slot key from
 * the spec (a frame slot's `key`, a member's `key`, a fixing rule's `key`), so
 * this is a lookup and never a guess. A rectangle whose key matches nothing in
 * the spec selects the panel: it belongs to a variant or a version the editor is
 * no longer pointed at, and inventing an element for it would be worse. */
export function selectionForSlot(spec, slotKey) {
  // the two parts a fence has that the panel does not: they carry their own
  // marker rather than a spec key, because they belong to the MODEL's post slot
  if (slotKey === "cap") return { kind: "cap", key: "cap" };
  if (slotKey === "post" || String(slotKey).startsWith("post:"))
    return { kind: "post", key: "post" };
  if ((spec?.frame || []).some((s) => s.key === slotKey))
    return { kind: "frame", key: slotKey };
  if ((spec?.infill?.pattern || []).some((m) => m.key === slotKey))
    return { kind: "infill", key: slotKey };
  if ((spec?.fixings || []).some((f) => f.key === slotKey))
    return { kind: "fixing", key: slotKey };
  return { kind: "panel", key: null };
}

function wireSelection(svg, spec, onSelect) {
  svg.addEventListener("click", (ev) => {
    if (ev.target.closest?.("[data-handle]")) return;   // a handle is not a selection
    const hit = ev.target.closest?.("[data-slot]");
    onSelect(hit ? selectionForSlot(spec, hit.getAttribute("data-slot"))
                 : { kind: "panel", key: null });
  });
  svg.classList.add("elev-clickable");
}

function applySelection(svg, selection) {
  highlightSlot(svg, selection?.key ?? null);
  for (const dot of svg.querySelectorAll(".elev-fixing"))
    dot.classList.toggle("selected",
      !!selection?.key && dot.getAttribute("data-slot") === selection.key);
}

// --- handles -----------------------------------------------------------------

function mountHandles(svg, layout, elev, spec, onCommit) {
  const group = el("g", { class: "canvas-handles" }, svg);
  const ghost = el("line", { class: "canvas-ghost", hidden: "" }, svg);
  const readout = el("text", { class: "canvas-readout",
                               "text-anchor": "middle" }, svg);

  for (const handle of handlesFor(elev, spec)) {
    const [cx, cy] = layoutPx(layout, handle.x_mm, handle.y_mm);
    const dot = el("circle", {
      class: `canvas-handle canvas-handle-${handle.kind}`,
      cx: round(cx), cy: round(cy), r: 6,
      "data-handle": handle.id, "data-axis": handle.axis,
    }, group);
    el("title", {}, dot).textContent = t(`canvas.handle.${handle.kind}`);
    wireDrag(dot, svg, layout, handle, elev, spec, { ghost, readout, onCommit });
  }
}

function wireDrag(dot, svg, layout, handle, elev, spec, { ghost, readout, onCommit }) {
  dot.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    dot.setPointerCapture(ev.pointerId);
    drag = { handle, start: pointerMm(svg, layout, ev), value: null };
    dot.classList.add("dragging");
  });

  dot.addEventListener("pointermove", (ev) => {
    if (!drag || drag.handle !== handle) return;
    const at = pointerMm(svg, layout, ev);
    drag.value = valueFor(handle, spec, elev, drag.start, at);
    if (drag.value === null) return;
    const [x, y] = handle.axis === "x"
      ? [at[0], handle.y_mm] : [handle.x_mm, at[1]];
    const [px, py] = layoutPx(layout, x, y);
    dot.setAttribute("cx", round(px));
    dot.setAttribute("cy", round(py));
    showGhost(ghost, readout, layout, handle, [px, py], drag.value.readout_mm);
  });

  const finish = (ev) => {
    if (!drag || drag.handle !== handle) return;
    const committed = drag.value;
    drag = null;
    dot.classList.remove("dragging");
    ghost.setAttribute("hidden", "");
    readout.textContent = "";
    if (dot.hasPointerCapture?.(ev.pointerId)) dot.releasePointerCapture(ev.pointerId);
    if (committed) onCommit(handle, committed);
  };
  dot.addEventListener("pointerup", finish);
  dot.addEventListener("pointercancel", finish);
}

/** The pointer, in PANEL millimetres.
 *
 * The one DOM-bound step of the transform, and the reason `layoutMm` is pure
 * and lives next door: a client point has to cross the SVG's own screen matrix
 * before any of the arithmetic means anything. */
function pointerMm(svg, layout, ev) {
  const ctm = svg.getScreenCTM();
  if (!ctm) return [0, 0];
  const point = svg.createSVGPoint();
  point.x = ev.clientX;
  point.y = ev.clientY;
  const local = point.matrixTransform(ctm.inverse());
  return layoutMm(layout, local.x, local.y);
}

/** The authored value this drag would write, and the number to show while it is
 *  being dragged. `null` when the handle cannot write anything — an interior
 *  rail of a distributed slot, whose position is not authored anywhere.
 *
 *  Exported because it is pure and it is where the two rules that matter meet:
 *  which authored field each handle kind writes, and that a WIDTH reads the
 *  pointer absolutely while a GAP and a MARGIN read the distance it moved. A
 *  browser can only show that something changed. */
export function valueFor(handle, spec, elev, start, at) {
  switch (handle.kind) {
    case "placement": {
      const slot = (spec.frame || []).find((s) => s.key === handle.slot_key);
      if (!slot) return null;
      const drawn = (elev.members || [])
        .filter((m) => m.kind === "frame" && m.slot_key === handle.slot_key);
      const placement = placementFromDrag(slot.placement, {
        orientation: slot.orientation, index: handle.index, count: drawn.length,
        height_mm: elev.height_mm, width_mm: elev.width_mm,
        x_mm: at[0], y_mm: at[1],
      });
      if (JSON.stringify(placement) === JSON.stringify(slot.placement)) return null;
      // the number being WRITTEN, not where the pointer is: a `from_top` rail
      // dragged to 640 above the panel bottom authors 1160 down from the top,
      // and a readout showing 640 would disagree with the field it is about to
      // put 1160 into
      return { kind: "placement", placement,
               readout_mm: authoredLength(placement, elev, slot, handle) };
    }
    case "width": {
      const member = memberOf(spec, handle.slot_key);
      const first = firstDrawn(elev, handle.slot_key);
      if (!member || !first) return null;
      const width = widthFromDrag(member, {
        x_mm: handle.axis === "x" ? at[0] : at[1],
        member_x_mm: handle.axis === "x" ? first.x_mm : first.y_mm,
      });
      return { kind: "width", width_mm: width, readout_mm: width };
    }
    case "gap": {
      const member = memberOf(spec, handle.slot_key);
      if (!member) return null;
      const gap = gapFromDrag(member, { delta_mm: delta(handle, start, at) });
      return { kind: "gap", gap_after_mm: gap, readout_mm: Math.abs(gap) };
    }
    case "margin": {
      const infill = spec.infill;
      if (!infill) return null;
      // the start edge moves INWARD as the pointer moves along the axis, so the
      // margin grows with the pointer rather than against it
      const margin = marginFromDrag(infill, { delta_mm: delta(handle, start, at) });
      return { kind: "margin", edge_margin_mm: margin, readout_mm: margin };
    }
    default:
      return null;
  }
}

/** What a placement's own number reads as, in millimetres.
 *
 * `fraction` has no millimetre of its own — it is a permille of the height — so
 * it reports the height it lands at, which is the one figure a person dragging
 * it is watching. */
function authoredLength(placement, elev, slot, handle) {
  const axisLen = slot.orientation === "vertical" ? elev.width_mm : elev.height_mm;
  switch (placement.kind) {
    case "from_bottom":
    case "from_top":
      return placement.offset_mm;
    case "fraction":
      return Math.round((placement.permille * axisLen) / 1000);
    case "distributed":
      // the inset on the side that was grabbed — the other one did not move,
      // and reporting it would read as the drag having done nothing
      return handle.index === 0
        ? (placement.bottom_inset_mm || 0) : (placement.top_inset_mm || 0);
    default:
      return 0;
  }
}

const delta = (handle, start, at) =>
  (handle.axis === "x" ? at[0] - start[0] : at[1] - start[1]);

const memberOf = (spec, key) =>
  (spec?.infill?.pattern || []).find((m) => m.key === key);

const firstDrawn = (elev, key) => (elev.members || [])
  .filter((m) => m.kind === "infill" && m.slot_key === key)
  .sort((a, b) => (a.x_mm - b.x_mm) || (a.y_mm - b.y_mm))[0];

function showGhost(ghost, readout, layout, handle, [px, py], valueMm) {
  ghost.removeAttribute("hidden");
  if (handle.axis === "x") {
    ghost.setAttribute("x1", round(px));
    ghost.setAttribute("x2", round(px));
    ghost.setAttribute("y1", round(layout.y0));
    ghost.setAttribute("y2", round(layout.y0 + layout.dh));
  } else {
    ghost.setAttribute("y1", round(py));
    ghost.setAttribute("y2", round(py));
    ghost.setAttribute("x1", round(layout.x0));
    ghost.setAttribute("x2", round(layout.x0 + layout.dw));
  }
  readout.setAttribute("x", round(handle.axis === "x" ? px : layout.x0 + layout.dw / 2));
  readout.setAttribute("y", round(handle.axis === "x" ? layout.y0 - 6 : py - 8));
  readout.textContent = tu("canvas.value", { len_mm: valueMm });
}

const round = (n) => String(Math.round(n * 10) / 10);
