// Gesture-based undo/redo (Task 6). Snapshots are deep copies of
// {topology, overrides, choices, context} pushed once per committed user
// gesture — never for non-user changes (openProject, server refresh).
// Undo/redo restore the snapshot locally and PUT it as a NEW forward
// revision: server revisions are monotonic, never rolled back (spec §2).
//
// Context (house/street/… landmarks) rides this SAME stack rather than a
// second one — a second stack would make Ctrl/Cmd+Z do a different thing
// depending on which tool was last active, which is worse than sharing. That
// is legal even though `saveTopology`'s revision must never go backwards,
// because `SiteContext` is UNREVISIONED (project/model.py: "there is nothing
// downstream that could be stale against it") — so restoring it is a plain
// idempotent PUT via `saveContext`, never `saveTopology`.

import { apiSend } from "./api.js";
import { emit, on, reloadProject, saveContext, saveStated, saveTopology, state } from "./state.js";

on("project-opened", () => resetHistory());

const CAP = 100;
let past = [];
let future = [];
let queue = Promise.resolve(); // restores are serialized, never dropped
let lastTarget = null;         // logical current state while restores are in flight
let generation = 0;            // bumped on reset: queued restores from a previous
                               // project/session must never write (review #4)

function snapshot() {
  return structuredClone({
    topology: state.project.topology,
    overrides: state.project.overrides || [],
    // Answering an open question is a committed user gesture like any other, and
    // it was NOT in here: undoing it therefore popped the drawing edit before
    // it — the person pressed Ctrl+Z once and lost a wall instead of a choice.
    // A selection is an INPUT to generation stored on the project (spec §3), so
    // it belongs in the snapshot beside the overrides rather than in the
    // topology it is not part of.
    choices: state.project.choices || [],
    // Landmarks are not topology (a moved driveway must never 409 the
    // structure sheet), but they ARE a committed user gesture like any
    // other, and undoing a house placement must pop the house rather than
    // reach past it into the fence edit underneath.
    context: state.project.context || { landmarks: [] },
    // "No gates on this job", "nothing was promised" — a claim of ABSENCE, and
    // a committed user gesture like any other. `road.js` already called
    // `pushSnapshot("state-fact")` before setting one, and the comment there
    // said "as undoable as any other job edit" while this function did not
    // carry the field: the snapshot held no `stated`, `restore` never wrote
    // one, so Ctrl+Z left the claim standing and popped the drawing edit
    // underneath it instead — with the redo stack already discarded. That is
    // the `choices` bug three comments up, reintroduced by the next field to
    // join the project.
    stated: state.project.stated || {},
  });
}

// Call AFTER a completed user gesture is decided, BEFORE mutating
// state.project (then saveTopology() after the mutation).
export function pushSnapshot(_label) {
  if (!state.project) return;
  past.push(snapshot());
  if (past.length > CAP) past.shift();
  future = []; // redo stack clears on any new gesture
}

export function canUndo() { return past.length > 0; }
export function canRedo() { return future.length > 0; }

export function resetHistory() { generation++; past = []; future = []; lastTarget = null; }

// what "current" means for stack bookkeeping: the target of the most recently
// queued restore if one is still in flight, else the live state
function logicalSnapshot() {
  return lastTarget ? structuredClone(lastTarget) : snapshot();
}

// Overrides live in per-override server endpoints; restoring a snapshot means
// diffing by id: delete extras, re-add missing (POST keeps the original id).
async function syncOverrides(target) {
  const current = state.project.overrides || [];
  const targetIds = new Set(target.map((o) => o.id));
  const currentIds = new Set(current.map((o) => o.id));
  for (const ov of current) {
    if (!targetIds.has(ov.id)) {
      await apiSend("DELETE", `/api/projects/${state.projectId}/overrides/${ov.id}`);
    }
  }
  for (const ov of target) {
    if (!currentIds.has(ov.id)) {
      await apiSend("POST", `/api/projects/${state.projectId}/overrides`, ov);
    }
  }
}

// ...and the choices half of the same diff. Their endpoint is an UPSERT keyed on
// (choice_set, scope), so re-adding one is a PUT rather than a POST, and the
// DELETE carries the scope as a query parameter because a real scope
// (`model:mfr/certainteed/rail`) contains slashes.
//
// Snapshotting choices without restoring them would leave undo doing nothing on
// a choice gesture while still consuming a stack slot, which is the same bug
// this change is here to fix, one step further along.
async function syncChoices(target) {
  // Separator written as escape \0 (not raw NUL) to prevent git treating this file as binary, which hides diffs from review.
  const key = (c) => `${c.choice_set}\0${c.scope}`;
  const current = state.project.choices || [];
  const wanted = new Map(target.map((c) => [key(c), c]));
  const held = new Map(current.map((c) => [key(c), c]));
  for (const c of current) {
    if (!wanted.has(key(c))) {
      await apiSend("DELETE",
        `/api/projects/${state.projectId}/choices/${encodeURIComponent(c.choice_set)}`
        + `?scope=${encodeURIComponent(c.scope)}`);
    }
  }
  for (const c of target) {
    const now = held.get(key(c));
    // an unchanged answer is not re-sent: a PUT per undo would rewrite
    // `created_at` and make the panel report the wrong moment
    if (!now || JSON.stringify(now) !== JSON.stringify(c))
      await apiSend("PUT", `/api/projects/${state.projectId}/choices`, c);
  }
}

// Context has no revision, so restoring it is a plain replace rather than the
// per-id diff overrides/choices need — but it is skipped when unchanged so an
// ordinary fence-only undo does not fire a second network write on every
// step (`saveContext`, never `saveTopology`: that would bump a revision this
// data does not have and cannot go stale against).
async function syncContext(target) {
  const wanted = target || { landmarks: [] };
  const current = state.project.context || { landmarks: [] };
  if (JSON.stringify(current) === JSON.stringify(wanted)) return;
  state.project.context = structuredClone(wanted);
  await saveContext();
}

// `stated` is a plain replace like `context`, and for the same two reasons: its
// endpoint carries no revision, and re-sending an unchanged claim would fire a
// needless write on every ordinary fence undo. `saveStated` re-emits
// `project-loaded`, which is what repaints the road's step badges.
async function syncStated(target) {
  const wanted = target || {};
  const current = state.project.stated || {};
  if (JSON.stringify(current) === JSON.stringify(wanted)) return;
  state.project.stated = structuredClone(wanted);
  await saveStated();
}


// `put_topology` bumps `Project.topology.revision` UNCONDITIONALLY on every
// call (app.py) — it does not compare content. Restoring an unchanged
// topology (the case for a context-only, choice-only or override-only undo)
// would therefore 409 the structure sheet the next time anybody so much as
// nudges a driveway, exactly the failure landmarks sharing this stack must
// not cause. `reloadProject` still picks up whatever the syncs above already
// wrote server-side, without touching a revision this gesture never meant to
// bump.
async function syncTopology(target) {
  if (JSON.stringify(state.project.topology) === JSON.stringify(target)) {
    await reloadProject();
    return;
  }
  state.project.topology = target;
  await saveTopology();
}

function restore(snap, dir) {
  // stack bookkeeping is synchronous (callers already did it); the server
  // round-trips are chained so rapid Ctrl+Z presses are applied in order.
  // Guards: a queued restore must never write into a different project or a
  // reset session (review #4); a failed PUT rolls the bookkeeping back (#8).
  const gen = generation;
  const pid = state.projectId;
  lastTarget = snap;
  queue = queue
    .then(async () => {
      if (gen !== generation || state.projectId !== pid) return;
      try {
        await syncOverrides(snap.overrides);
        await syncChoices(snap.choices || []);
        await syncContext(snap.context);
        await syncStated(snap.stated);
        await syncTopology(snap.topology); // forward revision ONLY when topology itself changed
        emit("topology-changed");
      } catch (err) {
        if (gen === generation) {
          if (dir === "undo") { past.push(snap); future.pop(); }
          else { future.push(snap); past.pop(); }
          emit("topology-changed"); // refresh button disabled states
        }
        throw err;
      }
    })
    .catch(() => {})
    .finally(() => { if (lastTarget === snap) lastTarget = null; });
}

export function undo() {
  if (!state.project || !past.length) return false;
  const snap = past.pop();
  future.push(logicalSnapshot());
  restore(snap, "undo");
  return true;
}

export function redo() {
  if (!state.project || !future.length) return false;
  const snap = future.pop();
  past.push(logicalSnapshot());
  restore(snap, "redo");
  return true;
}
