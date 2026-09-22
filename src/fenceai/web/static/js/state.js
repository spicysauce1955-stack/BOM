// Shared state + pub/sub + server sync. Modules communicate ONLY through this
// (events + exported functions) — never each other's DOM (spec module map).

import { apiGet, apiSend } from "./api.js";

export const state = {
  projectId: null,
  project: null,
  result: null,        // last GenerationResult
  critique: [],
  selection: { runId: null, dotIndex: null, elementId: null },
  // Is the OFFICE reading rather than editing? Owned by `js/job-screen.js`,
  // which is the only writer; declared here rather than created dynamically,
  // because a field that appears from nowhere is the trap `view` already fell
  // into once (see the note below). False for every other reader, so the lock
  // answers exactly as it did before this existed.
  officeReading: false,
  locale: "en",        // Task 10 flips the default to "he"
  units: "mm",         // DISPLAY unit only (mm | cm); storage is always int mm
  // Which view is on screen (sales | backoffice | all). A presentation
  // preference exactly like `units`, and never a permission: it hides surfaces,
  // it revokes nothing, and what an account may DO is its `capacity`, checked on
  // the server. Declared here as `view` — the rename left this ONE declaration
  // behind, so `state.view` was created dynamically by `initView` and this field
  // was dead. Everything worked, which is why nothing caught it.
  view: "all",
  // The signed-in account, or null. Owned by `session.js`.
  me: null,
  mayChooseView: true,
  // What `GET /api/session` answered about this browser, owned by `session.js`
  // and read by `app.js` to choose between the picker and the no-access screen.
  // Declared here for the same reason `officeReading` and `view` are: a field
  // created dynamically by its writer is invisible to every other reader until
  // it is too late.
  authStatus: null,   // ok | no_identity | no_capacity | deactivated | subject_mismatch
  authCode: null,     // the PLATFORM refusal code for that status, or null
  authEmail: "",      // who IAP says this is, even when they have no access
  // The road step on screen, or null when the view has no road. Owned by
  // `road.js`, which emits "step-changed" AFTER the screen is scoped to it.
  step: null,
  tool: "select",
  draftNodes: [],
  nodeSeq: 1,
  runSeq: 1,
  evSeq: 1,
};

// events: "project-loaded","topology-changed","result-changed",
//         "selection-changed","locale-changed","units-changed","tool-changed",
//         "view-changed","job-changed","context-changed",
//         "tab-changed","structure-loaded","fit-view","fence-models-changed",
//         "step-changed" (road.js, after data-step), "road-go" (ask road.js for a step)
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
  emit("project-opened", id);  // true project switch: history subscribes and resets
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

/** Persist the house/street/boundary layer.
 *
 *  Here rather than in `context.js` for the same reason `saveTopology` is here:
 *  state.js is the one channel modules mutate through, and a module reaching
 *  the API on its own would put two writers on one project.
 *
 *  It does NOT touch `saveTopology`. A landmark changes no quantity, so it must
 *  not bump the topology revision — that would 409 the structure sheet because
 *  somebody nudged a driveway. */
export async function saveContext() {
  state.project = await apiSend(
    "PUT", `/api/projects/${state.projectId}/context`, state.project.context
  );
  emit("context-changed", state.project.context);
}

/** Persist what this job does NOT have.
 *
 *  Unrevisioned, like `saveJob` — a claim about an absence changes no
 *  quantity. Emits `project-loaded` rather than a bespoke event because the
 *  handover must be re-fetched: stating a fact can CREATE a gap
 *  (`gates_contradicted`), so the road's own state depends on the round trip.
 */
export async function saveStated() {
  state.project = await apiSend(
    "PUT", `/api/projects/${state.projectId}/stated`, state.project.stated
  );
  emit("project-loaded", state.project);
}

/** Add a landmark locally. The caller persists with `saveContext()` — same
 *  shape as `addPointEvent` + `saveTopology`, so a drag that is cancelled
 *  mid-gesture leaves nothing on the server. */
export function addLandmark(landmark) {
  if (!state.project) return false;
  state.project.context = state.project.context || { landmarks: [] };
  state.project.context.landmarks.push(landmark);
  return true;
}

/** Job states in which a SALESPERSON may still change the drawing: hers until
 *  she sends it, and hers again when the office hands it back. Pure, for node;
 *  `SUBMIT_JOB.from_states` is the same set and a test pins the two. */
export const SALES_EDITABLE = ["drafting", "returned"];

/** Is the drawing view-only for the person looking?
 *
 *  Two answers, because the two readers are locked for different reasons and a
 *  single rule would have to lie about one of them:
 *
 *  * **the SALESPERSON is locked by STATUS.** A job she has sent is on the
 *    office's desk, and a drag there would bump the topology revision under a
 *    run the office generated (409 `topology_changed`).
 *  * **the OFFICE is locked by MODE.** It may edit anything — the backoffice
 *    design decided that in as many words, and this does not touch it — but it
 *    lands in reading and turns editing on deliberately. Status has nothing to
 *    do with it: the office holds the job in every status it can edit.
 *
 *  `reading` is passed in rather than imported, so this stays a pure function
 *  node can test and so `job-screen.js` remains the one owner of that answer.
 *  Callers that pass nothing keep exactly today's behaviour.
 *
 *  Presentation, like every view rule — the server does not gate topology writes
 *  by status or by mode. */
export function drawingLockedFor(view, status, reading = false) {
  if (view === "sales") return !!status && !SALES_EDITABLE.includes(status);
  return !!reading;
}

export function drawingLocked() {
  return drawingLockedFor(state.view, state.project?.status, state.officeReading);
}

/** Perform a named command on a job — the one gated door
 *  (`POST /projects/{id}/actions`). Resolves `{ok, project}` or
 *  `{ok: false, code, params}`: a refusal is an answer a screen renders in the
 *  reader's language (`error.<code>`), never a thrown alert. */
export async function runCommand(projectId, kind, payload = {}) {
  let r;
  try {
    r = await fetch(`/api/projects/${projectId}/actions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, payload }),
    });
  } catch {
    return { ok: false, code: "server_unreachable", params: {} };
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const d = body?.detail;
    // A typed refusal carries `{code, params}`. Anything else — a 422 from the
    // request schema (a list), a plain-string 404, a body that is not JSON — is
    // not "no action by that name", and saying so would send the reader looking
    // for the wrong fault.
    if (d && typeof d === "object" && !Array.isArray(d) && d.code)
      return { ok: false, code: d.code, params: d.params || {} };
    return { ok: false, code: r.status === 422 ? "command_payload_invalid" : "command_failed",
             params: {} };
  }
  return { ok: true, project: body };
}

export async function reloadProject() {
  // refresh server state after a non-topology mutation (annotations, overrides)
  // WITHOUT resetting undo history or selection (final UI-v2 review #2)
  state.project = await apiGet(`/api/projects/${state.projectId}`);
  emit("project-loaded", state.project);
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

/** The resolved maximum span for a run, read off the DECISION GRAPH rather than
 *  inferred from what the last generation happened to build.
 *
 *  `resolve_max_span` — or `uncovered_param`, where no rule covered it — carries
 *  the value the run was actually laid out to. Two fence models can meet on one
 *  run and resolve differently, so a preview takes the SMALLEST: warning early
 *  is a nuisance, promising a bay the generator will refuse is a wrong price
 *  shown confidently. `0` means "no run yet", which disables the check.
 *
 *  It lives here, on the bus, because both drag adapters need it and neither may
 *  import the other. It was written twice — once in `editor.js`, and once in
 *  `profile.js` as a `{}` seam that made `violations()` inert — which is exactly
 *  the drift `post-drag.js` exists to prevent, one level up. The pure module
 *  cannot hold it: it may not see `state`. */
export function maxSpanFor(runId) {
  let out = 0;
  for (const node of state.result?.graph?.nodes || []) {
    const p = node.payload || {};
    if (p.param !== "max_span_mm" || p.run_id !== runId) continue;
    if (!Number.isFinite(p.value)) continue;
    out = out ? Math.min(out, p.value) : p.value;
  }
  return out;
}
