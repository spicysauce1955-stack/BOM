// What the office still needs, and an estimate that says it is an estimate —
// slice 4 of the salesperson MVP.
//
// The MVP's success condition is *a sold job, captured completely enough that
// the office person never has to phone the salesperson*. This panel is the
// deliverable: the questions the office would otherwise ring up and ask, shown
// to the salesperson while they can still answer them.
//
// **Reported, never enforced.** A sheet that refused to hand over an incomplete
// job would be worked around within a week. The one exception is narrow and
// lives on the backend: a BLOCKING item withholds the ESTIMATE, because a price
// for a fence with no model chosen is a number with nothing behind it.
//
// **The estimate is not a quote and must never read as one.** A `Quote` in this
// system is an immutable document with a status lifecycle that somebody stands
// behind. This is a number computed from what has been recorded so far, and the
// salesperson closed the sale at the house from experience anyway — so the words
// around it carry more weight than the digits, and they are locale entries
// rather than anything assembled here.

import { apiGet, esc } from "./api.js";
import { t } from "./i18n.js";
import { emit, on, state } from "./state.js";
import { money, tu } from "./units.js";

// Three states, not two, and that is audit finding B01
// (`docs/visualizations/salesperson-mvp/sales-ui-audit.md`): a 500 on
// `/handover` set `cache = null`, `cache?.gaps || []` read as an empty list, and
// an empty list rendered as "Nothing missing — this job is ready to hand over."
// on a project with ZERO runs. Readiness may only be established by a
// successful response for the current job; not-yet-loaded and failed must both
// say so instead of inheriting the happiest reading.
const LOADING = "loading", FAILED = "failed", CHECKED = "checked";
let status = LOADING;
let cache = null;   // last successful /handover payload
let total = null;   // last BOM total in cents, or null for "no run yet"

/** True when the number may be shown at all. Mirrors the backend's own answer
 *  rather than recomputing it: two opinions about whether a price is meaningful
 *  is exactly one too many. */
export function estimateReady(handover, bomTotalCents) {
  return Boolean(handover?.estimate_ready) && Number.isFinite(bomTotalCents);
}

/** Whether "nothing missing" may be SHOWN. Separate from "the gap list is
 *  empty", because those coincide only when a check actually succeeded — the
 *  conflation audit B01 reproduced. */
export function readinessShown(state_, handover) {
  return state_ === CHECKED && (handover?.gaps || []).length === 0;
}

/** The sentence under the number. Separate and pure so the rule — an estimate
 *  computed from an incomplete layout must SAY it is incomplete — is testable
 *  without a browser and without a price. */
export function estimateNoteKey(handover, bomTotalCents) {
  if (!handover?.estimate_ready) return "handover.estimate_blocked";
  if (!Number.isFinite(bomTotalCents)) return "handover.estimate_needs_run";
  return (handover.gaps || []).length ? "handover.estimate_stale"
                                      : "handover.estimate_note";
}

function gapSentence(gap) {
  // `code` + `params` through the bundle, never a sentence built here: English
  // assembled in JS reaches a Hebrew-first reader as English. `u` is supplied
  // for the length-bearing item so `{height_mm} {u}` renders in the reader's
  // own display unit rather than always in millimetres.
  // Any item carrying a LENGTH goes through `tu`, which converts and supplies
  // `{u}` — `uncovered_mm` made that two items rather than one, and a literal
  // millimetre figure in a centimetre-mode sentence is the exact defect the
  // `{…_mm}` + `{u}` convention exists to prevent.
  const params = gap.params || {};
  return params.uncovered_mm !== undefined || params.height_mm !== undefined
    ? tu(`handover.${gap.code}`, params)
    : t(`handover.${gap.code}`, params);
}

function render() {
  const host = ensureHost();
  if (!host) return;
  const gaps = status === CHECKED ? (cache.gaps || []) : [];
  const noteKey = estimateNoteKey(cache, total);
  const showNumber = estimateReady(cache, total);
  const summary = gaps.length
    ? `<div class="meta">${esc(t("handover.intro"))}</div>
       <ul class="handover-gaps">${gaps.map((g) => `
         <li class="${g.blocking ? "blocking" : ""}">${esc(gapSentence(g))}</li>`
       ).join("")}</ul>`
    : readinessShown(status, cache)
      ? `<div class="handover-ready">${esc(t("handover.ready"))}</div>`
      // Never "ready". An unknown state reads as unknown, because the one thing
      // this panel must not do is tell somebody their job is complete when
      // nobody checked.
      : `<div class="handover-unknown meta">${
          esc(t(status === FAILED ? "handover.unavailable" : "handover.checking"))
        }</div>`;
  host.innerHTML = `
    <h3>${esc(t("handover.title"))}</h3>
    ${summary}
    <div class="handover-estimate">
      ${showNumber
        ? `<div class="handover-amount">
             <span class="handover-amount-label">${esc(t("handover.estimate"))}</span>
             <span class="num">${esc(money(total))}</span>
           </div>`
        : ""}
      <div class="meta">${esc(t(noteKey))}</div>
    </div>`;
}

async function refresh() {
  if (!state.projectId) return;
  try {
    cache = await apiGet(`/api/projects/${state.projectId}/handover`);
    status = CHECKED;
  } catch {
    // The previous payload is dropped along with the status: a stale list beside
    // a fresh drawing is a different wrong answer, not a safer one.
    cache = null;
    status = FAILED;
  }
  // `road.js` reads this SAME payload rather than issuing its own request —
  // "one request is behind both the road and the estimate" (road-model.js).
  // A failed check publishes `null`, same as this panel: the road must read
  // `unknown` rather than inherit whatever gap list happened to load last.
  state.handover = cache;
  emit("handover-changed", cache);
  // The BOM is fetched only when a run exists — asking for a price before
  // anything has been generated would 404 on every keystroke, and "no run yet"
  // is a state with its own sentence rather than an error.
  total = null;
  if (state.result?.run?.id) {
    try {
      const doc = await apiGet(`/api/runs/${state.result.run.id}/bom`);
      // `doc.bom.total_cents`, not `doc.total_cents`. The route returns the
      // whole priced supply run — requirements, unresolved, supply, grouped —
      // with the `Bom` nested inside it, and the outer object has no total at
      // all. Reading the wrong path yields `undefined`, which is not finite, so
      // the panel silently fell back to "press ⚙ to see an estimate" for
      // somebody who just had.
      total = Number.isFinite(doc?.bom?.total_cents) ? doc.bom.total_cents : null;
    } catch {
      total = null;
    }
  }
  render();
}

function ensureHost() {
  if (typeof document === "undefined") return null;
  let host = document.getElementById("handover-panel");
  if (host) return host;
  const side = document.querySelector(".side-col");
  if (!side) return null;
  host = document.createElement("div");
  host.className = "panel";
  host.id = "handover-panel";
  // Last in the column: it is what you read when you are finished, not while
  // you are drawing.
  side.appendChild(host);
  return host;
}

export function initHandover() {
  render();
  refresh();
  on("project-loaded", refresh);
  on("result-changed", refresh);
  on("context-changed", refresh);
  on("job-changed", refresh);
  on("locale-changed", render);
  on("units-changed", render);
  on("role-changed", render);
}
