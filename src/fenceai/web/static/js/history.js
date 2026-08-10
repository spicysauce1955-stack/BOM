// Gesture-based undo/redo (Task 6). Snapshots are deep copies of
// {topology, overrides} pushed once per committed user gesture — never for
// non-user changes (openProject, server refresh). Undo/redo restore the
// snapshot locally and PUT it as a NEW forward revision: server revisions are
// monotonic, never rolled back (spec §2).

import { apiSend } from "./api.js";
import { emit, on, saveTopology, state } from "./state.js";

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
        state.project.topology = snap.topology;
        await saveTopology(); // forward revision; refreshes state.project, emits project-loaded
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
