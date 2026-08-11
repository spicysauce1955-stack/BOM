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
let tags = new Map();   // element id -> tag, built once per report

export function getReport() {
  return report;
}

export async function loadStructure() {
  const wanted = state.result?.run?.id || null;
  if (!wanted) {
    report = null; runId = null; tags = new Map();
    emit("structure-loaded", null); return null;
  }
  if (runId === wanted && report) return report;
  if (inFlight) return inFlight;
  inFlight = apiGet(`/api/runs/${wanted}/structure`)
    .then((doc) => {
      report = doc;
      runId = wanted;
      tags = indexTags(doc);
      return doc;
    })
    .catch(() => { report = null; runId = null; tags = new Map(); return null; })
    .finally(() => { inFlight = null; });
  const doc = await inFlight;
  emit("structure-loaded", doc);
  return doc;
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
}
