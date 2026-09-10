// The property around the fence — slice 3 of the salesperson MVP, widened.
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
// This file used to open by defending "one gesture, one shape: press, drag,
// release" — a house is the rectangle you dragged, a street is the line — on the
// grounds that a click-click-click builder would be a second draft state machine
// beside the one `editor.js` already owns. The user overruled it, and the reasons
// were better than ours:
//   - a house is NOT a rectangle. It is a closed shape of straight lines, and a
//     salesperson who has to approximate an L-shaped building with a box is
//     drawing something the office person will then have to ask about.
//   - a street with no width cannot be edited. "The street should be rectangle,
//     and editable (angle, ...)" is one requirement, not two: a bare line has no
//     width to type, so making the street a band is what makes it editable at all.
// So the gesture is now per kind (`landmark-shape.js: GESTURE`) — drag a band, a
// rect or a circle, click-build a polygon — and the cost we were avoiding is paid
// once, in `editor.js`, rather than pushed onto every person who draws a house.
//
// The kinds beyond house and street (sidewalk, pool, tree, boundary, other) are
// deliberately NOT offered as default tools; `index.html` puts them behind
// "other". Simple and intuitive is the requirement, and seven equal buttons is
// neither.
//
// ALL geometry construction lives in `./landmark-shape.js` — pure, no DOM, no
// state, tested in node. This module owns hit-testing, rendering and the panel:
// the parts that need a canvas or a document. `shapeFor` and `DRAG_KINDS` are
// re-exported here because that is where every caller already looks for them.

import { esc } from "./api.js";
import { clearGroup, el, toPx } from "./geom.js";
import { pushSnapshot } from "./history.js";
import { t } from "./i18n.js";
import {
  circleFromMetrics, circleMetrics, gestureFor, LANDMARK_KINDS, MIN_MM,
  metricsKind, rectFromMetrics, rectMetrics, shapeFor, TREE_SIDES,
} from "./landmark-shape.js";
import { on, state } from "./state.js";
import { inputStep, toDisplayValue, toMm, tu } from "./units.js";

export { shapeFor };

// Which kinds a press-drag-release draws, and therefore which ones `editor.js`
// may hand to `shapeFor`. DERIVED from the registry rather than listed, so a new
// kind added to `landmark-shape.js` is drawable the moment it has a gesture —
// the hand-written list this replaces was a second registry to forget to update.
// A polygon kind is not here: it is click-built and has no drag to interpret.
export const DRAG_KINDS = LANDMARK_KINDS.filter((k) => gestureFor(k) !== "polygon");

// Ray-casting point-in-polygon: a house has an interior, so "on the house"
// means inside its outline, not near an edge. Every kind is a closed shape now
// (a street is a band, a tree a 16-gon), so this is the usual answer.
function pointInPolygon([px, py], points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i], [xj, yj] = points[j];
    const crosses = (yi > py) !== (yj > py)
      && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

// Shortest distance from a point to a polyline (nearest point per segment,
// clamped to the segment) — an OPEN landmark has no interior to land inside of.
function distToPolyline([px, py], points) {
  let best = Infinity;
  for (let i = 0; i + 1 < points.length; i++) {
    const [ax, ay] = points[i], [bx, by] = points[i + 1];
    const dx = bx - ax, dy = by - ay;
    const lenSq = dx * dx + dy * dy;
    const t = lenSq ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq)) : 0;
    const d = Math.hypot(px - (ax + dx * t), py - (ay + dy * t));
    if (d < best) best = d;
  }
  return best;
}

// A line has no area: without a tolerance band it would be nearly impossible to
// grab with a mouse. It survives the move to bands because streets drawn BEFORE
// that move are still two-point polylines on saved projects, and they must stay
// grabbable. 300 mm mirrors `MIN_MM` — as easy to grab as it was to draw.
const LINE_HIT_TOL_MM = MIN_MM;

function hits(lm, point) {
  return lm.closed ? pointInPolygon(point, lm.points)
                   : distToPolyline(point, lm.points) <= LINE_HIT_TOL_MM;
}

/** The existing landmark of KIND under `point`, or null. PURE — no DOM, no
 *  state — so a move-drag can ask "is this press on a landmark" the same way
 *  `shapeFor` is asked "what shape does this drag describe": tested in node
 *  rather than by aiming a mouse at a canvas.
 *
 *  Only landmarks of KIND are considered: with the house tool active, a press
 *  over a street must fall through to "draw a new house" rather than silently
 *  start moving the street. */
export function landmarkAt(landmarks, point, kind) {
  for (const lm of landmarks || []) if (lm.kind === kind && hits(lm, point)) return lm;
  return null;
}

/** The topmost landmark under `point`, whatever its kind, or null.
 *
 *  The select/note tools have no kind in hand: a person pointing at the pool
 *  means the pool. Reverse order because `render()` draws the list front to
 *  back, so the LAST one drawn is the one they can see under the cursor — a
 *  tree standing on the lawn must win over the lawn it was drawn on top of. */
export function landmarkAtAny(landmarks, point) {
  const marks = landmarks || [];
  for (let i = marks.length - 1; i >= 0; i--) if (hits(marks[i], point)) return marks[i];
  return null;
}

/** The current landmark with this id, read fresh from whatever list is
 *  passed in — never a reference captured once at press time. A move-drag
 *  spans an async `saveContext()` (its own, or one queued by undo/redo);
 *  `geom.runById`/`nodeById` are looked up fresh on every `onDragMove` for
 *  the same reason: a captured object goes stale the moment a `state.project`
 *  swap (a PUT response landing) replaces the array it lived in, and a drag
 *  that kept mutating the stale copy would save nothing. */
export function landmarkById(landmarks, id) {
  return (landmarks || []).find((lm) => lm.id === id);
}

/** A stable id that does not collide with a landmark already on the project.
 *  Sequence-based rather than time-based so two landmarks drawn in the same
 *  millisecond cannot share one — the duplicate the backend refuses. */
export function nextLandmarkId(existing) {
  const used = new Set((existing || []).map((lm) => lm.id));
  for (let i = 1; ; i++) if (!used.has(`lm${i}`)) return `lm${i}`;
}

// --- rendering ---------------------------------------------------------------

// Muted on purpose, all of it. The context sits UNDER the fence drawing and the
// fence is what the drawing is about: a pool in swimming-pool blue that outshouts
// the run it stands beside has made the drawing worse, not richer. So every fill
// is a pale tint of the thing it names and every stroke is one step darker.
const STYLE = {
  house:    { fill: "#e2e8f0", stroke: "#94a3b8", dash: "" },
  // A street is a filled band now, not a hairline — see the header.
  street:   { fill: "#e5e7eb", stroke: "#cbd5e1", dash: "" },
  sidewalk: { fill: "#f1f5f9", stroke: "#cbd5e1", dash: "4 3" },
  pool:     { fill: "#bae6fd", stroke: "#38bdf8", dash: "" },
  tree:     { fill: "#bbf7d0", stroke: "#4ade80", dash: "" },
  boundary: { fill: "none",    stroke: "#a3a3a3", dash: "6 4" },
  other:    { fill: "none",    stroke: "#cbd5e1", dash: "2 3" },
};

// Kinds whose NAME earns the space when the salesperson typed no label. A street
// and "the neighbour's side" look identical as geometry and mean different things
// to the office, so the word is worth more than the band. A pool and a tree are
// the opposite: the shape and the colour already say it, and printing "tree"
// across a 16-gon the size of a tree is noise over the drawing it sits under.
const NAMED_KINDS = new Set(["house", "street", "sidewalk", "boundary", "other"]);

function pathData(pts, closed) {
  return pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ")
       + (closed ? " Z" : "");
}

export function render() {
  const g = clearGroup("g-context");
  if (!g) return;
  for (const lm of state.project?.context?.landmarks || []) {
    const s = STYLE[lm.kind] || STYLE.other;
    const pts = lm.points.map(toPx);
    // `pointer-events: none` throughout: the context is a backdrop. A house
    // that swallowed a click on the fence in front of it would make the drawing
    // harder to edit than it was before there was a house.
    el("path", { d: pathData(pts, lm.closed), fill: s.fill, stroke: s.stroke,
                 "stroke-width": 2, "stroke-dasharray": s.dash,
                 "pointer-events": "none" }, g);
    const text = lm.label || (NAMED_KINDS.has(lm.kind) ? t(`context.kind.${lm.kind}`) : "");
    if (text) {
      // Centroid of the corners: right for a rectangle, right enough for a band,
      // and for a click-built house it lands inside anything that is not deeply
      // concave — which a building traced from a plan is not.
      const mid = pts.reduce((a, p) => [a[0] + p[0] / pts.length,
                                        a[1] + p[1] / pts.length], [0, 0]);
      el("text", { x: mid[0], y: mid[1], "font-size": 11, fill: "#64748b",
                   "text-anchor": "middle", class: "context-label",
                   "pointer-events": "none" }, g).textContent = text;
    }
  }
}

/** The rubber band during a DRAG, drawn in its own group so a redraw of the
 *  committed landmarks cannot wipe it and vice versa. */
export function renderDraft(kind, from, to) {
  const g = clearGroup("g-context-draft");
  if (!g) return;
  const shape = shapeFor(kind, from, to, MIN_MM);
  if (!shape) return;
  el("path", { d: pathData(shape.points.map(toPx), shape.closed), fill: "none",
               stroke: "#64748b", "stroke-width": 2, "stroke-dasharray": "4 3",
               "pointer-events": "none" }, g);
}

/** The rubber band while a house is being CLICK-BUILT: the corners placed so far
 *  as a solid polyline, a dashed leg to wherever the cursor is, and a ring on the
 *  first corner.
 *
 *  The ring is the whole affordance. A click-built shape has no release to end
 *  it, so the person needs to be told where "finish" is, and the answer — click
 *  the point you started from — is only obvious once something marks that point.
 *
 *  Same group as `renderDraft`, so `clearDraft()` wipes either kind of draft and
 *  neither tool has to know which one is live. */
export function renderDraftPolygon(points, cursor) {
  const g = clearGroup("g-context-draft");
  if (!g || !points?.length) return;
  const pts = points.map(toPx);
  if (pts.length > 1)
    el("path", { d: pathData(pts, false), fill: "none", stroke: "#64748b",
                 "stroke-width": 2, "pointer-events": "none" }, g);
  if (cursor) {
    const c = toPx(cursor);
    el("path", { d: pathData([pts[pts.length - 1], c], false), fill: "none",
                 stroke: "#64748b", "stroke-width": 2, "stroke-dasharray": "4 3",
                 "pointer-events": "none" }, g);
  }
  el("circle", { cx: pts[0][0], cy: pts[0][1], r: 5, fill: "#fff",
                 stroke: "#64748b", "stroke-width": 2,
                 "pointer-events": "none" }, g);
}

export function clearDraft() {
  clearGroup("g-context-draft");
}

// --- the list, so a landmark can be named, resized or removed -----------------

// A number field wide enough for "12000" and no wider. `.num` is the app-wide
// ltr/isolate class: a Latin numeral inside a Hebrew row reorders without it.
function metricField(id, name, label, value, step) {
  return `<label style="display:inline-flex;align-items:center;gap:3px">
      <span class="meta">${esc(label)}</span>
      <input class="context-metric num" type="number" step="${esc(step)}"
             data-lm="${esc(id)}" data-metric="${esc(name)}"
             value="${esc(String(value))}" style="inline-size:66px">
    </label>`;
}

// The editable numbers for one landmark, in the reader's display unit.
//
// "The street should be rectangle, and editable (angle, ...)": a landmark whose
// shape is a rectangle is described completely by centre + angle + length +
// width, and those are the four things a person wants to correct after sketching
// one by hand. A circle is radius. A click-built house is NEITHER, and gets no
// fields at all — inventing an angle for a free polygon would mean typing one
// silently squares off a shape somebody traced, which is worse than not offering
// it. Its corner count is shown instead, because "is this the shape I drew" is
// the only question the panel can answer about it.
function metricsHtml(lm) {
  const kind = metricsKind(lm);
  if (kind === "rect") {
    const m = rectMetrics(lm.points);
    if (!m) return "";
    return metricField(lm.id, "angle", t("context.angle"), Math.round(m.angle_deg), "1")
         + metricField(lm.id, "length", tu("context.length"),
                       toDisplayValue(m.length_mm), inputStep())
         + metricField(lm.id, "width", tu("context.width"),
                       toDisplayValue(m.width_mm), inputStep());
  }
  if (kind === "circle") {
    const m = circleMetrics(lm.points);
    if (!m) return "";
    return metricField(lm.id, "radius", tu("context.radius"),
                       toDisplayValue(m.radius_mm), inputStep());
  }
  return `<span class="meta">${esc(t("context.corners", { n: lm.points.length }))}</span>`;
}

function renderPanel() {
  const host = ensureHost();
  if (!host) return;
  const marks = state.project?.context?.landmarks || [];
  host.innerHTML = `
    <h3>${esc(t("context.title"))}</h3>
    ${marks.length ? `<ul class="context-list">${marks.map((lm) => `
      <li data-lm="${esc(lm.id)}" style="flex-wrap:wrap">
        <span class="context-kind">${esc(t(`context.kind.${lm.kind}`))}</span>
        <input class="context-label-input" data-lm="${esc(lm.id)}"
               value="${esc(lm.label)}"
               placeholder="${esc(t("context.label_placeholder"))}">
        <button class="context-remove" data-lm="${esc(lm.id)}"
                title="${esc(t("context.remove"))}">✕</button>
        <div class="context-metrics"
             style="flex-basis:100%;display:flex;flex-wrap:wrap;align-items:center;gap:6px"
             >${metricsHtml(lm)}</div>
      </li>`).join("")}</ul>`
      : `<div class="meta">${esc(t("context.empty"))}</div>`}`;
  for (const input of host.querySelectorAll(".context-label-input"))
    input.addEventListener("change", () => labelLandmark(input.dataset.lm, input.value));
  for (const input of host.querySelectorAll(".context-metric"))
    input.addEventListener("change", () => resizeLandmark(input.dataset.lm));
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
  // First on the side, with no sibling anchor. This used to insert itself after
  // `#job-panel`; the job panel now lives in `.canvas-col` ("this job" is not a
  // side thing), so anchoring to it would be positioning against a panel in
  // ANOTHER column — `insertBefore` throws NotFoundError on a node that is not a
  // child of `side`, and the whole property panel would simply never appear.
  side.insertBefore(host, side.firstChild);
  return host;
}

function metricValue(id, name) {
  const input = document.querySelector(
    `#context-panel .context-metric[data-lm="${CSS.escape(id)}"][data-metric="${name}"]`);
  return input ? input.value : "";
}

// A typed length, in mm, or null for "do not touch the shape". Blank and
// unparseable are the SAME answer here and both mean refuse: `toMm("")` is null
// and writing that into a point list gives a landmark with no coordinates, which
// renders as nothing and cannot be selected to fix. Non-positive is refused for
// the same reason a zero-area drag is — it is not a shape anybody meant to draw.
function typedMm(raw) {
  const mm = toMm(raw);
  return Number.isFinite(mm) && mm > 0 ? mm : null;
}

// `landmark-shape.js` hands back the corner list; accept a `{points}` envelope
// too, so a signature change over there cannot quietly write `undefined` into a
// saved project. Rounded here because millimetres are integers at rest
// (ADR-0002) and cos/sin are not.
function cornerList(result) {
  const pts = Array.isArray(result) ? result : result?.points;
  if (!Array.isArray(pts) || pts.length < 3) return null;
  return pts.map(([x, y]) => [Math.round(x), Math.round(y)]);
}

async function resizeLandmark(id) {
  const { saveContext } = await import("./state.js");
  const lm = landmarkById(state.project?.context?.landmarks, id);
  if (!lm) return;
  const kind = metricsKind(lm);
  let points = null;
  if (kind === "rect") {
    const m = rectMetrics(lm.points);
    const angle = Number(metricValue(id, "angle"));
    const length_mm = typedMm(metricValue(id, "length"));
    const width_mm = typedMm(metricValue(id, "width"));
    // Any angle is legal — `rectFromMetrics` normalises it, so a person who
    // types 190 or -20 gets the rectangle they described rather than a refusal.
    // Only a non-number is refused.
    if (m && Number.isFinite(angle) && length_mm && width_mm)
      // The landmark keeps its OWN centre: typing a width must widen the pool
      // where it stands, not move it.
      points = cornerList(rectFromMetrics(
        { center: m.center, angle_deg: angle, length_mm, width_mm }));
  } else if (kind === "circle") {
    const m = circleMetrics(lm.points);
    const radius_mm = typedMm(metricValue(id, "radius"));
    if (m && radius_mm)
      points = cornerList(circleFromMetrics(m.center, radius_mm, TREE_SIDES));
  }
  // Refused: leave the shape exactly as it was and re-render, which puts the
  // real number back in the field the person emptied. Silently keeping their
  // bad text would let the next edit save half of it.
  if (!points) { renderPanel(); return; }
  pushSnapshot("resize-landmark");
  lm.points = points;
  await saveContext();
}

async function labelLandmark(id, label) {
  const { saveContext } = await import("./state.js");
  const lm = (state.project?.context?.landmarks || []).find((m) => m.id === id);
  if (!lm) return;
  // BEFORE the mutation, same discipline as every topology edit: context now
  // shares the ONE undo stack (history.js) rather than a second one, so
  // renaming a landmark is as undoable as any fence edit.
  pushSnapshot("rename-landmark");
  lm.label = label.trim();
  await saveContext();
}

async function removeLandmark(id) {
  const { saveContext } = await import("./state.js");
  const ctx = state.project?.context;
  if (!ctx) return;
  pushSnapshot("delete-landmark");
  ctx.landmarks = ctx.landmarks.filter((m) => m.id !== id);
  await saveContext();
}

export function initContext() {
  render();
  renderPanel();
  // `clearDraft` too, and it is the whole of a real bug. The rubber band lives
  // in its own group so a redraw of the committed landmarks cannot wipe it —
  // which also means `render()` never wipes it. It was cleared in exactly ONE
  // place, the pointerup that commits a landmark, so a gesture that never
  // reached that path (pointer released off-window, a project switched
  // mid-drag) left a street-shaped line on the canvas that:
  //   - could not be clicked, because a draft carries `pointer-events: none`
  //   - could not be deleted, being no landmark and having no row in the list
  //   - SURVIVED opening another job, because nothing here cleared it
  // Four symptoms, one cause. A project being loaded is the clearest possible
  // signal that whatever was mid-gesture is over. The click-built house makes
  // this MORE likely, not less: a polygon draft has no release that ends it, so
  // "walked away half-way through" is now an ordinary way to leave one behind.
  const redraw = () => { clearDraft(); render(); renderPanel(); };
  on("project-loaded", redraw);
  on("context-changed", redraw);
  on("locale-changed", redraw);
  on("role-changed", redraw);
  on("fit-view", render);
  // Only the panel: the canvas draws world millimetres and does not care what
  // unit they are typed in. The fields DO hold mm rendered in the display unit,
  // so a mm↔cm flip has to re-convert them — the same reason `panel.js`
  // re-renders here, and without it a width typed in mm reads as a tenth of one.
  on("units-changed", renderPanel);
}
