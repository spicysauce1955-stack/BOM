// THE JOB'S HISTORY — what changed, who changed it, newest first.
//
// The owner's answer to "the office changed what sales entered" is LOG IT: no
// approval and no notification (docs/superpowers/specs/2026-10-12-office-desk-
// without-ai-design.md). This panel is where the log is read. The office sees
// it while reading a job and on the road's first step; the salesperson sees it
// on her review step, which is where she finds out what the office changed.
//
// It FETCHES ONLY WHILE OPEN. The panel is a closed `<details>` most of the
// time, and the canvas emits `project-loaded` on every save — a history nobody
// is looking at must not cost a request per drag.
//
// Four states, never two: not loaded, loading, failed, ready. A failed fetch
// says so; it never renders as "no changes recorded yet", which would be a lie
// about a job somebody has been editing all morning.
//
// DOM ownership: `#change-log` and everything inside it. The sentences are
// `js/change-text.js`'s, which is pure and tested in node.

import { apiGet, esc } from "./api.js";
import { actorName, changeHtml, isMilestone } from "./change-text.js";
import { currentLocale, t } from "./i18n.js";
import { on, state } from "./state.js";

let status = "idle";          // idle | loading | failed | ready
let entries = [];
let names = {};
let loadedFor = null;          // the project the entries are about
let generation = 0;            // a reply for an earlier request never lands

function host() {
  return document.getElementById("change-log");
}

function when(at) {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at || "";
  return d.toLocaleString(currentLocale() === "he" ? "he-IL" : "en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function entryHtml(entry) {
  const milestone = entry.changes.some(isMilestone);
  const lines = entry.changes
    .map((c) => `<li class="change-line">${changeHtml(c, { names })}</li>`).join("");
  return `<li class="change-entry${milestone ? " milestone" : ""}">
    <div class="change-who"><bdi>${esc(actorName(entry.actor, names))}</bdi>
      · <span class="num">${esc(when(entry.at))}</span></div>
    <ul class="change-lines">${lines}</ul>
  </li>`;
}

function render() {
  const el = host();
  if (!el) return;
  // The summary is built ONCE and only its words change after: rewriting it
  // would drop keyboard focus from the very control somebody just toggled.
  if (!el.querySelector(":scope > summary")) {
    el.innerHTML = `<summary><h3></h3></summary>
      <div class="meta change-hint"></div><div class="change-body"></div>`;
  }
  el.querySelector(":scope > summary h3").textContent = t("change.title");
  el.querySelector(".change-hint").textContent = t("change.hint");
  el.querySelector(".change-body").innerHTML =
    status === "loading" ? `<div class="meta">${esc(t("change.loading"))}</div>`
    : status === "failed" ? `<div class="warning">${esc(t("change.failed"))}</div>`
    : status === "ready" && !entries.length
      ? `<div class="meta">${esc(t("change.empty"))}</div>`
    : status === "ready" ? `<ul class="change-entries">${entries.map(entryHtml).join("")}</ul>`
    : "";
}

async function load() {
  const el = host();
  const projectId = state.projectId;
  if (!el || !el.open || !projectId) { render(); return; }
  const mine = ++generation;
  if (loadedFor !== projectId) { status = "loading"; entries = []; render(); }
  try {
    const out = await apiGet(`/api/projects/${encodeURIComponent(projectId)}/changes`);
    if (mine !== generation) return;
    entries = out.entries || [];
    names = out.names || {};
    loadedFor = projectId;
    status = "ready";
  } catch {
    if (mine !== generation) return;
    status = "failed";
  }
  render();
}

export function initChangeLog() {
  const el = host();
  if (!el) return;
  el.addEventListener("toggle", () => { if (el.open) load(); });
  // A switch of job forgets the last one's entries and waits: `openProject`
  // emits `project-loaded` right after, and that is the one fetch it needs.
  on("project-opened", () => {
    generation++; loadedFor = null; entries = []; status = "idle"; render();
  });
  // every save that can change the job ends in one of these
  on("project-loaded", load);
  on("context-changed", load);
  on("job-changed", load);
  on("locale-changed", render);
  on("units-changed", render);
  render();
}
