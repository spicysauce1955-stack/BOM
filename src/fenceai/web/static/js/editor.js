// Plan-canvas editor: rendering + tools. Select (handles/ghosts/drag/delete),
// Draw (snapped dots, rubber band, typed lengths) — plan Tasks 6-8.
// The canvas is never mirrored in RTL (spec §4).

import { apiSend, esc } from "./api.js";
import { loadCatalogProducts } from "./builder-ui.js";
import { isSelectable, loadModelListing, modelOptionLabel } from "./fence-models.js";
import {
  anchorFor, clearGroup, el, endpointNodeAt, GROUND_TOL_MM, groundSamplesFor,
  groundZAt, nearestNode, nodeById, pointAtStation, RUN_HIT_MM, runAtPoint,
  runById, runLength, runPoints, snapPoint, stationAtPoint, stationOfAnchor,
  toMmRaw, toPx,
} from "./geom.js";
import { pushSnapshot, redo, undo } from "./history.js";
import { currentLocale, t } from "./i18n.js";
import { inspect } from "./inspector.js";
import {
  clearDraft as clearContextDraft, landmarkAt, landmarkAtAny, landmarkById,
  nextLandmarkId, render as renderContext, renderDraft as renderContextDraft,
  renderDraftPolygon as renderContextDraftPolygon,
} from "./context.js";
import { chosenGateKit, nextGateId } from "./gates.js";
import {
  gestureFor, LANDMARK_KINDS, MIN_MM, polygonFromClicks, shapeFor,
} from "./landmark-shape.js";
import { openNotePopover, targetLabel } from "./notes.js";
import { layoutWithPin, snapCandidates, violations } from "./post-drag.js";
import {
  addIntervalEvent, addLandmark, addPointEvent, generateStrategy, maxSpanFor, on,
  reloadProject, saveContext, saveTopology, setSelection, setTool, state,
} from "./state.js";
import { tagOf } from "./structure-data.js";
import {
  currentUnit, enumWord, fmt, fmtLen, inputStep, money, parseTypedLength,
  toDisplayValue, toMm, tu,
} from "./units.js";
import { gapsPanelHtml } from "./gaps.js";
import { localizedByCode, warningRowHtml } from "./warnings.js";

// `gate` is deliberately NOT here any more. An event tool writes onto a RUN,
// and a gate is no longer something that happens to a run: it is its own
// element standing beside one (`topology/model.py: GateSpan`). The in-run gate
// remains valid data — stored projects have them and the golden scenarios build
// them — but nothing in this UI authors one, because it models something a
// salesperson does not do.
const EVENT_TOOLS = ["base", "ground", "height", "pin", "model"];

// How near a press has to land to mean "this node". A gate is placed AT THE END
// of a fence, so the whole gesture is about hitting the post that is there;
// generous on purpose, and the same order as the drawing snap.
const GATE_SNAP_MM = 700;

const BASE_COLORS = { soil: "#a16207", concrete: "#64748b", masonry_wall: "#dc2626" };
const POST_COLORS = { line: "#2563eb", end: "#1e293b", corner: "#1e293b",
  junction: "#1e293b", gate: "#0891b2", transition: "#dc2626" };

export function initEditor() {
  setupCanvas();
  setupToolbar();
  renderGrid();
  loadCatalogProducts(); // warm the cache so the gate popover opens instantly
  on("project-loaded", () => { renderAllCanvas(); renderHandles(); });
  on("result-changed", () => {
    renderOverlay(); renderWarnings(); renderGaps(); renderStrategySummary();
  });
  on("tool-changed", () => {
    updateToolButtons(); renderHandles(); updateStatus(); closePopover();
    clearLengthBuffer();
  });
  on("selection-changed", () => { renderTopology(); renderHandles(); });
  on("locale-changed", () => { renderAllCanvas(); renderHandles(); updateStatus(); });
  on("units-changed", () => {
    closePopover();          // its fields hold values in the OLD unit
    renderAllCanvas(); renderHandles(); updateStatus(); updateLengthChip();
  });
  on("structure-loaded", renderOverlay);   // the tags the schedule gave us
  on("fit-view", fitView);                 // the print sheet asks before it prints
  updateStatus();
}

function renderAllCanvas() {
  renderTopology();
  renderOverlay();
  renderWarnings();
  renderGaps();
  renderStrategySummary();
}

// ---------- toolbar ----------
const TOOLS = ["select", "draw", "gate", "base", "ground", "height", "pin", "model",
               "note", ...LANDMARK_KINDS];
// The property layer. Its own list because these do not place an EVENT on a run
// — they describe what is around the fence, and nothing they draw reaches
// generation (see `project/model.py` SiteContext).
//
// DERIVED from the registry, never hand-written: a hand-written copy is a second
// registry, and the day somebody adds a kind and forgets this line the new tool
// draws nothing and the canvas silently pans instead.
const CONTEXT_TOOLS = LANDMARK_KINDS;
// ...and within it, the kinds built CLICK BY CLICK rather than by one drag. A
// house is a closed shape of straight lines — an L-shaped building approximated
// by a box is something the office person then has to ring up and ask about —
// so it gets the draw tool's gesture, not the rubber band's.
const POLYGON_TOOLS = LANDMARK_KINDS.filter((k) => gestureFor(k) === "polygon");
// How near the first corner a click has to land to mean "close the shape".
// Twice the minimum gesture: `polygonFromClicks` discards a final point that
// close to the first anyway, so a looser target here only makes the same
// gesture easier to hit.
const POLY_CLOSE_MM = MIN_MM * 2;

// The click-built landmark in progress: `{kind, points}` or null. It is NOT
// `state.draftNodes` — that is the fence draft, and one buffer for both would
// mean Escape, Enter and the Finish button could not tell a half-drawn house
// from a half-drawn fence.
let polyDraft = null;

function setupToolbar() {
  for (const tool of TOOLS) {
    const btn = document.getElementById(`tool-${tool}`);
    // BUTTONS only, and the exclusion is a real bug rather than tidiness.
    // `#tool-other` is a SELECT whose id matches the `other` KIND, so this loop
    // gave it a click listener arming `other`. A native select fires `change`
    // when an option is chosen and `click` when the dropdown closes — in that
    // order — so every tree, pool and sidewalk was armed by `change` and then
    // immediately overwritten by `click`, and the whole picker recorded nothing
    // but "Other".
    if (btn && btn.tagName === "BUTTON")
      btn.addEventListener("click", () => { setTool(tool); updateStatus(); });
  }
  // "Other…" — one control for every property object that is not the house or
  // the street. A tree, a pool, a sidewalk and a boundary each deserve to be
  // drawable and none of them deserves a permanent button: seven equal buttons
  // on the rail is the opposite of the simple, intuitive screen this is for.
  // A `<select>` rather than a popup menu because it is twenty lines less code,
  // it is keyboard- and touch-native, and index.html can localize its options
  // through the same `data-i18n` pass as everything else.
  const other = document.getElementById("tool-other");
  if (other) other.addEventListener("change", () => {
    if (other.value) { setTool(other.value); updateStatus(); }
  });
  // `apiSend` has already shown the user a localized sentence and logged the
  // server's body by the time it rethrows; passing the async function straight
  // to addEventListener made every refused generation ALSO an unhandled
  // rejection (which the smoke suite's page-error check counts).
  document.getElementById("btn-generate").addEventListener("click", () => {
    generateStrategy().catch(() => {});
  });
  document.getElementById("btn-fit").addEventListener("click", fitView);
  document.getElementById("chk-overlay").addEventListener("change", renderOverlay);
  document.getElementById("btn-clear").addEventListener("click", clearDrawing);
  updateToolButtons();
}

function updateToolButtons() {
  for (const tool of TOOLS) {
    const btn = document.getElementById(`tool-${tool}`);
    if (btn) btn.classList.toggle("active", state.tool === tool);
  }
  // The "other" picker is a tool button that happens to be a select: it lights
  // up while one of its kinds is active, and falls back to its own label the
  // moment another tool is chosen — a select left reading "Pool" while the
  // draw tool is armed is a control lying about what the next click will do.
  const other = document.getElementById("tool-other");
  if (other) {
    const mine = [...other.options].some((o) => o.value && o.value === state.tool);
    other.classList.toggle("active", mine);
    if (!mine) other.value = "";
  }
  // cursors are affordances: only the select tool opens the length editor, so
  // only it may promise a text caret over a run label (style.css)
  const svg = document.getElementById("canvas");
  if (svg) svg.dataset.tool = state.tool;
}

function updateStatus(cursor) {
  const bar = document.getElementById("statusbar");
  if (!bar) return;
  // the draw hint documents the typed-length rules, which differ per unit
  const hintKey = state.tool === "draw" && currentUnit() === "cm"
    ? "hint.draw_cm" : `hint.${state.tool}`;
  let text = tu(hintKey, { ex_mm: 4200 });
  if (cursor) text += ` · ${tu("hint.cursor", cursor)}`;
  bar.textContent = text;
}

async function clearDrawing() {
  if (!confirm(t("confirm.clear_drawing"))) return;
  // ONE snapshot for both halves: to the person pressing this, the fence and
  // the house are one picture, so undoing it must bring back one picture and
  // not the fence alone. Context rides the same history stack for exactly
  // this reason (`history.js`).
  pushSnapshot("clear");
  state.draftNodes = [];
  clearGroup("g-draft");
  clearGroup("g-snap");
  clearContextDraft();
  setSelection({});
  state.project.topology = {
    revision: state.project.topology.revision, nodes: [], runs: [],
  };
  // The landmarks too. They are not `Topology` and must never be — a landmark
  // changes no quantity, and in the topology it would bump the revision and
  // 409 the structure sheet because somebody nudged a driveway. But that is a
  // fact about the DATA MODEL, and this button is a promise to a salesperson:
  // the label reads "Clear", the house and the street are things they drew,
  // and leaving them behind read as the button being broken. The model keeps
  // its separation; the button keeps its word.
  const hadLandmarks = (state.project.context?.landmarks || []).length > 0;
  if (hadLandmarks) state.project.context.landmarks = [];
  await saveTopology();
  // `saveTopology()` just replaced the whole `state.project` with the
  // server's response, which still carries the PRE-clear landmarks (that
  // route never touches context) — clear them again or `saveContext()`
  // below re-persists the ones we meant to remove.
  if (hadLandmarks) {
    state.project.context.landmarks = [];
    await saveContext();
  }
}

// ---------- canvas input ----------
let drag = null;           // active handle/ghost drag session
let suppressClick = false; // swallow the click that follows a pointer gesture

function svgCoords(ev) {
  const svg = document.getElementById("canvas");
  const pt = svg.createSVGPoint();
  pt.x = ev.clientX; pt.y = ev.clientY;
  const { x, y } = pt.matrixTransform(svg.getScreenCTM().inverse());
  return toMmRaw(x, y);
}

// ONE answer per pixel, shared by the status readout and by every click: nearest
// run by real distance (geom.runAtPoint), and only when nothing is in range does
// the element under the pointer get a say — a decorated element (fat hit band,
// strategy overlay) may reach past the geometry but never contradict it.
// Before this, hover looped runs in array order while clicks took SVG paint
// order, so the corner of an L answered two different runs (persona-lab B4).
function runHitAt(ev) {
  if (!state.project) return null;
  const [mx, my] = svgCoords(ev);
  const geo = runAtPoint(mx, my);
  if (geo) return geo;
  const tagged = ev.target.closest && ev.target.closest("[data-run]");
  const run = tagged && runById(tagged.dataset.run);
  if (!run) return null;
  const { station, dist } = stationAtPoint(run, mx, my);
  return { run, station, dist };
}

function setupCanvas() {
  const svg = document.getElementById("canvas");
  // The post drag's preview layer, and the reason `pointermove` can promise to
  // touch nothing else: a preview drawn HERE cannot be mistaken for state,
  // because nothing but the drag ever writes to it and the drag clears it on
  // release. Last child, so it draws over the overlay; `pointer-events: none`
  // so a preview mark can never eat the drop.
  el("g", { id: "g-post-preview", "pointer-events": "none" }, svg);

  svg.addEventListener("click", (ev) => {
    if (suppressClick) { suppressClick = false; return; }
    if (!state.project) return;
    if (state.tool === "draw") {
      const [mx, my] = svgCoords(ev);
      const anchor = state.draftNodes.length
        ? state.draftNodes[state.draftNodes.length - 1] : null;
      const snap = snapPoint(mx, my, anchor, { alt: ev.altKey });
      state.draftNodes.push(snap.p);
      clearLengthBuffer(); // typed buffer resets after each placed dot
      renderDraft();
    } else if (state.tool === "select") {
      // resolved geometrically, so the strategy overlay drawn over a run (span
      // lines sit on the run's own line when it is vertical) can no longer
      // swallow the selection click — the real cause of "dragging does nothing"
      const hit = runHitAt(ev);
      if (hit) setSelection({ runId: hit.run.id });
      else if (!ev.target.closest("#g-overlay") && !ev.target.closest("#g-handles"))
        setSelection({});
    } else if (POLYGON_TOOLS.includes(state.tool)) {
      // Click by click, exactly like the draw tool one branch up — and for the
      // same reason it exists there: the shape is whatever the person walked
      // around, not whatever a rectangle could approximate.
      const [mx, my] = svgCoords(ev);
      addPolyPoint(state.tool, [Math.round(mx), Math.round(my)]);
    } else if (state.tool === "note") {
      // A promise is made ABOUT something. The Annotations tab asked a
      // salesperson to pick "r2" out of a list of run ids; here they point at
      // the thing they mean, and `noteTargetAt` says what that was.
      const target = noteTargetAt(ev);
      closePopover();
      openNotePopover(target, ev.clientX, ev.clientY);
    } else if (EVENT_TOOLS.includes(state.tool)) {
      const hit = runHitAt(ev);
      closePopover();
      if (hit) openEventPopover(state.tool, hit.run.id, hit.station, ev.clientX, ev.clientY);
    }
  });

  svg.addEventListener("dblclick", (ev) => {
    ev.preventDefault();
    // Whichever draft is open. Two buffers, one gesture that means "that is the
    // whole shape" — see `polyDraft`'s declaration for why they are separate.
    if (polyDraft) closePolyDraft(); else finishDraft();
  });

  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    zoomAt(ev, ev.deltaY > 0 ? 1.15 : 1 / 1.15);
  }, { passive: false });

  svg.addEventListener("pointerdown", (ev) => {
    const target = ev.target;
    // The other half of the same fault: an SVG is not focusable, so focus stays
    // on the last button pressed while the whole gesture happens on the canvas.
    // Taking focus here means the keys that mean something to the DRAWING —
    // Enter, Escape, a typed length — are delivered to it and to nothing else.
    // `preventScroll`, or the page jumps to the canvas on every press.
    if (document.activeElement && document.activeElement !== svg
        && document.activeElement !== document.body)
      document.activeElement.blur();
    svg.focus?.({ preventScroll: true });
    // BEFORE the pan check, and that ordering is the whole bug this line fixes.
    // A landmark is drawn on EMPTY canvas by definition — the house goes where
    // the fence is not — so `onSomething` below is false for every one of these
    // gestures and panning swallowed them all. Ctrl/middle-drag still pans,
    // because a person needs to move the view while placing a house.
    // A GATE is placed by dragging it out beside the fence — press at the post
    // it hangs from, release where the far post goes. Before the pan check for
    // the same reason the landmark tools are: the gesture starts on empty
    // canvas by definition, since a gate stands where the fence does not.
    // ...but never on a gate's own controls. `#g-gates` is `js/gates.js`'s
    // subtree and its marks answer their own clicks — flip the swing, move the
    // hinge. Capturing the pointer here would swallow those, and with the gate
    // tool armed on the gates step that is EVERY press a person makes on a gate
    // they have just placed: the controls would work on every step except the
    // one that shows them.
    if (state.tool === "gate" && state.project && !ev.target.closest?.("#g-gates")
        && ev.button === 0 && !ev.ctrlKey && !ev.metaKey) {
      ev.preventDefault();
      const from = svgCoords(ev);
      // Snapped to a post if there is one near, because "at the end of the
      // fence" is the whole gesture — the gate is what JOINS two stretches, and
      // it can only join them by sharing their nodes.
      const node = nearestNode(from[0], from[1], GATE_SNAP_MM);
      drag = { kind: "gate-span",
               from: node ? [node.x_mm, node.y_mm] : from,
               fromNodeId: node ? node.id : null,
               started: false, start: [ev.clientX, ev.clientY] };
      svg.setPointerCapture(ev.pointerId);
      return;
    }
    // ...but a POLYGON kind is built from clicks, so its press must usually
    // fall through to the pan branch below and let the click listener have the
    // gesture — capturing the pointer here would swallow every corner of the
    // house. The one exception is a press on a house that is already there
    // while nothing is half-drawn: that is a MOVE, and losing it would mean a
    // house could be drawn and never repositioned. Mid-shape the exception is
    // off, or the click that closes an outline drawn over an older house would
    // pick the old one up instead.
    const polyTool = gestureFor(state.tool) === "polygon";
    const movingPoly = polyTool && !polyDraft && state.project
      && landmarkAt(state.project.context?.landmarks, svgCoords(ev), state.tool);
    if (CONTEXT_TOOLS.includes(state.tool) && (!polyTool || movingPoly)
        && state.project && ev.button === 0 && !ev.ctrlKey && !ev.metaKey) {
      // One gesture, one shape: press, drag, release. A click-click-click
      // polyline would be a second draft state machine beside the one this file
      // already owns for runs, and a house is a rectangle anyway.
      //
      // `svgCoords`, not units.js's `toMm` — this is a POINT on the canvas and
      // the other converts a display value. Both are called toMm in their own
      // module, which is exactly how they get confused.
      ev.preventDefault();
      const from = svgCoords(ev);
      // The hit-test is done HERE, in code against the landmark's own
      // geometry — never via a DOM listener on the shape, which stays
      // `pointer-events: none` (context.js) so a house can never swallow a
      // click meant for the fence in front of it. Pressing on an existing
      // landmark of THIS tool's kind moves it; pressing anywhere else still
      // draws a new one exactly as before.
      const hit = landmarkAt(state.project.context?.landmarks, from, state.tool);
      // Stores the ID, not the landmark object: an in-flight `saveContext`
      // (this gesture's own, or one queued by undo/redo) can swap in a new
      // `state.project` mid-drag, and a captured object would then be a
      // detached copy that `onDragMove` kept mutating for nothing. Looked up
      // fresh every move via `landmarkById`, exactly like `runById` above.
      drag = hit
        ? { kind: "landmark-move", landmarkId: hit.id,
            origin: hit.points.map((p) => [...p]), from,
            started: false, start: [ev.clientX, ev.clientY] }
        : { kind: "landmark", landmarkKind: state.tool, from,
            started: false, start: [ev.clientX, ev.clientY] };
      svg.setPointerCapture(ev.pointerId);
      return;
    }
    // Panning, in order of how likely a user is to find it:
    //   drag empty canvas (any tool)  ·  middle button  ·  Ctrl/Cmd + drag
    // "empty" means the pointer is on nothing editable — a drag that starts on a
    // run, a handle, a ghost or an overlay element still means what it meant.
    const onSomething = target.closest
      && (target.closest(".run-hit") || target.closest("#g-handles")
          || target.closest("#g-overlay") || target.closest("#g-gates")
          || target.classList.contains("run-label"));
    if (ev.button === 1 || (ev.button === 0 && (ev.ctrlKey || ev.metaKey))
        || (ev.button === 0 && !onSomething)) {
      ev.preventDefault();
      pan = { screen: [ev.clientX, ev.clientY], view: { ...viewBox },
        moved: false, pointerId: ev.pointerId };
      svg.setPointerCapture(ev.pointerId);
      svg.classList.add("panning");
      return;
    }
    if (state.tool !== "select" || !state.project) return;
    if (target.classList.contains("handle")) {
      drag = { kind: "dot", runId: target.dataset.run, dotIndex: +target.dataset.dot,
        started: false, start: [ev.clientX, ev.clientY] };
      svg.setPointerCapture(ev.pointerId);
    } else if (target.classList.contains("ghost")) {
      drag = { kind: "ghost", runId: target.dataset.run, seg: +target.dataset.seg,
        started: false, start: [ev.clientX, ev.clientY] };
      svg.setPointerCapture(ev.pointerId);
    } else if (target.dataset.post && runById(target.dataset.run)) {
      // A THIRD kind on the one drag session, not a second session: the 4 px
      // threshold, the single pushSnapshot and the pointer capture below are the
      // gesture discipline (spec §9.2), and two sessions would be two copies of
      // it that could disagree. `from` is where this drag started, which is what
      // pointerup needs in order to DELETE the pin it is replacing.
      drag = { kind: "post", runId: target.dataset.run,
        postId: target.dataset.post, from: +target.dataset.station,
        postKind: target.dataset.kind, postPinned: target.dataset.pinned === "1",
        overrideId: target.dataset.override || null,
        station: +target.dataset.station, suppress: false, refused: false,
        started: false, start: [ev.clientX, ev.clientY] };
      svg.setPointerCapture(ev.pointerId);
      // Capture retargets the compatibility `click` to the capturing element,
      // so the circle's own click listener will not fire for this gesture and
      // the under-threshold click is answered in `onDragEnd` instead. Deferring
      // the capture to the 4 px threshold to keep that listener alive is worse
      // and was tried: a capture taken mid-gesture drops every pointermove
      // after it, and the post lands one step into the drag.
    }
  });
  svg.addEventListener("pointermove", (ev) => {
    if (pan) {
      if (!pan.moved && Math.hypot(ev.clientX - pan.screen[0],
                                   ev.clientY - pan.screen[1]) < 4) return;
      pan.moved = true;
      // delta in SCREEN pixels scaled by the pan-start view: immune to the
      // feedback of viewBox changing mid-gesture
      const svgEl = document.getElementById("canvas");
      viewBox.x = pan.view.x - (ev.clientX - pan.screen[0]) * (pan.view.w / svgEl.clientWidth);
      viewBox.y = pan.view.y - (ev.clientY - pan.screen[1]) * (pan.view.h / svgEl.clientHeight);
      applyViewBox();
      return;
    }
    onPointerMove(ev);
  });
  svg.addEventListener("pointerup", (ev) => {
    if (pan) {
      const moved = pan.moved;
      pan = null;
      svg.classList.remove("panning");
      // a press that never moved was a click, not a pan: let the tool have it
      if (moved) {
        suppressClick = true;
        setTimeout(() => { suppressClick = false; }, 0);
      }
      return;
    }
    onDragEnd(ev);
  });
  svg.addEventListener("pointercancel", (ev) => {
    if (pan) { pan = null; svg.classList.remove("panning"); return; }
    onDragEnd(ev);
  });

  document.addEventListener("keydown", (ev) => {
    const tag = ev.target && ev.target.tagName;
    const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") {
      if (typing) return; // leave text-field undo alone
      ev.preventDefault();
      if (ev.shiftKey) redo(); else undo();
      return;
    }
    if (typing) return;
    // SketchUp-style typed lengths: digits typed anywhere while drawing feed the
    // length buffer (never when focus is in a field — the guard above)
    const drawTyping = state.tool === "draw" && state.draftNodes.length > 0;
    if (drawTyping && !ev.ctrlKey && !ev.metaKey && !ev.altKey
        && /^[\d.cmמ]$/.test(ev.key)) {
      const next = lengthBuffer + ev.key;
      if (/^(\d+(\.\d*)?|\.\d*)(mm|cm|c|m|מ)?$/.test(next)) {
        ev.preventDefault();
        lengthBuffer = next;
        updateLengthChip();
        return;
      }
    }
    if (drawTyping && ev.key === "Backspace" && lengthBuffer) {
      ev.preventDefault();
      lengthBuffer = lengthBuffer.slice(0, -1);
      updateLengthChip();
      return;
    }
    if (ev.key === "Escape") {
      closePopover();
      // first Esc clears only the typed buffer; a second Esc cancels the draft
      if (drawTyping && lengthBuffer) { clearLengthBuffer(); return; }
      cancelDraft();
    }
    // `preventDefault` FIRST, and it is the whole of a reported bug. Enter is
    // "that is the whole shape" here, and it is also the browser's activation
    // key for whatever button happens to have focus — which, after arriving at
    // a step by pressing *Done — next: ...*, is the road's own Done button,
    // because clicking on an SVG moves focus nowhere. So finishing a run with
    // the keyboard finished the run AND walked the salesperson to the next
    // step. One keystroke, two commits, and only one of them asked for.
    if (ev.key === "Enter" && polyDraft) {
      ev.preventDefault();
      closePolyDraft();
      return;
    }
    if (ev.key === "Enter" && state.draftNodes.length) {
      ev.preventDefault();
      if (drawTyping && lengthBuffer) { commitTypedDot(); return; }
      finishDraft();
    }
    if ((ev.key === "Delete" || ev.key === "Backspace") && state.tool === "select")
      deleteSelectedDot();
  });
  document.getElementById("btn-finish-draft").addEventListener("click", finishDraft);
  document.getElementById("btn-cancel-draft").addEventListener("click", cancelDraft);
}

function onPointerMove(ev) {
  if (drag) { onDragMove(ev); return; }
  const [mx, my] = svgCoords(ev);
  if (polyDraft) renderContextDraftPolygon(polyDraft.points, [mx, my]);
  if (state.tool === "draw" && state.draftNodes.length) {
    lastDrawMouse = [mx, my]; // remembered aim for typed-length commits
    renderRubberBand(mx, my, ev.altKey);
  }
  // live cursor readout — the SAME resolver the click uses, so the station the
  // status bar prints is the station the click records
  const hit = runHitAt(ev);
  updateStatus(hit
    ? { station_mm: hit.station, x_mm: Math.round(mx), y_mm: Math.round(my) }
    : null);
}

// ---------- select tool: drag / insert / delete ----------
function onDragMove(ev) {
  const [mx, my] = svgCoords(ev);
  if (drag.kind === "gate-span") {
    drag.started = true;
    const node = nearestNode(mx, my, GATE_SNAP_MM, drag.fromNodeId);
    drag.to = node ? [node.x_mm, node.y_mm] : [mx, my];
    drag.toNodeId = node ? node.id : null;
    renderGateDraft(drag);
    return;
  }
  if (drag.kind === "landmark") {
    drag.started = true;
    drag.to = [mx, my];
    renderContextDraft(drag.landmarkKind, drag.from, drag.to);
    return;
  }
  if (drag.kind === "landmark-move") {
    if (!drag.started) {
      if (Math.hypot(ev.clientX - drag.start[0], ev.clientY - drag.start[1]) < 4) return;
      // snapshot BEFORE the mutation, same discipline as every other drag
      // here: context shares the ONE undo stack with the topology now, so a
      // moved house must undo exactly like a moved fence dot.
      pushSnapshot("move-landmark");
      drag.started = true;
    }
    const lm = landmarkById(state.project.context?.landmarks, drag.landmarkId);
    if (!lm) return; // undo/redo removed it out from under this drag
    const dx = mx - drag.from[0], dy = my - drag.from[1];
    // int mm at rest (ADR-0002): round at the boundary, same as
    // `Landmark._round_to_mm` does server-side.
    lm.points = drag.origin.map(([x, y]) => [
      Math.round(x + dx), Math.round(y + dy),
    ]);
    renderContext();
    return;
  }
  if (!drag.started) {
    if (Math.hypot(ev.clientX - drag.start[0], ev.clientY - drag.start[1]) < 4) return;
    // gesture begins: snapshot BEFORE any mutation.
    // A post drag is the one kind that mutates NOTHING while it moves, so its
    // single snapshot is pushed at release instead (`commitPostDrag`), where it
    // is still the last thing before the first write. Pushed here it would also
    // be pushed for a drop the pointer REFUSED, and an undo step that restores
    // an identical project is a keystroke that does nothing.
    if (drag.kind !== "post")
      pushSnapshot(drag.kind === "ghost" ? "insert-vertex" : "move-dot");
    if (drag.kind === "ghost") {
      const run = runById(drag.runId);
      run.interior_vertices.splice(drag.seg, 0, [mx, my]);
      drag.dotIndex = drag.seg + 1;
      drag.kind = "dot";
    }
    drag.started = true;
  }
  // A post drag draws and nothing else: no state.project, no history past the
  // snapshot above, no fetch. Everything it needs is a position, and every
  // position it needs comes from post-drag.js.
  if (drag.kind === "post") { previewPostDrag(mx, my); return; }
  const run = runById(drag.runId);
  const pts = runPoints(run);
  const anchor = pts[drag.dotIndex > 0 ? drag.dotIndex - 1 : 1];
  const isNode = drag.dotIndex === 0 || drag.dotIndex === pts.length - 1;
  const nodeId = drag.dotIndex === 0 ? run.start_node_id : run.end_node_id;
  const snap = snapPoint(mx, my, anchor,
    { alt: ev.altKey, excludeNodeId: isNode ? nodeId : undefined });
  applyDotPosition(run, drag.dotIndex, snap.p);
  renderTopology();
  renderHandles();
  renderSnapFeedback(snap, anchor);
}

function applyDotPosition(run, dotIndex, [x, y]) {
  const last = runPoints(run).length - 1;
  if (dotIndex === 0) {
    const n = nodeById(run.start_node_id); n.x_mm = x; n.y_mm = y;
  } else if (dotIndex === last) {
    const n = nodeById(run.end_node_id); n.x_mm = x; n.y_mm = y;
  } else {
    run.interior_vertices[dotIndex - 1] = [x, y];
  }
}

function onDragEnd() {
  if (!drag) return;
  const d = drag;
  drag = null;
  clearGroup("g-snap");
  clearGroup("g-post-preview");
  updateStatus();
  // swallow the click that may follow this pointer gesture; a drag fires no
  // click at all, so clear the flag on the next tick either way
  suppressClick = true;
  setTimeout(() => { suppressClick = false; }, 0);
  if (d.kind === "gate-span") {
    clearGroup("g-snap");
    commitGateSpan(d);
    return;
  }
  if (d.kind === "landmark") {
    clearContextDraft();
    const shape = shapeFor(d.landmarkKind, d.from, d.to);
    // null for a gesture too small to be deliberate — a stray click with the
    // house tool active must not leave an invisible 3 mm building the office
    // person then has to ask about.
    if (!shape) return;
    // `pushSnapshot` BEFORE the mutation, sharing the topology's ONE undo
    // stack rather than a second one of its own: `SiteContext` is UNREVISIONED
    // (project/model.py — "there is nothing downstream that could be stale
    // against it"), so a landmark can ride this stack without sharing the
    // topology's revision counter. Two stacks would make Ctrl+Z do a
    // different thing depending on which tool was last active, and that is
    // worse than what this replaces.
    pushSnapshot("place-landmark");
    addLandmark({
      id: nextLandmarkId(state.project?.context?.landmarks),
      kind: d.landmarkKind, label: "", ...shape,
    });
    saveContext();
    return;
  }
  if (d.kind === "landmark-move") {
    // Moved (vs. a plain click on an existing landmark, which does nothing):
    // persist via `saveContext`, never `saveTopology` — a landmark carries no
    // revision to bump.
    if (d.started) saveContext();
    return;
  }
  if (d.kind === "post") {
    // Under the 4 px threshold the gesture IS a click and opens the inspector
    // (spec §9.2.5) — answered here rather than by the circle's own listener,
    // which the pointer capture taken at pointerdown has already bypassed.
    if (d.started) commitPostDrag(d);
    else openPostInspector(d);
    return;
  }
  if (d.started) {
    setSelection({ runId: d.runId, dotIndex: d.dotIndex });
    saveTopology(); // snapshot was pushed at gesture start
  } else if (d.kind === "dot") {
    setSelection({ runId: d.runId, dotIndex: d.dotIndex }); // plain click on a dot
  } else {
    setSelection({ runId: d.runId });
  }
}

function deleteSelectedDot() {
  const { runId, dotIndex } = state.selection;
  if (runId == null || dotIndex == null) return;
  const run = runById(runId);
  if (!run) return;
  const last = runPoints(run).length - 1;
  if (dotIndex > 0 && dotIndex < last) {
    pushSnapshot("delete-vertex");
    run.interior_vertices.splice(dotIndex - 1, 1);
    setSelection({ runId });
    saveTopology();
  } else if (run.interior_vertices.length === 0) {
    // end node of a 2-dot run: delete the run (and orphaned nodes), confirmed
    if (!confirm(t("confirm.delete_run"))) return;
    pushSnapshot("delete-run");
    const topo = state.project.topology;
    topo.runs = topo.runs.filter((r) => r.id !== run.id);
    for (const nid of [run.start_node_id, run.end_node_id]) {
      const used = topo.runs.some(
        (r) => r.start_node_id === nid || r.end_node_id === nid);
      if (!used) topo.nodes = topo.nodes.filter((n) => n.id !== nid);
    }
    setSelection({});
    saveTopology();
  }
}

// ---------- select tool: dragging a post (spec §9, adapter A) ----------------
// This is the CANVAS half of the gesture and nothing else: hit-test a circle,
// project a pointer onto the run's polyline, write the one override both
// adapters write. Every number comes from `post-drag.js`, which the side view
// calls too — inlining the arithmetic here is exactly the drift `base-top.js`
// exists to prevent, and the two views would then draw the same post in two
// places.
//
// Pointer tolerances, in world millimetres:
//   POST_SNAP_MM    — how close a snap candidate must be to be taken;
//   DROP_ON_POST_MM — how close a drop must be to a neighbouring post to MEAN
//                     that post, which is the suppress gesture.
const POST_SNAP_MM = 100;
const DROP_ON_POST_MM = RUN_HIT_MM;

/** Where a placement directive currently applies, or null when it says nothing.
 *
 *  Mirrors backend `override_station` (strategy/overrides.py): the ANCHOR wins
 *  where a directive carries both, because `station_mm` is the reading the
 *  geometry HAD, and preferring it would freeze a pin at the number it wore
 *  when the run was a different length. */
function placementStation(run, directive) {
  if (directive.anchor) return stationOfAnchor(run, directive.anchor);
  return directive.station_mm || null;
}

/** The stations a drag may neither move nor lay out across: run ends, every
 *  generated post that is not a plain line post — a corner, a gate edge, a step,
 *  a transition — and every post a person already pinned.
 *
 *  That set is the generator's own `fixed` (`{0, length} | corners |
 *  transitions | pinned | gate_edges | steps`), READ BACK off the last run
 *  rather than recomputed here. The browser owning a second copy of that rule is
 *  how a preview starts promising a layout the generator will not build. */
function fixedStationsFor(runId, exceptStation) {
  const run = runById(runId);
  const out = new Set();
  for (const post of state.result?.strategy.posts || []) {
    if (post.run_ref !== runId) continue;
    if (post.kind === "line" && !post.pinned) continue;
    out.add(post.station_mm);
  }
  for (const ov of state.project?.overrides || []) {
    if (ov.run_id !== runId || ov.directive.kind !== "pin_post") continue;
    const s = placementStation(run, ov.directive);
    if (s !== null) out.add(s);
  }
  out.delete(exceptStation);
  return [...out].sort((a, b) => a - b);
}

/** Every post the pointer could land ON, which is a different question from
 *  which stations are fixed: a plain line post is free to be re-laid-out, but
 *  dropping another post onto it is still a gesture about it. */
function neighbourStations(runId, exceptStation) {
  const run = runById(runId);
  const out = new Set([0, runLength(run)]);
  for (const post of state.result?.strategy.posts || [])
    if (post.run_ref === runId) out.add(post.station_mm);
  for (const s of fixedStationsFor(runId, exceptStation)) out.add(s);
  out.delete(exceptStation);
  return [...out].sort((a, b) => a - b);
}

/** The picture one pointermove needs. Rebuilt per move because the neighbours
 *  change as the pointer crosses them.
 *
 *  `minSpanMm: 0` is deliberate and not a stub: the sliver PREFERENCE lives in
 *  knowledge and reaches no frontend surface, and inventing one here would draw
 *  a rule nobody wrote. `violations()` therefore reports only the hard maximum,
 *  which is the one the plan and the quote carry. */
function postDragContext(d) {
  const run = runById(d.runId);
  return {
    run,
    length: runLength(run),
    fixed: fixedStationsFor(d.runId, d.from),
    neighbours: neighbourStations(d.runId, d.from),
    limits: { maxSpanMm: maxSpanFor(d.runId), minSpanMm: 0 },
  };
}

// The two stations a candidate sits between. Not layout arithmetic — the bays
// themselves are `layoutWithPin`'s answer, never this function's.
function bracket(stations, station) {
  let prev = 0, next = Infinity;
  for (const s of stations) {
    if (s < station) prev = Math.max(prev, s);
    else if (s > station) next = Math.min(next, s);
  }
  return [prev, next];
}

function previewPostDrag(mx, my) {
  const d = drag;
  const ctx = postDragContext(d);
  // stationAtPoint returns {station, dist} and DISCARDS which segment won, so
  // the anchor is re-derived with anchorFor at drop time — never from this.
  const raw = stationAtPoint(ctx.run, mx, my).station;
  const station = Math.max(0, Math.min(raw, ctx.length));

  // Dropping a post onto its neighbour says "this post should not be here",
  // which is a suppression and not a move.
  const onto = ctx.neighbours.find((s) => Math.abs(s - station) <= DROP_ON_POST_MM);
  if (onto !== undefined) {
    d.station = onto;
    d.suppress = true;
    // ...but only a LINE post can be suppressed. A corner, a gate edge, a step
    // or a pinned post is structural, so the gesture is refused HERE, at the
    // pointer, rather than written as an override that immediately reports
    // itself orphaned in a warning list nobody was looking at.
    d.refused = d.postKind !== "line" || d.postPinned;
    renderPostPreview(ctx, d, []);
    return;
  }
  d.suppress = false;
  d.refused = false;
  const [prev, next] = bracket(ctx.neighbours, station);
  // No `stock`/`piecesPerBay`: the browser has no infill stock length for this
  // bay that it did not invent, and a yield tick computed from a guess
  // advertises a saving the cut list will not deliver. Counts come from the
  // backend (spec §9.1) — this module only ever computes a position.
  const snaps = snapCandidates({
    station, prev, next, ...ctx.limits, displayUnit: currentUnit(),
  });
  let taken = null;
  for (const c of snaps)
    if (taken === null || Math.abs(c.station - station) < Math.abs(taken.station - station))
      taken = c;
  d.station = taken && Math.abs(taken.station - station) <= POST_SNAP_MM
    ? taken.station : station;
  renderPostPreview(ctx, d, snaps);
}

function renderPostPreview(ctx, d, snaps) {
  const g = clearGroup("g-post-preview");
  // The layout this drop would produce — the one the backend will build, from
  // the module that mirrors `equal_layout`. A pin does not exempt the run from
  // the maximum: it only says where one post goes.
  const { widths } = layoutWithPin(
    ctx.fixed, ctx.length, d.suppress ? null : d.station, ctx.limits);
  const broken = violations(widths, ctx.limits);
  const badBays = new Set(broken.map((v) => v.index));
  let at = 0;
  for (let i = 0; i < widths.length; i++) {
    const a = toPx(pointAtStation(ctx.run.id, at));
    const b = toPx(pointAtStation(ctx.run.id, at + widths[i]));
    el("line", { x1: a[0], y1: a[1] + 13, x2: b[0], y2: b[1] + 13,
      stroke: badBays.has(i) ? "#dc2626" : "#0f766e", "stroke-width": 3,
      "stroke-dasharray": "3 3", opacity: 0.85 }, g);
    at += widths[i];
  }
  for (const c of snaps) {
    const p = toPx(pointAtStation(ctx.run.id, c.station));
    el("line", { x1: p[0], y1: p[1] - 15, x2: p[0], y2: p[1] + 15,
      stroke: "#94a3b8", "stroke-width": 1, "stroke-dasharray": "2 3" }, g);
  }
  const p = toPx(pointAtStation(ctx.run.id, d.station));
  el("circle", { cx: p[0], cy: p[1], r: 9, fill: "none",
    stroke: d.suppress ? "#dc2626" : "#f59e0b", "stroke-width": 3,
    "stroke-dasharray": d.suppress ? "3 3" : "none" }, g);
  if (d.refused) {
    // a refusal has to be visible at the pointer, or it reads as a dead drag
    el("line", { x1: p[0] - 10, y1: p[1] - 10, x2: p[0] + 10, y2: p[1] + 10,
      stroke: "#dc2626", "stroke-width": 3 }, g);
    el("line", { x1: p[0] + 10, y1: p[1] - 10, x2: p[0] - 10, y2: p[1] + 10,
      stroke: "#dc2626", "stroke-width": 3 }, g);
  }
  const bar = document.getElementById("statusbar");
  if (!bar) return;
  if (d.suppress) {
    bar.textContent = t(d.refused ? "editor.drag_no_suppress" : "editor.drag_suppress");
    return;
  }
  const worst = broken[0];
  bar.textContent = tu("editor.drag_station", { station_mm: d.station })
    + (widths.length
      ? ` · ${tu("editor.drag_bays", { min_mm: Math.min(...widths), max_mm: Math.max(...widths) })}`
      : "")
    + (worst ? ` · ${tu("editor.drag_over_max", { over_mm: worst.over_mm })}` : "");
}

/** A press on a post that never became a drag: select it and explain it.
 *
 *  A PENDING marker is deliberately silent here. It is not a generated element,
 *  there is no decision trail to walk, and asking for one would answer "no
 *  decisions" about a placement the person made themselves. Its own panel is
 *  the inspector work Task 5 owns. */
function openPostInspector(d) {
  setSelection({ runId: d.runId, elementId: d.postId });
  const post = (state.result?.strategy.posts || []).find((p) => p.id === d.postId);
  if (post)
    inspect(post.id, "inspect.post", { sku: post.sku, station_mm: post.station_mm });
}

/** The placement overrides this drag started from — the ones pointerup has to
 *  delete before it posts a replacement.
 *
 *  Exact when the drag started on a PENDING marker (it carries its own override
 *  id); by resolved station otherwise, which is how a drag that started on a
 *  generated post finds the pin that put it there. */
function placementOverridesFrom(d) {
  const run = runById(d.runId);
  return (state.project?.overrides || []).filter((ov) => {
    if (ov.run_id !== d.runId) return false;
    if (d.overrideId) return ov.id === d.overrideId;
    const kind = ov.directive.kind;
    if (kind !== "pin_post" && kind !== "suppress_post") return false;
    const s = placementStation(run, ov.directive);
    return s !== null && Math.abs(s - d.from) <= GROUND_TOL_MM;
  });
}

async function commitPostDrag(d) {
  if (!runById(d.runId)) return;
  if (d.refused) return;   // refused at the pointer: nothing is written at all
  // A suppression is about the post the drag STARTED on, so it is anchored
  // there; a move is anchored where the pointer let go.
  const station = d.suppress ? d.from : d.station;
  const anchor = { ...anchorFor(d.runId, station), reanchor: "rigid" };
  // once per gesture, and the last thing before the first write
  pushSnapshot("move-post");
  try {
    // DELETE first. There is no `PUT /overrides`: without this a second drag on
    // the same post leaves TWO pins and a bay nobody asked for.
    for (const ov of placementOverridesFrom(d))
      await apiSend("DELETE",
        `/api/projects/${state.projectId}/overrides/${ov.id}`);
    await apiSend("POST", `/api/projects/${state.projectId}/overrides`, {
      id: "", run_id: d.runId,
      directive: { kind: d.suppress ? "suppress_post" : "pin_post", anchor },
    });
    // reloadProject, never openProject: an override is not a topology change and
    // must not wipe the undo stack. It does NOT refresh state.result — which is
    // why the placement is drawn as a pending marker below, and why nothing here
    // generates. Generation stays behind the button.
    await reloadProject();
  } catch { /* apiSend has already shown and logged the failure */ }
}

// ---------- event tools: gate/base/ground/pin popover (Task 8) ----------
let popover = null;

function closePopover() {
  if (!popover) return;
  popover.remove();
  popover = null;
  document.removeEventListener("pointerdown", onOutsidePointer, true);
}

function onOutsidePointer(ev) {
  if (popover && !popover.contains(ev.target)) closePopover();
}

// ---------- gate kit catalog ----------
// Both `gateKitProducts` and `declaredOpening` now live in `js/gates.js`, with
// the panel that asks the question they answer. They were private here, which is
// why the ONLY place a gate product was ever named was inside this popover —
// i.e. after the user had already committed to a spot on the fence. The gates
// step of the salesperson's road showed no gate and no way to choose one, which
// is the defect the panel fixes; keeping a second copy of the catalog filter
// here would let the panel and the popover disagree about what a gate is.

async function openEventPopover(tool, runId, station, clientX, clientY) {
  closePopover();
  const run = runById(runId);
  if (!run) return;
  const L = runLength(run);
  // model: only PUBLISHED models may be authored onto a run — a draft's document
  // can still change under its version, so a run pinned to one is a run whose
  // panel could be rewritten under it
  const models = tool === "model" ? (await loadModelListing()).filter(isSelectable) : [];
  // length fields carry mm in, display units out (units.js is the only converter).
  // A null value opens the field EMPTY — save() then refuses it — which is how a
  // figure nobody stated stays unstated instead of becoming a plausible default.
  const numField = (key, id, valueMm) =>
    `<label>${tu(key)}<input id="${id}" type="number" step="${inputStep()}"
      value="${valueMm === null ? "" : toDisplayValue(valueMm)}"></label>`;
  const fieldMm = (id) => toMm(document.getElementById(id).value);
  // ground at a run END is the elevation of the SHARED corner node, not of one
  // leg: recorded run-locally, the two legs of an L disagree about the same
  // point and a climb gets priced as level ground (persona-lab B4)
  const groundNode = tool === "ground" ? endpointNodeAt(run, station) : null;
  // the header names what will actually be written: the corner node and ITS
  // station, never the pixel that happened to be under the cursor
  const shownStation = groundNode ? (station <= L / 2 ? 0 : L) : station;
  // base, height and model state a stretch, not a point: no station in the header
  const wholeRun = tool === "base" || tool === "height" || tool === "model";
  let html = `<h4>${t("tool." + tool)}</h4>
    <div class="meta"><bdi>${esc(groundNode ? groundNode.id : runId)}</bdi>${wholeRun ? ""
      : ` · ${t("popover.station")} <span class="num">${esc(fmtLen(shownStation))}</span>`}</div>`;
  if (tool === "base") {
    const currentTilt = run.interval_events.find((iv) => iv.payload.kind === "post_tilt");
    const tiltMode = currentTilt?.payload.mode || "plumb";
    html += `<label>${t("popover.surface")}<select id="pop-surface">
      <option value="soil">${t("surface.soil")}</option>
      <option value="concrete">${t("surface.concrete")}</option>
      <option value="masonry_wall">${t("surface.masonry_wall")}</option>
    </select></label>`;
    html += `<label>${t("popover.post_tilt")}<select id="pop-tilt">
      <option value="plumb"${tiltMode === "plumb" ? " selected" : ""}>${t("tilt.plumb")}</option>
      <option value="perpendicular"${tiltMode === "perpendicular" ? " selected" : ""}>${t("tilt.perpendicular")}</option>
      <option value="custom"${tiltMode === "custom" ? " selected" : ""}>${t("tilt.custom")}</option>
    </select></label>
    <label id="pop-tilt-deg-row"${tiltMode === "custom" ? "" : " hidden"}>${t("popover.tilt_deg")}
      <input id="pop-tilt-deg" type="number" min="-45" max="45"
        value="${currentTilt?.payload.tilt_deg ?? 15}"></label>`;
  } else if (tool === "ground") {
    // seed the elevation that is already there (node z / interpolated ground),
    // never a bare 0 that looks like an answer
    html += numField("popover.z", "pop-z", groundNode
      ? (groundNode.z_mm ?? 0)
      : groundZAt(groundSamplesFor(run, L), station));
  } else if (tool === "height") {
    // the whole section, like the base tool: seeding start from the clicked
    // station left half a fence at the wrong height, with nothing to notice.
    // Height leads — it is the tool's question, so it is what the auto-focus
    // selects and what a typed number followed by Enter answers.
    html += numField("popover.height", "pop-height", 1800);
    html += numField("popover.start", "pop-start", 0);
    html += numField("popover.end", "pop-end", L);
  } else if (tool === "model") {
    // the same shape as the height tool, one question along: which model this
    // stretch is built to, and where that stretch starts and ends
    if (models.length) {
      html += `<label>${t("popover.model")}<select id="pop-model">` + models.map((row) =>
        `<option value="${esc(row.id)}" dir="auto">${esc(modelOptionLabel(row))}</option>`
      ).join("") + `</select></label>`;
    } else {
      html += `<div class="meta">${t("popover.no_models")}</div>`;
    }
    html += numField("popover.start", "pop-start", 0);
    html += numField("popover.end", "pop-end", L);
  } else if (tool === "pin") {
    html += `<div class="meta">${t("popover.pin_hint")}</div>`;
  }
  html += `<div class="popover-actions">
    <button id="pop-cancel">${t("popover.cancel")}</button>
    <button id="pop-save" class="primary">${t("popover.save")}</button></div>`;
  popover = document.createElement("div");
  popover.className = "popover";
  popover.innerHTML = html;
  document.body.appendChild(popover);
  // position at the click, kept inside the viewport (cursor-anchored:
  // physical coords by nature; the canvas is never mirrored)
  popover.style.left = `${Math.max(4, Math.min(clientX + 8, window.innerWidth - popover.offsetWidth - 12))}px`;
  popover.style.top = `${Math.max(4, Math.min(clientY + 8, window.innerHeight - popover.offsetHeight - 12))}px`;

  async function save() {
    // a blank or unparseable length is NOT zero: refuse the save, flag the field
    // and leave the popover open — never push null into a topology payload
    const needed = { ground: ["pop-z"],
      height: ["pop-height", "pop-start", "pop-end"],
      model: ["pop-start", "pop-end"] }[tool] || [];
    const values = {};
    let bad = null;
    for (const id of needed) {
      const field = document.getElementById(id);
      values[id] = fieldMm(id);
      field.classList.toggle("invalid", values[id] === null);
      if (values[id] === null && !bad) bad = field;
    }
    if (bad) { bad.focus(); return; }
    // nothing published to choose: close rather than write an event naming a
    // model that does not resolve — the generator would refuse the whole run
    if (tool === "model" && !models.length) { closePopover(); return; }
    pushSnapshot(tool);
    if (tool === "base") {
      // one base + one post-orientation per section: replace, whole run
      run.interval_events = run.interval_events.filter(
        (iv) => iv.payload.kind !== "base" && iv.payload.kind !== "post_tilt");
      addIntervalEvent(runId, {
        kind: "base", surface: document.getElementById("pop-surface").value,
      }, 0, runLength(run));
      const tiltMode = document.getElementById("pop-tilt").value;
      if (tiltMode !== "plumb") {
        addIntervalEvent(runId, {
          kind: "post_tilt", mode: tiltMode,
          tilt_deg: tiltMode === "custom"
            ? Math.max(-45, Math.min(45, Math.round(+document.getElementById("pop-tilt-deg").value || 0)))
            : 0,
        }, 0, runLength(run));
      }
    } else if (tool === "ground") {
      if (groundNode) {
        groundNode.z_mm = values["pop-z"];
        // an endpoint sample on ANY leg overrides the node for that leg only —
        // clear those, or the corner keeps two elevations (backend
        // ground_samples(): a sample within GROUND_TOL_MM of an end wins)
        for (const r of state.project.topology.runs) {
          const at = r.start_node_id === groundNode.id ? 0
            : r.end_node_id === groundNode.id ? runLength(r) : null;
          if (at === null) continue;
          r.point_events = r.point_events.filter((pe) =>
            pe.payload.kind !== "elevation_sample"
            || Math.abs(stationOfAnchor(r, pe.anchor) - at) > GROUND_TOL_MM);
        }
      } else {
        addPointEvent(runId, {
          kind: "elevation_sample", z_mm: values["pop-z"],
        }, station);
      }
    } else if (tool === "height") {
      addIntervalEvent(runId, {
        kind: "height_intent", height_mm: values["pop-height"], source: "user",
      }, values["pop-start"], values["pop-end"]);
    } else if (tool === "model") {
      const start = values["pop-start"], end = values["pop-end"];
      // Replace on save, as the base tool does — but scoped to the stretch,
      // because this event is an interval. `fence_model_at` (topology/station.py)
      // answers with the FIRST event covering a station, so an older overlapping
      // choice left in the list would silently defeat the one just authored:
      // the user picks M-SLAT here, presses save, and the fence stays M-LEGACY
      // with nothing to see. Anything the new stretch touches goes.
      run.interval_events = run.interval_events.filter((iv) =>
        iv.payload.kind !== "fence_model"
        || stationOfAnchor(run, iv.end_anchor) <= start
        || stationOfAnchor(run, iv.start_anchor) >= end);
      addIntervalEvent(runId, {
        // no version pin: an unpinned choice follows the published line, and the
        // resolved (id, version) is stamped on the run either way
        kind: "fence_model", model_id: document.getElementById("pop-model").value,
        version_pin: null, options: {},
      }, start, end);
    } else if (tool === "pin") {
      await apiSend("POST", `/api/projects/${state.projectId}/overrides`, {
        id: "", run_id: runId,
        directive: { kind: "pin_post", station_mm: station },
      });
    }
    closePopover();
    await saveTopology();
  }

  popover.addEventListener("keydown", (ev) => {
    ev.stopPropagation();
    if (ev.key === "Escape") closePopover();
    else if (ev.key === "Enter") { ev.preventDefault(); save(); }
  });
  popover.querySelector("#pop-tilt")?.addEventListener("change", (ev) => {
    document.getElementById("pop-tilt-deg-row").hidden = ev.target.value !== "custom";
  });
  popover.querySelector("#pop-cancel").addEventListener("click", closePopover);
  popover.querySelector("#pop-save").addEventListener("click", save);
  // focus AND select: a caret parked at position 0 of a number field turns a
  // typed 1000 into 10000 — ten metres, silently saveable (openLengthInput does
  // the same, and every field this builds is pre-filled)
  const first = popover.querySelector("input, select, button");
  if (first) { first.focus(); first.select?.(); }
  // blur = pointer down anywhere outside cancels (registered after this click)
  setTimeout(() => document.addEventListener("pointerdown", onOutsidePointer, true), 0);
}

// ---------- typed exact length ----------
function openLengthInput(runId) {
  const existing = document.getElementById("length-editor");
  if (existing) existing.remove();
  const run = runById(runId);
  if (!run) return;
  const mid = toPx(pointAtStation(run.id, runLength(run) / 2));
  const g = document.getElementById("g-handles");
  const fo = el("foreignObject", { x: mid[0] - 45, y: mid[1] - 34, width: 92,
    height: 28, id: "length-editor" }, g);
  const input = document.createElement("input");
  input.type = "number";
  input.className = "mm-input";
  input.step = inputStep();
  input.value = toDisplayValue(runLength(run));
  fo.appendChild(input);
  input.focus();
  input.select();
  let done = false;
  const close = () => { done = true; fo.remove(); };
  input.addEventListener("keydown", (ev) => {
    ev.stopPropagation();
    if (ev.key === "Enter") { const v = toMm(input.value); close(); commitTypedLength(runId, v); }
    else if (ev.key === "Escape") close();
  });
  input.addEventListener("blur", () => { if (!done) close(); });
}

function commitTypedLength(runId, typedTotal) {
  const run = runById(runId);
  if (!run || !Number.isFinite(typedTotal)) return;
  const pts = runPoints(run);
  const A = pts[pts.length - 2], B = pts[pts.length - 1];
  const h = Math.hypot(B[0] - A[0], B[1] - A[1]);
  if (!h) return;
  const upTo = runLength(run) - Math.round(h); // length up to the last segment
  if (typedTotal <= upTo) { alert(tu("editor.invalid_length", { min_mm: upTo })); return; }
  const d = [(B[0] - A[0]) / h, (B[1] - A[1]) / h];
  pushSnapshot("typed-length");
  const end = nodeById(run.end_node_id); // end NODE moves; shared runs follow by design
  end.x_mm = Math.round(A[0] + d[0] * (typedTotal - upTo));
  end.y_mm = Math.round(A[1] + d[1] * (typedTotal - upTo));
  saveTopology();
}

// ---------- type-while-drawing lengths (SketchUp Measurements-box mechanic) ----
let lengthBuffer = "";     // raw typed entry, e.g. "4", "3.5", "250cm"
let lastDrawMouse = null;  // last cursor world position while drawing (the aim)
let chipAnchorView = null; // rubber-band end in SVG view coords (chip anchor)

function clearLengthBuffer() {
  lengthBuffer = "";
  updateLengthChip();
}

function updateLengthChip() {
  let chip = document.getElementById("length-chip");
  if (!lengthBuffer) { if (chip) chip.remove(); return; }
  if (!chip) {
    chip = document.createElement("div");
    chip.id = "length-chip";
    document.body.appendChild(chip);
  }
  const mm = parseTypedLength(lengthBuffer);
  const echo = mm ? tu("editor.length_chip_echo", { v_mm: mm }) : "";
  chip.innerHTML = `<span class="num">${esc(lengthBuffer)}</span>`
    + (echo ? `<span class="chip-echo">${esc(echo)}</span>` : "");
  positionLengthChip();
}

function positionLengthChip() {
  const chip = document.getElementById("length-chip");
  if (!chip) return;
  const ref = chipAnchorView
    || (state.draftNodes.length ? toPx(state.draftNodes[state.draftNodes.length - 1]) : null);
  if (!ref) return;
  const svg = document.getElementById("canvas");
  const ctm = svg.getScreenCTM();
  if (!ctm) return;
  const pt = svg.createSVGPoint();
  pt.x = ref[0]; pt.y = ref[1];
  const q = pt.matrixTransform(ctm); // chip is cursor-anchored: physical coords
  chip.style.left = `${q.x + 14}px`;
  chip.style.top = `${q.y - 34}px`;
}

// Enter with a buffer: place the next dot at EXACTLY the typed distance along the
// current rubber-band direction. The direction gets the same 45-degree/6-degree
// angle snap as drawing (aim roughly + type = perfect axis-aligned segments); the
// magnitude is exact — deliberately no grid snap.
function commitTypedDot() {
  const mm = parseTypedLength(lengthBuffer);
  if (!mm || !state.draftNodes.length) return;
  const anchor = state.draftNodes[state.draftNodes.length - 1];
  let ang = 0; // no aim yet: default along +x
  if (lastDrawMouse) {
    const dx = lastDrawMouse[0] - anchor[0], dy = lastDrawMouse[1] - anchor[1];
    if (Math.hypot(dx, dy) >= 1) {
      ang = Math.atan2(dy, dx);
      const step = Math.PI / 4;
      const k = Math.round(ang / step);
      if (Math.abs(ang - k * step) <= (6 * Math.PI) / 180) ang = k * step;
    }
  }
  state.draftNodes.push([
    Math.round(anchor[0] + Math.cos(ang) * mm),
    Math.round(anchor[1] + Math.sin(ang) * mm),
  ]);
  clearLengthBuffer();
  chipAnchorView = null;
  clearGroup("g-snap"); // stale rubber band anchored on the previous dot
  renderDraft();
}

// ---------- placing a gate ----------

/** The rubber band while a gate is being dragged out.
 *
 *  Drawn into `g-snap`, which every gesture in this file uses for the mark that
 *  is not state yet and which the next render clears — a preview that outlived
 *  its gesture is the bug `clearDraft` exists to prevent. */
function renderGateDraft(d) {
  const g = clearGroup("g-snap");
  if (!g || !d.to) return;
  const a = toPx(d.from), b = toPx(d.to);
  el("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "#0891b2",
    "stroke-width": 5, opacity: 0.6, "pointer-events": "none" }, g);
  const len = Math.round(Math.hypot(d.to[0] - d.from[0], d.to[1] - d.from[1]));
  el("text", { x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2 - 10, "font-size": 10,
    fill: "#0891b2", "text-anchor": "middle", class: "num",
    "pointer-events": "none" }, g).textContent = tu("canvas.mm", { n_mm: len });
  // ...and a ring on an end that has FOUND a post, so "this is what it will
  // join" is visible before the gesture is committed rather than after.
  for (const [p, id] of [[a, d.fromNodeId], [b, d.toNodeId]])
    if (id) el("circle", { cx: p[0], cy: p[1], r: 9, fill: "none",
      class: "snap-guide", "pointer-events": "none" }, g);
}

/** Commit the dragged gate.
 *
 *  Either end that landed on a post SHARES that node — which is the whole of
 *  "it can combine 2 unconnected runs": two stretches drawn separately become
 *  one fence because the gate between them is anchored to both their ends. An
 *  end that found no post gets a node of its own, so a gate hanging off the end
 *  of a single stretch still has something to hang from (the generator emits
 *  the post there, because nothing else would).
 *
 *  It writes to `topology.gates` and touches no run — a gate is not a stretch
 *  of fence and placing one changes the layout of none. */
function commitGateSpan(d) {
  if (!d.started || !d.to || !state.project) return;
  const topo = state.project.topology;
  const span = Math.hypot(d.to[0] - d.from[0], d.to[1] - d.from[1]);
  // Too small to be deliberate — a stray press with the gate tool armed must
  // not leave a 3 mm opening somebody then has to find and delete.
  if (span < MIN_MM) return;
  pushSnapshot("place-gate");
  const nodeFor = (point, existingId) => {
    if (existingId) return existingId;
    const id = `n${state.nodeSeq++}`;
    topo.nodes.push({ id, x_mm: Math.round(point[0]), y_mm: Math.round(point[1]),
                      kind: "terminal" });
    return id;
  };
  const startId = nodeFor(d.from, d.fromNodeId);
  const endId = nodeFor(d.to, d.toNodeId);
  topo.gates = [...(topo.gates || []), {
    id: nextGateId(topo),
    start_node_id: startId,
    end_node_id: endId,
    // The gate chosen once in the panel, not asked again per gate. Which way it
    // opens is deliberately NOT guessed: it is a question mark on the drawing
    // until somebody answers it, because a swing drawn from a default is a
    // confident wrong drawing.
    kit_sku: chosenGateKit(),
    leaf: "single",
  }];
  saveTopology();
}

// ---------- click-built landmarks (the house) ----------

/** Add one corner, or close the shape when the click lands back on the first.
 *
 *  There is no separate "close" button and there deliberately is not one: the
 *  gesture that ends a shape is pointing at where it started, which is what a
 *  person drawing on paper does. Enter and a double-click do it too, for
 *  whoever reaches for a keyboard instead. */
function addPolyPoint(kind, point) {
  // Switching tools mid-shape abandons it rather than welding a pool onto a
  // half-drawn house: `polyDraft` remembers which kind it belongs to.
  if (polyDraft && polyDraft.kind !== kind) polyDraft = null;
  if (!polyDraft) polyDraft = { kind, points: [] };
  const first = polyDraft.points[0];
  if (first && polyDraft.points.length >= 3
      && Math.hypot(point[0] - first[0], point[1] - first[1]) <= POLY_CLOSE_MM) {
    closePolyDraft();
    return;
  }
  polyDraft.points.push(point);
  renderContextDraftPolygon(polyDraft.points, null);
}

/** Commit whatever has been clicked so far, or drop it if it is not a shape.
 *
 *  `polygonFromClicks` is the judge — it drops a doubled corner and the closing
 *  click, and refuses anything under three points, because `Landmark`'s own
 *  validator refuses those too and getting a 422 back after drawing a building
 *  is worse than the gesture quietly needing one more corner. */
function closePolyDraft() {
  const draft = polyDraft;
  polyDraft = null;
  clearContextDraft();
  if (!draft || !state.project) return;
  const shape = polygonFromClicks(draft.points);
  if (!shape) return;
  // Snapshot BEFORE the mutation, on the ONE undo stack the topology uses —
  // the same discipline the drag-drawn landmarks keep in `onDragEnd`.
  pushSnapshot("place-landmark");
  addLandmark({
    id: nextLandmarkId(state.project?.context?.landmarks),
    kind: draft.kind, label: "", ...shape,
  });
  saveContext();
}

// ---------- the note tool: what did they point at? ----------

/** The thing under a click, as a note target.
 *
 *  Order matters and each rung is a judgement:
 *    1. a POINT event on a run — a gate, a ground reading, a pinned post. It is
 *       the smallest thing there, so pointing at it means it.
 *    2. a corner NODE, when the click is at the end of a run: "the post by the
 *       gate post" is about the corner, not about either leg of it.
 *    3. the RUN. Interval events (base, height, model) are deliberately NOT
 *       matched: `base` covers the whole run, so matching it would mean no click
 *       on a fence could ever be about the fence.
 *    4. a LANDMARK — the house, the pool, a tree.
 *    5. the job itself, for a click on empty ground.
 *  The label travels with the ref because the popover has to say what it heard,
 *  and `notes.js` owns how a ref is put into words. */
function noteTargetAt(ev) {
  const at = (ref) => ({ ref, label: targetLabel(ref) });
  const [mx, my] = svgCoords(ev);
  const hit = runHitAt(ev);
  if (hit) {
    const run = hit.run;
    let best = null, bestD = RUN_HIT_MM;
    for (const pe of run.point_events || []) {
      const d = Math.abs(stationOfAnchor(run, pe.anchor) - hit.station);
      if (d <= bestD) { best = pe; bestD = d; }
    }
    if (best) return at(`event:${best.id}`);
    const node = endpointNodeAt(run, hit.station);
    if (node) return at(`node:${node.id}`);
    return at(`run:${run.id}`);
  }
  const lm = landmarkAtAny(state.project?.context?.landmarks, [mx, my]);
  if (lm) return at(`landmark:${lm.id}`);
  return at("project");
}

// ---------- draw tool ----------
function cancelDraft() {
  state.draftNodes = [];
  lastDrawMouse = null;
  chipAnchorView = null;
  clearLengthBuffer();
  clearGroup("g-draft");
  clearGroup("g-snap");
  polyDraft = null;
  // The LANDMARK rubber band as well. Escape cancels "the draft" as a
  // salesperson means it — whatever I am half-way through drawing — and a
  // house or street half-drawn is exactly that. Left out, Escape cleared the
  // fence draft and left a street-shaped line nothing could select or remove.
  clearContextDraft();
  updateDraftButtons();
}

function finishDraft() {
  if (state.draftNodes.length >= 2) {
    pushSnapshot("draw");
    const topo = state.project.topology;
    const ids = state.draftNodes.map((p) => {
      const existing = topo.nodes.find(
        (n) => Math.hypot(n.x_mm - p[0], n.y_mm - p[1]) <= 100
      );
      if (existing) return existing.id;
      const id = `n${state.nodeSeq++}`;
      topo.nodes.push({ id, x_mm: p[0], y_mm: p[1], kind: "terminal" });
      return id;
    });
    for (let i = 0; i + 1 < ids.length; i++) {
      topo.runs.push({
        id: `run${state.runSeq++}`, start_node_id: ids[i], end_node_id: ids[i + 1],
        interior_vertices: [], point_events: [], interval_events: [],
      });
    }
    saveTopology();
  }
  cancelDraft();
}

function renderDraft() {
  const g = clearGroup("g-draft");
  const pts = state.draftNodes.map(toPx);
  if (pts.length > 1)
    el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none",
      stroke: "#94a3b8", "stroke-dasharray": "6 4", "stroke-width": 2 }, g);
  for (const p of pts)
    el("circle", { cx: p[0], cy: p[1], r: 4, fill: "#94a3b8" }, g);
  updateDraftButtons();
}

function renderRubberBand(mx, my, alt) {
  const g = clearGroup("g-snap");
  const anchor = state.draftNodes[state.draftNodes.length - 1];
  const snap = snapPoint(mx, my, anchor, { alt });
  const a = toPx(anchor), p = toPx(snap.p);
  el("line", { x1: a[0], y1: a[1], x2: p[0], y2: p[1], class: "rubber" }, g);
  if (snap.kind === "dot" && snap.node)
    el("circle", { cx: p[0], cy: p[1], r: 9, fill: "none", class: "snap-guide" }, g);
  else if (snap.kind === "angle")
    el("line", { x1: a[0], y1: a[1], x2: p[0], y2: p[1], class: "snap-guide" }, g);
  const len = Math.round(Math.hypot(snap.p[0] - anchor[0], snap.p[1] - anchor[1]));
  el("text", { x: (a[0] + p[0]) / 2 + 8, y: (a[1] + p[1]) / 2 - 8, "font-size": 10,
    fill: "#2563eb", class: "num" }, g).textContent = tu("canvas.mm", { n_mm: len });
  chipAnchorView = p; // the typed-length chip follows the rubber-band end
  positionLengthChip();
}

function renderSnapFeedback(snap, anchor) {
  const g = clearGroup("g-snap");
  if (snap.kind === "dot" && snap.node) {
    const p = toPx([snap.node.x_mm, snap.node.y_mm]);
    el("circle", { cx: p[0], cy: p[1], r: 9, fill: "none", class: "snap-guide" }, g);
  } else if (snap.kind === "angle" && anchor) {
    const a = toPx(anchor), p = toPx(snap.p);
    el("line", { x1: a[0], y1: a[1], x2: p[0], y2: p[1], class: "snap-guide" }, g);
  }
}

function updateDraftButtons() {
  const show = state.draftNodes.length > 0;
  document.getElementById("draft-actions").style.display = show ? "flex" : "none";
}

// ---------- rendering ----------
function renderGrid() {
  const g = clearGroup("g-grid");
  // 1 m grid aligned to world coordinates, covering the current viewBox
  // (5 m spacing when zoomed far out so the grid never becomes a moiré)
  let step = 1000 * 0.045;
  if (viewBox.w > 2700) step *= 5;
  const x0 = Math.floor(viewBox.x / step) * step;
  const y0 = Math.floor(viewBox.y / step) * step;
  for (let x = x0; x < viewBox.x + viewBox.w; x += step)
    el("line", { x1: x, y1: viewBox.y, x2: x, y2: viewBox.y + viewBox.h, stroke: "#eef2f6" }, g);
  for (let y = y0; y < viewBox.y + viewBox.h; y += step)
    el("line", { x1: viewBox.x, y1: y, x2: viewBox.x + viewBox.w, y2: y, stroke: "#eef2f6" }, g);
  const scale = viewBox.w / 900;
  el("text", { x: viewBox.x + 6 * scale, y: viewBox.y + 14 * scale,
    "font-size": 10 * scale, fill: "#94a3b8", class: "grid-note" }, g)
    .textContent = viewBox.w > 2700 ? t("canvas.grid_note_5m") : t("canvas.grid_note");
}

// ---------- zoom & pan (viewBox only; world<->viewBox mapping is unchanged) ----
const DEFAULT_VIEW = { x: 0, y: 0, w: 900, h: 500 };
let viewBox = { ...DEFAULT_VIEW };
let pan = null; // active pan session

function applyViewBox() {
  document.getElementById("canvas")
    .setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`);
  renderGrid();
  positionLengthChip(); // the typed-length chip glued to its anchor
}

function svgViewPoint(ev) {
  const svg = document.getElementById("canvas");
  const pt = svg.createSVGPoint();
  pt.x = ev.clientX; pt.y = ev.clientY;
  const { x, y } = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [x, y];
}

function zoomAt(ev, factor) {
  const [cx, cy] = svgViewPoint(ev);
  const w = Math.max(225, Math.min(viewBox.w * factor, 5400)); // 0.25x .. 6x
  const scale = w / viewBox.w;
  viewBox = {
    x: cx - (cx - viewBox.x) * scale,
    y: cy - (cy - viewBox.y) * scale,
    w, h: viewBox.h * scale,
  };
  applyViewBox();
}

function fitView() {
  const pts = [];
  for (const n of state.project?.topology.nodes || []) pts.push(toPx([n.x_mm, n.y_mm]));
  for (const r of state.project?.topology.runs || [])
    for (const v of r.interior_vertices || []) pts.push(toPx(v));
  if (!pts.length) { viewBox = { ...DEFAULT_VIEW }; applyViewBox(); return; }
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const pad = 60;
  let x = Math.min(...xs) - pad, y = Math.min(...ys) - pad;
  let w = Math.max(...xs) - x + pad * 2, h = Math.max(...ys) - y + pad * 2;
  // preserve the 900:500 aspect so nothing distorts
  if (w / h > 900 / 500) { const nh = w * 500 / 900; y -= (nh - h) / 2; h = nh; }
  else { const nw = h * 900 / 500; x -= (nw - w) / 2; w = nw; }
  if (w < 450) { const nw = 450, nh = 250; x -= (nw - w) / 2; y -= (nh - h) / 2; w = nw; h = nh; }
  viewBox = { x, y, w, h };
  applyViewBox();
}

function renderTopology() {
  const g = clearGroup("g-topology");
  renderGrid();
  if (!state.project) return;
  const topo = state.project.topology;
  for (const run of topo.runs) {
    const selected = state.selection.runId === run.id;
    const pts = runPoints(run).map(toPx);
    const ptsAttr = pts.map((p) => p.join(",")).join(" ");
    el("polyline", { points: ptsAttr, fill: "none",
      stroke: selected ? "#2563eb" : "#334155", "stroke-width": selected ? 4 : 3 }, g);
    for (const iv of run.interval_events) {
      if (iv.payload.kind !== "base") continue;
      const L = runLength(run);
      const p0 = toPx(pointAtStation(run.id, stationOfAnchor(run, iv.start_anchor)));
      const p1 = toPx(pointAtStation(run.id, Math.min(stationOfAnchor(run, iv.end_anchor), L)));
      el("line", { x1: p0[0], y1: p0[1] + 7, x2: p1[0], y2: p1[1] + 7,
        stroke: BASE_COLORS[iv.payload.surface] || "#a16207", "stroke-width": 4,
        "stroke-linecap": "round", opacity: 0.7 }, g);
    }
    for (const pe of run.point_events) {
      const evStation = stationOfAnchor(run, pe.anchor);
      const p = toPx(pointAtStation(run.id, evStation));
      // A gate is drawn by `js/gates.js` into its own `#g-gates` group, not
      // here: the mark now carries the opening's real width, the way it opens
      // and two controls for changing that, and none of it belongs in the
      // module that draws the fence. This branch used to draw a dashed segment
      // labelled "gate" — a placement, which is exactly what the user said is
      // "not sufficient for an opening fence".
      if (pe.payload.kind === "elevation_sample") {
        el("text", { x: p[0] - 8, y: p[1] + 20, "font-size": 9, fill: "#7c3aed" }, g)
          .textContent = `z=${fmt(pe.payload.z_mm)}`;
      }
    }
    // invisible fat hit line: run selection + event-tool clicks + touch targets
    el("polyline", { points: ptsAttr, fill: "none", class: "run-hit",
      "data-run": run.id }, g);
    const mid = toPx(pointAtStation(run.id, runLength(run) / 2));
    const label = el("text", { x: mid[0] - 12, y: mid[1] - 8, "font-size": 10,
      fill: selected ? "#2563eb" : "#334155", class: "run-label", "data-run": run.id }, g);
    label.textContent = `${run.id} (${fmtLen(runLength(run))})`;
    el("title", {}, label).textContent = t("editor.length_tooltip");
    label.addEventListener("click", (ev) => {
      // the length editor belongs to the select tool. Unguarded, the height tool
      // shrank a 6 m run to 1800 mm because the label ate the click meant for the
      // run — every other tool must see the canvas click it aimed at.
      if (state.tool !== "select") return;
      ev.stopPropagation();
      openLengthInput(run.id);
    });
  }
  for (const n of topo.nodes) {
    const p = toPx([n.x_mm, n.y_mm]);
    // visual only — must not steal clicks from the run hit lines underneath
    el("rect", { x: p[0] - 4, y: p[1] - 4, width: 8, height: 8, fill: "#334155",
      "pointer-events": "none" }, g);
  }
}

const GHOST_OFFSET_PX = 12;

// Dots of the selected run: squares (vertex handles) + midpoint ghosts (circles).
function renderHandles() {
  const g = clearGroup("g-handles");
  if (state.tool !== "select" || !state.project || !state.selection.runId) return;
  const run = runById(state.selection.runId);
  if (!run) return;
  const pts = runPoints(run);
  for (let i = 0; i + 1 < pts.length; i++) {
    const a = toPx(pts[i]), b = toPx(pts[i + 1]);
    const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    // Offset PERPENDICULAR to the segment, not laid on it.
    //
    // A ghost drawn at the true midpoint collides with the generated post that
    // lands there whenever a run divides evenly into its bays — which is the
    // ordinary case, not a corner one. `#g-handles` paints after `#g-overlay`,
    // so the ghost took the pointerdown and the post could not be dragged;
    // resolving that in the hit test only moved the dead affordance from one to
    // the other, because both wanted the same pixel. So the handle steps aside:
    // 12 px clears r 6 + r 5 with room, and perpendicular works on a run of any
    // direction, unlike the overlay's flat -8 y (which slides ALONG a vertical
    // run rather than beside it).
    //
    // The vertex this inserts is still computed from `data-seg` and the drop
    // point, so where the handle sits changes nothing about what it does.
    const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
    const len = Math.hypot(dx, dy) || 1;
    const off = [(-dy / len) * GHOST_OFFSET_PX, (dx / len) * GHOST_OFFSET_PX];
    el("circle", { cx: m[0] + off[0], cy: m[1] + off[1], r: 5, class: "ghost",
      "data-run": run.id, "data-seg": i }, g);
  }
  pts.forEach((p, i) => {
    const q = toPx(p);
    el("rect", { x: q[0] - 5, y: q[1] - 5, width: 10, height: 10,
      class: "handle" + (state.selection.dotIndex === i ? " selected" : ""),
      "data-run": run.id, "data-dot": i }, g);
  });
}

function renderOverlay() {
  const g = clearGroup("g-overlay");
  if (!document.getElementById("chk-overlay").checked) return;
  if (state.result) renderGeneratedOverlay(g);
  // LAST, so a pending marker sits ON TOP of the generated post it displaces and
  // the next drag grabs the placement rather than the stale run state.
  renderPendingPlacements(g);
}

function renderGeneratedOverlay(g) {
  const s = state.result.strategy;
  for (const span of s.spans) {
    // Resolved BEFORE `toPx`, which dereferences its argument: the old order
    // threw on a span whose run this drawing no longer has, instead of skipping
    // it — and one throw here abandons the whole overlay mid-draw.
    const a = pointAtStation(span.run_ref, span.start_station_mm);
    const b = pointAtStation(span.run_ref, span.end_station_mm);
    if (!a || !b) continue;
    const p0 = toPx(a), p1 = toPx(b);
    const color = span.vertical === "stepped" ? "#7c3aed"
      : span.vertical === "raked" ? "#059669" : "#93c5fd";
    // data-run: an overlay line lies ON its run when the run is vertical, so it
    // must be able to name the run it decorates instead of eating the click
    const line = el("line", { x1: p0[0], y1: p0[1] - 8, x2: p1[0], y2: p1[1] - 8,
      stroke: color, "stroke-width": 6, opacity: 0.75, cursor: "pointer",
      "data-run": span.run_ref }, g);
    line.addEventListener("click", () =>
      inspect(span.id, "inspect.span",
        { width_mm: span.width_mm, height_mm: span.height_mm, mode: span.vertical }));
    const bayTag = tagOf(span.id);
    if (bayTag)
      el("text", { x: (p0[0] + p1[0]) / 2, y: (p0[1] + p1[1]) / 2 + 14, "font-size": 9,
        "text-anchor": "middle", class: "elem-tag bay", "pointer-events": "none" }, g)
        .textContent = bayTag;
  }
  for (const gate of s.gates) {
    // A gate that lies on NO run is the standalone kind, and `js/gates.js` draws
    // it — at its real width, with the way it opens, from the topology rather
    // than from a generated strategy. Skipped here rather than guarded further
    // down, because `run_ref: null` is not a missing value to tolerate: it is
    // this loop being told the gate is somebody else's to draw.
    if (!gate.run_ref) continue;
    const a = pointAtStation(gate.run_ref, gate.start_station_mm);
    const b = pointAtStation(gate.run_ref, gate.end_station_mm);
    // BEFORE `toPx`, which dereferences its argument — the old order threw on a
    // run this strategy no longer has rather than skipping the element.
    if (!a || !b) continue;
    const p0 = toPx(a), p1 = toPx(b);
    const line = el("line", { x1: p0[0], y1: p0[1] - 8, x2: p1[0], y2: p1[1] - 8,
      stroke: "#0891b2", "stroke-width": 6, "stroke-dasharray": "4 4",
      cursor: "pointer", "data-run": gate.run_ref }, g);
    line.addEventListener("click", () => inspect(gate.id, "inspect.gate", { kit: gate.kit_sku }));
  }
  for (const post of s.posts) {
    let xy;
    if (post.run_ref.startsWith("node:")) {
      const node = state.project.topology.nodes.find((n) => `node:${n.id}` === post.run_ref);
      xy = node ? [node.x_mm, node.y_mm] : null;
    } else {
      xy = pointAtStation(post.run_ref, post.station_mm);
    }
    if (!xy) continue;
    const p = toPx(xy);
    // A post had no identity in the DOM at all — a bare <circle>. These
    // attributes are what makes it draggable: which post, on which run, at which
    // station, and (kind + pinned) whether it is a post that may be suppressed
    // at all. A node post (`run_ref` "node:...") gets them too and is simply
    // never picked up, because `runById` cannot resolve its run.
    const c = el("circle", { cx: p[0], cy: p[1], r: post.reinforced ? 8 : 6,
      fill: POST_COLORS[post.kind] || "#2563eb",
      stroke: post.pinned ? "#f59e0b" : post.mounting === "masonry" ? "#dc2626" : "#fff",
      "stroke-width": post.pinned ? 3 : 2, cursor: "pointer",
      "data-post": post.id, "data-run": post.run_ref,
      "data-station": post.station_mm, "data-kind": post.kind,
      "data-pinned": post.pinned ? "1" : "0" }, g);
    el("title", {}, c).textContent =
      `${post.id}\n${post.sku} (${enumWord(post.kind)}, ${enumWord(post.mounting)})`;
    const postTag = tagOf(post.id);
    if (postTag)
      el("text", { x: p[0] + 7, y: p[1] - 7, "font-size": 9, class: "elem-tag",
        "pointer-events": "none" }, g).textContent = postTag;
    c.addEventListener("click", () => {
      // the latch the pointer gesture sets: a completed drag must not ALSO open
      // the inspector. Under the 4 px threshold the latch is never set, and the
      // gesture is the click it looks like.
      if (suppressClick) return;
      inspect(post.id, "inspect.post", { sku: post.sku, station_mm: post.station_mm });
    });
  }
}

/** Placements the person has made and the engine has not yet been asked about.
 *
 *  Drawn from `state.project.overrides`, hollow and dashed, deliberately not
 *  looking like a generated post — because they are not one. `reloadProject()`
 *  does not refresh `state.result`, so the overlay still holds the previous
 *  run's posts; without this marker the post a person just dropped springs back
 *  to where the old run put it and a working feature reads as a broken one.
 *
 *  Showing the two as two kinds of thing is the honest rendering, not a
 *  cosmetic one: a pin is a fact about the PROJECT and is saved immediately, a
 *  post position is a fact about the RUN and has not been recomputed. Nothing
 *  here generates — that stays behind the button.
 *
 *  Only a pin is draggable. A suppression marks a post that should not exist,
 *  and dragging one would be a gesture with no meaning. */
function renderPendingPlacements(g) {
  if (!state.project) return;
  for (const ov of state.project.overrides || []) {
    const d = ov.directive;
    const suppressed = d.kind === "suppress_post";
    if (d.kind !== "pin_post" && !suppressed) continue;
    const run = runById(ov.run_id);
    if (!run) continue;
    const station = placementStation(run, d);
    if (station === null) continue;   // orphaned: the warning list says so
    const xy = pointAtStation(run.id, station);
    if (!xy) continue;
    const p = toPx(xy);
    const c = el("circle", { cx: p[0], cy: p[1], r: 7, fill: "none",
      stroke: suppressed ? "#dc2626" : "#f59e0b", "stroke-width": 2.5,
      "stroke-dasharray": "3 3", class: "pending-post", "data-pending": "1",
      ...(suppressed ? {} : {
        // `fill: none` under the default `visiblePainted` leaves the INTERIOR of
        // the ring transparent to hit-testing, so a pointer aimed at the middle
        // of the marker fell straight through to the run's hit band and the
        // marker could not be picked up at all. `all` is what makes the shape a
        // target rather than its outline.
        "pointer-events": "all",
        cursor: "pointer", "data-post": `pending:${ov.id}`, "data-override": ov.id,
        "data-run": run.id, "data-station": station,
        // a pinned post is not suppressible, so a drag of this marker onto a
        // neighbour is refused the same way the generator would refuse it
        "data-kind": "line", "data-pinned": "1",
      }),
    }, g);
    el("title", {}, c).textContent =
      t(suppressed ? "editor.pending_suppress" : "editor.pending_pin");
    if (suppressed)
      el("line", { x1: p[0] - 5, y1: p[1] - 5, x2: p[0] + 5, y2: p[1] + 5,
        stroke: "#dc2626", "stroke-width": 2, "pointer-events": "none" }, g);
  }
}

// What did the button actually produce? The overlay draws it and the BOM prices
// it, but neither says it in words — so the strategy read as "something happened".
function renderStrategySummary() {
  const box = document.getElementById("strategy-summary");
  if (!box) return;
  if (!state.result) {
    // Nothing, not a sentence. "No strategy yet — press ⚙ Generate strategy" sat
    // directly beneath the button it was describing, on every step of the road
    // including the ones with no drawing on screen at all. A label that repeats
    // the control above it is not a hint; it is one more thing to read before
    // finding out that nothing has happened yet. The empty box keeps its place
    // in the column so the layout does not jump when a run does produce one.
    box.innerHTML = "";
    return;
  }
  const s = state.result.strategy;
  const widths = s.spans.map((sp) => sp.width_mm);
  const fenceLen = widths.reduce((a, b) => a + b, 0)
    // `width_mm`, not the station difference: a standalone gate lies on no run
    // and carries 0/0 for its stations, so the old arithmetic left it out of the
    // fence length entirely — a fence with a 1 m gate at the end read a metre
    // short. For an in-run gate the two are the same number by construction.
    + s.gates.reduce((a, g) => a + (g.width_mm || 0), 0);
  const modes = [...new Set(s.spans.map((sp) => sp.vertical))];
  const heights = [...new Set(s.spans.map((sp) => sp.height_mm))];
  const skus = [...new Set(s.posts.map((p) => p.sku))].filter(Boolean);
  const errors = s.warnings.filter((w) => w.severity === "error").length;
  // Hebrew (and English) count agreement: one post, not "1 posts"
  const stat = (labelKey, value) =>
    `<span class="stat"><b class="num">${esc(String(value))}</b> `
    + `${esc(t(value === 1 ? `${labelKey}_one` : labelKey))}</span>`;
  box.innerHTML = `
    <div class="summary-line">
      <b>${esc(t("strategy.title"))}</b>
      ${stat("strategy.posts", s.posts.length)}
      ${stat("strategy.spans", s.spans.length)}
      ${s.gates.length ? stat("strategy.gates", s.gates.length) : ""}
      <span class="stat">${esc(tu("strategy.length", { total_mm: fenceLen }))}</span>
    </div>
    <div class="summary-line meta">
      ${widths.length ? esc(tu("strategy.span_widths", {
        min_mm: Math.min(...widths), max_mm: Math.max(...widths),
      })) : ""}
      ${heights.length === 1 ? " · " + esc(tu("strategy.height", { height_mm: heights[0] })) : ""}
      ${modes.length ? " · " + esc(t("strategy.vertical")) + " "
        + modes.map((m) => esc(enumWord(m))).join(", ") : ""}
      ${skus.length ? " · " + esc(t("strategy.post_skus")) + " "
        + skus.map((k) => `<span class="sku">${esc(k)}</span>`).join(", ") : ""}
    </div>
    <div class="summary-line meta">
      ${esc(s.warnings.length === 0 ? t("strategy.no_warnings")
        : tu(s.warnings.length === 1 ? "strategy.warnings_count_one"
          : "strategy.warnings_count", { n: s.warnings.length, errors }))}
      · <a href="#" id="summary-to-bom">${esc(t("strategy.see_bom"))}</a>
      · ${esc(t("strategy.click_hint"))}
    </div>`;
  const link = document.getElementById("summary-to-bom");
  if (link) link.addEventListener("click", (ev) => {
    ev.preventDefault();
    document.querySelector('#tabs button[data-tab="bom"]')?.click();
  });
}

/** The gap surface beside the warnings, on the screen where a run is read.
 *
 *  Its own container rather than more rows inside `#warnings`: a warning is a
 *  note about this plan and a gap is a work item about the knowledge behind
 *  every plan, and folding the second into the first is how `would_close` — the
 *  only field that makes a gap worth receiving — ends up with nowhere to go. */
function renderGaps() {
  const div = document.getElementById("gaps");
  if (!div) return;
  // `empty: true` is deliberate on THIS surface: after a generation, "no gaps"
  // is an answer to a question the reader is entitled to ask, and silence is
  // indistinguishable from a panel that failed to render.
  div.innerHTML = state.result
    ? gapsPanelHtml(state.result.strategy?.gaps, { empty: true }) : "";
}

function renderWarnings() {
  const div = document.getElementById("warnings");
  div.innerHTML = "";
  if (!state.result) return;
  // the same row the BOM and structure tabs render for a supply warning — one
  // shape, so a warning does not read differently depending on which tab it is
  // seen from
  for (const w of state.result.strategy.warnings)
    div.insertAdjacentHTML("beforeend", warningRowHtml(w));
  for (const c of state.critique || []) {
    const d = document.createElement("div");
    d.className = "warning";
    d.innerHTML = `🤖 ${t("warning.critic_prefix")}: ${localizedByCode("critique", c.code, c.params, c.text)}`;
    div.appendChild(d);
  }
}
