// Plan-canvas editor: rendering + tools. Task 1 carries over V1 behavior
// (draw + clear + overlay); Tasks 6-8 add select/drag/snapping/popovers.

import { esc } from "./api.js";
import {
  clearGroup, el, pointAtStation, runLength, runPoints, toMm, toPx,
} from "./geom.js";
import { pushSnapshot } from "./history.js";
import { t } from "./i18n.js";
import { inspect } from "./inspector.js";
import {
  emit, generateStrategy, on, saveTopology, setTool, state,
} from "./state.js";

const BASE_COLORS = { soil: "#a16207", concrete: "#64748b", masonry_wall: "#dc2626" };
const POST_COLORS = { line: "#2563eb", end: "#1e293b", corner: "#1e293b",
  junction: "#1e293b", gate: "#0891b2", transition: "#dc2626" };

export function initEditor() {
  setupCanvas();
  setupToolbar();
  renderGrid();
  on("project-loaded", renderAllCanvas);
  on("result-changed", () => { renderOverlay(); renderWarnings(); });
  on("tool-changed", updateToolButtons);
  on("locale-changed", () => { renderAllCanvas(); updateStatus(); });
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

function updateStatus() {
  const bar = document.getElementById("statusbar");
  if (bar) bar.textContent = t(`hint.${state.tool}`);
}

async function clearTopology() {
  if (!confirm(t("confirm.clear_topology"))) return;
  pushSnapshot("clear");
  state.draftNodes = [];
  clearGroup("g-draft");
  state.project.topology = {
    revision: state.project.topology.revision, nodes: [], runs: [],
  };
  await saveTopology();
}

// ---------- draw tool (V1 behavior; Task 7 upgrades) ----------
function setupCanvas() {
  const svg = document.getElementById("canvas");
  svg.addEventListener("click", (ev) => {
    if (state.tool !== "draw" || !state.project) return;
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const { x, y } = pt.matrixTransform(svg.getScreenCTM().inverse());
    state.draftNodes.push(toMm(x, y));
    renderDraft();
  });
  svg.addEventListener("dblclick", (ev) => { ev.preventDefault(); finishDraft(); });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") cancelDraft();
    if (ev.key === "Enter" && state.draftNodes.length) finishDraft();
  });
  document.getElementById("btn-finish-draft").addEventListener("click", finishDraft);
  document.getElementById("btn-cancel-draft").addEventListener("click", cancelDraft);
}

function cancelDraft() {
  state.draftNodes = [];
  clearGroup("g-draft");
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
    const pts = runPoints(run).map(toPx);
    el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none",
      stroke: "#334155", "stroke-width": 3 }, g);
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
    const mid = toPx(pointAtStation(run.id, runLength(run) / 2));
    el("text", { x: mid[0] - 12, y: mid[1] - 8, "font-size": 10, fill: "#334155",
      class: "run-label", "data-run": run.id }, g)
      .textContent = `${run.id} (${runLength(run)} mm)`;
  }
  for (const n of topo.nodes) {
    const p = toPx([n.x_mm, n.y_mm]);
    el("rect", { x: p[0] - 4, y: p[1] - 4, width: 8, height: 8, fill: "#334155" }, g);
  }
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
