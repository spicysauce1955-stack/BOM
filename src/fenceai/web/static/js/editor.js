// Plan-canvas editor: rendering + tools. Select (handles/ghosts/drag/delete),
// Draw (snapped dots, rubber band, typed lengths) — plan Tasks 6-8.
// The canvas is never mirrored in RTL (spec §4).

import {
  clearGroup, el, nodeById, pointAtStation, runById, runLength, runPoints,
  snapPoint, stationAtPoint, toMmRaw, toPx,
} from "./geom.js";
import { pushSnapshot, redo, undo } from "./history.js";
import { t } from "./i18n.js";
import { inspect } from "./inspector.js";
import {
  generateStrategy, on, saveTopology, setSelection, setTool, state,
} from "./state.js";

const BASE_COLORS = { soil: "#a16207", concrete: "#64748b", masonry_wall: "#dc2626" };
const POST_COLORS = { line: "#2563eb", end: "#1e293b", corner: "#1e293b",
  junction: "#1e293b", gate: "#0891b2", transition: "#dc2626" };
const HOVER_RUN_MM = 400; // cursor-readout proximity

export function initEditor() {
  setupCanvas();
  setupToolbar();
  renderGrid();
  on("project-loaded", () => { renderAllCanvas(); renderHandles(); });
  on("result-changed", () => { renderOverlay(); renderWarnings(); });
  on("tool-changed", () => { updateToolButtons(); renderHandles(); updateStatus(); });
  on("selection-changed", () => { renderTopology(); renderHandles(); });
  on("locale-changed", () => { renderAllCanvas(); renderHandles(); updateStatus(); });
  updateStatus();
}

function renderAllCanvas() {
  renderTopology();
  renderOverlay();
  renderWarnings();
}

// ---------- toolbar ----------
const TOOLS = ["select", "draw", "gate", "base", "ground", "pin"];

function setupToolbar() {
  for (const tool of TOOLS) {
    const btn = document.getElementById(`tool-${tool}`);
    if (btn) btn.addEventListener("click", () => { setTool(tool); updateStatus(); });
  }
  document.getElementById("btn-generate").addEventListener("click", generateStrategy);
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
  let text = t(`hint.${state.tool}`);
  if (cursor) text += ` · ${t("hint.cursor", cursor)}`;
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

  svg.addEventListener("click", (ev) => {
    if (suppressClick) { suppressClick = false; return; }
    if (!state.project) return;
    if (state.tool === "draw") {
      const [mx, my] = svgCoords(ev);
      const anchor = state.draftNodes.length
        ? state.draftNodes[state.draftNodes.length - 1] : null;
      const snap = snapPoint(mx, my, anchor, { alt: ev.altKey });
      state.draftNodes.push(snap.p);
      renderDraft();
    } else if (state.tool === "select") {
      const hit = ev.target.closest && ev.target.closest(".run-hit");
      if (hit) setSelection({ runId: hit.dataset.run });
      else if (!ev.target.closest("#g-overlay") && !ev.target.closest("#g-handles"))
        setSelection({});
    }
  });

  svg.addEventListener("dblclick", (ev) => { ev.preventDefault(); finishDraft(); });

  svg.addEventListener("pointerdown", (ev) => {
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
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", onDragEnd);
  svg.addEventListener("pointercancel", onDragEnd);

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
    if (ev.key === "Escape") cancelDraft();
    if (ev.key === "Enter" && state.draftNodes.length) finishDraft();
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
    renderRubberBand(mx, my, ev.altKey);
  }
  // live cursor readout when hovering a run
  let cursor = null;
  if (state.project) {
    for (const run of state.project.topology.runs) {
      const hit = stationAtPoint(run, mx, my);
      if (hit.dist <= HOVER_RUN_MM) {
        cursor = { station: hit.station, x: Math.round(mx), y: Math.round(my) };
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
  input.value = runLength(run);
  fo.appendChild(input);
  input.focus();
  input.select();
  let done = false;
  const close = () => { done = true; fo.remove(); };
  input.addEventListener("keydown", (ev) => {
    ev.stopPropagation();
    if (ev.key === "Enter") { const v = Math.round(+input.value); close(); commitTypedLength(runId, v); }
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
  if (typedTotal <= upTo) { alert(t("editor.invalid_length", { min: upTo })); return; }
  const d = [(B[0] - A[0]) / h, (B[1] - A[1]) / h];
  pushSnapshot("typed-length");
  const end = nodeById(run.end_node_id); // end NODE moves; shared runs follow by design
  end.x_mm = Math.round(A[0] + d[0] * (typedTotal - upTo));
  end.y_mm = Math.round(A[1] + d[1] * (typedTotal - upTo));
  saveTopology();
}

// ---------- draw tool ----------
function cancelDraft() {
  state.draftNodes = [];
  clearGroup("g-draft");
  clearGroup("g-snap");
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
    fill: "#2563eb", class: "num" }, g).textContent = t("canvas.mm", { n: len });
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
  const step = 1000 * 0.045; // 1 m in px
  for (let x = 0; x < 900; x += step)
    el("line", { x1: x, y1: 0, x2: x, y2: 500, stroke: "#eef2f6" }, g);
  for (let y = 0; y < 500; y += step)
    el("line", { x1: 0, y1: y, x2: 900, y2: y, stroke: "#eef2f6" }, g);
  el("text", { x: 6, y: 14, "font-size": 10, fill: "#94a3b8", class: "grid-note" }, g)
    .textContent = t("canvas.grid_note");
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
      const p0 = toPx(pointAtStation(run.id, iv.start_anchor.offset_mm));
      const p1 = toPx(pointAtStation(run.id, Math.min(iv.end_anchor.offset_mm, L)));
      el("line", { x1: p0[0], y1: p0[1] + 7, x2: p1[0], y2: p1[1] + 7,
        stroke: BASE_COLORS[iv.payload.surface] || "#a16207", "stroke-width": 4,
        "stroke-linecap": "round", opacity: 0.7 }, g);
    }
    for (const pe of run.point_events) {
      const p = toPx(pointAtStation(run.id, pe.anchor.offset_mm));
      if (pe.payload.kind === "gate") {
        const pEnd = toPx(pointAtStation(run.id, pe.anchor.offset_mm + pe.payload.width_mm));
        el("line", { x1: p[0], y1: p[1], x2: pEnd[0], y2: pEnd[1], stroke: "#fff",
          "stroke-width": 5 }, g);
        el("line", { x1: p[0], y1: p[1], x2: pEnd[0], y2: pEnd[1], stroke: "#0891b2",
          "stroke-width": 3, "stroke-dasharray": "5 4" }, g);
        el("text", { x: (p[0] + pEnd[0]) / 2 - 10, y: p[1] - 10, "font-size": 10,
          fill: "#0891b2" }, g).textContent = t("canvas.gate");
      } else if (pe.payload.kind === "elevation_sample") {
        el("text", { x: p[0] - 8, y: p[1] + 20, "font-size": 9, fill: "#7c3aed" }, g)
          .textContent = `z=${pe.payload.z_mm}`;
      }
    }
    // invisible fat hit line: run selection + event-tool clicks + touch targets
    el("polyline", { points: ptsAttr, fill: "none", class: "run-hit",
      "data-run": run.id }, g);
    const mid = toPx(pointAtStation(run.id, runLength(run) / 2));
    const label = el("text", { x: mid[0] - 12, y: mid[1] - 8, "font-size": 10,
      fill: selected ? "#2563eb" : "#334155", class: "run-label", "data-run": run.id }, g);
    label.textContent = `${run.id} (${runLength(run)} mm)`;
    el("title", {}, label).textContent = t("editor.length_tooltip");
    label.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openLengthInput(run.id);
    });
  }
  for (const n of topo.nodes) {
    const p = toPx([n.x_mm, n.y_mm]);
    el("rect", { x: p[0] - 4, y: p[1] - 4, width: 8, height: 8, fill: "#334155" }, g);
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
      inspect(span.id, t("inspect.span", { width: span.width_mm, height: span.height_mm, mode: span.vertical })));
  }
  for (const gate of s.gates) {
    const p0 = toPx(pointAtStation(gate.run_ref, gate.start_station_mm));
    const p1 = toPx(pointAtStation(gate.run_ref, gate.end_station_mm));
    if (!p0 || !p1) continue;
    const line = el("line", { x1: p0[0], y1: p0[1] - 8, x2: p1[0], y2: p1[1] - 8,
      stroke: "#0891b2", "stroke-width": 6, "stroke-dasharray": "4 4", cursor: "pointer" }, g);
    line.addEventListener("click", () => inspect(gate.id, t("inspect.gate", { kit: gate.kit_sku })));
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
    el("title", {}, c).textContent = `${post.id}\n${post.sku} (${post.kind}, ${post.mounting})`;
    c.addEventListener("click", () =>
      inspect(post.id, t("inspect.post", { sku: post.sku, station: post.station_mm })));
  }
}

function renderWarnings() {
  const div = document.getElementById("warnings");
  div.innerHTML = "";
  if (!state.result) return;
  for (const w of state.result.strategy.warnings) {
    const d = document.createElement("div");
    d.className = `warning ${w.severity}`;
    d.textContent = `⚠ [${w.code}] ${w.message}`;
    div.appendChild(d);
  }
  for (const c of state.critique || []) {
    const d = document.createElement("div");
    d.className = "warning";
    d.textContent = `🤖 ${t("warning.critic_prefix")}: ${c.text}`;
    div.appendChild(d);
  }
}
