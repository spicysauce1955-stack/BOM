// THE OFFICE'S READING SURFACE — a job it did not draw, laid out to be understood.
//
// The office used to land on step 1 of an EDITING road, holding the
// salesperson's pencils, with her customer and address in a form with a Save
// button under it. Nothing on that screen said what the job WAS. This is what
// it lands on instead: the plan in the middle, every stretch open beside it with
// its own side view, and every problem marked where it actually is.
//
// **It does not draw the plan.** The map is `#canvas`, rendered by
// `js/editor.js`, and a second plan renderer would be a second implementation of
// the drawing — the thing this repo forbids everywhere else. So this module is a
// LAYOUT around the canvas rather than a screen beside it: it owns `#job-screen`
// in the side column, and `html[data-jobmode="read"]` is what empties the rest of
// that column. That is also why it is not a tab: "a map in the centre" is what
// the canvas column already is.
//
// DOM ownership: `#job-screen` and its three children — `#job-mode`,
// `#job-flags`, `#job-sections`. All four are LOOKED UP in index.html, never
// created. It talks to the rest of the app only through `state.js`.
//
// **Four states, never two.** Not yet loaded, loaded and empty, loaded and
// stale, failed. `cache?.sections || []` would render a 500 as "this job has no
// fence", which is audit finding B01 wearing a different hat: a failed
// `/handover` fetch once rendered as "Nothing missing — this job is ready to
// hand over" on a project with zero runs.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { renderSectionElevation } from "./section-elevation.js";
import { on, setSelection, state } from "./state.js";
import { sentence, tu } from "./units.js";
import { currentView } from "./view.js";

const LOADING = "loading", FAILED = "failed", READY = "ready";

let status = LOADING;
let sections = [];
/** Which project the cache is FOR. Without it, switching jobs renders the
 *  previous job's stretches under the new job's name for as long as the fetch
 *  takes — and on a failed fetch, for ever. */
let loadedFor = null;

/** Is this screen the one the reader is on? A presentation question and nothing
 *  more: what an account may DO is its capacity, checked on the server. */
export function screenApplies() {
  return currentView() === "backoffice" && !!state.projectId;
}

// ---------- the cards ---------------------------------------------------------

/** One stretch, at rest. Length, what it stands on, its side view, and the
 *  numbers a planner reads first.
 *
 *  Everything user-typed is escaped; every length goes through `tu()` so a `cm`
 *  display preference changes it; every sentence is a locale key, so nothing
 *  here is English assembled in JS. */
function cardHtml(section) {
  const surface = t(`surface.${section.base_surface}`) || section.base_surface;
  return `<article class="job-card" data-run="${esc(section.run_id)}"
            tabindex="0" role="button" aria-pressed="false">
      <header class="job-card-head">
        <span class="job-card-tag">${esc(section.tag)}</span>
        <span class="job-card-meta">${tu("job.card_meta", {
          length_mm: section.length_mm })} · ${esc(surface)}</span>
      </header>
      <div class="job-card-elev"></div>
      <dl class="job-card-facts">
        <dt>${esc(t("job.fact_height"))}</dt>
        <dd>${heightText(section)}</dd>
        <dt>${esc(t("job.fact_slope"))}</dt>
        <dd>${sentence("job.slope", { permille: section.max_slope_permille })}</dd>
      </dl>
    </article>`;
}

/** What this stretch's height is, in the three states it genuinely has.
 *
 *  A stated height covering all of it is a fact. A stated height covering PART
 *  of it is the one the office has to see — `handover.py` exists because "a
 *  height stated over the first metre of five" reported as complete once — and
 *  nothing stated at all is the silent 1800 default that looks decided by the
 *  time a strategy exists.
 */
function heightText(section) {
  if (section.height_intent_mm === null || section.height_intent_mm === undefined) {
    return section.height_covered_mm > 0
      ? sentence("job.height_mixed", { covered_mm: section.height_covered_mm })
      : esc(t("job.height_unstated"));
  }
  if (section.height_covered_mm < section.length_mm) {
    return sentence("job.height_partial", {
      height_mm: section.height_intent_mm,
      covered_mm: section.height_covered_mm,
      length_mm: section.length_mm });
  }
  return sentence("job.height_stated", { height_mm: section.height_intent_mm });
}

/** What was sold, as text.
 *
 *  Reading mode hides `#job-panel` — her customer and address in an editable
 *  form with a Save button, which is the complaint this whole screen answers —
 *  so the same four facts have to be READABLE somewhere, or hiding the form
 *  would have taken the sale off the office's screen entirely.
 *
 *  Rendered as a description list rather than as disabled inputs. A disabled
 *  control is skipped by screen readers and fails contrast, and a read-first
 *  surface should look like a document rather than a form somebody switched
 *  off. Every value is somebody's typed text, so every value is escaped.
 */
function saleHtml() {
  const job = state.project?.job;
  if (!job) return "";
  const rows = [
    ["job.sale_customer", job.customer],
    ["job.sale_address", job.address],
    ["job.sale_by", job.sold_by],
    ["job.sale_on", job.sold_on],
  ].filter(([, v]) => v);
  if (!rows.length) return "";
  return `<section class="job-sale">
      <h3>${esc(t("job.sale"))}</h3>
      <dl>${rows.map(([k, v]) =>
        `<dt>${esc(t(k))}</dt><dd dir="auto">${esc(v)}</dd>`).join("")}</dl>
    </section>`;
}

function render() {
  const host = document.getElementById("job-sections");
  const screen = document.getElementById("job-screen");
  if (!host || !screen) return;

  const applies = screenApplies();
  screen.hidden = !applies;
  // REMOVED rather than set to "", for `road.js`'s reason about `data-step`: an
  // absent attribute matches no `html[data-jobmode="…"]` rule, while an empty
  // one is a value somebody will eventually write a selector against.
  if (applies) document.documentElement.dataset.jobmode = "read";
  else delete document.documentElement.dataset.jobmode;
  if (!applies) { host.innerHTML = ""; return; }

  if (status === LOADING) {
    host.innerHTML = `<p class="meta">${esc(t("job.loading"))}</p>`;
    return;
  }
  if (status === FAILED) {
    // Said out loud. An empty list here would read as "this job has no fence",
    // which is a wrong answer shaped exactly like a right one.
    host.innerHTML = `<p class="warning error">${esc(t("job.failed"))}</p>`;
    return;
  }
  if (!sections.length) {
    host.innerHTML = `<p class="meta">${esc(t("job.nothing_drawn"))}</p>`;
    return;
  }

  host.innerHTML = saleHtml() +
    `<h3 class="job-sections-title">${esc(t("job.sections"))}</h3>` +
    sections.map(cardHtml).join("");

  // The drawings are DOM nodes rather than markup: `section-elevation.js`
  // returns a detached element, which is what keeps it free of innerHTML and of
  // anything to escape.
  for (const section of sections) {
    const slot = host.querySelector(
      `.job-card[data-run="${CSS.escape(section.run_id)}"] .job-card-elev`);
    if (slot) {
      slot.appendChild(renderSectionElevation(section, {
        width: 300, height: 74,
        label: t("job.elev_label", { tag: section.tag }),
      }));
    }
  }
  paintSelection();
}

/** Only the selected state, so choosing a stretch does not rebuild the
 *  drawings — and never writes the selection, which would be a loop. */
function paintSelection() {
  const runId = state.selection?.runId || null;
  for (const card of document.querySelectorAll("#job-sections .job-card")) {
    const on_ = card.dataset.run === runId;
    card.dataset.on = on_ ? "1" : "0";
    card.setAttribute("aria-pressed", on_ ? "true" : "false");
  }
}

// ---------- loading -----------------------------------------------------------

async function load() {
  const projectId = state.projectId;
  if (!projectId) { sections = []; status = READY; loadedFor = null; render(); return; }
  status = LOADING;
  loadedFor = projectId;
  render();
  let body;
  try {
    const r = await fetch(`/api/projects/${projectId}/sections`);
    if (!r.ok) throw new Error(String(r.status));
    body = await r.json();
  } catch {
    // The cache is NOT kept: a failed reload must not leave the previous job's
    // stretches on screen under this job's name.
    if (loadedFor !== projectId) return;
    sections = [];
    status = FAILED;
    render();
    return;
  }
  // A slower answer for a job the reader has already left is thrown away.
  if (loadedFor !== projectId) return;
  sections = body.sections || [];
  status = READY;
  render();
}

// ---------- wiring ------------------------------------------------------------

export function initJobScreen() {
  const host = document.getElementById("job-sections");
  if (host) {
    host.addEventListener("click", (ev) => {
      const card = ev.target.closest(".job-card[data-run]");
      if (card) selectRun(card.dataset.run);
    });
    host.addEventListener("keydown", (ev) => {
      const card = ev.target.closest(".job-card[data-run]");
      if (card && (ev.key === "Enter" || ev.key === " ")) {
        ev.preventDefault();
        selectRun(card.dataset.run);
      }
    });
  }
  on("project-loaded", load);
  on("view-changed", () => { render(); if (screenApplies() && loadedFor !== state.projectId) load(); });
  on("locale-changed", render);
  on("units-changed", render);
  on("selection-changed", paintSelection);
  render();
}

/** Clicking the card a second time clears the selection, so there is a way back
 *  to the whole job that is not "find the one empty spot on the map". */
function selectRun(runId) {
  const same = state.selection?.runId === runId;
  setSelection(same ? { runId: null } : { runId });
}
