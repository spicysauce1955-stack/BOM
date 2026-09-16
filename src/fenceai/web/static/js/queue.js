// The backoffice's home screen: what should I work on next.
//
// It owns `#tab-queue` and nothing else, and it talks to exactly two routes —
// `GET /api/queue` and the one command door. It never reads a project document:
// the row the server sends IS the row, so the list and the job screen can never
// disagree about a status.
//
// The `With` column is the point of the whole screen. Three states, and the empty
// one is a REAL state rather than a blank cell — "nobody has taken this" is the
// reason a queue exists at all.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { on, state } from "./state.js";
import { setTab } from "./tabs.js";

const STATUSES = ["drafting", "waiting", "planning", "planned", "quoted",
                  "returned", "delivered", "cancelled"];

let bucket = "open";

/** How long a job has been waiting, in words somebody would say.
 *
 *  Pure, so node can test it. Whole units only: "3 d" is what an office person
 *  says, and "3 d 4 h 12 m" is a number pretending to be a decision.
 */
export function waitedWord(seconds) {
  if (seconds < 60) return "now";
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h`;
  return `${Math.floor(h / 24)} d`;
}

/** Which of the two lists a status belongs to. Mirrors `lifecycle.py`, and the
 *  node test pins the two against each other so they cannot drift. */
export function bucketFor(status) {
  return (status === "delivered" || status === "cancelled") ? "finished" : "open";
}

/** The `With` cell, as data rather than markup, so it is testable.
 *
 *  `takeable` is the whole reason this is a function: a job nobody has taken is
 *  the only one that offers the button, and offering it on a job somebody else
 *  holds would turn a name into a race.
 */
export function withCell(row, meId) {
  if (!row.assignee) return { who: t("queue.nobody"), mine: false, takeable: true };
  if (row.assignee === meId) return { who: t("queue.you"), mine: true, takeable: false };
  return { who: row.assignee, mine: false, takeable: false };
}

function option(value, label, selected) {
  return `<option value="${esc(value)}"${selected ? " selected" : ""}>${esc(label)}</option>`;
}

function fillFilters() {
  const status = document.getElementById("queue-status");
  const wanted = bucket === "open"
    ? STATUSES.filter((s) => bucketFor(s) === "open")
    : STATUSES.filter((s) => bucketFor(s) === "finished");
  status.innerHTML = option("", t("queue.any_status"), true)
    + wanted.map((s) => option(s, t(`queue.status.${s}`), false)).join("");

  const who = document.getElementById("queue-with");
  who.innerHTML = option("", t("queue.anyone"), true)
    + option("me", t("queue.mine"), false)
    + option("none", t("queue.unassigned"), false);
}

function rowHtml(row, meId) {
  const w = withCell(row, meId);
  // Every one of these is somebody's typed text. `esc` on all of them, because
  // a customer called `<script>` is a customer, not an attack we get to refuse.
  return `<tr data-id="${esc(row.id)}">
    <td><strong>${esc(row.customer || row.label)}</strong></td>
    <td>${esc(row.town)}</td>
    <td>${esc(row.sold_by)}</td>
    <td class="num">${esc(row.submitted_at.slice(0, 10))}</td>
    <td class="num">${esc(waitedWord(row.waiting_seconds))}</td>
    <td><span class="badge">${esc(t(`queue.status.${row.status}`))}</span></td>
    <td class="${w.mine ? "queue-mine" : ""}">${esc(w.who)}
      ${w.takeable ? `<button class="primary queue-take">${esc(t("queue.take"))}</button>` : ""}</td>
    <td class="num">${row.open_questions || ""}</td>
  </tr>`;
}

/** A cancelled job can come back; a delivered one cannot (`TRANSITIONS` gives
 *  `delivered` no way out — a plan that has been priced and handed on is
 *  finished, and un-finishing one would make the word untrustworthy). Pure, so
 *  the rule is testable where the button is not. */
export function reopenable(status) {
  return status === "cancelled";
}

function finishedRowHtml(row) {
  return `<tr data-id="${esc(row.id)}">
    <td><strong>${esc(row.customer || row.label)}</strong></td>
    <td>${esc(row.town)}</td>
    <td>${esc(row.sold_by)}</td>
    <td class="num">${esc((row.closed_at || "").slice(0, 10))}</td>
    <td><span class="badge">${esc(t(`queue.status.${row.status}`))}</span></td>
    <td>${esc(row.assignee || "")}
      ${reopenable(row.status)
        ? `<button class="queue-reopen">${esc(t("queue.reopen"))}</button>` : ""}</td>
  </tr>`;
}

async function render() {
  const host = document.getElementById("queue-list");
  if (!host) return;
  const params = new URLSearchParams({ bucket });
  const status = document.getElementById("queue-status").value;
  const who = document.getElementById("queue-with").value;
  const q = document.getElementById("queue-q").value.trim();
  if (status) params.set("status", status);
  if (who) params.set("assignee", who);
  if (q) params.set("q", q);

  host.innerHTML = `<p class="meta">${esc(t("queue.loading"))}</p>`;
  const r = await fetch(`/api/queue?${params}`);
  if (!r.ok) {
    // A refusal here is a code the bundles carry, never a raw status.
    const body = await r.json().catch(() => ({}));
    const code = body?.detail?.code || "not_signed_in";
    host.innerHTML = `<p class="warning error">${esc(t(`error.${code}`))}</p>`;
    return;
  }
  const { rows } = await r.json();
  document.getElementById("queue-count").textContent =
    t("queue.count", { n: rows.length });
  if (!rows.length) {
    host.innerHTML = `<p class="meta">${esc(t("queue.empty"))}</p>`;
    return;
  }
  const meId = state.me?.id || null;
  const head = bucket === "open"
    ? [t("queue.customer"), t("queue.town"), t("queue.sold_by"), t("queue.submitted"),
       t("queue.waiting"), t("queue.status"), t("queue.with"), t("queue.open_questions")]
    : [t("queue.customer"), t("queue.town"), t("queue.sold_by"), t("queue.closed"),
       t("queue.status"), t("queue.with")];
  host.innerHTML = `<table><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>`
    + rows.map((row) => (bucket === "open" ? rowHtml(row, meId) : finishedRowHtml(row))).join("")
    + "</table>";
}

export function initQueue() {
  const openBtn = document.getElementById("queue-open");
  const doneBtn = document.getElementById("queue-finished");
  if (!openBtn) return;

  const pick = (which) => {
    bucket = which;
    openBtn.classList.toggle("active", which === "open");
    doneBtn.classList.toggle("active", which === "finished");
    fillFilters();
    render();
  };
  openBtn.addEventListener("click", () => pick("open"));
  doneBtn.addEventListener("click", () => pick("finished"));
  for (const id of ["queue-status", "queue-with"]) {
    document.getElementById(id).addEventListener("change", render);
  }
  document.getElementById("queue-q").addEventListener("change", render);

  document.getElementById("queue-list").addEventListener("click", async (e) => {
    // A click on the row OPENS the job; a click on the button TAKES it. Two
    // intentions, and doing both would open a job somebody only meant to claim
    // — which on a list you are working down is the difference between keeping
    // your place and losing it.
    const reopen = e.target.closest(".queue-reopen");
    if (reopen) {
      // Back onto the open list, where somebody can take it again. Rejecting is
      // the one act with no undo on the job's own screen, so its undo lives
      // here, beside the jobs it applies to.
      const { reloadProject, runCommand, state: shared } = await import("./state.js");
      const id = reopen.closest("tr").dataset.id;
      const out = await runCommand(id, "reopen_job");
      if (!out.ok) {
        // A refusal re-rendered the identical row and said nothing at all.
        const { refusalText } = await import("./my-jobs.js");
        document.getElementById("queue-list").insertAdjacentHTML("afterbegin",
          `<p class="warning error">${esc(refusalText(out))}</p>`);
        return;
      }
      // The job just reopened may be the one still OPEN on every other screen —
      // rejecting drops you on this queue with it loaded — and those screens
      // would go on reading `cancelled`.
      if (id === shared.projectId) await reloadProject();
      render();
      return;
    }
    const btn = e.target.closest(".queue-take");
    const row = e.target.closest("tr[data-id]");
    if (!btn && row) {
      const { openProject } = await import("./state.js");
      await openProject(row.dataset.id);
      setTab("canvas");
      return;
    }
    if (!btn) return;
    // Taking a job is one click and two effects — it becomes yours AND it moves
    // to planning, because in an office those are one gesture.
    const id = btn.closest("tr").dataset.id;
    await fetch(`/api/projects/${id}/actions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "claim_job", payload: {} }),
    });
    render();
  });

  fillFilters();
  on("locale-changed", () => { fillFilters(); render(); });
  on("tab-changed", (name) => { if (name === "queue") render(); });

  // A backoffice account opens ON the queue. Its whole day starts with choosing
  // what to work on, and landing on a drawing means choosing by scrolling a
  // picker. Sales does not get this tab at all — a salesperson has no queue,
  // they work the job they just sold.
  on("signed-in", (user) => {
    if (user?.capacity === "backoffice" || user?.capacity === "admin") setTab("queue");
    render();
  });
  on("signed-out", render);
}
