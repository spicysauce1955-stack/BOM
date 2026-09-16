// THE OFFICE'S QUESTION BACK — hand a job to the salesperson with what has to
// be answered first.
//
// `return_to_sales` has existed as a command since the desk was built, and no
// screen performed it: the office could only find a gap, not ask about it. The
// question travels as the salesperson will read it — verbatim, on her home
// screen and on the job — and anything more specific ("which side is the
// street?") is pinned on the drawing with the note tool before sending.
//
// DOM ownership: `#desk-actions` only, looked up in index.html.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { refusalText } from "./my-jobs.js";
import { on, reloadProject, runCommand, state } from "./state.js";
import { setTab } from "./tabs.js";
import { currentView } from "./view.js";

/** States `return_to_sales` accepts (`commands/desk.py`). Pure data, pinned
 *  against the Python row by `test_my_jobs_module.py`. */
export const RETURNABLE = ["waiting", "planning"];

/** Whether this panel has anything to offer. Pure, for node. */
export function canSendBack(view, capacity, status) {
  return view !== "sales" && (capacity === "backoffice" || capacity === "admin")
    && RETURNABLE.includes(status);
}

// The question being typed, kept across re-renders and keyed by the job. The
// hint tells the office to pin a note first — and saving a note reloads the
// project, which re-renders this panel; without this the reason typed before
// pinning was wiped by following the hint.
let draftReason = { projectId: null, text: "" };

function render() {
  const host = document.getElementById("desk-actions");
  if (!host) return;
  if (!canSendBack(currentView(), state.me?.capacity, state.project?.status)) {
    host.hidden = true;
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  host.innerHTML = `<h3>${esc(t("desk.send_back_title"))}</h3>
    <div class="meta">${esc(t("desk.send_back_hint"))}</div>
    <textarea id="desk-reason" dir="auto" rows="3"
      placeholder="${esc(t("desk.reason_placeholder"))}">${esc(
        draftReason.projectId === state.projectId ? draftReason.text : "")}</textarea>
    <div class="toolbar">
      <button id="desk-send-back">${esc(t("desk.send_back"))}</button>
    </div>
    <div id="desk-error" class="warning error" hidden></div>`;
  host.querySelector("#desk-reason").addEventListener("input", (ev) => {
    draftReason = { projectId: state.projectId, text: ev.target.value };
  });
  host.querySelector("#desk-send-back").addEventListener("click", sendBack);
}

async function sendBack() {
  const reason = document.getElementById("desk-reason")?.value ?? "";
  const box = document.getElementById("desk-error");
  if (!reason.trim()) {
    box.textContent = t("desk.reason_required");
    box.hidden = false;
    return;
  }
  const out = await runCommand(state.projectId, "return_to_sales", { reason });
  if (!out.ok) {
    box.textContent = refusalText(out);
    box.hidden = false;
    return;
  }
  draftReason = { projectId: null, text: "" };
  await reloadProject();
  setTab("queue");
}

export function initDeskActions() {
  on("project-loaded", render);
  on("view-changed", render);
  on("signed-in", render);
  on("locale-changed", render);
  render();
}
