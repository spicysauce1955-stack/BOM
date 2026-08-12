// The structure report, fetched once per generation run and shared.
//
// Tags (P1, B1, G1, section A) are DERIVED BY THE BACKEND. The tables, the plan
// canvas and the side view all read them from here, so a tag drawn on a bay and
// a tag printed in a row can never disagree — which is the whole point of tagging
// a drawing against a schedule.

import { apiGet } from "./api.js";
import { emit, on, state } from "./state.js";

let report = null;      // last fetched StructureReport
let runId = null;       // the run it belongs to
let inFlight = null;
let inFlightFor = null; // the run id that fetch was started for
let tags = new Map();   // element id -> tag, built once per report
// why the last attempt found nothing (409s are real states, not failures):
// "topology" (the drawing moved) | "catalog" (products changed) | null (no attempt yet)
let staleReason = null;

export function getReport() {
  return report;
}

export async function loadStructure() {
  const wanted = state.result?.run?.id || null;
  if (!wanted) {
    report = null; runId = null; tags = new Map(); staleReason = null;
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
      report = doc; runId = wanted; tags = indexTags(doc); staleReason = null;
      return doc;
    })
    .catch((err) => {
      report = null; runId = null; tags = new Map();
      // 409: the run no longer matches something it was read against.
      // 400 run_predates_fence_model: the run is older than fence models, so it
      // cannot be laid out at all — a real, nameable state, NOT "no structure
      // yet", which is what an unrecognised failure falls back to saying.
      const msg = String(err?.message || "");
      staleReason = msg.includes("catalog_changed") ? "catalog"
        : msg.includes("topology_changed") ? "topology"
        : msg.includes("run_predates_fence_model") ? "predates" : null;
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

// "topology" | "catalog" | "predates" | null — why the last attempt failed
export function staleKind() {
  return staleReason;
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
