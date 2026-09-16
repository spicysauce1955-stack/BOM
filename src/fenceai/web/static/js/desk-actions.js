// THE OFFICE'S CONTROLS FOR THE STEP IT IS ON — the acts that move a job, as
// opposed to the edits that fill one in.
//
// Every one of these was a command with no screen. `return_to_sales` existed and
// the office could only find a gap, not ask about it; `acknowledge_sale` and
// `acknowledge_warnings` are the one thing the system cannot work out for itself
// and steps 1 and 4 turned on them; `commit_plan` is the decision itself —
// generating is cheap and repeated, and until it was pressable a project
// accumulated runs with none marked as the one people build from (backoffice
// design §7), which is why steps 6 and 7 read amber on every job.
//
// ONE panel, keyed on the step, rather than four panels each scoped to one step:
// what it offers is "the thing this step is for", and `step-surfaces.js` already
// decides which steps show it. A second host per act would be four entries in
// three maps and a stylesheet copy, for four buttons that are never on screen
// together.
//
// DOM ownership: `#desk-actions` in the canvas column and `#desk-actions-plan`
// on the structure sheet — both looked up in index.html, never created. Two
// hosts because the office road's PLAN step is read on the sheet and every other
// step on the canvas, and a panel in the canvas column is simply not on screen
// there; `hostFor` picks by step and the other host is emptied, so the same act
// can never be drawn twice.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { emit, on, reloadProject, runCommand, state } from "./state.js";
import { setTab } from "./tabs.js";
import { currentView } from "./view.js";
import { refusalText } from "./my-jobs.js";

/** States `return_to_sales` accepts (`commands/desk.py`). Pure data, pinned
 *  against the Python row by `test_my_jobs_module.py`. */
export const RETURNABLE = ["waiting", "planning"];

/** ...and `commit_plan`'s, for the same reason. Committing from `planned` is
 *  refused on purpose: changing the answer goes back through `planning`, so a
 *  plan somebody may be building from cannot be swapped by one click. */
export const COMMITTABLE = ["planning"];

/** ...and `revise_plan`'s: taking the committed plan back so it can be planned
 *  again. Without it `planned` is a one-way door and a plan that has gone stale
 *  can only be corrected by rejecting the job, which the salesperson reads as
 *  REJECTED for what was an office decision. */
export const REVISABLE = ["planned", "quoted"];

/** Every OPEN state — what `cancel_job` accepts. A finished job is not rejected
 *  again, and offering the button there would be a refusal waiting to happen. */
export const CANCELLABLE = ["drafting", "waiting", "planning", "planned", "quoted",
                            "returned"];

/** Is this an office person looking at somebody's job? Every control here is
 *  the office's; the sales view never shows this panel at all. */
export function isDeskUser(view, capacity) {
  return view !== "sales" && (capacity === "backoffice" || capacity === "admin");
}

/** Whether this panel has anything to offer. Pure, for node. */
export function canSendBack(view, capacity, status) {
  return isDeskUser(view, capacity) && RETURNABLE.includes(status);
}

/** What the panel offers on this step of the office road. Pure, for node —
 *  the acts are data here and the DOM below only draws them.
 *
 *  `null` where the step has no act of its own: the blanks step is filling
 *  things in, and the road's own Done button carries it.
 */
export function deskActs(step, status, hasRun) {
  const acts = [];
  // Only while the job is OPEN. Reading what she sold is part of doing the work,
  // and a cancelled or delivered job has none left — the button would record an
  // acknowledgement nobody acts on.
  if (step === "sale" && CANCELLABLE.includes(status)) acts.push("acknowledge_sale");
  if (step === "generate" && hasRun) acts.push("acknowledge_warnings");
  if (step === "plan" && hasRun && COMMITTABLE.includes(status)) acts.push("commit_plan");
  if (step === "plan" && REVISABLE.includes(status)) acts.push("revise_plan");
  if (RETURNABLE.includes(status) && (step === "sale" || step === "blanks"))
    acts.push("return_to_sales");
  // Rejecting is not a step's work — it can be the answer at any point an open
  // job is on screen, so it rides wherever the panel already shows rather than
  // getting a step of its own.
  if (acts.length && CANCELLABLE.includes(status)) acts.push("cancel_job");
  return acts;
}

// The question being typed, kept across re-renders and keyed by the job. The
// hint tells the office to pin a note first — and saving a note reloads the
// project, which re-renders this panel; without this the reason typed before
// pinning was wiped by following the hint.
let draftReason = { projectId: null, text: "" };

function runId() {
  return state.result?.run?.id || "";
}

function actHtml(act) {
  if (act === "return_to_sales") {
    return `<div class="desk-act">
      <div class="meta">${esc(t("desk.send_back_hint"))}</div>
      <textarea id="desk-reason" dir="auto" rows="3"
        placeholder="${esc(t("desk.reason_placeholder"))}">${esc(
          draftReason.projectId === state.projectId ? draftReason.text : "")}</textarea>
      <button id="desk-send-back">${esc(t("desk.send_back"))}</button>
    </div>`;
  }
  if (act === "commit_plan") {
    return `<div class="desk-act">
      <div class="meta">${esc(t("desk.commit_hint"))}</div>
      <button id="desk-commit" class="primary">${esc(t("command.commit_plan"))}</button>
    </div>`;
  }
  if (act === "revise_plan") {
    return `<div class="desk-act">
      <div class="meta">${esc(t("desk.revise_hint"))}</div>
      <button id="desk-revise">${esc(t("desk.revise"))}</button>
    </div>`;
  }
  if (act === "acknowledge_sale") {
    return `<div class="desk-act">
      <button id="desk-ack-sale">${esc(t("desk.ack_sale"))}</button>
    </div>`;
  }
  if (act === "acknowledge_warnings") {
    return `<div class="desk-act">
      <button id="desk-ack-warnings">${esc(t("desk.ack_warnings"))}</button>
    </div>`;
  }
  return `<div class="desk-act desk-reject">
    <button id="desk-cancel">${esc(t("desk.reject"))}</button>
  </div>`;
}

/** What the committed plan is, said where the commit button would be. A job
 *  whose plan is committed still has to say so — the step is otherwise a screen
 *  with nothing on it and no way to tell whether anybody decided. */
function committedHtml() {
  const committed = state.project?.committed_run_id;
  if (!committed) return "";
  // Parameterised, not concatenated: a fragment cannot be re-ordered by a
  // translator, and "<id> — is the committed plan" reads backwards in RTL.
  return `<div class="meta desk-committed">${
    esc(t("desk.committed", { run_id: committed }))}</div>`;
}

/** The two hosts this module owns. The plan step is read on the structure
 *  sheet and every other step on the canvas, so its act is drawn there. */
export const HOSTS = ["desk-actions", "desk-actions-plan"];

/** Which host this step's act belongs in. Pure, for node. */
export function hostIdFor(step) {
  return step === "plan" ? "desk-actions-plan" : "desk-actions";
}

function hostFor(step) {
  return document.getElementById(hostIdFor(step));
}

function hide(host) {
  if (!host) return;
  host.hidden = true;
  host.innerHTML = "";
}

function render() {
  const host = hostFor(state.step);
  if (!host) return;
  // The other host holds nothing: a step moves between tabs and a panel left
  // rendered on the one it came from would offer the previous step's act.
  for (const id of HOSTS)
    if (document.getElementById(id) !== host) hide(document.getElementById(id));
  const desk = isDeskUser(currentView(), state.me?.capacity);
  const acts = desk ? deskActs(state.step, state.project?.status, !!runId()) : [];
  if (!acts.length && !(desk && state.step === "plan" && state.project?.committed_run_id)) {
    hide(host);
    return;
  }
  host.hidden = false;
  host.innerHTML = `<h3>${esc(t("desk.title"))}</h3>
    ${state.step === "plan" ? committedHtml() : ""}
    ${acts.map(actHtml).join("")}
    <div id="desk-error" class="warning error" hidden></div>`;
  wire(host);
}

function wire(host) {
  host.querySelector("#desk-reason")?.addEventListener("input", (ev) => {
    draftReason = { projectId: state.projectId, text: ev.target.value };
  });
  host.querySelector("#desk-send-back")?.addEventListener("click", sendBack);
  host.querySelector("#desk-commit")?.addEventListener("click",
    () => perform("commit_plan", { run_id: runId() }));
  host.querySelector("#desk-revise")?.addEventListener("click",
    () => perform("revise_plan", {}));
  host.querySelector("#desk-ack-sale")?.addEventListener("click",
    () => perform("acknowledge_sale", {}));
  host.querySelector("#desk-ack-warnings")?.addEventListener("click",
    () => perform("acknowledge_warnings", { run_id: runId() }));
  host.querySelector("#desk-cancel")?.addEventListener("click", () => {
    // The one act here nobody can undo from a screen — `reopen_job` exists, on
    // the finished list, and a person who meant to send the job back instead
    // should not find that out afterwards.
    if (!window.confirm(t("desk.reject_confirm"))) return;
    perform("cancel_job", {});
  });
}

function showError(out) {
  const box = hostFor(state.step)?.querySelector("#desk-error");
  if (!box) return;
  box.textContent = refusalText(out);
  box.hidden = false;
}

/** Run one act, and show a refusal where the button is. The road re-reads
 *  `/readiness` on `project-loaded`, so a step that has just been satisfied
 *  stops being amber without anybody navigating. */
async function perform(kind, payload) {
  const out = await runCommand(state.projectId, kind, payload);
  if (!out.ok) { showError(out); return; }
  await reloadProject();
  // Cancelled and returned jobs leave this desk. The queue is where the next
  // one is chosen, and staying on a job nobody holds any more reads as if the
  // act had not happened.
  if (kind === "cancel_job" || kind === "return_to_sales") {
    draftReason = { projectId: null, text: "" };
    setTab("queue");
    return;
  }
  // ...and an act that FINISHES a step moves the road on, because these steps
  // suppress the road's own Done button on the grounds that they have a control
  // of their own. Taking a plan back is the exception: it undoes step 6 rather
  // than finishing it.
  if (kind !== "revise_plan") emit("road-advance");
}

async function sendBack() {
  const host = hostFor(state.step);
  const reason = host?.querySelector("#desk-reason")?.value ?? "";
  if (!reason.trim()) {
    const box = host.querySelector("#desk-error");
    box.textContent = t("desk.reason_required");
    box.hidden = false;
    return;
  }
  await perform("return_to_sales", { reason });
}

export function initDeskActions() {
  on("project-loaded", render);
  on("view-changed", render);
  on("signed-in", render);
  on("locale-changed", render);
  // The panel IS the step's act, so it follows the step — and a new run is what
  // gives the generate and plan steps something to act on.
  on("step-changed", render);
  on("result-changed", render);
  render();
}
