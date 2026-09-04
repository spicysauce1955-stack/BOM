// The house and the street — slice 3 of the salesperson MVP.
//
// A salesperson does not think "node at (0,0) to node at (12000,0)". They think
// "along the street side, then it turns in toward the house." Without this the
// office person cannot read the layout as a PLACE, and every question they would
// otherwise answer themselves becomes a phone call.
//
// **It touches generation nowhere.** A landmark changes no quantity, so it lives
// on `Project.context` and not in `Topology` — in the topology it would bump the
// revision and 409 the structure sheet because somebody nudged a driveway. That
// constraint is what keeps this slice cheap, and it is asserted in
// `tests/project/test_context.py`, not merely intended.
//
// One gesture, one shape: press, drag, release. A house is the rectangle you
// dragged, a street is the line. A salesperson sketching on paper draws both
// with the same stroke, and a click-click-click polyline builder would be a
// second draft state machine beside the one `editor.js` already owns.

import { esc } from "./api.js";
import { clearGroup, el, toPx } from "./geom.js";
import { t } from "./i18n.js";
import { on, state } from "./state.js";

// Which kinds are drawn by dragging, and what a drag makes of them. The registry
// mirrors `LANDMARK_KINDS` on the backend; `boundary` and `other` are authored
// there today and render here, which is why this map is a subset rather than a
// copy.
export const DRAG_KINDS = ["house", "street"];

/** The landmark a press-drag-release describes. PURE — no DOM, no state, so it
 *  is tested in node rather than by aiming a mouse at a canvas.
 *
 *  A house is the rectangle the drag spans, in world millimetres; a street is
 *  the line itself, because a road is not a box and squaring it off would put a
 *  corner where the salesperson drew none.
 *
 *  Returns null for a gesture too small to be deliberate: a stray click while
 *  the house tool is active must not leave an invisible 3 mm building on the
 *  drawing that the office person then has to ask about. */
export function shapeFor(kind, from, to, minMm = 300) {
  if (!from || !to) return null;
  const [x0, y0] = from;
  const [x1, y1] = to;
  if (Math.abs(x1 - x0) < minMm && Math.abs(y1 - y0) < minMm) return null;
  if (kind === "street")
    return { points: [[x0, y0], [x1, y1]], closed: false };
  if (kind === "house")
    return {
      points: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
      closed: true,
    };
  return null;
}

/** A stable id that does not collide with a landmark already on the project.
 *  Sequence-based rather than time-based so two landmarks drawn in the same
 *  millisecond cannot share one — the duplicate the backend refuses. */
export function nextLandmarkId(existing) {
  const used = new Set((existing || []).map((lm) => lm.id));
  for (let i = 1; ; i++) if (!used.has(`lm${i}`)) return `lm${i}`;
}

// --- rendering ---------------------------------------------------------------

const STYLE = {
  house:    { fill: "#e2e8f0", stroke: "#94a3b8", dash: "" },
  street:   { fill: "none",    stroke: "#cbd5e1", dash: "" },
  boundary: { fill: "none",    stroke: "#a3a3a3", dash: "6 4" },
  other:    { fill: "none",    stroke: "#cbd5e1", dash: "2 3" },
};

export function render() {
  const g = clearGroup("g-context");
  if (!g) return;
  for (const lm of state.project?.context?.landmarks || []) {
    const s = STYLE[lm.kind] || STYLE.other;
    const pts = lm.points.map(toPx);
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ")
            + (lm.closed ? " Z" : "");
    // `pointer-events: none` throughout: the context is a backdrop. A house
    // that swallowed a click on the fence in front of it would make the drawing
    // harder to edit than it was before there was a house.
    el("path", { d, fill: s.fill, stroke: s.stroke, "stroke-width": 2,
                 "stroke-dasharray": s.dash, "pointer-events": "none" }, g);
    // A street label is worth more than the line: "street" and "the neighbour's
    // side" look identical as geometry and mean different things to the office.
    const text = lm.label || t(`context.kind.${lm.kind}`);
    if (text) {
      const mid = pts.reduce((a, p) => [a[0] + p[0] / pts.length,
                                        a[1] + p[1] / pts.length], [0, 0]);
      el("text", { x: mid[0], y: mid[1], "font-size": 11, fill: "#64748b",
                   "text-anchor": "middle", class: "context-label",
                   "pointer-events": "none" }, g).textContent = text;
    }
  }
}

/** The rubber band during the drag, drawn in its own group so a redraw of the
 *  committed landmarks cannot wipe it and vice versa. */
export function renderDraft(kind, from, to) {
  const g = clearGroup("g-context-draft");
  if (!g) return;
  const shape = shapeFor(kind, from, to);
  if (!shape) return;
  const pts = shape.points.map(toPx);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ")
          + (shape.closed ? " Z" : "");
  el("path", { d, fill: "none", stroke: "#64748b", "stroke-width": 2,
               "stroke-dasharray": "4 3", "pointer-events": "none" }, g);
}

export function clearDraft() {
  clearGroup("g-context-draft");
}

// --- the list, so a landmark can be named or removed --------------------------

function renderPanel() {
  const host = ensureHost();
  if (!host) return;
  const marks = state.project?.context?.landmarks || [];
  host.innerHTML = `
    <h3>${esc(t("context.title"))}</h3>
    ${marks.length ? `<ul class="context-list">${marks.map((lm) => `
      <li data-lm="${esc(lm.id)}">
        <span class="context-kind">${esc(t(`context.kind.${lm.kind}`))}</span>
        <input class="context-label-input" data-lm="${esc(lm.id)}"
               value="${esc(lm.label)}"
               placeholder="${esc(t("context.label_placeholder"))}">
        <button class="context-remove" data-lm="${esc(lm.id)}"
                title="${esc(t("context.remove"))}">✕</button>
      </li>`).join("")}</ul>`
      : `<div class="meta">${esc(t("context.empty"))}</div>`}`;
  for (const input of host.querySelectorAll(".context-label-input"))
    input.addEventListener("change", () => labelLandmark(input.dataset.lm, input.value));
  for (const btn of host.querySelectorAll(".context-remove"))
    btn.addEventListener("click", () => removeLandmark(btn.dataset.lm));
}

function ensureHost() {
  if (typeof document === "undefined") return null;
  let host = document.getElementById("context-panel");
  if (host) return host;
  const side = document.querySelector(".side-col");
  if (!side) return null;
  host = document.createElement("div");
  host.className = "panel";
  host.id = "context-panel";
  const after = document.getElementById("job-panel");
  side.insertBefore(host, after ? after.nextSibling : side.firstChild);
  return host;
}

async function labelLandmark(id, label) {
  const { saveContext } = await import("./state.js");
  const lm = (state.project?.context?.landmarks || []).find((m) => m.id === id);
  if (!lm) return;
  lm.label = label.trim();
  await saveContext();
}

async function removeLandmark(id) {
  const { saveContext } = await import("./state.js");
  const ctx = state.project?.context;
  if (!ctx) return;
  ctx.landmarks = ctx.landmarks.filter((m) => m.id !== id);
  await saveContext();
}

export function initContext() {
  render();
  renderPanel();
  const redraw = () => { render(); renderPanel(); };
  on("project-loaded", redraw);
  on("context-changed", redraw);
  on("locale-changed", redraw);
  on("role-changed", redraw);
  on("fit-view", render);
}
