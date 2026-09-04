// Who bought this fence, where, who sold it and when — slice 1 of the
// salesperson MVP.
//
// `Project` was `id, name`, so every screen after the first read as "project 7".
// This panel is what makes the rest of the page read as a real job, and it is
// the first thing the office person looks for when the layout reaches them.
//
// It owns its own host, like `choices.js`: index.html is not this module's file,
// and reaching into another module's subtree is what the frontend map forbids.
// It sits at the TOP of the side column, above what the fence is built from,
// because whose fence it is comes before what it is made of.

import { apiSend, esc } from "./api.js";
import { t } from "./i18n.js";
import { emit, on, reloadProject, state } from "./state.js";

const FIELDS = ["customer", "address", "sold_by", "sold_on"];

/** The job as a person would say it: customer first, because that is how a
 *  salesperson refers to a job out loud, with the address to tell two fences for
 *  the same person apart. Mirrors `Job.label()` on the backend — the picker is
 *  rendered from the API's own `label`, so this is only for the panel heading
 *  before a reload has happened. */
export function jobLabel(job) {
  if (!job) return "";
  const parts = [job.customer, job.address].filter(Boolean);
  if (parts.length) return parts.join(" — ");
  return job.sold_by || job.sold_on || "";
}

/** Which fields are still blank.
 *
 *  Reported, never enforced. A salesperson enters this after the visit from
 *  paper notes, so refusing to save a job because the address has not been typed
 *  yet would make the first field they fill in the one that blocks them. Slice 4
 *  turns this into the handover sheet's "what the office still needs"; here it
 *  is only the quiet hint under the panel.
 */
export function missingFields(job) {
  return FIELDS.filter((f) => !(job && job[f]));
}

function render() {
  const host = ensureHost();
  if (!host) return;
  const job = state.project?.job || null;
  const missing = missingFields(job);
  const rows = FIELDS.map((f) => `
    <label class="job-field">
      <span>${esc(t(`job.${f}`))}</span>
      <input id="job-${f}" type="${f === "sold_on" ? "date" : "text"}"
             value="${esc(job?.[f] || "")}"
             ${f === "sold_on" ? "" :
               `placeholder="${esc(t(`job.${f}.placeholder`))}"`}>
    </label>`).join("");
  host.innerHTML = `
    <h3>${esc(t("job.title"))}</h3>
    <div class="job-fields">${rows}</div>
    <div class="job-actions">
      <button id="job-save">${esc(t("job.save"))}</button>
      <span id="job-status" class="meta"></span>
    </div>
    ${missing.length ? `<div class="job-missing meta">${
      esc(t("job.missing", { fields: missing.map((f) => t(`job.${f}`)).join(", ") }))
    }</div>` : ""}`;
  host.querySelector("#job-save").addEventListener("click", save);
}

async function save() {
  const body = {};
  for (const f of FIELDS)
    body[f] = document.getElementById(`job-${f}`).value.trim();
  const status = document.getElementById("job-status");
  // A job with nothing in it is refused by the model — `job is not None` would
  // otherwise be a lie the handover sheet reports as an identified job. Caught
  // here so the reader gets a sentence instead of a 422.
  if (!FIELDS.some((f) => body[f])) {
    status.textContent = t("job.needs_something");
    return;
  }
  try {
    await apiSend("PUT", `/api/projects/${state.projectId}/job`, body);
    // `reloadProject`, never `openProject`: this is a non-topology mutation and
    // reopening would wipe the undo stack the salesperson has been building.
    await reloadProject();
    // The picker is rebuilt only when a project is CREATED, so without this the
    // job stays labelled by whatever it was called before it was a job — which
    // is the exact surface ("project 7") this slice exists to fix. Announced
    // rather than reached for: `refreshProjectList` belongs to app.js, and a
    // module reaching into another's business is what the frontend map forbids.
    emit("job-changed", state.project?.job || null);
    status.textContent = t("job.saved");
  } catch (e) {
    status.textContent = String(e.message || e);
  }
}

function ensureHost() {
  if (typeof document === "undefined") return null;
  let host = document.getElementById("job-panel");
  if (host) return host;
  const side = document.querySelector(".side-col");
  if (!side) return null;
  host = document.createElement("div");
  host.className = "panel";
  host.id = "job-panel";
  side.insertBefore(host, side.firstChild);
  return host;
}

export function initJob() {
  render();
  on("project-loaded", render);
  on("locale-changed", render);
  // The words change with the role too (`sales.job.*` beats `job.*`), and this
  // panel renders through `t()` at render time rather than through the static
  // pass — so unlike index.html's labels it needs telling.
  on("role-changed", render);
}
