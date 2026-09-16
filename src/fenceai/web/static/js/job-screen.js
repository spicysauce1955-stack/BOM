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
import { renderFlagMarks } from "./flag-marks.js";
import { renderJobLayers } from "./job-layers.js";
import { t } from "./i18n.js";
import { localizedByCode } from "./warnings.js";
import { renderSectionElevation } from "./section-elevation.js";
import { renderSectionMaterials } from "./section-materials.js";
import { drawingLocked, emit, on, setSelection, state } from "./state.js";
import { sentence } from "./units.js";
import { currentView } from "./view.js";

const LOADING = "loading", FAILED = "failed", READY = "ready";

let status = LOADING;
let sections = [];
let flags = [];
/** What `/flags` said it read. `""` means NO RUN, which is a different fact
 *  from "a run with nothing wrong" — and the screen says so (see `flagsHtml`).
 *  Without this, a job nobody has generated and a job generated clean render
 *  identically, and the first is the one with something to do about it. */
let flagsRunId = "";
/** Was the run `/flags` read laid out against THIS drawing?
 *
 *  A `strategy` finding's place is a STATION minted against the run's topology.
 *  Move a node and those stations describe a fence that no longer exists — a red
 *  `!` at 4000 mm of a stretch that is now 3000 mm long, drawn confidently at a
 *  spot that is not there. The route refuses to 409 (it is how somebody finds
 *  out the drawing moved) and hands over both revisions instead, so this is the
 *  screen's own conclusion from them. */
let runIsStale = false;
/** The grouped BOM for the run `/flags` read, or `null` when there is no run.
 *  `null` is the honest answer for a job nobody has generated, and the
 *  materials block renders it as such rather than as "nothing to cut". */
let grouped = null;

/** Which emphasis layers are on. They EMPHASISE and never HIDE: nothing
 *  disappears when one is off, and `job-layers.js: PROTECTED` names everything
 *  no layer may ever affect. Off by default, because the screen is complete
 *  without them — a layer here adds emphasis to a whole picture rather than
 *  restoring something that was missing. */
const layerState = { ground: false, heights: false };
/** Which project the cache is FOR. Without it, switching jobs renders the
 *  previous job's stretches under the new job's name for as long as the fetch
 *  takes — and on a failed fetch, for ever. */
let loadedFor = null;

/** Reading, or editing. Starts at reading on every job, and is NOT remembered:
 *  a mode that persisted would let somebody open tomorrow's job already holding
 *  a pencil, which is the posture this screen exists to change. Turning it on is
 *  meant to be a decision about the job in front of you. */
let editing = false;

/** Is this screen the one the reader is on? A presentation question and nothing
 *  more: what an account may DO is its capacity, checked on the server. */
export function screenApplies() {
  return currentView() === "backoffice" && !!state.projectId;
}

/** Is the office reading rather than editing? Exported for `state.js`'s lock,
 *  which needs the same answer and must not keep a second copy of it. */
export function isReading() {
  return screenApplies() && !editing;
}

/** The switch, and the sentence that says which side of it you are on.
 *
 *  **This is presentation, not protection**, and the module says so out loud
 *  because the distinction is load-bearing in this codebase: hiding is CSS,
 *  `localStorage` is editable, and what an account may DO is its capacity,
 *  checked on the server. Most routes still have no capacity check, so a person
 *  typing their own requests is not stopped by this. What it changes is the
 *  office's default POSTURE — it reads first, and edits because of something it
 *  saw, instead of landing in an editing road holding the salesperson's pencils.
 *
 *  Turning it on brings the office road back, whole: the seven steps, their
 *  panels, their tools. This module hides none of that itself — it stops setting
 *  `data-jobmode`, and every rule keyed on it lapses at once.
 */
function renderMode() {
  const host = document.getElementById("job-mode");
  if (!host) return;
  if (!screenApplies()) { host.innerHTML = ""; return; }
  host.innerHTML = `<div class="job-mode">
      <span class="job-mode-state">${esc(t(editing ? "job.mode_edit" : "job.mode_read"))}</span>
      <button type="button" id="job-mode-toggle" aria-pressed="${editing}">${
        esc(t(editing ? "job.mode_stop_editing" : "job.mode_start_editing"))}</button>
    </div>`;
  host.querySelector("#job-mode-toggle").addEventListener("click", () => {
    editing = !editing;
    render();
    // The lock is keyed on the same answer, and `editor.js` only re-reads it on
    // these two events — so saying nothing here would leave the tools visible
    // and refusing every gesture, which reads as the app being broken.
    emit("view-changed", currentView());
  });
}

/** The layer switches.
 *
 *  Checkboxes rather than a segmented control, because the layers are not
 *  alternatives — the office can want to see what a stretch stands on AND how
 *  tall it is at once, and a control that implied otherwise would be lying
 *  about the data.
 */
function renderLayerRail() {
  const host = document.getElementById("job-layers");
  if (!host) return;
  if (!screenApplies() || status !== READY || !sections.length) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = `<div class="job-layers">${
    Object.keys(layerState).map((key) => `
      <label data-on="${layerState[key] ? 1 : 0}">
        <input type="checkbox" data-layer="${key}"${layerState[key] ? " checked" : ""}>
        ${esc(t(`job.layer_${key}`))}
      </label>`).join("")}</div>`;
}

// ---------- the cards ---------------------------------------------------------

/** One stretch, at rest. Length, what it stands on, its side view, and the
 *  numbers a planner reads first.
 *
 *  Everything user-typed is escaped; every length carries a `_mm` param so the
 *  reader's display unit applies; every sentence is a locale key, so nothing
 *  here is English assembled in JS. */
function cardHtml(section) {
  // `sentence()` rather than `tu()`: it escapes the template and wraps each
  // param in `<bdi>`, which a length and a Latin surface word sitting inside a
  // Hebrew line both need. `unitParams` routes `surface` through `enumWord` —
  // `surface` is already in its ENUM_PARAMS list — so an unregistered surface
  // falls back to its own name instead of printing `surface.gravel`, which is
  // what `t(...) || …` did: `t()` returns the KEY on a miss, and a key is
  // truthy, so the fallback was dead code.
  //
  // The separator moved into the locale string for the same reason: punctuation
  // assembled in JS is punctuation no translator can move.
  return `<article class="job-card" data-run="${esc(section.run_id)}"
            tabindex="0" role="button" aria-pressed="false">
      <header class="job-card-head">
        <span class="job-card-tag sku">${esc(section.tag)}</span>
        <span class="job-card-meta">${sentence("job.card_meta", {
          length_mm: section.length_mm, surface: section.base_surface })}</span>
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

// ---------- the flags ---------------------------------------------------------

/** The findings that may be DRAWN on the plan as it stands now. */
function drawableFlags() {
  if (!runIsStale) return flags;
  return flags.filter((f) => f.source !== "strategy");
}

/** The run a flag is about, for selecting from its row. `""` when it is about
 *  the whole job — which is a real answer, not a missing one. */
function flagRun(flag) {
  for (const place of flag.places || []) {
    if (place.run_id) return place.run_id;
  }
  return "";
}

/** One row per finding, worst first — the order `report/flags.py` already put
 *  them in, never re-sorted here. Two surfaces sorting the same list by
 *  different rules is how a screen and its own summary come to disagree.
 *
 *  **Every row clicks through to its geometry.** A list that does not is the
 *  documented way a review surface dies: the industry's cautionary tale is a
 *  dialog of a thousand unlinked warnings, where the volume is what hides the
 *  critical ones.
 */
function flagsHtml() {
  const stale = runIsStale
    ? `<p class="job-stale">${esc(t("job.run_stale"))}</p>` : "";
  if (!flags.length) {
    if (stale) return stale;
    // Three answers, not two. "Nothing is wrong" and "nothing has been worked
    // out yet" look identical on an empty list, and only one of them means the
    // office has something to do.
    return `<p class="job-flags-empty meta">${esc(t(
      flagsRunId ? "job.flags_clear" : "job.flags_ungenerated"))}</p>`;
  }
  return stale + `<h3 class="job-sections-title">${esc(t("job.flags"))}</h3>` +
    `<ul class="job-flag-list">${flags.map((flag) => {
      const run = flagRun(flag);
      return `<li class="job-flag" data-sev="${esc(flag.severity)}"
                ${run ? `data-run="${esc(run)}" tabindex="0" role="button"` : ""}>
          <span class="job-flag-glyph" aria-hidden="true">${
            flag.severity === "blocking" ? "!" : "?"}</span>
          <span class="job-flag-sev">${esc(t(`job.sev.${flag.severity}`))}</span>
          <span class="job-flag-text">${flagText(flag)}</span>
        </li>`;
    }).join("")}</ul>`;
}

/** Which bundle a finding's sentence lives in.
 *
 *  Three namespaces, because three read models emit these and each owns its
 *  own. Guessing one would leave two-thirds of the codes rendering as their raw
 *  key — which is how eight `readiness.*` entries nearly shipped unreachable,
 *  guarded on the Python side and by nothing on the render side.
 */
const NAMESPACE = { handover: "handover", readiness: "readiness", strategy: "warning" };

/** A finding's sentence.
 *
 *  Rendered by `warnings.js: localizedByCode`, which already owns this and owns
 *  it better. Writing it here with `sentence()` looked like three lines and lost
 *  three behaviours:
 *
 *  * **the fallback.** `t()` returns the KEY when there is no entry, so an
 *    unregistered code printed `warning.foo` on screen in both languages. Codes
 *    are an OPEN registry in this system — CLAUDE.md says adding one is not an
 *    amendment — so a code with no bundle entry is the expected case, not a bug,
 *    and the English `message` the backend already carries is what it falls back
 *    to.
 *  * **`paramText`.** `sentence()` does `String(v)`, and these params are a bare
 *    dict: `run_ids` is a list and renders comma-joined with no spaces, and a
 *    structured param renders `[object Object]`. That shipped once already,
 *    which is why `warnings.js` has the function.
 *  * **`labelledParams`.** Several warning sentences carry `{pegs}`, a param
 *    only `warnings.js` synthesizes from `element_refs`. Through a hand-rolled
 *    renderer they print a literal `{pegs}`.
 */
function flagText(flag) {
  const ns = NAMESPACE[flag.source] || "warning";
  return localizedByCode(ns, flag.code, flag.params || {},
                         flag.message || flag.code);
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

/** Write the findings into `#job-flags` — the host this module claims in its
 *  header and, until this was fixed, never touched. */
function renderFlags() {
  const host = document.getElementById("job-flags");
  if (!host) return;
  host.innerHTML = status === READY ? flagsHtml() : "";
}

function render() {
  const host = document.getElementById("job-sections");
  const screen = document.getElementById("job-screen");
  if (!host || !screen) return;

  const applies = screenApplies();
  screen.hidden = !applies;
  // The marks go on the MAP, which is not this module's subtree — `flag-marks.js`
  // owns `#g-flags` and is the only thing that writes there. Cleared when the
  // screen does not apply, so a salesperson never inherits the office's marks.
  // A stale run's `strategy` findings keep their ROW and lose their MARK. The
  // row is still true — something is wrong with this job — but the station it
  // names belongs to a drawing that has since moved, and a mark is a claim
  // about a spot. The handover findings are unaffected: they are placed on
  // runs, which are the drawing itself.
  renderFlagMarks(applies ? drawableFlags() : [], { onSelect: selectRun });
  // Erased when the screen does not apply — one call with everything off is how
  // a salesperson never inherits the office's bands.
  renderJobLayers(applies ? sections : [], applies ? layerState : {});
  // REMOVED rather than set to "", for `road.js`'s reason about `data-step`: an
  // absent attribute matches no `html[data-jobmode="…"]` rule, while an empty
  // one is a value somebody will eventually write a selector against.
  // Set only while READING. Editing removes it, and every rule keyed on it —
  // the emptied side column, the hidden toolbar, the hidden road — lapses
  // together, so the office road comes back exactly as it was.
  if (applies && !editing) document.documentElement.dataset.jobmode = "read";
  else delete document.documentElement.dataset.jobmode;
  // The lock reads this. One writer, one answer — `drawingLockedFor` must not
  // keep a second copy of "is the office reading".
  state.officeReading = isReading();
  document.documentElement.dataset.locked = drawingLocked() ? "yes" : "no";
  if (!applies) { host.innerHTML = ""; return; }

  renderMode();
  renderLayerRail();

  // Flags render into their OWN host, and BEFORE the three early returns
  // below. Folded into `#job-sections` they sat behind the sections state
  // machine, so a job with nothing drawn rendered "nothing has been drawn" and
  // silently dropped every finding — including the ones that are about a job
  // with nothing drawn, which are the only findings such a job has.
  renderFlags();

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
    const card = host.querySelector(
      `.job-card[data-run="${CSS.escape(section.run_id)}"]`);
    // Appended as a NODE for the elevation's reason: the module returns a
    // detached element, which is what keeps it free of innerHTML and of
    // anything to escape. Re-appended on every render because `render()`
    // rebuilds the markup.
    if (card) card.appendChild(renderSectionMaterials(grouped, section.run_id, {}));
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
  // **Nothing is fetched for a screen nobody is looking at.** Every job load in
  // the sales view was costing two requests for a surface that is hidden — and
  // `/flags` runs the whole supply and pricing pass, so it was the expensive
  // one. Beyond the waste, the latency was real: it made an existing check in
  // the browser suite read a panel one project behind, which is the kind of
  // flake that gets written off as "the smoke is slow" rather than fixed.
  // `view-changed` calls this again the moment the office does look.
  if (!screenApplies()) {
    sections = []; flags = []; flagsRunId = ""; runIsStale = false;
    grouped = null; loadedFor = null;
    status = READY;
    render();
    return;
  }
  status = LOADING;
  loadedFor = projectId;
  render();
  let body, flagBody;
  try {
    // Both at once: they answer different halves of one screen, and fetching
    // them in series would show the stretches for a beat before anything said
    // what was wrong with them.
    const [sectionsRes, flagsRes] = await Promise.all([
      fetch(`/api/projects/${projectId}/sections`),
      fetch(`/api/projects/${projectId}/flags`),
    ]);
    if (!sectionsRes.ok || !flagsRes.ok) throw new Error("not ok");
    [body, flagBody] = await Promise.all([sectionsRes.json(), flagsRes.json()]);
    // The BOM is a SECOND round trip because it needs the run id the first one
    // answers, and it is skipped entirely when there is no run — which is both
    // cheaper and more honest than asking for the materials of a job nobody has
    // worked out.
    grouped = null;
    if (flagBody.run_id) {
      const bomRes = await fetch(`/api/runs/${flagBody.run_id}/bom`);
      if (bomRes.ok) grouped = (await bomRes.json()).grouped || null;
    }
  } catch {
    // The cache is NOT kept: a failed reload must not leave the previous job's
    // stretches on screen under this job's name.
    if (loadedFor !== projectId) return;
    sections = [];
    flags = [];
    flagsRunId = "";
    runIsStale = false;
    grouped = null;
    status = FAILED;
    render();
    return;
  }
  // A slower answer for a job the reader has already left is thrown away.
  if (loadedFor !== projectId) return;
  sections = body.sections || [];
  flags = flagBody.flags || [];
  flagsRunId = flagBody.run_id || "";
  runIsStale = !!flagsRunId
    && flagBody.run_topology_revision !== flagBody.topology_revision;
  status = READY;
  render();
}

// ---------- wiring ------------------------------------------------------------

/** A card or a finding: clicking either selects the stretch it is about.
 *
 *  One implementation for both hosts. Two would be two answers to one question,
 *  and the click-through rule (spec §4) is that a finding reaches its geometry
 *  by exactly the path a card does.
 */
function wireSelection(hostId) {
  const host = document.getElementById(hostId);
  if (!host) return;
  const target = (ev) => ev.target.closest("[data-run]");
  host.addEventListener("click", (ev) => {
    const el = target(ev);
    if (el) selectRun(el.dataset.run);
  });
  host.addEventListener("keydown", (ev) => {
    const el = target(ev);
    if (el && (ev.key === "Enter" || ev.key === " ")) {
      ev.preventDefault();
      selectRun(el.dataset.run);
    }
  });
}

export function initJobScreen() {
  // BOTH hosts. The cards live in one and the findings in the other, and they
  // do the SAME thing — select the stretch they are about. Wiring only the
  // cards is how moving the flag list into its own host made every finding
  // unclickable while the suite stayed green on everything else.
  for (const id of ["job-sections", "job-flags"]) wireSelection(id);
  document.getElementById("job-layers")?.addEventListener("change", (ev) => {
    const key = ev.target.getAttribute("data-layer");
    if (!(key in layerState)) return;
    layerState[key] = ev.target.checked;
    render();
  });
  on("project-loaded", () => {
    // Reset only when the JOB changes, never on a reload of the same one.
    // `reloadProject()` fires this after every desk command — acknowledge the
    // sale, commit a plan — so resetting here switched editing off underneath
    // somebody in the middle of working, which in the browser suite showed up
    // as the office road vanishing three checks after it was turned on.
    if (state.projectId !== loadedFor) editing = false;
    load();
  });
  on("view-changed", () => { render(); if (screenApplies() && loadedFor !== state.projectId) load(); });
  on("locale-changed", render);
  on("units-changed", render);
  on("selection-changed", paintSelection);
  render();
}

/** Select a stretch from the list, and frame it on the map.
 *
 *  Clicking the card a second time clears the selection, so there is a way back
 *  to the whole job that is not "find the one empty spot on the map".
 *
 *  **The fit happens HERE and not on `selection-changed`**, which is the
 *  difference between a map that follows you and one that fights you. That
 *  event fires from six places — a click on the canvas, the side view's
 *  dropdown, a setting-out row, the run picker — and re-framing on all of them
 *  would zoom the map out from under somebody who had just clicked a post on
 *  it. Choosing a stretch from this list is the one gesture that MEANS "show me
 *  that stretch".
 */
async function selectRun(runId) {
  const same = state.selection?.runId === runId;
  const next = same ? null : runId;
  setSelection({ runId: next });
  // Imported lazily: `editor.js` is the biggest module on the page and this one
  // has no other reason to depend on it, so the cost is paid by the first
  // person who clicks a card rather than by every page load.
  const { fitToRun } = await import("./editor.js");
  fitToRun(next || "");
}
