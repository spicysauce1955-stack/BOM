// The structure report, fetched once per generation run and shared.
//
// Tags (P1, B1, G1, section A) are DERIVED BY THE BACKEND. The tables, the plan
// canvas and the side view all read them from here, so a tag drawn on a bay and
// a tag printed in a row can never disagree — which is the whole point of tagging
// a drawing against a schedule.

import { apiGet } from "./api.js";
import { emit, on, state } from "./state.js";

// Roles a CUSTOMER sheet describes rather than itemises — an itemised screw
// count on a proposal invites an argument about the screws that were not used.
// It lives here, beside the report the classification is about, because both the
// structure tables and the supply-problems panel have to agree on it and neither
// may import the other's module.
export const CONSUMABLE_ROLES = new Set(["screw", "concrete"]);

let report = null;      // last fetched StructureReport
let runId = null;       // the run it belongs to
let inFlight = null;
let inFlightFor = null; // the run id that fetch was started for
let tags = new Map();   // element id -> tag, built once per report
// why the last attempt found nothing (409s are real states, not failures):
// "topology" (the drawing moved) | "catalog" (products changed) |
// "predates" (older than fence models) | "unknown" (a refusal with no branch —
// still a refusal) | null (no attempt yet, the ONLY case that means "no run")
let staleReason = null;
let staleDetail = "";   // the refusal's code, so "unknown" can still name itself

export function getReport() {
  return report;
}

export async function loadStructure() {
  const wanted = state.result?.run?.id || null;
  if (!wanted) {
    report = null; runId = null; tags = new Map();
    staleReason = null; staleDetail = "";
    emit("structure-loaded", null); return null;
  }
  if (runId === wanted && report) return report;
  // an in-flight fetch belongs to the run it was STARTED for: adopting it for a
  // different run would label one drawing with another's schedule
  if (inFlight && inFlightFor === wanted) return inFlight;
  inFlightFor = wanted;
  inFlight = apiGet(`/api/runs/${wanted}/structure`)
    .then((doc) => {
      if (state.result?.run?.id !== wanted) return null;   // the run moved on
      report = doc; runId = wanted; tags = indexTags(doc);
      staleReason = null; staleDetail = "";
      return doc;
    })
    .catch((err) => {
      report = null; runId = null; tags = new Map();
      // 409: the run no longer matches something it was read against.
      // 400 run_predates_fence_model: the run is older than fence models, so it
      // cannot be laid out at all.
      const msg = String(err?.message || "");
      staleDetail = refusalCode(msg);
      staleReason = msg.includes("catalog_changed") ? "catalog"
        : msg.includes("topology_changed") ? "topology"
        : msg.includes("run_predates_fence_model") ? "predates"
        // Anything ELSE is still a refusal. This used to fall back to `null`,
        // which means "no attempt yet", so the tab said "generate a strategy to
        // see how it is laid out" about a run that had been generated and could
        // not be read — the exact false message wave H was written to remove.
        // The gap-1 400 reached it by this door; that cause is fixed, and the
        // door is closed here so the next unrecognised code cannot use it.
        : "unknown";
      return null;
    })
    .finally(() => { inFlight = null; inFlightFor = null; });
  const doc = await inFlight;
  emit("structure-loaded", doc);
  return doc;
}

// true when the last attempt found a run that could not be read as-is
export function isStale() {
  return staleReason !== null;
}

// "topology" | "catalog" | "predates" | "unknown" | null — why the last attempt failed
export function staleKind() {
  return staleReason;
}

// The refusal's `code`, for the branch that has no sentence of its own. Naming
// the code is not a great message; claiming there is no structure is a false one.
export function staleCode() {
  return staleDetail;
}

function refusalCode(bodyText) {
  let text = bodyText;
  try {
    const detail = JSON.parse(bodyText)?.detail;
    if (detail?.code) return String(detail.code);
    if (typeof detail === "string") text = detail;
  } catch {
    /* not JSON — fall through to the raw body */
  }
  // a code is short; a raw body is whatever the server said, and a panel is not
  // a log viewer (the full text is already in the console, via apiGet's throw)
  return text.length > 120 ? `${text.slice(0, 120)}…` : text;
}

function indexTags(doc) {
  const map = new Map();
  for (const section of doc?.sections || [])
    for (const row of [...section.setting_out, ...section.bays, ...section.gates])
      map.set(row.element_id, row.tag);
  return map;
}

// element id -> its tag ("P3", "B2", "G1"), or null when the report is stale.
// Indexed once per report: this is called for EVERY element drawn, on every
// render, so a scan here would make a big fence quadratic.
export function tagOf(elementId) {
  return tags.get(elementId) ?? null;
}

export function sectionOf(runIdWanted) {
  return report?.sections.find((s) => s.run_id === runIdWanted) || null;
}

export function initStructureData() {
  // a new result invalidates every tag: refetch eagerly so the drawings can
  // label themselves without each view fetching its own copy
  on("result-changed", () => { report = null; runId = null; tags = new Map(); loadStructure(); });
  // and a project LOAD carries a result too (a reload lands on the last run, and
  // a topology edit clears it) — without this the drawings lose their tags until
  // the user presses generate again
  on("project-loaded", () => { report = null; runId = null; tags = new Map(); loadStructure(); });
  // the parts name the BAR a piece is cut from, so a change in the yard changes
  // this document even though the layout is untouched
  on("inventory-saved", () => { report = null; runId = null; tags = new Map(); loadStructure(); });
}
