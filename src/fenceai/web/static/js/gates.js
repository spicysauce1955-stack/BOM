// WHICH GATE — the gate step's own panel, and the only surface that names a
// gate product before one has been placed.
//
// Until this panel existed the salesperson's "Gates" step scoped in the gate
// tool and nothing else: the only place a gate product was ever named was inside
// the popover that opens AFTER you have clicked a spot on the fence. So the step
// that is entirely about gates showed no gate, no model, and no list of what had
// already been placed — you found out what you were buying one click too late,
// and you re-chose it in every popover.
//
// This panel answers the three questions in the order a person asks them: which
// gate, where do I click, and what have I placed so far.
//
// DOM ownership: `#gates-panel` and nothing else. index.html is not this
// module's file — the host is looked up, never created and never moved, and if
// it is absent this module renders nothing at all.

import { esc } from "./api.js";
import { loadCatalogProducts } from "./builder-ui.js";
import { landmarkAtAny } from "./context.js";
import {
  openingEdges, screenSideOf, sideProbe, slideArrow, swingLeaf,
} from "./gate-geom.js";
import {
  clearGroup, el, nodeById, runById, runPoints, stationOfAnchor, toPx,
} from "./geom.js";
import { pushSnapshot } from "./history.js";
import { currentLocale, t } from "./i18n.js";
import { on, saveTopology, state } from "./state.js";
import { money, sentence, tu } from "./units.js";

// ---------- the catalog half (moved verbatim from editor.js) ----------
// The cache lives in builder-ui.js, shared with the rule builder and the model
// editor. It used to live in editor.js AND there, with different failure
// behaviour on each side: one copy retried after a failed fetch and the other
// cached the empty catalog forever, so the same lost request left the gate
// picker working and the SKU pickers permanently blank. These two functions moved
// HERE (rather than being copied) for the same reason: editor.js imports them
// from this module, so the popover and the panel offer one list, not two.

export function gateKitProducts(products) {
  // components of assembly kits (gate leaves, hinge sets...) are parts, not
  // sellable gates — exclude them even when their sku matches /GATE/i
  const kitComponents = new Set(
    Object.values(products).flatMap((p) =>
      p.consumption?.kind === "assembly_kit"
        ? (p.consumption.components || []).map((c) => c.sku) : []
    )
  );
  return Object.values(products).filter((p) => {
    if (kitComponents.has(p.sku)) return false;
    // declaring an opening width IS declaring yourself a gate product
    if (declaredOpening(p) !== null) return true;
    if ((p.attrs || {}).category === "gate") return true;
    if (/GATE/i.test(p.sku)) return true;
    if (p.consumption?.kind === "assembly_kit") {
      const names = [p.name || "", ...Object.values(p.name_i18n || {})];
      return names.some((n) => /gate/i.test(n));
    }
    return false;
  });
}

// The opening a product DECLARES it fits — catalog DATA, exactly like posts'
// attrs.length_mm and exactly what the generator reads (KIT_OPENING_ATTR in
// strategy/generator.py). A sku is an opaque id: "GATE-KIT-1000" is one
// catalog's naming accident and "BAR-GATE-1168" carries a leaf size, so parsing
// digits out of either invents a width for somebody else's catalog. A product
// that declares nothing is never second-guessed here, as in the generator.
export const KIT_OPENING_ATTR = "opening_width_mm";
export function declaredOpening(p) {
  const v = p && (p.capabilities || {})[KIT_OPENING_ATTR];
  return Number.isFinite(v) ? v : null;
}

// ---------- the chosen kit ----------
//
// MODULE state, deliberately not persisted. "Which gate am I placing right now"
// is a working choice for this sitting, not a fact about the job: the facts are
// the gates actually on the fence, each carrying its own `kit_sku`. Storing the
// pending choice on the project would invent a field the backend has no place
// for — and it would then need a revision, a 409 story and a migration, all for
// a value that means nothing once the browser tab is closed.
let chosenSku = null;

/** The sku the user picked in this panel, or `null` when the catalog offered
 *  none. `editor.js` reads it to seed the gate popover, so a salesperson picks
 *  the gate ONCE here and then just clicks where the gates go. */
export function chosenGateKit() {
  return chosenSku;
}

// ---------- the pure half ----------

/** Every gate placed on this job: `[{run_id, event_id, station_mm, width_mm,
 *  kit_sku}]`, in drawing order of the runs and by station within each run.
 *
 *  Pure over its argument — no DOM, no `state` — so it can be checked in node
 *  the way `base-top.js` is.
 *
 *  A gate is a POINT EVENT (`payload.kind === "gate"`), and its position is its
 *  ANCHOR, which is segment-local: `anchor.offset_mm` is an offset within one
 *  segment and is NOT a station (reading it as one is the mistake CLAUDE.md
 *  names explicitly). `stationOfAnchor` is the mirror of the backend's
 *  `anchor_station`, and it resolves the run's geometry through `geom.nodeById`,
 *  which reads the global project — hence the `stationOf` seam: it is the one
 *  reference to anything outside `project`, and a node test can pass its own
 *  resolver instead of standing up a global. */
export function placedGates(project, stationOf = stationOfAnchor) {
  const out = [];
  // The gate that is its OWN element, standing beside the runs. It has no
  // stored width: the opening is the distance between its two nodes, exactly
  // as a run's length is the distance between its own — one fact, one place,
  // so nothing can disagree with the drawing after a node is dragged
  // (`topology/station.py: gate_opening_mm` makes the same measurement).
  for (const g of project?.topology?.gates || []) {
    const a = nodeById(g.start_node_id), b = nodeById(g.end_node_id);
    if (!a || !b) continue;                       // a node deleted under it
    out.push({
      kind: "span", id: g.id, run_id: null, event_id: null,
      start_node_id: g.start_node_id, end_node_id: g.end_node_id,
      points: [[a.x_mm, a.y_mm], [b.x_mm, b.y_mm]],
      station_mm: 0,
      width_mm: Math.round(Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm)),
      kit_sku: g.kit_sku ?? null,
      leaf: g.leaf ?? "single",
      opens_to: g.opens_to ?? null,
      hinge: g.hinge ?? null,
      slides_to: g.slides_to ?? null,
    });
  }
  for (const run of project?.topology?.runs || []) {
    const mine = [];
    for (const ev of run.point_events || []) {
      if (ev?.payload?.kind !== "gate") continue;
      mine.push({
        // the OTHER kind: an opening punched inside a run. Still supported,
        // still on stored projects, and still what the golden scenarios build.
        kind: "event",
        id: ev.id,
        run_id: run.id,
        event_id: ev.id,
        points: null,
        station_mm: stationOf(run, ev.anchor),
        width_mm: Number.isFinite(ev.payload.width_mm) ? ev.payload.width_mm : null,
        kit_sku: ev.payload.kit_sku ?? null,
        // How it opens, carried verbatim. `null` is NOBODY HAS SAID and is a
        // different thing from any direction — the drawing marks it, and this
        // panel says it, rather than picking a side and drawing it confidently.
        leaf: ev.payload.leaf ?? "single",
        opens_to: ev.payload.opens_to ?? null,
        hinge: ev.payload.hinge ?? null,
        slides_to: ev.payload.slides_to ?? null,
      });
    }
    // sorted WITHIN the run and appended in topology order: "by run" means the
    // order the fence was drawn, which is the order it reads on the canvas, not
    // an alphabetical one that puts run10 before run2
    mine.sort((a, b) => a.station_mm - b.station_mm);
    out.push(...mine);
  }
  return out;
}

// ---------- the stateful half ----------

// Renders are async (they await the catalog), and five events can start one.
// A token drops every render but the newest, so a locale flip mid-fetch cannot
// be overwritten by the answer to the fetch that preceded it.
let renderSeq = 0;

export function initGates() {
  render();
  renderGates();
  wireDrawing();
  for (const ev of ["project-loaded", "topology-changed", "context-changed",
                    "locale-changed", "units-changed", "fit-view"])
    on(ev, renderGates);
  on("project-loaded", render);
  on("topology-changed", render);
  on("locale-changed", render);
  // stations and opening widths are millimetres shown in the DISPLAY unit — a
  // mm<->cm flip has to re-convert them, it is not a no-op here
  on("units-changed", render);
  // and the words change with the ROLE: `t()` resolves `sales.<key>` before
  // `<key>`, so every label this panel renders is stale the instant the role
  // changes (`job.js` documents the same subscription, for the same reason)
  on("role-changed", render);
}

async function render() {
  if (typeof document === "undefined") return;
  const host = document.getElementById("gates-panel");
  // index.html owns the host. No host, no panel — this module never creates one.
  if (!host) return;
  const seq = ++renderSeq;
  const kits = gateKitProducts(await loadCatalogProducts());
  if (seq !== renderSeq) return;   // a newer render started while we fetched
  // Keep the standing choice if it is still on offer; otherwise fall back to the
  // first product in CATALOG order — no sku is special, and the popover picks
  // its default the same way.
  if (!kits.some((p) => p.sku === chosenSku)) chosenSku = kits[0]?.sku ?? null;
  host.innerHTML = `<h3>${esc(t("gates.title"))}</h3>
    ${whichHtml(kits)}
    <div class="meta">${esc(t("gates.hint"))}</div>
    <h4>${esc(t("gates.placed"))}</h4>
    ${placedHtml()}`;
  wire(host);
}

function whichHtml(kits) {
  // No catalog reached us (or it holds no gate product): say so, and invent no
  // sku on the user's behalf — `chosenGateKit()` is null and the popover falls
  // back to a typed width, exactly as it does today.
  if (!kits.length) return `<div class="meta">${esc(t("gates.no_catalog"))}</div>`;
  const options = kits.map((p) => {
    const name = p.name_i18n?.[currentLocale()] || p.name || p.sku;
    // options cannot hold nested markup, so a `.num` span is not available: an
    // LRM (U+200E) before the figure is how the price stays readable inside an
    // RTL option, and `dir="auto"` lets the NAME pick its own direction. The
    // gate popover in editor.js does exactly this; the trick and the reason are
    // the same one.
    const price = Number.isFinite(p.price_cents)
      ? ` — ‎${esc(money(p.price_cents))}` : "";
    return `<option value="${esc(p.sku)}" dir="auto"${
      p.sku === chosenSku ? " selected" : ""}>${esc(name)}${price}</option>`;
  }).join("");
  return `<label class="builder-field">
    <span class="meta">${esc(t("gates.which"))}</span>
    <select id="gate-kit-select">${options}</select></label>`;
}

function placedHtml() {
  const gates = placedGates(state.project);
  if (!gates.length) return `<div class="meta">${esc(t("gates.none"))}</div>`;
  return gates.map((g) => {
    // A span stands between two POSTS and belongs to no stretch, so naming a
    // run and a station for it would be inventing a place it does not have.
    const bits = g.kind === "span"
      ? [`<bdi>${esc(g.start_node_id)}</bdi>–<bdi>${esc(g.end_node_id)}</bdi>`]
      : [`<bdi>${esc(g.run_id)}</bdi>`,
         sentence("gates.at", { station_mm: g.station_mm })];
    // `sentence` is `tu` for innerHTML: same `{u}` conversion, with the template
    // escaped and each figure dropped in bidi-isolated, so a station inside a
    // Hebrew phrase does not reorder against its punctuation.
    if (g.width_mm !== null)
      bits.push(sentence("gates.row_width", { width_mm: g.width_mm }));
    // A row with no kit shows the width ALONE. A gate placed against an empty
    // catalog stated an opening and no product, and an empty sku chip would read
    // as a missing part rather than as a choice nobody made.
    if (g.kit_sku) bits.push(`<bdi class="sku">${esc(g.kit_sku)}</bdi>`);
    // ...and the answer to the question a placement alone cannot give. A gate
    // nobody has stated a direction for says so, rather than reading as one
    // that opens some default way.
    const swing = swingPhraseFor(g);
    const type = `<select class="gate-type-select" data-gate="${esc(g.id)}"
        data-kind="${esc(g.kind)}" data-run="${esc(g.run_id || "")}">`
      + ["single", "double", "sliding"].map((k) =>
        `<option value="${k}"${k === g.leaf ? " selected" : ""}>${
          esc(t(`gate.type.${k}`))}</option>`).join("")
      + `</select>`;
    return `<div class="event-row"><span>${bits.join(" · ")} ${type}${
      swing ? `<br><span class="meta">${esc(swing)}</span>` : ""}</span>
      <button class="event-delete" title="${esc(t("gates.remove"))}"
        data-gate="${esc(g.id)}" data-kind="${esc(g.kind)}"
        data-run="${esc(g.run_id || "")}">✕</button></div>`;
  }).join("");
}

function wire(host) {
  host.querySelector("#gate-kit-select")?.addEventListener("change", (ev) => {
    chosenSku = ev.target.value || null;
  });
  for (const btn of host.querySelectorAll("button.event-delete"))
    btn.addEventListener("click", () =>
      removeGate(btn.dataset.kind, btn.dataset.gate, btn.dataset.run));
  for (const sel of host.querySelectorAll("select.gate-type-select"))
    sel.addEventListener("change", () =>
      setLeaf(sel.dataset.kind, sel.dataset.gate, sel.dataset.run, sel.value));
}

/** Delete one placed gate — a topology mutation, so: snapshot, mutate, save.
 *
 *  BY ID, never by index: this list is sorted for display, and an index into
 *  the sorted view is not an index into the array behind it. The existence
 *  check comes first so a stale render pushes no undo step for a no-op.
 *
 *  A SPAN leaves its two nodes behind on purpose. One of them is usually a
 *  run's own end node, and deleting it would take a stretch of fence with it;
 *  a stranded node draws nothing and costs nothing. */
async function removeGate(kind, gateId, runId) {
  const topo = state.project?.topology;
  if (!topo) return;
  if (kind === "span") {
    if (!(topo.gates || []).some((g) => g.id === gateId)) return;
    pushSnapshot("delete-gate");
    topo.gates = topo.gates.filter((g) => g.id !== gateId);
  } else {
    const run = (topo.runs || []).find((r) => r.id === runId);
    if (!run || !(run.point_events || []).some((e) => e.id === gateId)) return;
    pushSnapshot("delete-gate");
    run.point_events = run.point_events.filter((e) => e.id !== gateId);
  }
  await saveTopology();
}

/** A gate id nothing on this project already uses. Sequence-based rather than
 *  time-based, exactly like `nextLandmarkId`: two gates placed in the same
 *  millisecond must not share one, and the backend refuses a duplicate — and
 *  refuses a gate id that collides with a RUN id too, since both are element
 *  ids downstream. */
export function nextGateId(topo) {
  const used = new Set([...(topo?.gates || []).map((g) => g.id),
                        ...(topo?.runs || []).map((r) => r.id)]);
  for (let i = 1; ; i++) if (!used.has(`gate${i}`)) return `gate${i}`;
}

// ---------- how it opens, in words and on the drawing ------------------------
//
// The stored fact is `left`/`right` of the RUN's own direction, which is
// geometric truth and cannot go stale. The SENTENCE — "opens toward the house"
// — is rendered here from the landmarks actually on that side, because that is
// the only place that knows what is on the property. Storing the sentence
// instead would be storing a rendering: move the house, and the gate would go
// on claiming to open toward it.
//
// `docs/integration-contract/contract.md` obligation 18 is why this lives on
// our side at all: `PanelSpec` models no gate — "no handedness, no swing
// direction" — so nothing across the boundary can tell us, and nothing across
// it needs to be told.

// How far off the fence to look for what a gate opens toward. Three distances
// rather than one: a house set well back is not within a metre of the fence,
// and a pool coping might be. The first thing found wins, so the nearest thing
// on that side is the thing named.
const PROBE_MM = [1200, 3000, 6000];

/** Which way a vector points ON THE DRAWING. The world is y-up and the canvas
 *  draws y down, so a positive `y` is toward the TOP of the drawing. The plan
 *  canvas is never mirrored in RTL (CLAUDE.md), which is what makes this an
 *  honest description in either language rather than a direction that flips. */
function screenWord([vx, vy]) {
  if (Math.abs(vy) >= Math.abs(vx)) return vy >= 0 ? "up" : "down";
  return vx >= 0 ? "right" : "left";
}

/** The landmark on `side` of this opening, or null. */
function landmarkBeside(points, station, width, side) {
  for (const dist of PROBE_MM) {
    const probe = sideProbe(points, station, width, side, dist);
    if (!probe) return null;
    const lm = landmarkAtAny(state.project?.context?.landmarks, probe);
    if (lm) return lm;
  }
  return null;
}

function landmarkWord(lm) {
  return lm.label || t(`context.kind.${lm.kind}`);
}

/** The phrase for one side of an opening: "toward the house", or — when there
 *  is nothing on that side to name — "toward the top of the drawing". */
function sidePhrase(points, station, width, side) {
  const lm = landmarkBeside(points, station, width, side);
  if (lm) return t("gate.side.toward", { what: landmarkWord(lm) });
  const edges = openingEdges(points, station, width);
  if (!edges) return "";
  const dir = [edges.b[0] - edges.a[0], edges.b[1] - edges.a[1]];
  const screen = screenSideOf(dir, side);
  return screen ? t(`gate.side.${screen}`) : "";
}

/** The phrase for the way a sliding gate retracts, along the fence. */
function slidePhrase(points, station, width, slidesTo) {
  const edges = openingEdges(points, station, width);
  if (!edges) return "";
  const along = [edges.b[0] - edges.a[0], edges.b[1] - edges.a[1]];
  const motion = slidesTo === "start" ? [-along[0], -along[1]] : along;
  return t(`gate.side.${screenWord(motion)}`);
}

/** "opens toward the house" / "slides toward the top of the drawing" / "which
 *  way it opens has not been said".
 *
 *  Takes a row in `placedGates` shape rather than an event, so the structure
 *  sheet — whose `GateRow` carries the same four facts and a start station and
 *  an opening — can render the same sentence through the same function. Two
 *  surfaces answering "which way does it open" differently is the defect this
 *  avoids by construction. */
/** The two-point line a gate lies on.
 *
 *  A gate SPAN is already two points; an in-run gate borrows its run's
 *  polyline. Everything downstream — `gate-geom.js`, the swing, the label — is
 *  written against a point list and a station, so the two kinds share one
 *  renderer rather than growing a second one. */
function lineOf(gate) {
  if (gate.points) return gate.points;
  // A caller with no geometry at all — the setting-out sheet, which reads a
  // GateRow and not the drawing. It can still say the TYPE and the opening; the
  // side, which is a fact about the property this gate stands on, needs the
  // drawing and honestly says nothing rather than guessing.
  if (!gate.run_id) return null;
  const run = runById(gate.run_id);
  return run ? runPoints(run) : null;
}

export function swingPhraseFor(gate) {
  const points = lineOf(gate);
  if (!points || !Number.isFinite(gate.width_mm)) return "";
  if (gate.leaf === "sliding") {
    if (!gate.slides_to) return t("gate.opens_unstated");
    const side = slidePhrase(points, gate.station_mm, gate.width_mm, gate.slides_to);
    return side ? t("gate.slides_phrase", { side }) : "";
  }
  if (!gate.opens_to) return t("gate.opens_unstated");
  const side = sidePhrase(points, gate.station_mm, gate.width_mm, gate.opens_to);
  return side ? t("gate.opens_phrase", { side }) : "";
}

/** The two answers to "which way?", named, for a picker to offer.
 *
 *  `[{value, label}, {value, label}]` — `left`/`right` for a gate that swings,
 *  `start`/`end` for one that slides. Named rather than valued: the user's
 *  instruction was to state the direction by pointing at a side, and "left of
 *  the run as it happens to have been drawn" is not something a salesperson
 *  should ever have to work out. Empty when the run or the width is not known
 *  yet, so a caller renders no choice rather than two identical ones. */
export function sideOptions(runId, stationMm, widthMm, leaf) {
  const run = runById(runId);
  if (!run || !Number.isFinite(widthMm) || widthMm <= 0) return [];
  const points = runPoints(run);
  if (leaf === "sliding")
    return ["start", "end"].map((value) => ({
      value, label: slidePhrase(points, stationMm, widthMm, value) }));
  return ["left", "right"].map((value) => ({
    value, label: sidePhrase(points, stationMm, widthMm, value) }));
}

// ---------- the gate, drawn ---------------------------------------------------
//
// Drawn from the topology EVENT, not from a generated strategy, and that is the
// whole point: "the placement is not sufficient for an opening fence". A gate
// used to be invisible until Generate and then appeared as a plain segment with
// no width and no swing, so the one drawing a salesperson shows a customer could
// not answer the first question anybody asks about a gate.
//
// This module owns `#g-gates` exactly as it owns `#gates-panel`. The group is
// declared in index.html and only looked up here.

const GATE_COLOR = "#0891b2";
const LABEL_OFFSET_PX = 14;

/** Every gate on the plan: the opening at its true width, and the way it opens. */
export function renderGates() {
  const g = clearGroup("g-gates");
  if (!g) return;
  for (const gate of placedGates(state.project)) drawGate(g, gate);
}

function drawGate(g, gate) {
  const points = lineOf(gate);
  if (!points || !Number.isFinite(gate.width_mm) || gate.width_mm <= 0) return;
  const edges = openingEdges(points, gate.station_mm, gate.width_mm);
  if (!edges) return;
  const [ax, ay] = toPx(edges.a), [bx, by] = toPx(edges.b);
  // Identity, not position: the controls below mutate a gate by its id and its
  // kind, so a redraw between the click and the mutation cannot move which gate
  // is being flipped.
  const data = { "data-gate": gate.id, "data-kind": gate.kind,
                 "data-run": gate.run_id || "" };

  // the opening itself — the hole in the fence, at the width that was sold
  el("line", { x1: ax, y1: ay, x2: bx, y2: by, stroke: GATE_COLOR,
    "stroke-width": 6, "stroke-linecap": "butt", class: "gate-opening",
    "pointer-events": "none" }, g);
  // ...and its width in words, offset off the line so it never sits on the
  // fence it is measuring
  const mid = [(ax + bx) / 2, (ay + by) / 2];
  const len = Math.hypot(bx - ax, by - ay) || 1;
  const nx = -(by - ay) / len, ny = (bx - ax) / len;
  el("text", { x: mid[0] + nx * LABEL_OFFSET_PX, y: mid[1] + ny * LABEL_OFFSET_PX,
    "font-size": 10, fill: GATE_COLOR, "text-anchor": "middle",
    class: "num", "pointer-events": "none" }, g)
    .textContent = tu("canvas.mm", { n_mm: gate.width_mm });

  if (gate.leaf === "sliding") { drawSlide(g, points, gate, mid, data); return; }
  if (!gate.opens_to) { drawUnstated(g, mid, data); return; }
  if (gate.leaf === "double") {
    // two leaves, each half the opening, hinged on opposite edges — so each is
    // drawn as its own half-opening rather than as a full-width leaf that would
    // sweep twice the space the gate actually needs
    const half = Math.round(gate.width_mm / 2);
    drawLeaf(g, points, gate.station_mm, half, "start", gate.opens_to, gate, data);
    drawLeaf(g, points, gate.station_mm + half, gate.width_mm - half, "end",
             gate.opens_to, gate, data);
    return;
  }
  drawLeaf(g, points, gate.station_mm, gate.width_mm,
           gate.hinge || "start", gate.opens_to, gate, data);
}

/** One leaf: the panel where it stands open, and the arc showing it get there.
 *  The arc is the architectural convention, and it is what makes "which way
 *  does it open" answerable at a glance rather than by reading a table. */
function drawLeaf(g, points, station, width, hinge, side, gate, data) {
  const leaf = swingLeaf(points, station, width, hinge, side);
  if (!leaf) return;
  const pivot = toPx(leaf.pivot), tip = toPx(leaf.tip);
  const arc = leaf.arc.map(toPx);
  const d = arc.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ");
  el("path", { d, fill: "none", stroke: GATE_COLOR, "stroke-width": 1,
    "stroke-dasharray": "3 3", "pointer-events": "none" }, g);
  el("line", { x1: pivot[0], y1: pivot[1], x2: tip[0], y2: tip[1],
    stroke: GATE_COLOR, "stroke-width": 2, "pointer-events": "none" }, g);
  // A 1 px dashed arc is a target nobody can hit with a mouse. The visible
  // marks carry no pointer events at all and this transparent one carries them
  // all, which is the same split `.run-hit` makes over the fence line.
  hitPath(g, `${d} M${pivot[0]} ${pivot[1]} L${tip[0]} ${tip[1]}`,
          t("gate.flip"), data);
  // the hinge, as a dot on the post it hangs from. Its own control, because
  // which post carries the hinge is the other half of the question and the
  // crew reads it off this drawing.
  el("circle", { cx: pivot[0], cy: pivot[1], r: 5, fill: GATE_COLOR,
    class: "gate-hinge", cursor: "pointer", ...data }, g)
    .append(titleEl(t("gate.swap_hinge")));
}

function drawSlide(g, points, gate, midPx, data) {
  if (!gate.slides_to) { drawUnstated(g, midPx, data); return; }
  const arrow = slideArrow(points, gate.station_mm, gate.width_mm, gate.slides_to);
  if (!arrow) return;
  const from = toPx(arrow.from), to = toPx(arrow.to);
  el("line", { x1: from[0], y1: from[1], x2: to[0], y2: to[1],
    stroke: GATE_COLOR, "stroke-width": 2, "stroke-dasharray": "6 3",
    "pointer-events": "none" }, g);
  // the head, drawn from the line's own direction so it points where the leaf
  // goes rather than at a fixed angle
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  el("polyline", { points: [
    [to[0] - ux * 9 - uy * 5, to[1] - uy * 9 + ux * 5],
    [to[0], to[1]],
    [to[0] - ux * 9 + uy * 5, to[1] - uy * 9 - ux * 5]].map((p) => p.join(",")).join(" "),
    fill: "none", stroke: GATE_COLOR, "stroke-width": 2,
    "pointer-events": "none" }, g);
  hitPath(g, `M${from[0]} ${from[1]} L${to[0]} ${to[1]}`, t("gate.flip"), data);
}

/** The invisible wide stroke that actually receives the click. */
function hitPath(g, d, title, data) {
  const node = el("path", { d, fill: "none", stroke: "transparent",
    "stroke-width": 14, class: "gate-arc", cursor: "pointer", ...data }, g);
  node.append(titleEl(title));
  return node;
}

/** Nobody has said which way it opens. Marked rather than guessed: a swing
 *  drawn from a default is a confident wrong drawing, and this is the one
 *  question a gate on a plan exists to answer. */
function drawUnstated(g, midPx, data) {
  el("circle", { cx: midPx[0], cy: midPx[1], r: 8, fill: "#fff",
    stroke: GATE_COLOR, "stroke-width": 1.5, class: "gate-arc",
    cursor: "pointer", ...data }, g).append(titleEl(t("gate.opens_unstated")));
  el("text", { x: midPx[0], y: midPx[1] + 3.5, "font-size": 10, fill: GATE_COLOR,
    "text-anchor": "middle", "pointer-events": "none" }, g).textContent = "?";
}

function titleEl(text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "title");
  node.textContent = text;
  return node;
}

/** State a side, or turn it round. A click, not a drag: the answer is one of
 *  two and a 90 degree drag to choose between them is a gesture that can miss.
 *  From "not said" the first click STATES a side rather than cycling back
 *  through silence — a person clicking the marker is answering the question. */
/** The mutable record behind a gate, whichever kind it is.
 *
 *  A `GateSpan` on `topology.gates` and a gate PAYLOAD on a run's point event
 *  carry the same four swing facts under the same names, so once the record is
 *  in hand every edit below is identical — which is why there is one flip and
 *  one hinge swap rather than two of each. */
function gateRecord(kind, gateId, runId) {
  const topo = state.project?.topology;
  if (kind === "span") return (topo?.gates || []).find((g) => g.id === gateId) || null;
  const run = (topo?.runs || []).find((r) => r.id === runId);
  const ev = (run?.point_events || []).find((e) => e.id === gateId);
  return ev && ev.payload.kind === "gate" ? ev.payload : null;
}

async function flipSwing(kind, gateId, runId) {
  const rec = gateRecord(kind, gateId, runId);
  if (!rec) return;
  pushSnapshot("gate-swing");
  if ((rec.leaf ?? "single") === "sliding")
    rec.slides_to = rec.slides_to === "start" ? "end" : "start";
  else {
    rec.opens_to = rec.opens_to === "left" ? "right" : "left";
    // a leaf has to hang from something once it has a side to swing to; which
    // post is then one more click, on the hinge dot the drawing now shows
    if ((rec.leaf ?? "single") === "single" && !rec.hinge) rec.hinge = "start";
  }
  await saveTopology();
}

async function swapHinge(kind, gateId, runId) {
  const rec = gateRecord(kind, gateId, runId);
  if (!rec || (rec.leaf ?? "single") !== "single") return;  // nothing to swap
  pushSnapshot("gate-hinge");
  rec.hinge = rec.hinge === "end" ? "start" : "end";
  await saveTopology();
}

/** Which kind of gate it is, changed in place. A sliding gate states no swing
 *  and a double hangs from no single edge, so the facts that stop applying are
 *  cleared here — the backend REFUSES the contradiction, and sending one would
 *  turn a dropdown into a 422. */
async function setLeaf(kind, gateId, runId, leaf) {
  const rec = gateRecord(kind, gateId, runId);
  if (!rec || rec.leaf === leaf) return;
  pushSnapshot("gate-type");
  rec.leaf = leaf;
  if (leaf === "sliding") { rec.opens_to = null; rec.hinge = null; }
  else {
    rec.slides_to = null;
    if (leaf === "double") rec.hinge = null;
    else if (rec.opens_to && !rec.hinge) rec.hinge = "start";
  }
  await saveTopology();
}

/** One delegated listener on the group this module owns, rather than one per
 *  element on every redraw. `stopPropagation` because `editor.js` owns the
 *  canvas's own click — without it, flipping a swing with the gate tool armed
 *  would also open the place-a-gate popover underneath. */
function wireDrawing() {
  const g = document.getElementById("g-gates");
  if (!g || g.dataset.wired) return;
  g.dataset.wired = "1";
  g.addEventListener("click", (ev) => {
    const hinge = ev.target.closest(".gate-hinge");
    const arc = ev.target.closest(".gate-arc");
    const hit = hinge || arc;
    if (!hit) return;
    ev.stopPropagation();
    if (hinge) swapHinge(hinge.dataset.kind, hinge.dataset.gate, hinge.dataset.run);
    else flipSwing(arc.dataset.kind, arc.dataset.gate, arc.dataset.run);
  });
}
