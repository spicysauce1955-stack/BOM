// Fence AI — pragmatic V1 frontend (ADR-0010).
// Thin view over server JSON: no domain logic lives here. The only geometry the
// client does is mm->px projection for rendering straight runs.

const SCALE = 0.045;           // px per mm
const OX = 60, OY = 260;       // world origin in canvas px
const SNAP_MM = 100;           // drawing snap

const $ = (id) => document.getElementById(id);
// verbatim user/expert text must never be interpreted as HTML (script-injection
// surface: annotations, correction comments, knowledge source_text)
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const api = {
  async get(url) { const r = await fetch(url); if (!r.ok) throw new Error(await r.text()); return r.json(); },
  async send(method, url, body) {
    const r = await fetch(url, {
      method, headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) { const t = await r.text(); alert(`${method} ${url} failed:\n${t}`); throw new Error(t); }
    return r.json();
  },
};

const state = {
  projectId: null,
  project: null,
  result: null,       // last GenerationResult
  critique: [],
  drawing: false,
  draftNodes: [],     // [{x_mm,y_mm}] while drawing
  nodeSeq: 1,
  runSeq: 1,
  evSeq: 1,
};

// ---------- projection ----------
const toPx = (p) => [OX + p[0] * SCALE, OY - p[1] * SCALE];
const toMm = (x, y) => [
  Math.round((x - OX) / SCALE / SNAP_MM) * SNAP_MM,
  Math.round((OY - y) / SCALE / SNAP_MM) * SNAP_MM,
];

function runEndpoints(run) {
  const n = (id) => state.project.topology.nodes.find((nd) => nd.id === id);
  const a = n(run.start_node_id), b = n(run.end_node_id);
  return [[a.x_mm, a.y_mm], [b.x_mm, b.y_mm]];
}
function runLength(run) {
  const [a, b] = runEndpoints(run);
  return Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]));
}
function pointAtStation(runId, station) {
  const run = state.project.topology.runs.find((r) => r.id === runId);
  if (!run) return null;
  const [a, b] = runEndpoints(run);
  const L = runLength(run);
  const t = L ? Math.min(Math.max(station / L, 0), 1) : 0;
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

// ---------- svg helpers ----------
function el(tag, attrs, parent) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function clear(id) { const g = $(id); while (g.firstChild) g.removeChild(g.firstChild); return g; }

// ---------- projects ----------
async function loadProjects() {
  const list = await api.get("/api/projects");
  const sel = $("project-select");
  sel.innerHTML = "";
  for (const p of list) {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = p.name;
    sel.appendChild(o);
  }
  if (list.length && !state.projectId) state.projectId = list[0].id;
  if (state.projectId) sel.value = state.projectId;
}

async function openProject(id) {
  state.projectId = id;
  state.project = await api.get(`/api/projects/${id}`);
  state.result = null;
  state.critique = [];
  // never re-mint ids that already exist in the loaded project
  const maxSuffix = (items, prefix) => items.reduce((m, it) => {
    const match = it.id.match(new RegExp(`^${prefix}(\\d+)$`));
    return match ? Math.max(m, +match[1]) : m;
  }, 0);
  state.nodeSeq = maxSuffix(state.project.topology.nodes, "n") + 1;
  state.runSeq = maxSuffix(state.project.topology.runs, "run") + 1;
  // resume the latest persisted generation run, if any
  try {
    const runs = await api.get(`/api/projects/${id}/runs`);
    if (runs.length) state.result = await api.get(`/api/runs/${runs[runs.length - 1].id}`);
  } catch { /* no runs yet */ }
  renderAll();
}

// ---------- topology editing ----------
function anchorFor(runId, station) {
  // straight single-segment runs in the UI: segment 0, offset = station
  const run = state.project.topology.runs.find((r) => r.id === runId);
  const L = runLength(run);
  return { segment_index: 0, offset_mm: Math.min(station, L), seg_len_at_authoring_mm: L };
}

async function saveTopology() {
  state.project = await api.send(
    "PUT", `/api/projects/${state.projectId}/topology`, state.project.topology
  );
  state.result = null;
  renderAll();
}

function finishDraft() {
  if (state.draftNodes.length >= 2) {
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
  state.draftNodes = [];
  clear("g-draft");
}

function setupCanvas() {
  const svg = $("canvas");
  svg.addEventListener("click", (ev) => {
    if (!state.drawing || !state.project) return;
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const { x, y } = pt.matrixTransform(svg.getScreenCTM().inverse());
    state.draftNodes.push(toMm(x, y));
    renderDraft();
  });
  svg.addEventListener("dblclick", (ev) => { ev.preventDefault(); finishDraft(); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") finishDraft(); });
}

function renderDraft() {
  const g = clear("g-draft");
  const pts = state.draftNodes.map(toPx);
  if (pts.length > 1)
    el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none",
      stroke: "#94a3b8", "stroke-dasharray": "6 4", "stroke-width": 2 }, g);
  for (const p of pts)
    el("circle", { cx: p[0], cy: p[1], r: 4, fill: "#94a3b8" }, g);
}

// ---------- rendering ----------
function renderGrid() {
  const g = clear("g-grid");
  for (let x = 0; x < 900; x += 50 * 0.045 * 20)  // 1 m grid
    el("line", { x1: x, y1: 0, x2: x, y2: 500, stroke: "#eef2f6" }, g);
  for (let y = 0; y < 500; y += 50 * 0.045 * 20)
    el("line", { x1: 0, y1: y, x2: 900, y2: y, stroke: "#eef2f6" }, g);
  el("text", { x: 6, y: 14, "font-size": 10, fill: "#94a3b8" }, g).textContent =
    "1 grid square = 1 m";
}

const BASE_COLORS = { soil: "#a16207", concrete: "#64748b", masonry_wall: "#dc2626" };

function renderTopology() {
  const g = clear("g-topology");
  if (!state.project) return;
  const topo = state.project.topology;
  for (const run of topo.runs) {
    const [a, b] = runEndpoints(run).map(toPx);
    el("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "#334155", "stroke-width": 3 }, g);
    // base intervals as colored underlay
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
        el("text", { x: (p[0] + pEnd[0]) / 2 - 10, y: p[1] - 10, "font-size": 10, fill: "#0891b2" }, g)
          .textContent = "gate";
      } else if (pe.payload.kind === "elevation_sample") {
        el("text", { x: p[0] - 8, y: p[1] + 20, "font-size": 9, fill: "#7c3aed" }, g)
          .textContent = `z=${pe.payload.z_mm}`;
      }
    }
    const mid = toPx(pointAtStation(run.id, runLength(run) / 2));
    el("text", { x: mid[0] - 12, y: mid[1] - 8, "font-size": 10, fill: "#334155" }, g)
      .textContent = `${run.id} (${runLength(run)} mm)`;
  }
  for (const n of topo.nodes) {
    const p = toPx([n.x_mm, n.y_mm]);
    el("rect", { x: p[0] - 4, y: p[1] - 4, width: 8, height: 8, fill: "#334155" }, g);
  }
}

const POST_COLORS = { line: "#2563eb", end: "#1e293b", corner: "#1e293b", junction: "#1e293b",
  gate: "#0891b2", transition: "#dc2626" };

function renderOverlay() {
  const g = clear("g-overlay");
  if (!state.result || !$("chk-overlay").checked) return;
  const s = state.result.strategy;
  for (const span of s.spans) {
    const p0 = toPx(pointAtStation(span.run_ref, span.start_station_mm));
    const p1 = toPx(pointAtStation(span.run_ref, span.end_station_mm));
    if (!p0 || !p1) continue;
    const color = span.vertical === "stepped" ? "#7c3aed" : span.vertical === "raked" ? "#059669" : "#93c5fd";
    const line = el("line", { x1: p0[0], y1: p0[1] - 8, x2: p1[0], y2: p1[1] - 8,
      stroke: color, "stroke-width": 6, opacity: 0.75, cursor: "pointer" }, g);
    line.addEventListener("click", () => inspect(span.id, `Span ${span.width_mm} mm, h=${span.height_mm}, ${span.vertical}`));
  }
  for (const gate of s.gates) {
    const p0 = toPx(pointAtStation(gate.run_ref, gate.start_station_mm));
    const p1 = toPx(pointAtStation(gate.run_ref, gate.end_station_mm));
    const line = el("line", { x1: p0[0], y1: p0[1] - 8, x2: p1[0], y2: p1[1] - 8,
      stroke: "#0891b2", "stroke-width": 6, "stroke-dasharray": "4 4", cursor: "pointer" }, g);
    line.addEventListener("click", () => inspect(gate.id, `Gate ${gate.kit_sku}`));
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
    const title = el("title", {}, c);
    title.textContent = `${post.id}\n${post.sku} (${post.kind}, ${post.mounting})`;
    c.addEventListener("click", () => inspect(post.id, `Post ${post.sku} @ ${post.station_mm}`));
  }
}

function renderWarnings() {
  const div = $("warnings");
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
    d.textContent = `🤖 critic: ${c.text}`;
    div.appendChild(d);
  }
}

function renderRunSelectors() {
  const runs = state.project ? state.project.topology.runs : [];
  for (const selId of ["run-select", "ann-target"]) {
    const sel = $(selId);
    sel.innerHTML = "";
    if (selId === "ann-target") {
      const o = document.createElement("option");
      o.value = "project"; o.textContent = "whole project";
      sel.appendChild(o);
    }
    for (const r of runs) {
      const o = document.createElement("option");
      o.value = selId === "ann-target" ? `run:${r.id}` : r.id;
      o.textContent = `${r.id} (${runLength(r)} mm)`;
      sel.appendChild(o);
    }
  }
}

function renderOverrides() {
  const div = $("override-list");
  div.innerHTML = "<h3>Overrides</h3>";
  for (const ov of state.project?.overrides || []) {
    const d = document.createElement("div");
    d.className = "card";
    const orphaned = state.result?.orphaned_overrides?.includes(ov.id);
    d.innerHTML = `${esc(ov.directive.kind)} @ ${esc(ov.directive.station_mm ?? "")} on ${esc(ov.run_id)}
      ${orphaned ? '<span class="tag rejected">orphaned</span>' : ""}
      <button data-ov="${ov.id}">remove</button>`;
    d.querySelector("button").addEventListener("click", async () => {
      await api.send("DELETE", `/api/projects/${state.projectId}/overrides/${ov.id}`);
      await openProject(state.projectId);
    });
    div.appendChild(d);
  }
}

// ---------- inspector ----------
async function inspect(elementId, label) {
  const body = $("inspector-body");
  if (!state.result) return;
  body.innerHTML = `<strong>${label}</strong><div class="meta">${elementId}</div>`;
  try {
    const exp = await api.get(`/api/runs/${state.result.run.id}/explain/${encodeURIComponent(elementId)}`);
    for (const line of exp.explanation) {
      const d = document.createElement("div");
      d.className = line.startsWith("  ←") ? "expl sub" : "expl";
      d.textContent = line;
      body.appendChild(d);
    }
  } catch { body.innerHTML += "<div class='expl'>no decisions reference this element</div>"; }
  const corr = document.createElement("div");
  corr.innerHTML = `<hr><em>Expert correction</em><br>
    <input id="corr-comment" placeholder="what should be different, and why?" size="34">
    <button id="btn-correct">Record correction</button>`;
  body.appendChild(corr);
  $("btn-correct").addEventListener("click", async () => {
    const comment = $("corr-comment").value.trim();
    if (!comment) return alert("describe the correction");
    await api.send("POST", `/api/projects/${state.projectId}/corrections`, {
      generation_run_id: state.result.run.id, element_ref: elementId,
      before: {}, after: {}, comment, author: "expert",
    });
    alert("Correction recorded. Use the Review tab to propose knowledge from corrections.");
  });
}

// ---------- generation ----------
async function generateStrategy() {
  if (!state.projectId) return;
  const out = await api.send("POST", `/api/projects/${state.projectId}/generate`);
  state.result = out.result;
  state.critique = out.critique;
  renderOverlay(); renderWarnings(); renderOverrides(); renderBom();
}

// ---------- BOM tab ----------
async function renderBom() {
  const div = $("bom-body");
  if (!state.result) { div.innerHTML = "<em>Generate a strategy first.</em>"; return; }
  const data = await api.get(`/api/runs/${state.result.run.id}/bom`);
  const bom = data.bom;
  let html = `<div class="panel"><h3>Purchase BOM — total €${(bom.total_cents / 100).toFixed(2)}</h3>
  <table><tr><th>SKU</th><th>Purchase</th><th>Engineering demand</th><th>Overage</th><th>Unit €</th><th>Total €</th><th>Notes</th></tr>`;
  for (const l of bom.lines) {
    html += `<tr><td>${l.sku}<br><span class="meta">${l.name}</span></td>
      <td>${l.purchase_qty} × ${l.purchase_unit}</td>
      <td>${l.engineering_qty} ${l.engineering_unit}</td>
      <td>${l.overage_qty || ""}</td>
      <td>${(l.unit_price_cents / 100).toFixed(2)}</td>
      <td>${(l.total_cents / 100).toFixed(2)}</td>
      <td>${esc((l.notes || []).join("; "))}</td></tr>`;
  }
  html += "</table></div>";
  for (const [sku, plan] of Object.entries(bom.cut_plans || {})) {
    html += `<div class="panel"><h3>Cut plan — ${sku}
      ${plan.certified_optimal ? '<span class="tag active">optimal certified</span>'
        : `<span class="tag medium">heuristic (LP bound ${plan.lp_lower_bound})</span>`}</h3>
      <table><tr><th>Bar source</th><th>Stock</th><th>Cuts</th><th>Leftover</th></tr>`;
    for (const b of plan.bars) {
      html += `<tr><td>${b.source}</td><td>${b.stock_length_mm}</td>
        <td>${b.pieces.map((p) => p.length_mm).join(" + ")}</td>
        <td>${b.leftover_mm}${b.leftover_reusable ? " ♻ reusable" : ""}</td></tr>`;
    }
    html += "</table></div>";
  }
  if ((bom.allocations || []).length) {
    html += `<div class="panel"><h3>Inventory allocations</h3><table><tr><th>Item</th><th>SKU</th><th>Used</th></tr>`;
    for (const a of bom.allocations)
      html += `<tr><td>${a.inventory_item_id}</td><td>${a.sku}</td><td>${a.length_used_mm ? a.length_used_mm + " mm" : a.qty}</td></tr>`;
    html += "</table></div>";
  }
  div.innerHTML = html;
}

// ---------- annotations tab ----------
async function renderAnnotations() {
  const div = $("annotation-list");
  div.innerHTML = "";
  for (const ann of state.project?.annotations || []) {
    const card = document.createElement("div");
    card.className = "card";
    let html = `<div class="meta">${esc(ann.id)} · on ${esc(ann.target_ref)} · by ${esc(ann.author)}</div>
      <div class="verbatim">“${esc(ann.text)}”</div>
      <button data-act="interpret">Interpret with AI</button>`;
    for (const rec of ann.interpretations) {
      html += `<div class="meta">interpretation by ${esc(rec.interpreter)}</div>`;
      for (const c of rec.candidates) {
        html += `<div>→ <b>${esc(c.kind)}</b> ${esc(JSON.stringify(c.params))}
          <span class="tag ${c.confidence}">${c.confidence}</span>
          <span class="tag ${c.status}">${c.status}</span>`;
        if (c.status === "proposed")
          html += ` <button data-confirm="${c.id}" data-ann="${ann.id}">Confirm</button>
                    <button data-rejint="${c.id}">✕</button>`;
        html += "</div>";
        if (c.ambiguity_note) html += `<div class="meta">⚠ ${esc(c.ambiguity_note)}</div>`;
      }
      for (const u of rec.unparsed_spans)
        html += `<div class="meta">unparsed: “${esc(u)}”</div>`;
    }
    card.innerHTML = html;
    card.querySelector('[data-act="interpret"]').addEventListener("click", async () => {
      await api.send("POST", `/api/projects/${state.projectId}/annotations/${ann.id}/interpret`);
      await openProject(state.projectId);
    });
    card.querySelectorAll("[data-confirm]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        let runId = ann.target_ref.startsWith("run:") ? ann.target_ref.slice(4) : null;
        if (!runId) {
          const options = state.project.topology.runs.map((r) => r.id).join(", ");
          runId = prompt(`Apply to which run? (${options})`, state.project.topology.runs[0]?.id);
          if (!runId) return;
        }
        await api.send("POST", `/api/projects/${state.projectId}/intents/${btn.dataset.confirm}/confirm`,
          { annotation_id: btn.dataset.ann, run_id: runId });
        await openProject(state.projectId);
      }));
    div.appendChild(card);
  }
}

// ---------- knowledge tab ----------
async function renderKnowledge() {
  const versions = await api.get("/api/knowledge");
  const div = $("knowledge-list");
  div.innerHTML = "";
  for (const v of versions) {
    const card = document.createElement("div");
    card.className = "card";
    let html = `<span class="tag ${v.type}">${v.type}</span>
      <span class="tag ${v.status}">${v.status}</span>
      <b>${esc(v.object_id)}@v${v.version}</b> — ${esc(v.title)}
      <div class="meta">scope ${esc(JSON.stringify(v.scope))} · by ${esc(v.attributed_to)}
        ${v.derived_from?.length ? "· derived from " + esc(v.derived_from.join(", ")) : ""}</div>`;
    if (v.source_text) html += `<div class="verbatim">“${esc(v.source_text)}”</div>`;
    html += `<div class="meta">actions: ${esc(JSON.stringify(v.actions))}</div>`;
    if (v.status === "active")
      html += `<button data-retire="1">Retire</button>`;
    card.innerHTML = html;
    card.querySelector("[data-retire]")?.addEventListener("click", async () => {
      await api.send("POST", `/api/knowledge/${v.object_id}/${v.version}/retire`);
      renderKnowledge();
    });
    div.appendChild(card);
  }
}

// ---------- review tab ----------
async function renderCandidates() {
  const candidates = await api.get("/api/candidates");
  const div = $("candidate-list");
  div.innerHTML = candidates.length ? "" : "<em>No candidates awaiting review.</em>";
  for (const c of candidates) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<span class="tag candidate">candidate</span>
      <b>${esc(c.object_id)}@v${c.version}</b> — ${esc(c.title)}
      <div class="meta">proposed scope ${esc(JSON.stringify(c.scope))} ·
        derived from ${esc(c.derived_from.join(", "))}</div>
      ${c.source_text ? `<div class="verbatim">“${esc(c.source_text)}”</div>` : ""}
      <div class="meta">actions: ${esc(JSON.stringify(c.actions))}</div>
      <button data-a="approve">Approve</button>
      <button data-a="scope_restrict">Approve narrower…</button>
      <button data-a="reject">Reject…</button>`;
    card.querySelectorAll("button").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const action = btn.dataset.a;
        const body = { action, reviewer: "expert-admin" };
        if (action === "reject") {
          body.reason = prompt("Why reject?") || "no reason given";
        } else if (action === "scope_restrict") {
          const extra = prompt('Additional scope dimension as key=value (e.g. series=X):');
          if (!extra || !extra.includes("=")) return;
          const [k, val] = extra.split("=");
          body.edited_scope = { ...c.scope, [k.trim()]: val.trim() };
        }
        await api.send("POST", `/api/candidates/${c.object_id}/${c.version}/review`, body);
        renderCandidates(); renderKnowledge();
      }));
    div.appendChild(card);
  }
}

// ---------- inventory tab ----------
async function renderInventory() {
  if (!state.projectId) return;
  const inv = await api.get(`/api/projects/${state.projectId}/inventory`);
  $("inventory-json").value = JSON.stringify(inv, null, 2);
}

// ---------- event helpers ----------
function currentRun() {
  const id = $("run-select").value;
  return state.project.topology.runs.find((r) => r.id === id);
}
function addPointEvent(payload, station) {
  const run = currentRun();
  if (!run) return alert("draw a run first");
  run.point_events.push({ id: `ev${Date.now()}_${state.evSeq++}`, anchor: anchorFor(run.id, station), payload });
  saveTopology();
}
function addIntervalEvent(payload, start, end) {
  const run = currentRun();
  if (!run) return alert("draw a run first");
  run.interval_events.push({
    id: `ev${Date.now()}_${state.evSeq++}`,
    start_anchor: anchorFor(run.id, start), end_anchor: anchorFor(run.id, end), payload,
  });
  saveTopology();
}

// ---------- wiring ----------
function renderAll() {
  renderGrid(); renderTopology(); renderOverlay(); renderWarnings();
  renderRunSelectors(); renderOverrides(); renderAnnotations(); renderInventory();
  if ($("tab-bom").classList.contains("active")) renderBom();
}

function setupUi() {
  document.querySelectorAll("#tabs button").forEach((btn) =>
    btn.addEventListener("click", () => {
      document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      $(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "knowledge") renderKnowledge();
      if (btn.dataset.tab === "review") renderCandidates();
      if (btn.dataset.tab === "bom") renderBom();
    }));

  $("btn-new-project").addEventListener("click", async () => {
    const name = $("new-project-name").value.trim() || "untitled";
    const p = await api.send("POST", "/api/projects", { name });
    await loadProjects();
    await openProject(p.id);
  });
  $("project-select").addEventListener("change", (e) => openProject(e.target.value));

  $("btn-draw").addEventListener("click", () => {
    state.drawing = !state.drawing;
    $("btn-draw").classList.toggle("active", state.drawing);
  });
  state.drawing = true;
  $("btn-clear-topo").addEventListener("click", async () => {
    if (!confirm("Clear all topology for this project?")) return;
    state.project.topology = { revision: state.project.topology.revision, nodes: [], runs: [] };
    await saveTopology();
  });
  $("btn-generate").addEventListener("click", generateStrategy);
  $("chk-overlay").addEventListener("change", renderOverlay);

  $("btn-add-gate").addEventListener("click", () =>
    addPointEvent({ kind: "gate", width_mm: +$("gate-width").value, kit_sku: $("gate-kit").value || null },
      +$("gate-station").value));
  $("btn-add-base").addEventListener("click", () =>
    addIntervalEvent({ kind: "base", surface: $("base-surface").value },
      +$("base-start").value, +$("base-end").value));
  $("btn-add-elev").addEventListener("click", () =>
    addPointEvent({ kind: "elevation_sample", z_mm: +$("elev-z").value }, +$("elev-station").value));
  $("btn-add-height").addEventListener("click", () =>
    addIntervalEvent({ kind: "height_intent", height_mm: +$("height-mm").value, source: "user" },
      +$("height-start").value, +$("height-end").value));
  $("btn-pin-post").addEventListener("click", async () => {
    const run = currentRun();
    if (!run) return alert("draw a run first");
    await api.send("POST", `/api/projects/${state.projectId}/overrides`, {
      id: "", run_id: run.id,
      directive: { kind: "pin_post", station_mm: +$("pin-station").value },
    });
    await openProject(state.projectId);
  });

  $("btn-add-ann").addEventListener("click", async () => {
    const text = $("ann-text").value.trim();
    if (!text) return;
    await api.send("POST", `/api/projects/${state.projectId}/annotations`,
      { target_ref: $("ann-target").value, text });
    $("ann-text").value = "";
    await openProject(state.projectId);
  });

  $("btn-add-knowledge").addEventListener("click", async () => {
    let actions;
    try { actions = JSON.parse($("k-actions").value); }
    catch { return alert("actions must be valid JSON"); }
    await api.send("POST", "/api/knowledge", {
      object_id: $("k-object").value.trim(), type: $("k-type").value,
      title: $("k-title").value, actions, author: "expert-admin",
    });
    renderKnowledge();
  });

  $("btn-propose").addEventListener("click", async () => {
    const out = await api.send("POST", `/api/projects/${state.projectId}/propose-knowledge`);
    alert(out.length ? `${out.length} candidate(s) proposed` : "no new candidates from current corrections");
    renderCandidates();
  });

  $("btn-save-inventory").addEventListener("click", async () => {
    let inv;
    try { inv = JSON.parse($("inventory-json").value); }
    catch { return alert("inventory must be valid JSON"); }
    await api.send("PUT", `/api/projects/${state.projectId}/inventory`, inv);
    alert("inventory saved");
  });
}

async function main() {
  setupUi();
  setupCanvas();
  renderGrid();
  const health = await api.get("/api/health");
  $("ai-badge").textContent = `AI: ${health.interpreter}`;
  await loadProjects();
  if (!state.projectId) {
    const p = await api.send("POST", "/api/projects", { name: "demo project" });
    await loadProjects();
    state.projectId = p.id;
  }
  await openProject(state.projectId);
}

main();
