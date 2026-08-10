// Side-view profile panel: the WHOLE fence unrolled end-to-end in walking
// order (one continuous ground line across connected sections). Ground is
// anchored at NODE elevations (node.z_mm) plus interior elevation_sample
// events, mirroring backend topology/station.py ground_samples(). Edits go
// gesture -> pushSnapshot -> mutate -> saveTopology. The station axis is
// NEVER mirrored in RTL (spec §3; #profile-svg is direction:ltr in CSS).

import { esc } from "./api.js";
import { clearGroup, el, nodeById, runById, runLength, runPoints, stationOfAnchor } from "./geom.js";
import { pushSnapshot } from "./history.js";
import { t } from "./i18n.js";
import { inspect } from "./inspector.js";
import { addPointEvent, on, saveTopology, setSelection, state } from "./state.js";

// viewBox geometry (preserveAspectRatio=none stretches to the container width)
const W = 900, H = 180;
const PAD = 40;              // inline start/end padding, px (viewBox units)
const BASE = H - 30;         // y of z==zMin (plan: BASE = height-30)
const TOP_PAD = 12;          // px kept clear above the tallest element
const SY_BASE = 0.01;        // px per mm of elevation at 1x exaggeration
const Z_SNAP = 10;           // mm snap for vertical edits
const DEFAULT_POST_MM = 1800;
const GAP_MM = 600;          // visual gap before a disconnected section
const TOL_MM = 1;            // NUMERIC_TOLERANCE_MM (units.py)

let exag = 5;                // 1x / 5x toggle, default 5x
let view = null;             // { chain, span, sx, sy, zMin } of the last render
let drag = null;             // active vertical-drag session

export function initProfile() {
  const panel = document.getElementById("profile");
  const toggle = document.getElementById("profile-toggle");
  const open = localStorage.getItem("fenceai.profile.open") !== "false";
  panel.classList.toggle("collapsed", !open);
  toggle.addEventListener("click", () => {
    const collapsed = panel.classList.toggle("collapsed");
    localStorage.setItem("fenceai.profile.open", String(!collapsed));
  });

  const exagBtn = document.getElementById("profile-exag");
  exagBtn.textContent = `${exag}×`;
  exagBtn.addEventListener("click", () => {
    exag = exag === 5 ? 1 : 5;
    exagBtn.textContent = `${exag}×`;
    render();
  });

  setupSvg();
  on("project-loaded", () => { closeWallPopover(); render(); });
  on("topology-changed", render);
  on("result-changed", render);
  on("selection-changed", render);
  on("locale-changed", () => { closeWallPopover(); render(); });
  render();
}

// ---------- whole-fence chain ----------
// Runs in stored order, each placed at a global offset. A run connects forward
// when its start node is the chain's current end, REVERSED when its end node
// is; otherwise (disconnected piece / branch) it starts after a small gap.
function buildChain() {
  const runs = state.project?.topology.runs || [];
  const chain = [];
  let cursor = 0;
  let endNode = null;
  for (const run of runs) {
    const L = Math.max(runLength(run), 1);
    let reversed = false;
    if (endNode !== null) {
      if (run.start_node_id === endNode) reversed = false;
      else if (run.end_node_id === endNode) reversed = true;
      else cursor += GAP_MM; // disconnected: visual gap
    }
    const entry = { run, L, offset: cursor, reversed };
    entry.samples = groundSamplesFor(run, L);
    chain.push(entry);
    cursor += L;
    endNode = reversed ? run.start_node_id : run.end_node_id;
  }
  return { chain, span: Math.max(cursor, 1) };
}

// run-local station -> global station
const gsOf = (entry, s) => entry.offset + (entry.reversed ? entry.L - s : s);

// ---------- elevation model (mirrors backend ground_samples()) ----------
// [{station, z, ev? , node?}] sorted by station: node elevations anchor the
// endpoints; interior elevation_sample events between; an explicit event
// within TOL_MM of an endpoint overrides the node value.
function groundSamplesFor(run, L) {
  const events = run.point_events
    .filter((ev) => ev.payload.kind === "elevation_sample")
    .map((ev) => ({
      ev, station: Math.min(stationOfAnchor(run, ev.anchor), L), z: ev.payload.z_mm,
    }))
    .sort((a, b) => a.station - b.station);
  const samples = [...events];
  if (!events.some((e) => e.station <= TOL_MM)) {
    const n = nodeById(run.start_node_id);
    samples.unshift({ node: n, station: 0, z: n?.z_mm ?? 0 });
  }
  if (!events.some((e) => Math.abs(e.station - L) <= TOL_MM)) {
    const n = nodeById(run.end_node_id);
    samples.push({ node: n, station: L, z: n?.z_mm ?? 0 });
  }
  return samples.sort((a, b) => a.station - b.station);
}

// piecewise-linear ground, matching backend ground_z() (endpoints always present)
function groundZAt(samples, station) {
  const last = samples[samples.length - 1];
  const s = Math.max(samples[0].station, Math.min(station, last.station));
  for (let i = 0; i + 1 < samples.length; i++) {
    const a = samples[i], b = samples[i + 1];
    if (a.station <= s && s <= b.station)
      return b.station === a.station
        ? a.z : Math.round(a.z + ((b.z - a.z) * (s - a.station)) / (b.station - a.station));
  }
  return last.z;
}

function wallProfiles(run, L) {
  return run.interval_events
    .filter((iv) => iv.payload.kind === "wall_profile")
    .map((iv) => ({
      iv,
      s0: Math.min(stationOfAnchor(run, iv.start_anchor), L),
      s1: Math.min(stationOfAnchor(run, iv.end_anchor), L),
      z0: iv.payload.top_z_start_mm, z1: iv.payload.top_z_end_mm,
    }));
}

function heightIntents(run, L) {
  return run.interval_events
    .filter((iv) => iv.payload.kind === "height_intent")
    .map((iv) => ({
      s0: Math.min(stationOfAnchor(run, iv.start_anchor), L),
      s1: Math.min(stationOfAnchor(run, iv.end_anchor), L),
      h: iv.payload.height_mm,
    }));
}

// strategy elements for one run; node posts mapped to terminal stations
function resultFor(run, L) {
  const s = state.result?.strategy;
  if (!s) return { spans: [], posts: [], gates: [] };
  const posts = [];
  for (const p of s.posts) {
    if (p.run_ref === run.id) posts.push({ post: p, station: p.station_mm });
    else if (p.run_ref === `node:${run.start_node_id}`) posts.push({ post: p, station: 0 });
    else if (p.run_ref === `node:${run.end_node_id}`) posts.push({ post: p, station: L });
  }
  return {
    spans: s.spans.filter((sp) => sp.run_ref === run.id),
    posts,
    gates: s.gates.filter((g) => g.run_ref === run.id),
  };
}

// ---------- projection ----------
function computeView(chain, span) {
  let zMin = 0, zMax = 0;
  const see = (z) => { if (z < zMin) zMin = z; if (z > zMax) zMax = z; };
  for (const entry of chain) {
    const { run, L, samples } = entry;
    entry.result = resultFor(run, L);
    for (const s of samples) see(s.z);
    for (const w of wallProfiles(run, L)) { see(w.z0); see(w.z1); }
    for (const it of heightIntents(run, L)) {
      see(groundZAt(samples, it.s0) + it.h);
      see(groundZAt(samples, it.s1) + it.h);
    }
    for (const sp of entry.result.spans) {
      see(Math.min(sp.bottom_z_start_mm, sp.bottom_z_end_mm));
      see(Math.max(sp.bottom_z_start_mm, sp.bottom_z_end_mm) + sp.height_mm);
    }
    for (const { post } of entry.result.posts) {
      see(post.ground_z_mm); see(post.ground_z_mm + DEFAULT_POST_MM);
    }
  }
  const range = Math.max(zMax - zMin, 1000);
  const sy = Math.min(SY_BASE * exag, (BASE - TOP_PAD) / range);
  return { chain, span, sx: (W - 2 * PAD) / span, sy, zMin };
}

const xOf = (gs) => PAD + gs * view.sx;
const yOf = (z) => BASE - (z - view.zMin) * view.sy;

function svgPoint(ev) {
  const svg = document.getElementById("profile-svg");
  const pt = svg.createSVGPoint();
  pt.x = ev.clientX; pt.y = ev.clientY;
  const { x, y } = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [x, y];
}
const stationOfX = (x) => Math.round(Math.max(0, Math.min((x - PAD) / view.sx, view.span)));
const zOfY = (y) => Math.round(view.zMin + (BASE - y) / view.sy);
const snapZ = (z) => Math.round(z / Z_SNAP) * Z_SNAP;

// ---------- rendering ----------
const GROUPS = ["p-grid", "p-result", "p-ground", "p-wall", "p-intent", "p-edit", "p-labels"];

function ensureGroups() {
  const svg = document.getElementById("profile-svg");
  if (document.getElementById("p-grid")) return;
  const defs = el("defs", {}, svg);
  for (const [id, path] of [["p-arrow-e", "M0,0 L6,3 L0,6 z"], ["p-arrow-s", "M6,0 L0,3 L6,6 z"]]) {
    const m = el("marker", { id, markerWidth: 6, markerHeight: 6, refX: id === "p-arrow-e" ? 6 : 0,
      refY: 3, orient: "auto", markerUnits: "userSpaceOnUse" }, defs);
    el("path", { d: path, fill: "#0891b2" }, m);
  }
  for (const id of GROUPS) el("g", { id }, svg);
}

function render() {
  const svg = document.getElementById("profile-svg");
  if (!svg) return;
  ensureGroups();
  const placeholder = document.getElementById("profile-placeholder");
  const runs = state.project?.topology.runs || [];
  if (!runs.length) {
    view = null;
    for (const id of GROUPS) clearGroup(id);
    if (placeholder) placeholder.textContent = t("profile.empty");
    return;
  }
  if (placeholder) placeholder.textContent = "";
  const { chain, span } = buildChain();
  view = computeView(chain, span);

  renderGrid(chain);
  renderResult(chain);
  renderGround(chain);
  renderWall(chain);
  renderIntent(chain);
}

function renderGrid(chain) {
  const g = clearGroup("p-grid");
  const labels = clearGroup("p-labels");
  // z=0 reference line
  el("line", { x1: PAD, y1: yOf(0), x2: W - PAD, y2: yOf(0), class: "profile-zero" }, g);
  const tickSeen = new Set(); // global x dedupe: shared boundaries get ONE label
  for (const entry of chain) {
    const { run, L, offset } = entry;
    // section boundary: tall tick + section id label at the section's start
    const bx = xOf(offset);
    el("line", { x1: bx, y1: 16, x2: bx, y2: BASE + 6, class: "profile-section-tick" }, g);
    el("text", { x: bx + 3, y: 12, class: "profile-section-label" }, labels)
      .textContent = t("profile.section", { id: run.id });
    // station ticks at run dots (cumulative vertex stations) + generated posts
    const stations = [0];
    const pts = runPoints(run);
    let acc = 0;
    for (let i = 0; i + 1 < pts.length; i++) {
      acc += Math.round(Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]));
      stations.push(acc);
    }
    for (const { station } of entry.result.posts) stations.push(station);
    for (const s of stations.sort((a, b) => a - b)) {
      const x = xOf(gsOf(entry, s));
      const key = Math.round(x * 2);
      if (tickSeen.has(key)) continue; // shared corner: label once
      tickSeen.add(key);
      el("line", { x1: x, y1: BASE, x2: x, y2: BASE + 6, class: "profile-tick" }, g);
      el("text", { x, y: BASE + 17, "text-anchor": "middle",
        class: "profile-tick-label num" }, labels).textContent = String(s);
    }
  }
}

function renderGround(chain) {
  const g = clearGroup("p-ground");
  const edit = clearGroup("p-edit");
  // ONE continuous ground polyline per connected chunk (shared nodes have a
  // single z, so the line is continuous across connected sections)
  let chunk = [];
  const chunks = [chunk];
  let prevEnd = null;
  for (const entry of chain) {
    if (prevEnd !== null && entry.offset !== prevEnd) { chunk = []; chunks.push(chunk); }
    const ordered = entry.reversed ? [...entry.samples].reverse() : entry.samples;
    for (const s of ordered) {
      const p = [xOf(gsOf(entry, s.station)), yOf(s.z)];
      const last = chunk[chunk.length - 1];
      if (!last || last[0] !== p[0] || last[1] !== p[1]) chunk.push(p);
    }
    prevEnd = entry.offset + entry.L;
  }
  for (const c of chunks) {
    if (c.length < 2) continue;
    el("polyline", { points: c.map((p) => p.join(",")).join(" "), class: "profile-ground" }, g);
  }
  // per-section fat invisible hit line: double-click adds a sample there
  for (const entry of chain) {
    const attr = (entry.reversed ? [...entry.samples].reverse() : entry.samples)
      .map((s) => `${xOf(gsOf(entry, s.station))},${yOf(s.z)}`).join(" ");
    const hit = el("polyline", { points: attr, class: "profile-ground-hit",
      "data-run": entry.run.id }, g);
    el("title", {}, hit).textContent = t("profile.ground_hint");
  }
  // dots: NODE handles (section endpoints/corners, primary) + interior events
  const nodeSeen = new Set();
  for (const entry of chain) {
    for (const s of entry.samples) {
      const gx = xOf(gsOf(entry, s.station)), gy = yOf(s.z);
      if (s.ev) {
        const c = el("circle", { cx: gx, cy: gy, r: 4.5, class: "profile-sample",
          "data-ev": s.ev.id, "data-run": entry.run.id }, edit);
        el("title", {}, c).textContent = t("profile.sample_tooltip");
        el("text", { x: gx + 6, y: gy - 6,
          class: "profile-sample-label num" }, edit).textContent = String(s.z);
      } else if (s.node) {
        const key = `${s.node.id}@${Math.round(gx)}`;
        if (nodeSeen.has(key)) continue;
        nodeSeen.add(key);
        const c = el("circle", { cx: gx, cy: gy, r: 5, class: "profile-node",
          "data-node": s.node.id }, edit);
        el("title", {}, c).textContent = t("profile.node_tooltip");
        el("text", { x: gx + 6, y: gy - 6,
          class: "profile-node-label num" }, edit).textContent = String(s.z);
      }
    }
  }
  // wall-top endpoint handles live in p-edit too (drawn by renderWall)
}

function renderWall(chain) {
  const g = clearGroup("p-wall");
  const edit = document.getElementById("p-edit");
  for (const entry of chain) {
    for (const w of wallProfiles(entry.run, entry.L)) {
      const x0 = xOf(gsOf(entry, w.s0)), x1 = xOf(gsOf(entry, w.s1));
      el("line", { x1: x0, y1: yOf(w.z0), x2: x1, y2: yOf(w.z1),
        class: "profile-wall" }, g);
      // fat invisible band: click opens the typed start/end editor
      const hit = el("line", { x1: x0, y1: yOf(w.z0), x2: x1, y2: yOf(w.z1),
        class: "profile-wall-hit", "data-ev": w.iv.id, "data-run": entry.run.id }, g);
      el("title", {}, hit).textContent = t("profile.wall_band_tooltip");
      hit.addEventListener("click", (ev) =>
        openWallPopover(entry.run.id, w.iv.id, ev.clientX, ev.clientY));
      for (const [end, s, z] of [["start", w.s0, w.z0], ["end", w.s1, w.z1]]) {
        const h = el("rect", { x: xOf(gsOf(entry, s)) - 4, y: yOf(z) - 4, width: 8, height: 8,
          class: "profile-wall-handle", "data-ev": w.iv.id, "data-run": entry.run.id,
          "data-end": end }, edit);
        el("title", {}, h).textContent = t("profile.wall_tooltip");
      }
    }
  }
}

function renderIntent(chain) {
  const g = clearGroup("p-intent");
  for (const entry of chain) {
    for (const it of heightIntents(entry.run, entry.L)) {
      // dashed line at intent height above ground, following the ground profile
      const stations = [it.s0,
        ...entry.samples.map((s) => s.station).filter((s) => s > it.s0 && s < it.s1), it.s1];
      const attr = stations
        .map((s) => `${xOf(gsOf(entry, s))},${yOf(groundZAt(entry.samples, s) + it.h)}`)
        .join(" ");
      el("polyline", { points: attr, class: "profile-intent" }, g);
    }
  }
}

function renderResult(chain) {
  const g = clearGroup("p-result");
  const sel = state.selection.elementId;
  const postSeen = new Set(); // shared node posts appear on both adjacent runs

  for (const entry of chain) {
    const { run, samples } = entry;
    for (const sp of entry.result.spans) {
      const x0 = xOf(gsOf(entry, sp.start_station_mm)), x1 = xOf(gsOf(entry, sp.end_station_mm));
      const bz0 = sp.bottom_z_start_mm, bz1 = sp.bottom_z_end_mm, h = sp.height_mm;
      let shape;
      if (sp.vertical === "raked") {
        // parallelogram following the ground
        shape = el("polygon", { points: `${x0},${yOf(bz0)} ${x1},${yOf(bz1)} ` +
          `${x1},${yOf(bz1 + h)} ${x0},${yOf(bz0 + h)}` }, g);
      } else {
        // level rect; stepped panels sit level at max(bz0, bz1)
        const bottom = sp.vertical === "stepped" ? Math.max(bz0, bz1) : bz0;
        shape = el("rect", { x: Math.min(x0, x1), y: yOf(bottom + h),
          width: Math.abs(x1 - x0),
          height: Math.max(yOf(bottom) - yOf(bottom + h), 1) }, g);
      }
      shape.setAttribute("class",
        `profile-panel ${sp.vertical}${sel === sp.id ? " selected" : ""}`);
      shape.dataset.id = sp.id;
      el("title", {}, shape).textContent = `${sp.id} (${sp.vertical}, ${h} mm)`;
      shape.addEventListener("click", () => {
        setSelection({ runId: run.id, elementId: sp.id });
        inspect(sp.id, t("inspect.span",
          { width: sp.width_mm, height: sp.height_mm, mode: sp.vertical }));
      });
    }

    for (const gate of entry.result.gates) {
      const x0 = xOf(gsOf(entry, gate.start_station_mm));
      const x1 = xOf(gsOf(entry, gate.end_station_mm));
      const mid = (gate.start_station_mm + gate.end_station_mm) / 2;
      const y = yOf(groundZAt(samples, Math.round(mid)) + 900);
      const line = el("line", { x1: x0, y1: y, x2: x1, y2: y,
        class: `profile-gate${sel === gate.id ? " selected" : ""}`,
        "marker-start": "url(#p-arrow-s)", "marker-end": "url(#p-arrow-e)" }, g);
      line.dataset.id = gate.id;
      el("text", { x: (x0 + x1) / 2, y: y - 5, "text-anchor": "middle",
        class: "profile-gate-label num" }, g).textContent =
        t("profile.gate_label", { width: gate.end_station_mm - gate.start_station_mm });
      line.addEventListener("click", () => {
        setSelection({ runId: run.id, elementId: gate.id });
        inspect(gate.id, t("inspect.gate", { kit: gate.kit_sku }));
      });
    }

    for (const { post, station } of entry.result.posts) {
      if (postSeen.has(post.id)) continue;
      postSeen.add(post.id);
      const x = xOf(gsOf(entry, station));
      const y0 = yOf(post.ground_z_mm);
      const y1 = yOf(post.ground_z_mm + DEFAULT_POST_MM);
      el("line", { x1: x, y1: y0, x2: x, y2: y1,
        class: `profile-post${sel === post.id ? " selected" : ""}`,
        "data-id": post.id }, g);
      const hit = el("line", { x1: x, y1: y0, x2: x, y2: y1,
        class: "profile-post-hit", "data-id": post.id }, g);
      el("title", {}, hit).textContent = `${post.id}\n${post.sku} (${post.kind}, ${post.mounting})`;
      hit.addEventListener("click", () => {
        setSelection({ runId: run.id, elementId: post.id });
        inspect(post.id, t("inspect.post", { sku: post.sku, station: post.station_mm }));
      });
    }
  }
}

// ---------- editing ----------
function chainEntry(runId) {
  return view?.chain.find((e) => e.run.id === runId) || null;
}

function setupSvg() {
  const svg = document.getElementById("profile-svg");

  svg.addEventListener("pointerdown", (ev) => {
    if (!view) return;
    const target = ev.target;
    if (target.classList.contains("profile-node")) {
      drag = { kind: "node", nodeId: target.dataset.node, started: false, startY: ev.clientY };
      svg.setPointerCapture(ev.pointerId);
    } else if (target.classList.contains("profile-sample")) {
      drag = { kind: "sample", runId: target.dataset.run, evId: target.dataset.ev,
        started: false, startY: ev.clientY };
      svg.setPointerCapture(ev.pointerId);
    } else if (target.classList.contains("profile-wall-handle")) {
      drag = { kind: "wall", runId: target.dataset.run, evId: target.dataset.ev,
        end: target.dataset.end, started: false, startY: ev.clientY };
      svg.setPointerCapture(ev.pointerId);
    }
  });

  svg.addEventListener("pointermove", (ev) => {
    if (!drag || !view) return;
    if (!drag.started) {
      if (Math.abs(ev.clientY - drag.startY) < 3) return;
      // gesture begins: snapshot BEFORE the first mutation
      pushSnapshot(drag.kind === "wall" ? "profile-wall" : "ground");
      drag.started = true;
    }
    const [, y] = svgPoint(ev);
    const z = snapZ(zOfY(y));
    if (drag.kind === "node") {
      // one node z: moving it moves the ground of BOTH adjacent sections
      const node = nodeById(drag.nodeId);
      if (node) node.z_mm = z;
    } else if (drag.kind === "sample") {
      const run = runById(drag.runId);
      const pe = run?.point_events.find((e) => e.id === drag.evId);
      if (pe) pe.payload.z_mm = z;
    } else {
      const run = runById(drag.runId);
      const iv = run?.interval_events.find((e) => e.id === drag.evId);
      if (iv) {
        if (drag.end === "start") iv.payload.top_z_start_mm = z;
        else iv.payload.top_z_end_mm = z;
      }
    }
    render();
  });

  // pointer capture retargets pointerup/click to the svg itself, so the
  // "plain click on a dot types z" path lives here, not in a click handler
  const endDrag = (ev) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (d.started) {
      saveTopology(); // snapshot was pushed at gesture start
    } else if (ev.type === "pointerup" && d.kind === "sample") {
      openSampleZInput(d.runId, d.evId); // click without a drag: type an exact z
    } else if (ev.type === "pointerup" && d.kind === "node") {
      openNodeZInput(d.nodeId);
    }
  };
  svg.addEventListener("pointerup", endDrag);
  svg.addEventListener("pointercancel", endDrag);

  // double-click the ground line: add an interior sample at that station
  svg.addEventListener("dblclick", (ev) => {
    if (!view || !ev.target.classList.contains("profile-ground-hit")) return;
    ev.preventDefault();
    const entry = chainEntry(ev.target.dataset.run);
    if (!entry) return;
    const [x] = svgPoint(ev);
    // global station -> (run, local station) via the chain
    const gs = stationOfX(x);
    const local = Math.max(0, Math.min(
      entry.reversed ? entry.offset + entry.L - gs : gs - entry.offset, entry.L));
    const z = snapZ(groundZAt(entry.samples, local));
    pushSnapshot("profile-add-sample");
    addPointEvent(entry.run.id, { kind: "elevation_sample", z_mm: z }, local);
    saveTopology();
  });
}

// ---------- typed z editors ----------
function openZEditor(gx, gy, value, apply) {
  const existing = document.getElementById("profile-z-editor");
  if (existing) existing.remove();
  const g = document.getElementById("p-edit");
  const fo = el("foreignObject", { x: Math.min(gx + 8, W - 80),
    y: Math.max(gy - 26, 2), width: 76, height: 24,
    id: "profile-z-editor" }, g);
  const input = document.createElement("input");
  input.type = "number";
  input.className = "mm-input profile-z-input";
  input.step = Z_SNAP;
  input.value = value;
  fo.appendChild(input);
  input.focus();
  input.select();
  let done = false;
  const close = () => { done = true; fo.remove(); };
  input.addEventListener("keydown", (ev) => {
    ev.stopPropagation();
    if (ev.key === "Enter") {
      const z = Math.round(+input.value);
      close();
      if (Number.isFinite(z) && z !== value) apply(z);
    } else if (ev.key === "Escape") close();
  });
  input.addEventListener("blur", () => { if (!done) close(); });
}

function openSampleZInput(runId, evId) {
  const entry = chainEntry(runId);
  const run = entry?.run;
  const pe = run?.point_events.find((e) => e.id === evId);
  if (!pe) return;
  const station = Math.min(stationOfAnchor(run, pe.anchor), entry.L);
  openZEditor(xOf(gsOf(entry, station)), yOf(pe.payload.z_mm), pe.payload.z_mm, (z) => {
    pushSnapshot("profile-ground-typed");
    pe.payload.z_mm = z;
    saveTopology();
  });
}

function openNodeZInput(nodeId) {
  const node = nodeById(nodeId);
  if (!node || !view) return;
  // position at the node's first chain occurrence
  let gx = PAD, gy = yOf(node.z_mm ?? 0);
  for (const entry of view.chain) {
    if (entry.run.start_node_id === nodeId) { gx = xOf(gsOf(entry, 0)); break; }
    if (entry.run.end_node_id === nodeId) { gx = xOf(gsOf(entry, entry.L)); break; }
  }
  openZEditor(gx, gy, node.z_mm ?? 0, (z) => {
    pushSnapshot("ground");
    node.z_mm = z;
    saveTopology();
  });
}

// ---------- wall editor popover (profile owns its own element) ----------
let wallPopover = null;

function closeWallPopover() {
  if (!wallPopover) return;
  wallPopover.remove();
  wallPopover = null;
  document.removeEventListener("pointerdown", onWallOutside, true);
}

function onWallOutside(ev) {
  if (wallPopover && !wallPopover.contains(ev.target)) closeWallPopover();
}

function openWallPopover(runId, evId, clientX, clientY) {
  closeWallPopover();
  const run = runById(runId);
  const iv = run?.interval_events.find((e) => e.id === evId);
  if (!iv) return;
  wallPopover = document.createElement("div");
  wallPopover.className = "popover";
  wallPopover.innerHTML = `<h4>${t("profile.wall_editor")}</h4>
    <div class="meta"><bdi>${esc(runId)}</bdi></div>
    <label>${t("popover.wall_start")}
      <input id="profile-wall-start" type="number" step="${Z_SNAP}"
        value="${iv.payload.top_z_start_mm}"></label>
    <label>${t("popover.wall_end")}
      <input id="profile-wall-end" type="number" step="${Z_SNAP}"
        value="${iv.payload.top_z_end_mm}"></label>
    <div class="popover-actions">
      <button id="profile-wall-cancel">${t("popover.cancel")}</button>
      <button id="profile-wall-save" class="primary">${t("popover.save")}</button></div>`;
  document.body.appendChild(wallPopover);
  wallPopover.style.left = `${Math.max(4, Math.min(clientX + 8, window.innerWidth - wallPopover.offsetWidth - 12))}px`;
  wallPopover.style.top = `${Math.max(4, Math.min(clientY + 8, window.innerHeight - wallPopover.offsetHeight - 12))}px`;

  function save() {
    const z0 = Math.round(+document.getElementById("profile-wall-start").value);
    const z1 = Math.round(+document.getElementById("profile-wall-end").value);
    closeWallPopover();
    if (!Number.isFinite(z0) || !Number.isFinite(z1)) return;
    if (z0 === iv.payload.top_z_start_mm && z1 === iv.payload.top_z_end_mm) return;
    pushSnapshot("profile-wall-typed");
    iv.payload.top_z_start_mm = z0;
    iv.payload.top_z_end_mm = z1;
    saveTopology();
  }

  wallPopover.addEventListener("keydown", (ev) => {
    ev.stopPropagation();
    if (ev.key === "Escape") closeWallPopover();
    else if (ev.key === "Enter") { ev.preventDefault(); save(); }
  });
  wallPopover.querySelector("#profile-wall-cancel").addEventListener("click", closeWallPopover);
  wallPopover.querySelector("#profile-wall-save").addEventListener("click", save);
  const first = wallPopover.querySelector("input");
  if (first) { first.focus(); first.select(); }
  // pointer down anywhere outside cancels (registered after this click)
  setTimeout(() => document.addEventListener("pointerdown", onWallOutside, true), 0);
}
