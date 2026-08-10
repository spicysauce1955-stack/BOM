// Side-view profile panel (Task 9): synchronized unrolled elevation view of the
// selected run. Renders ground, wall-top, height-intent and generated
// panels/posts/gates; edits ground samples + wall-top endpoints (gesture ->
// pushSnapshot -> mutate -> saveTopology). Station axis is NEVER mirrored in
// RTL (spec §3; #profile-svg is direction:ltr in CSS).

import { clearGroup, el, runById, runLength, runPoints } from "./geom.js";
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

let exag = 5;                // 1x / 5x toggle, default 5x
let view = null;             // { runId, L, sx, sy, zMin } of the last render
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
  on("project-loaded", render);
  on("topology-changed", render);
  on("result-changed", render);
  on("selection-changed", render);
  on("locale-changed", render);
  render();
}

// ---------- run + elevation model ----------
function currentRun() {
  const runs = state.project?.topology.runs || [];
  if (!runs.length) return null;
  return runs.find((r) => r.id === state.selection.runId) || runs[0];
}

// [{ev, station, z}] sorted by station (UI-authored anchors: station==offset)
function groundSamples(run, L) {
  return run.point_events
    .filter((ev) => ev.payload.kind === "elevation_sample")
    .map((ev) => ({
      ev, station: Math.min(ev.anchor.offset_mm, L), z: ev.payload.z_mm,
    }))
    .sort((a, b) => a.station - b.station);
}

// piecewise-linear ground, matching backend topology/station.py ground_z():
// no samples -> flat 0; beyond outermost samples the nearest z extends
function groundZAt(samples, L, station) {
  if (!samples.length) return 0;
  const pts = samples.map((s) => [s.station, s.z]);
  if (pts[0][0] > 0) pts.unshift([0, pts[0][1]]);
  if (pts[pts.length - 1][0] < L) pts.push([L, pts[pts.length - 1][1]]);
  const s = Math.max(0, Math.min(station, L));
  for (let i = 0; i + 1 < pts.length; i++) {
    const [s0, z0] = pts[i], [s1, z1] = pts[i + 1];
    if (s0 <= s && s <= s1)
      return s1 === s0 ? z0 : Math.round(z0 + ((z1 - z0) * (s - s0)) / (s1 - s0));
  }
  return pts[pts.length - 1][1];
}

function wallProfiles(run, L) {
  return run.interval_events
    .filter((iv) => iv.payload.kind === "wall_profile")
    .map((iv) => ({
      iv,
      s0: Math.min(iv.start_anchor.offset_mm, L),
      s1: Math.min(iv.end_anchor.offset_mm, L),
      z0: iv.payload.top_z_start_mm, z1: iv.payload.top_z_end_mm,
    }));
}

function heightIntents(run, L) {
  return run.interval_events
    .filter((iv) => iv.payload.kind === "height_intent")
    .map((iv) => ({
      s0: Math.min(iv.start_anchor.offset_mm, L),
      s1: Math.min(iv.end_anchor.offset_mm, L),
      h: iv.payload.height_mm,
    }));
}

// strategy elements for this run; node posts mapped to terminal stations
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
function computeView(run) {
  const L = Math.max(runLength(run), 1);
  const samples = groundSamples(run, L);
  const { spans, posts } = resultFor(run, L);
  let zMin = 0, zMax = 0;
  const see = (z) => { if (z < zMin) zMin = z; if (z > zMax) zMax = z; };
  for (const s of samples) see(s.z);
  for (const w of wallProfiles(run, L)) { see(w.z0); see(w.z1); }
  for (const it of heightIntents(run, L)) {
    see(groundZAt(samples, L, it.s0) + it.h);
    see(groundZAt(samples, L, it.s1) + it.h);
  }
  for (const sp of spans) {
    see(Math.min(sp.bottom_z_start_mm, sp.bottom_z_end_mm));
    see(Math.max(sp.bottom_z_start_mm, sp.bottom_z_end_mm) + sp.height_mm);
  }
  for (const { post } of posts) { see(post.ground_z_mm); see(post.ground_z_mm + DEFAULT_POST_MM); }
  const range = Math.max(zMax - zMin, 1000);
  const sy = Math.min(SY_BASE * exag, (BASE - TOP_PAD) / range);
  return { runId: run.id, L, sx: (W - 2 * PAD) / L, sy, zMin };
}

const xOf = (station) => PAD + station * view.sx;
const yOf = (z) => BASE - (z - view.zMin) * view.sy;

function svgPoint(ev) {
  const svg = document.getElementById("profile-svg");
  const pt = svg.createSVGPoint();
  pt.x = ev.clientX; pt.y = ev.clientY;
  const { x, y } = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [x, y];
}
const stationOfX = (x) => Math.round(Math.max(0, Math.min((x - PAD) / view.sx, view.L)));
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
  const run = currentRun();
  if (!run) {
    view = null;
    for (const id of GROUPS) clearGroup(id);
    if (placeholder) placeholder.textContent = t("profile.empty");
    return;
  }
  if (placeholder) placeholder.textContent = "";
  view = computeView(run);
  const L = view.L;
  const samples = groundSamples(run, L);
  const result = resultFor(run, L);

  renderGrid(run, L, result);
  renderResult(run, result, samples, L);
  renderGround(run, samples, L);
  renderWall(run, L);
  renderIntent(run, samples, L);
}

function renderGrid(run, L, result) {
  const g = clearGroup("p-grid");
  // z=0 reference line
  el("line", { x1: PAD, y1: yOf(0), x2: W - PAD, y2: yOf(0), class: "profile-zero" }, g);
  // station ticks at run dots (cumulative vertex stations) + generated posts
  const stations = [];
  const pts = runPoints(run);
  let acc = 0;
  stations.push(0);
  for (let i = 0; i + 1 < pts.length; i++) {
    acc += Math.round(Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]));
    stations.push(acc);
  }
  for (const { station } of result.posts) stations.push(station);
  const seen = new Set();
  const labels = clearGroup("p-labels");
  for (const s of stations.sort((a, b) => a - b)) {
    if (seen.has(s)) continue;
    seen.add(s);
    const x = xOf(s);
    el("line", { x1: x, y1: BASE, x2: x, y2: BASE + 6, class: "profile-tick" }, g);
    el("text", { x, y: BASE + 17, "text-anchor": "middle",
      class: "profile-tick-label num" }, labels).textContent = String(s);
  }
  el("text", { x: PAD, y: 12, class: "profile-run-label" }, labels)
    .textContent = t("profile.run_label", { id: run.id, len: L });
}

function renderGround(run, samples, L) {
  const g = clearGroup("p-ground");
  const edit = clearGroup("p-edit");
  const pts = [[0, groundZAt(samples, L, 0)],
    ...samples.map((s) => [s.station, s.z]),
    [L, groundZAt(samples, L, L)]];
  const attr = pts.map(([s, z]) => `${xOf(s)},${yOf(z)}`).join(" ");
  el("polyline", { points: attr, class: "profile-ground" }, g);
  // fat invisible hit line: double-click adds a sample at that station
  const hit = el("polyline", { points: attr, class: "profile-ground-hit" }, g);
  el("title", {}, hit).textContent = t("profile.ground_hint");
  // sample dots (draggable vertically / click to type)
  for (const s of samples) {
    const c = el("circle", { cx: xOf(s.station), cy: yOf(s.z), r: 4.5,
      class: "profile-sample", "data-ev": s.ev.id }, edit);
    el("title", {}, c).textContent = t("profile.sample_tooltip");
    el("text", { x: xOf(s.station) + 6, y: yOf(s.z) - 6,
      class: "profile-sample-label num" }, edit).textContent = String(s.z);
  }
  // wall-top endpoint handles live in p-edit too (drawn by renderWall)
}

function renderWall(run, L) {
  const g = clearGroup("p-wall");
  const edit = document.getElementById("p-edit");
  for (const w of wallProfiles(run, L)) {
    el("line", { x1: xOf(w.s0), y1: yOf(w.z0), x2: xOf(w.s1), y2: yOf(w.z1),
      class: "profile-wall" }, g);
    for (const [end, s, z] of [["start", w.s0, w.z0], ["end", w.s1, w.z1]]) {
      const h = el("rect", { x: xOf(s) - 4, y: yOf(z) - 4, width: 8, height: 8,
        class: "profile-wall-handle", "data-ev": w.iv.id, "data-end": end }, edit);
      el("title", {}, h).textContent = t("profile.wall_tooltip");
    }
  }
}

function renderIntent(run, samples, L) {
  const g = clearGroup("p-intent");
  for (const it of heightIntents(run, L)) {
    // dashed line at intent height above ground, following the ground profile
    const stations = [it.s0,
      ...samples.map((s) => s.station).filter((s) => s > it.s0 && s < it.s1), it.s1];
    const attr = stations
      .map((s) => `${xOf(s)},${yOf(groundZAt(samples, L, s) + it.h)}`).join(" ");
    el("polyline", { points: attr, class: "profile-intent" }, g);
  }
}

function renderResult(run, result, samples, L) {
  const g = clearGroup("p-result");
  const sel = state.selection.elementId;

  for (const sp of result.spans) {
    const x0 = xOf(sp.start_station_mm), x1 = xOf(sp.end_station_mm);
    const bz0 = sp.bottom_z_start_mm, bz1 = sp.bottom_z_end_mm, h = sp.height_mm;
    let shape;
    if (sp.vertical === "raked") {
      // parallelogram following the ground
      shape = el("polygon", { points: `${x0},${yOf(bz0)} ${x1},${yOf(bz1)} ` +
        `${x1},${yOf(bz1 + h)} ${x0},${yOf(bz0 + h)}` }, g);
    } else {
      // level rect; stepped panels sit level at max(bz0, bz1)
      const bottom = sp.vertical === "stepped" ? Math.max(bz0, bz1) : bz0;
      shape = el("rect", { x: x0, y: yOf(bottom + h), width: x1 - x0,
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

  for (const gate of result.gates) {
    const x0 = xOf(gate.start_station_mm), x1 = xOf(gate.end_station_mm);
    const mid = (gate.start_station_mm + gate.end_station_mm) / 2;
    const y = yOf(groundZAt(samples, L, Math.round(mid)) + 900);
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

  for (const { post, station } of result.posts) {
    const x = xOf(station);
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

// ---------- editing ----------
function setupSvg() {
  const svg = document.getElementById("profile-svg");

  svg.addEventListener("pointerdown", (ev) => {
    if (!view) return;
    const target = ev.target;
    if (target.classList.contains("profile-sample")) {
      drag = { kind: "sample", evId: target.dataset.ev, started: false, startY: ev.clientY };
      svg.setPointerCapture(ev.pointerId);
    } else if (target.classList.contains("profile-wall-handle")) {
      drag = { kind: "wall", evId: target.dataset.ev, end: target.dataset.end,
        started: false, startY: ev.clientY };
      svg.setPointerCapture(ev.pointerId);
    }
  });

  svg.addEventListener("pointermove", (ev) => {
    if (!drag || !view) return;
    const run = runById(view.runId);
    if (!run) return;
    if (!drag.started) {
      if (Math.abs(ev.clientY - drag.startY) < 3) return;
      // gesture begins: snapshot BEFORE the first mutation
      pushSnapshot(drag.kind === "sample" ? "profile-ground" : "profile-wall");
      drag.started = true;
    }
    const [, y] = svgPoint(ev);
    const z = snapZ(zOfY(y));
    if (drag.kind === "sample") {
      const pe = run.point_events.find((e) => e.id === drag.evId);
      if (pe) pe.payload.z_mm = z;
    } else {
      const iv = run.interval_events.find((e) => e.id === drag.evId);
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
      openZInput(d.evId); // click without a drag: type an exact z
    }
  };
  svg.addEventListener("pointerup", endDrag);
  svg.addEventListener("pointercancel", endDrag);

  // double-click the ground line: add a sample at that station
  svg.addEventListener("dblclick", (ev) => {
    if (!view || !ev.target.classList.contains("profile-ground-hit")) return;
    ev.preventDefault();
    const run = runById(view.runId);
    if (!run) return;
    const [x] = svgPoint(ev);
    const station = stationOfX(x);
    const samples = groundSamples(run, view.L);
    const z = snapZ(groundZAt(samples, view.L, station));
    pushSnapshot("profile-add-sample");
    addPointEvent(run.id, { kind: "elevation_sample", z_mm: z }, station);
    saveTopology();
  });
}

function openZInput(evId) {
  const run = runById(view.runId);
  const pe = run?.point_events.find((e) => e.id === evId);
  if (!pe) return;
  const existing = document.getElementById("profile-z-editor");
  if (existing) existing.remove();
  const station = Math.min(pe.anchor.offset_mm, view.L);
  const g = document.getElementById("p-edit");
  const fo = el("foreignObject", { x: Math.min(xOf(station) + 8, W - 80),
    y: Math.max(yOf(pe.payload.z_mm) - 26, 2), width: 76, height: 24,
    id: "profile-z-editor" }, g);
  const input = document.createElement("input");
  input.type = "number";
  input.className = "mm-input profile-z-input";
  input.step = Z_SNAP;
  input.value = pe.payload.z_mm;
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
      if (Number.isFinite(z) && z !== pe.payload.z_mm) {
        pushSnapshot("profile-ground-typed");
        pe.payload.z_mm = z;
        saveTopology();
      }
    } else if (ev.key === "Escape") close();
  });
  input.addEventListener("blur", () => { if (!done) close(); });
}
