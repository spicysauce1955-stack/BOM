// A SALESPERSON'S HOME — the jobs she sold, where each one is, and what the
// office said about it.
//
// "The sales agent home screen should be a list of his jobs; there he could see
// comments or demands from the office on his jobs, open them and see exactly
// where and what." So the list carries the office's latest word verbatim, and
// opening a job the office has written on lands on the review step: the map with
// every note pinned where it was left, and the notes read back beside it.
//
// DOM ownership: `#myjobs-list` (inside `#tab-myjobs`), `#finish-job` (the review
// step's send-or-go-home panel) and the header's `#btn-my-jobs`. All three are
// LOOKED UP in index.html, never created.
//
// The list reads `GET /api/my-jobs` and nothing else: the row the server sends is
// the row, so the list and the job can never disagree about a status.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import {
  createProject, drawingLocked, emit, on, openProject, reloadProject, runCommand, state,
} from "./state.js";
import { setTab } from "./tabs.js";
import { currentView } from "./view.js";

/** The sales words, in the order the list is read. Mirrors
 *  `lifecycle.SALES_STATUS`'s values; a node test pins the two. */
export const SALES_STATUSES = ["needs_info", "draft", "pending", "accepted", "rejected"];

/** Which step a job opens on. Pure, for node.
 *
 *  A job the office has written on opens where those notes are READ — the
 *  review step, map and notes together — because the point of opening it is to
 *  see "exactly where and what". Anything else opens at the start of the road. */
export function stepToOpen(row) {
  return row && (row.office_notes > 0 || row.sales_status === "needs_info")
    ? "review" : "job";
}

/** What the review step offers for a job in `status`. Pure, for node.
 *
 *  Only a job still in her hands can be sent: a draft, or one handed back with
 *  a question. Everything else is out of her hands, and the panel says where it
 *  is instead of offering a button the server would refuse. */
export function finishOffer(status) {
  if (status === "drafting") return { send: true, sendKey: "myjobs.send" };
  if (status === "returned") return { send: true, sendKey: "myjobs.send_answers" };
  return { send: false, sendKey: null };
}

/** A refusal from the command door, in the reader's words. The job's status
 *  arrives as a code (`planning`) and is rendered through the queue's own status
 *  words, or a Hebrew sentence would carry an English identifier. */
export function refusalText(out) {
  const params = { ...(out.params || {}) };
  if (params.status) params.status = t(`queue.status.${params.status}`);
  return t(`error.${out.code}`, params);
}

function statusWord(salesStatus) {
  return t(`myjobs.status.${salesStatus}`);
}

// ---------- the list ----------------------------------------------------------

let lastRows = [];

async function renderList() {
  const host = document.getElementById("myjobs-list");
  if (!host) return;
  host.innerHTML = `<p class="meta">${esc(t("myjobs.loading"))}</p>`;
  let rows = [];
  try {
    const r = await fetch("/api/my-jobs");
    if (!r.ok) {
      const code = (await r.json().catch(() => ({})))?.detail?.code || "not_signed_in";
      host.innerHTML = `<p class="warning error">${esc(t(`error.${code}`))}</p>`;
      return;
    }
    rows = (await r.json()).rows;
  } catch {
    host.innerHTML = `<p class="warning error">${esc(t("error.server_unreachable"))}</p>`;
    return;
  }
  lastRows = rows;
  const head = `<div class="myjobs-head">
      <h2>${esc(t("myjobs.title"))}</h2>
      <button class="primary" id="myjobs-new">${esc(t("project.create"))}</button>
    </div>`;
  if (!rows.length) {
    host.innerHTML = `${head}<p class="meta">${esc(t("myjobs.empty"))}</p>`;
    return;
  }
  // Every one of these is somebody's typed text — the customer, the address, and
  // above all the office's note, which is carried verbatim and so goes out
  // escaped and `dir="auto"`, in whatever language the office wrote it.
  host.innerHTML = `${head}<ul class="myjobs-list">${rows.map((row) => `
    <li class="myjob" data-id="${esc(row.id)}" data-status="${esc(row.sales_status)}"
        tabindex="0" role="button">
      <div class="myjob-main">
        <strong dir="auto">${esc(row.customer || row.label)}</strong>
        <span class="meta" dir="auto">${esc(row.town)}</span>
      </div>
      <span class="myjob-status">${esc(statusWord(row.sales_status))}</span>
      ${row.office_notes ? `<div class="myjob-office">
        <span class="meta">${esc(t("myjobs.office_said", { n: row.office_notes }))}</span>
        <div class="verbatim" dir="auto">${esc(row.office_latest)}</div>
      </div>` : ""}
    </li>`).join("")}</ul>`;
}

async function openRow(id) {
  const row = lastRows.find((r) => r.id === id);
  await openProject(id);
  setTab("canvas");
  emit("road-go", stepToOpen(row));
}

export function goHome() {
  setTab("myjobs");
}

// ---------- finishing a job ---------------------------------------------------

function renderFinish() {
  const host = document.getElementById("finish-job");
  if (!host) return;
  const status = state.project?.status;
  // Hers alone: the office's road hides this panel, and in the whole-app view it
  // stays empty rather than offering somebody else's "send to the office".
  if (currentView() !== "sales" || !status) { host.hidden = true; host.innerHTML = ""; return; }
  host.hidden = false;
  const offer = finishOffer(status);
  host.innerHTML = `<h3>${esc(t("myjobs.finish_title"))}</h3>
    ${offer.send ? "" : `<div class="meta">${esc(t("myjobs.locked"))}</div>`}
    <div class="meta">${esc(t("myjobs.where", {
      status: statusWord(salesWordFor(status)) }))}</div>
    <div class="toolbar">
      ${offer.send ? `<button class="primary" id="finish-send">${esc(t(offer.sendKey))}</button>` : ""}
      <button id="finish-home">${esc(t("myjobs.back_home"))}</button>
    </div>
    <div id="finish-error" class="warning error" hidden></div>`;
  host.querySelector("#finish-home").addEventListener("click", goHome);
  host.querySelector("#finish-send")?.addEventListener("click", sendToOffice);
}

// The one place the browser folds a job state into her word, for the panel
// above (the list gets it from the server). `test_my_jobs_module.py` pins it
// against `lifecycle.SALES_STATUS`.
export const SALES_WORD = {
  drafting: "draft", waiting: "pending", returned: "needs_info",
  planning: "accepted", planned: "accepted", quoted: "accepted",
  delivered: "accepted", cancelled: "rejected",
};
function salesWordFor(status) { return SALES_WORD[status] || "draft"; }

async function sendToOffice() {
  const btn = document.getElementById("finish-send");
  if (btn) btn.disabled = true;
  const out = await runCommand(state.projectId, "submit_job");
  if (!out.ok) {
    const box = document.getElementById("finish-error");
    if (box) {
      box.textContent = refusalText(out);
      box.hidden = false;
    }
    if (btn) btn.disabled = false;
    return;
  }
  // Not a topology change: no history, and `reloadProject` so the status the
  // next screen reads is the one the server just wrote.
  await reloadProject();
  goHome();
}

// ---------- wiring ------------------------------------------------------------

export function initMyJobs() {
  document.getElementById("btn-my-jobs")?.addEventListener("click", goHome);
  const list = document.getElementById("myjobs-list");
  if (list) {
    list.addEventListener("click", async (ev) => {
      if (ev.target.closest("#myjobs-new")) {
        await createProject(t("project.untitled"));
        setTab("canvas");
        emit("road-go", "job");
        return;
      }
      const item = ev.target.closest(".myjob[data-id]");
      if (item) openRow(item.dataset.id);
    });
    list.addEventListener("keydown", (ev) => {
      const item = ev.target.closest(".myjob[data-id]");
      if (item && (ev.key === "Enter" || ev.key === " ")) {
        ev.preventDefault();
        openRow(item.dataset.id);
      }
    });
  }
  on("tab-changed", (name) => { if (name === "myjobs") renderList(); });
  on("locale-changed", () => { renderFinish(); if (document.getElementById("tab-myjobs")?.classList.contains("active")) renderList(); });
  // `data-locked` hides the drawing tools on a job she has sent (style.css);
  // the editor refuses the gestures themselves (`state.drawingLocked`).
  const lock = () => {
    document.documentElement.dataset.locked = drawingLocked() ? "yes" : "no";
  };
  on("project-loaded", () => { renderFinish(); lock(); });
  on("view-changed", () => { renderFinish(); lock(); });
  // A salesperson opens on her jobs. Registered AFTER `session.js` has applied
  // the view, which it does before emitting `signed-in`.
  on("signed-in", (user) => { if (user?.capacity === "sales") goHome(); });
  renderFinish();
}
