// Plan-canvas editor: rendering + tools. Select (handles/ghosts/drag/delete),
// Draw (snapped dots, rubber band, typed lengths) — plan Tasks 6-8.
// The canvas is never mirrored in RTL (spec §4).

import { apiGet, apiSend, esc } from "./api.js";
import {
  clearGroup, el, nodeById, pointAtStation, runById, runLength, runPoints,
  snapPoint, stationAtPoint, stationOfAnchor, toMmRaw, toPx,
} from "./geom.js";
import { pushSnapshot, redo, undo } from "./history.js";
import { currentLocale, t } from "./i18n.js";
import { inspect } from "./inspector.js";
import {
  addIntervalEvent, addPointEvent, generateStrategy, on, saveTopology,
  setSelection, setTool, state,
} from "./state.js";
import {
  currentUnit, enumWord, fmt, fmtLen, inputStep, toDisplayValue, toMm, tu,
  unitParams,
} from "./units.js";

const EVENT_TOOLS = ["gate", "base", "ground", "height", "pin"];

const BASE_COLORS = { soil: "#a16207", concrete: "#64748b", masonry_wall: "#dc2626" };
const POST_COLORS = { line: "#2563eb", end: "#1e293b", corner: "#1e293b",
  junction: "#1e293b", gate: "#0891b2", transition: "#dc2626" };
const HOVER_RUN_MM = 400; // cursor-readout proximity

export function initEditor() {
  setupCanvas();
  setupToolbar();
  renderGrid();
  loadCatalogProducts(); // warm the cache so the gate popover opens instantly
  on("project-loaded", () => { renderAllCanvas(); renderHandles(); });
  on("result-changed", () => { renderOverlay(); renderWarnings(); });
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
  updateStatus();
}

function renderAllCanvas() {
  renderTopology();
  renderOverlay();
  renderWarnings();
}

// ---------- toolbar ----------
const TOOLS = ["select", "draw", "gate", "base", "ground", "height", "pin"];

function setupToolbar() {
  for (const tool of TOOLS) {
    const btn = document.getElementById(`tool-${tool}`);
    if (btn) btn.addEventListener("click", () => { setTool(tool); updateStatus(); });
  }
  document.getElementById("btn-generate").addEventListener("click", generateStrategy);
  document.getElementById("btn-fit").addEventListener("click", fitView);
  document.getElementById("chk-overlay").addEventListener("change", renderOverlay);
  document.getElementById("btn-clear").addEventListener("click", clearTopology);
  updateToolButtons();
}

function updateToolButtons() {
  for (const tool of TOOLS) {
    const btn = document.getElementById(`tool-${tool}`);
    if (btn) btn.classList.toggle("active", state.tool === tool);
  }
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

async function clearTopology() {
  if (!confirm(t("confirm.clear_topology"))) return;
  pushSnapshot("clear");
  state.draftNodes = [];
  clearGroup("g-draft");
  clearGroup("g-snap");
  setSelection({});
  state.project.topology = {
    revision: state.project.topology.revision, nodes: [], runs: [],
  };
  await saveTopology();
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

function setupCanvas() {
  const svg = document.getElementById("canvas");
  // empty-canvas CTA layer (created here, not in index.html: editor-owned DOM);
  // separate from g-draft so clearing the draft layer never leaves CTA remnants
  el("g", { id: "g-cta", "pointer-events": "none" }, svg);

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
      const hit = ev.target.closest && ev.target.closest(".run-hit");
      if (hit) setSelection({ runId: hit.dataset.run });
      else if (!ev.target.closest("#g-overlay") && !ev.target.closest("#g-handles"))
        setSelection({});
    } else if (EVENT_TOOLS.includes(state.tool)) {
      const hit = ev.target.closest && ev.target.closest(".run-hit");
      closePopover();
      if (hit) {
        const run = runById(hit.dataset.run);
        const [mx, my] = svgCoords(ev);
        const station = stationAtPoint(run, mx, my).station;
        openEventPopover(state.tool, run.id, station, ev.clientX, ev.clientY);
      }
    }
  });

  svg.addEventListener("dblclick", (ev) => { ev.preventDefault(); finishDraft(); });

  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    zoomAt(ev, ev.deltaY > 0 ? 1.15 : 1 / 1.15);
  }, { passive: false });

  svg.addEventListener("pointerdown", (ev) => {
    // pan: middle button, or Ctrl/Cmd + primary (never conflicts with editing)
    if (ev.button === 1 || (ev.button === 0 && (ev.ctrlKey || ev.metaKey))) {
      ev.preventDefault();
      pan = { screen: [ev.clientX, ev.clientY], view: { ...viewBox } };
      svg.setPointerCapture(ev.pointerId);
      return;
    }
    if (state.tool !== "select" || !state.project) return;
    const target = ev.target;
    if (target.classList.contains("handle")) {
      drag = { kind: "dot", runId: target.dataset.run, dotIndex: +target.dataset.dot,
        started: false, start: [ev.clientX, ev.clientY] };
      svg.setPointerCapture(ev.pointerId);
    } else if (target.classList.contains("ghost")) {
      drag = { kind: "ghost", runId: target.dataset.run, seg: +target.dataset.seg,
        started: false, start: [ev.clientX, ev.clientY] };
      svg.setPointerCapture(ev.pointerId);
    }
  });
  svg.addEventListener("pointermove", (ev) => {
    if (pan) {
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
    if (pan) { pan = null; suppressClick = true; setTimeout(() => { suppressClick = false; }, 0); return; }
    onDragEnd(ev);
  });
  svg.addEventListener("pointercancel", (ev) => {
    if (pan) { pan = null; return; }
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
    if (ev.key === "Enter" && state.draftNodes.length) {
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
  if (state.tool === "draw" && state.draftNodes.length) {
    lastDrawMouse = [mx, my]; // remembered aim for typed-length commits
    renderRubberBand(mx, my, ev.altKey);
  }
  // live cursor readout when hovering a run
  let cursor = null;
  if (state.project) {
    for (const run of state.project.topology.runs) {
      const hit = stationAtPoint(run, mx, my);
      if (hit.dist <= HOVER_RUN_MM) {
        cursor = { station_mm: hit.station, x_mm: Math.round(mx), y_mm: Math.round(my) };
        break;
      }
    }
  }
  updateStatus(cursor);
}

// ---------- select tool: drag / insert / delete ----------
function onDragMove(ev) {
  const [mx, my] = svgCoords(ev);
  if (!drag.started) {
    if (Math.hypot(ev.clientX - drag.start[0], ev.clientY - drag.start[1]) < 4) return;
    // gesture begins: snapshot BEFORE any mutation
    pushSnapshot(drag.kind === "ghost" ? "insert-vertex" : "move-dot");
    if (drag.kind === "ghost") {
      const run = runById(drag.runId);
      run.interior_vertices.splice(drag.seg, 0, [mx, my]);
      drag.dotIndex = drag.seg + 1;
      drag.kind = "dot";
    }
    drag.started = true;
  }
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
  // swallow the click that may follow this pointer gesture; a drag fires no
  // click at all, so clear the flag on the next tick either way
  suppressClick = true;
  setTimeout(() => { suppressClick = false; }, 0);
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

// ---------- gate kit catalog (fetched once, cached like tabs.js does) ----------
let catalogPromise = null;
function loadCatalogProducts() {
  catalogPromise ??= apiGet("/api/catalog")
    .then((c) => c.products || {})
    .catch(() => { catalogPromise = null; return {}; }); // retry on next open
  return catalogPromise;
}

function gateKitProducts(products) {
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
    if ((p.attrs || {}).category === "gate") return true;
    if (/GATE/i.test(p.sku)) return true;
    if (p.consumption?.kind === "assembly_kit") {
      const names = [p.name || "", ...Object.values(p.name_i18n || {})];
      return names.some((n) => /gate/i.test(n));
    }
    return false;
  });
}

// width encoded in the product (e.g. GATE-KIT-1000, BAR-GATE-1168) — sku first
function widthFromProduct(p) {
  const m = /\b(\d{3,4})\b/.exec(p.sku || "") || /\b(\d{3,4})\b/.exec(p.name || "");
  return m ? +m[1] : null;
}

async function openEventPopover(tool, runId, station, clientX, clientY) {
  closePopover();
  const run = runById(runId);
  if (!run) return;
  const L = runLength(run);
  // gate: kit choices come from the catalog; empty catalog falls back to free text
  let gateKits = [], defaultKit = null;
  if (tool === "gate") {
    gateKits = gateKitProducts(await loadCatalogProducts());
    defaultKit = gateKits.find((p) => p.sku === "GATE-KIT-1000") || gateKits[0] || null;
  }
  // length fields carry mm in, display units out (units.js is the only converter)
  const numField = (key, id, valueMm) =>
    `<label>${tu(key)}<input id="${id}" type="number" step="${inputStep()}"
      value="${toDisplayValue(valueMm)}"></label>`;
  const fieldMm = (id) => toMm(document.getElementById(id).value);
  // base applies to the whole section: no station in the header, no range fields
  let html = `<h4>${t("tool." + tool)}</h4>
    <div class="meta"><bdi>${esc(runId)}</bdi>${tool === "base" ? ""
      : ` · ${t("popover.station")} <span class="num">${esc(fmtLen(station))}</span>`}</div>`;
  if (tool === "gate") {
    html += numField("popover.width", "pop-width",
      (defaultKit && widthFromProduct(defaultKit)) || 1000);
    if (gateKits.length) {
      // options cannot hold nested markup: dir="auto" + an LRM before the price
      // keep the €-figure readable in RTL (in lieu of a .num span)
      html += `<label>${t("popover.kit")}<select id="pop-kit">` + gateKits.map((p) =>
        `<option value="${esc(p.sku)}" dir="auto"${p === defaultKit ? " selected" : ""}>`
        + `${esc(p.name_i18n?.[currentLocale()] || p.name)}`
        + ` — ‎€${(p.price_cents / 100).toFixed(2)}</option>`).join("")
        + `</select></label>`;
    } else {
      html += `<label>${t("popover.kit")}<input id="pop-kit" value="GATE-KIT-1000"></label>`;
    }
  } else if (tool === "base") {
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
    html += numField("popover.z", "pop-z", 0);
  } else if (tool === "height") {
    html += numField("popover.start", "pop-start", station);
    html += numField("popover.end", "pop-end", L);
    html += numField("popover.height", "pop-height", 1800);
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
    const needed = { gate: ["pop-width"], ground: ["pop-z"],
      height: ["pop-height", "pop-start", "pop-end"] }[tool] || [];
    const values = {};
    let bad = null;
    for (const id of needed) {
      const field = document.getElementById(id);
      values[id] = fieldMm(id);
      field.classList.toggle("invalid", values[id] === null);
      if (values[id] === null && !bad) bad = field;
    }
    if (bad) { bad.focus(); return; }
    pushSnapshot(tool);
    if (tool === "gate") {
      addPointEvent(runId, {
        kind: "gate",
        width_mm: values["pop-width"],
        kit_sku: document.getElementById("pop-kit").value.trim() || null,
      }, station);
    } else if (tool === "base") {
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
      addPointEvent(runId, {
        kind: "elevation_sample", z_mm: values["pop-z"],
      }, station);
    } else if (tool === "height") {
      addIntervalEvent(runId, {
        kind: "height_intent", height_mm: values["pop-height"], source: "user",
      }, values["pop-start"], values["pop-end"]);
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
  // kit choice drives the width field when the product encodes one
  const kitSel = popover.querySelector("select#pop-kit");
  if (kitSel) kitSel.addEventListener("change", () => {
    const p = gateKits.find((g) => g.sku === kitSel.value);
    const w = p && widthFromProduct(p);   // product widths are mm, like the catalog
    if (w) popover.querySelector("#pop-width").value = toDisplayValue(w);
  });
  const first = popover.querySelector("input, select, button");
  if (first) first.focus();
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

// An explicit trailing unit always wins: "250cm" -> 2500, "1.2m"/"1.2מ" -> 1200,
// "80mm" -> 80. A bare number is read in the ACTIVE display unit — "4200" is
// 4200 mm in mm mode, "420" is 4200 mm in cm mode — except in mm mode, where a
// value under 100 is metres ("4" -> 4000).
function parseLengthMm(buf) {
  const m = /^(\d+(?:\.\d+)?|\.\d+)(mm|cm|m|מ)?$/.exec(buf);
  if (!m) return null;
  const v = parseFloat(m[1]);
  if (!(v > 0)) return null;
  const mm = m[2] === "mm" ? v : m[2] === "cm" ? v * 10 : m[2] ? v * 1000
    // the "small bare number = metres" shortcut only makes sense in mm mode:
    // in cm a value under 100 is the COMMON case (anything under a metre), so a
    // bare number is always centimetres there
    : currentUnit() === "mm" && v < 100 ? v * 1000 : toMm(v);
  return Math.round(mm);
}

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
  const mm = parseLengthMm(lengthBuffer);
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
  const mm = parseLengthMm(lengthBuffer);
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

// ---------- draw tool ----------
function cancelDraft() {
  state.draftNodes = [];
  lastDrawMouse = null;
  chipAnchorView = null;
  clearLengthBuffer();
  clearGroup("g-draft");
  clearGroup("g-snap");
  updateDraftButtons();
  renderCta();
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
  renderCta(); // a draft dot hides the empty-canvas CTA
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
  renderCta();          // keep the CTA centered in the new view
  positionLengthChip(); // and the typed-length chip glued to its anchor
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

// ---------- empty-canvas CTA (g-cta; disappears once a run or draft dot exists) --
function renderCta() {
  const g = document.getElementById("g-cta");
  if (!g) return;
  while (g.firstChild) g.removeChild(g.firstChild);
  if (!state.project) return;
  if (state.project.topology.runs.length || state.draftNodes.length) return;
  const scale = viewBox.w / 900;
  const cx = viewBox.x + viewBox.w / 2, cy = viewBox.y + viewBox.h / 2;
  el("text", { x: cx, y: cy, "text-anchor": "middle", "font-size": 22 * scale,
    fill: "#94a3b8" }, g).textContent = t("editor.empty_cta");
  // subtle arrow from the message toward the Draw tool button — computed from the
  // button's actual screen position, so it points correctly in LTR and RTL while
  // the canvas itself stays unmirrored
  const btn = document.getElementById("tool-draw");
  const svg = document.getElementById("canvas");
  const ctm = svg.getScreenCTM();
  if (!btn || !ctm) return;
  const r = btn.getBoundingClientRect();
  const pt = svg.createSVGPoint();
  pt.x = r.left + r.width / 2; pt.y = r.top + r.height / 2;
  const q = pt.matrixTransform(ctm.inverse());
  const start = [cx, cy - 40 * scale];
  let dx = q.x - start[0], dy = q.y - start[1];
  const h = Math.hypot(dx, dy) || 1;
  dx /= h; dy /= h;
  const len = Math.min(h * 0.55, viewBox.w * 0.3);
  const end = [start[0] + dx * len, start[1] + dy * len];
  el("line", { x1: start[0], y1: start[1], x2: end[0], y2: end[1],
    stroke: "#cbd5e1", "stroke-width": 2 * scale,
    "stroke-dasharray": `${6 * scale} ${5 * scale}` }, g);
  const a = 9 * scale;
  el("polygon", { fill: "#cbd5e1", points: [
    [end[0] + dx * a, end[1] + dy * a],
    [end[0] - dy * a * 0.5, end[1] + dx * a * 0.5],
    [end[0] + dy * a * 0.5, end[1] - dx * a * 0.5],
  ].map((p) => p.join(",")).join(" ") }, g);
}

function renderTopology() {
  const g = clearGroup("g-topology");
  renderGrid();
  renderCta();
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
      if (pe.payload.kind === "gate") {
        const pEnd = toPx(pointAtStation(run.id, evStation + pe.payload.width_mm));
        el("line", { x1: p[0], y1: p[1], x2: pEnd[0], y2: pEnd[1], stroke: "#fff",
          "stroke-width": 5 }, g);
        el("line", { x1: p[0], y1: p[1], x2: pEnd[0], y2: pEnd[1], stroke: "#0891b2",
          "stroke-width": 3, "stroke-dasharray": "5 4" }, g);
        el("text", { x: (p[0] + pEnd[0]) / 2 - 10, y: p[1] - 10, "font-size": 10,
          fill: "#0891b2" }, g).textContent = t("canvas.gate");
      } else if (pe.payload.kind === "elevation_sample") {
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

// Dots of the selected run: squares (vertex handles) + midpoint ghosts (circles).
function renderHandles() {
  const g = clearGroup("g-handles");
  if (state.tool !== "select" || !state.project || !state.selection.runId) return;
  const run = runById(state.selection.runId);
  if (!run) return;
  const pts = runPoints(run);
  for (let i = 0; i + 1 < pts.length; i++) {
    const m = toPx([(pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2]);
    el("circle", { cx: m[0], cy: m[1], r: 5, class: "ghost",
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
  if (!state.result || !document.getElementById("chk-overlay").checked) return;
  const s = state.result.strategy;
  for (const span of s.spans) {
    const p0 = toPx(pointAtStation(span.run_ref, span.start_station_mm));
    const p1 = toPx(pointAtStation(span.run_ref, span.end_station_mm));
    if (!p0 || !p1) continue;
    const color = span.vertical === "stepped" ? "#7c3aed"
      : span.vertical === "raked" ? "#059669" : "#93c5fd";
    const line = el("line", { x1: p0[0], y1: p0[1] - 8, x2: p1[0], y2: p1[1] - 8,
      stroke: color, "stroke-width": 6, opacity: 0.75, cursor: "pointer" }, g);
    line.addEventListener("click", () =>
      inspect(span.id, "inspect.span",
        { width_mm: span.width_mm, height_mm: span.height_mm, mode: span.vertical }));
  }
  for (const gate of s.gates) {
    const p0 = toPx(pointAtStation(gate.run_ref, gate.start_station_mm));
    const p1 = toPx(pointAtStation(gate.run_ref, gate.end_station_mm));
    if (!p0 || !p1) continue;
    const line = el("line", { x1: p0[0], y1: p0[1] - 8, x2: p1[0], y2: p1[1] - 8,
      stroke: "#0891b2", "stroke-width": 6, "stroke-dasharray": "4 4", cursor: "pointer" }, g);
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
    const c = el("circle", { cx: p[0], cy: p[1], r: post.reinforced ? 8 : 6,
      fill: POST_COLORS[post.kind] || "#2563eb",
      stroke: post.pinned ? "#f59e0b" : post.mounting === "masonry" ? "#dc2626" : "#fff",
      "stroke-width": post.pinned ? 3 : 2, cursor: "pointer" }, g);
    el("title", {}, c).textContent =
      `${post.id}\n${post.sku} (${enumWord(post.kind)}, ${enumWord(post.mounting)})`;
    c.addEventListener("click", () =>
      inspect(post.id, "inspect.post", { sku: post.sku, station_mm: post.station_mm }));
  }
}

// Localize a warning/critique by code: t("<prefix>.<code>", params) with each param
// bidi-isolated (<bdi>); falls back to the server's English text when no key exists.
// Backend params are mm — unitParams converts every `*_mm` and supplies {u}.
function localizedByCode(prefix, code, params, fallback) {
  const key = `${prefix}.${code}`;
  const template = t(key);  // no params: placeholders stay intact for wrapped interpolation
  if (template === key) return esc(fallback ?? code);
  let s = esc(template);
  for (const [k, v] of Object.entries(unitParams(params || {})))
    s = s.replaceAll(`{${k}}`, `<bdi>${esc(String(v))}</bdi>`);
  return s;
}

function renderWarnings() {
  const div = document.getElementById("warnings");
  div.innerHTML = "";
  if (!state.result) return;
  for (const w of state.result.strategy.warnings) {
    const d = document.createElement("div");
    d.className = `warning ${w.severity}`;
    d.innerHTML = `⚠ [<span class="sku">${esc(w.code)}</span>] ${localizedByCode("warning", w.code, w.params, w.message)}`;
    div.appendChild(d);
  }
  for (const c of state.critique || []) {
    const d = document.createElement("div");
    d.className = "warning";
    d.innerHTML = `🤖 ${t("warning.critic_prefix")}: ${localizedByCode("critique", c.code, c.params, c.text)}`;
    div.appendChild(d);
  }
}
