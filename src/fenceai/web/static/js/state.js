// Shared state + pub/sub + server sync. Modules communicate ONLY through this
// (events + exported functions) — never each other's DOM (spec module map).

import { apiGet, apiSend } from "./api.js";
import { resetHistory } from "./history.js";

export const state = {
  projectId: null,
  project: null,
  result: null,        // last GenerationResult
  critique: [],
  selection: { runId: null, dotIndex: null, elementId: null },
  locale: "en",        // Task 10 flips the default to "he"
  tool: "select",
  draftNodes: [],
  nodeSeq: 1,
  runSeq: 1,
  evSeq: 1,
};

// events: "project-loaded","topology-changed","result-changed",
//         "selection-changed","locale-changed","tool-changed"
const bus = new EventTarget();
export function on(event, fn) { bus.addEventListener(event, (e) => fn(e.detail)); }
export function emit(event, detail) { bus.dispatchEvent(new CustomEvent(event, { detail })); }

export function setTool(name) {
  state.tool = name;
  emit("tool-changed", name);
}

export function setSelection(sel) {
  state.selection = { runId: null, dotIndex: null, elementId: null, ...sel };
  emit("selection-changed", state.selection);
}

export async function loadProjects() {
  const list = await apiGet("/api/projects");
  if (list.length && !state.projectId) state.projectId = list[0].id;
  return list;
}

export async function openProject(id) {
  state.projectId = id;
  state.project = await apiGet(`/api/projects/${id}`);
  state.result = null;
  state.critique = [];
  state.selection = { runId: null, dotIndex: null, elementId: null };
  resetHistory();
  const maxSuffix = (items, prefix) => items.reduce((m, it) => {
    const match = it.id.match(new RegExp(`^${prefix}(\\d+)$`));
    return match ? Math.max(m, +match[1]) : m;
  }, 0);
  state.nodeSeq = maxSuffix(state.project.topology.nodes, "n") + 1;
  state.runSeq = maxSuffix(state.project.topology.runs, "run") + 1;
  try {
    const runs = await apiGet(`/api/projects/${id}/runs`);
    if (runs.length) state.result = await apiGet(`/api/runs/${runs[runs.length - 1].id}`);
  } catch { /* no runs yet */ }
  emit("project-loaded", state.project);
}

export async function createProject(name) {
  const p = await apiSend("POST", "/api/projects", { name });
  await openProject(p.id);
  return p;
}

export async function saveTopology() {
  state.project = await apiSend(
    "PUT", `/api/projects/${state.projectId}/topology`, state.project.topology
  );
  state.result = null;
  emit("project-loaded", state.project);
}

export async function generateStrategy() {
  if (!state.projectId) return;
  const out = await apiSend("POST", `/api/projects/${state.projectId}/generate`);
  state.result = out.result;
  state.critique = out.critique;
  emit("result-changed", state.result);
}

export async function refreshProject() {
  await openProject(state.projectId);
}

// ---------- topology mutation helpers (data ops; callers push history first) ----
import { anchorFor } from "./geom.js";

export function addPointEvent(runId, payload, station) {
  const run = state.project.topology.runs.find((r) => r.id === runId);
  if (!run) return false;
  run.point_events.push({
    id: `ev${Date.now()}_${state.evSeq++}`, anchor: anchorFor(runId, station), payload,
  });
  return true;
}

export function addIntervalEvent(runId, payload, start, end) {
  const run = state.project.topology.runs.find((r) => r.id === runId);
  if (!run) return false;
  run.interval_events.push({
    id: `ev${Date.now()}_${state.evSeq++}`,
    start_anchor: anchorFor(runId, start), end_anchor: anchorFor(runId, end), payload,
  });
  return true;
}
