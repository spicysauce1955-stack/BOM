// Fence AI frontend bootstrap — composition only (UI v2 scaffold).
// All behavior lives in js/* modules communicating via state.js events.

import { apiGet } from "./js/api.js";
import { initAgentAdvice } from "./js/agent-advice.js";
import { initPublishedParts } from "./js/published-parts.js";
import { initAssembly } from "./js/assembly.js";
import { initEditor } from "./js/editor.js";
import { initEvidence } from "./js/evidence.js";
import { initGates } from "./js/gates.js";
import { currentLocale, initI18n, setLocale, t } from "./js/i18n.js";
import { canRedo, canUndo, redo, undo } from "./js/history.js";
import { initInspector } from "./js/inspector.js";
import { initContext } from "./js/context.js";
import { initHandover } from "./js/handover.js";
import { initJob } from "./js/job.js";
import { initModelEditor } from "./js/model-editor.js";
import { initNotes } from "./js/notes.js";
import { initPanel } from "./js/panel.js";
import { initProfile } from "./js/profile.js";
import { initRoad } from "./js/road.js";
import {
  createProject, loadProjects, on, openProject, state,
} from "./js/state.js";
import { initSectionDecisions } from "./js/section-decisions.js";
import { initSite } from "./js/site.js";
import { initStructureData } from "./js/structure-data.js";
import { initStructure } from "./js/structure.js";
import { initTabs } from "./js/tabs.js";
import { initView, setView } from "./js/view.js";
import { loadMe, signIn, signOut } from "./js/session.js";
import { initQueue } from "./js/queue.js";
import { initUnits, toggleUnits, updateUnitsButton } from "./js/units.js";

function setupHeader() {
  document.getElementById("btn-new-project").addEventListener("click", async () => {
    const name = document.getElementById("new-project-name").value.trim() || t("project.untitled");
    await createProject(name);
    await refreshProjectList();
  });
  document.getElementById("project-select").addEventListener("change",
    (e) => openProject(e.target.value));
  document.getElementById("btn-locale").addEventListener("click",
    () => setLocale(currentLocale() === "he" ? "en" : "he"));
  document.getElementById("btn-units").addEventListener("click", toggleUnits);
  const viewSelect = document.getElementById("view-select");
  viewSelect.value = state.view;
  viewSelect.addEventListener("change", () => setView(viewSelect.value));
  initQueue();
  wireIdentity();
  // the unit label itself is localized: relabel the button when the language flips
  on("locale-changed", updateUnitsButton);
  // ...and the picker is labelled by the JOB, which can be named long after the
  // project was created.
  on("job-changed", refreshProjectList);
}

/** The sign-in form and the who-am-I chip.
 *
 *  `loadMe()` runs AFTER `initView()` rather than instead of it: a signed-out
 *  browser must reach today's app without waiting on a round trip, and a signed-in
 *  one then corrects the view. The same ordering `initView` already needs against
 *  `initI18n` — audit observation 2, where a reload in sales mode hid the right
 *  surfaces and then showed an engineer's words on them.
 */
function wireIdentity() {
  const form = document.getElementById("sign-in");
  const chip = document.getElementById("signed-in-as");
  const err = document.getElementById("sign-in-error");

  const render = () => {
    const me = state.me;
    form.hidden = !!me;
    chip.hidden = !me;
    if (!me) return;
    // `esc` is not needed for textContent, which is the point of using it: a
    // person's own name is user text and never reaches innerHTML here.
    document.getElementById("me-name").textContent = me.name;
    document.getElementById("me-capacity").textContent =
      t(`signin.capacity.${me.capacity}`);
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    const ok = await signIn(document.getElementById("sign-in-email").value,
                            document.getElementById("sign-in-password").value);
    // One message for a wrong password and for an address with no account — the
    // server already refuses both identically, and a kinder message here would
    // undo that by telling somebody which half they got right.
    if (!ok) err.hidden = false;
    else document.getElementById("sign-in-password").value = "";
  });
  document.getElementById("sign-out").addEventListener("click", () => signOut());

  on("signed-in", render);
  on("signed-out", render);
  render();
  loadMe();
}

async function refreshProjectList() {
  const list = await loadProjects();
  const sel = document.getElementById("project-select");
  sel.innerHTML = "";
  for (const p of list) {
    const o = document.createElement("option");
    // `label` is the API's own answer (Job.label(), or the name when
    // there is no job) — computed there so the picker and the handover
    // cannot disagree about what a job is called.
    o.value = p.id; o.textContent = p.label || p.name;
    sel.appendChild(o);
  }
  if (state.projectId) sel.value = state.projectId;
}

function setupUndoButtons() {
  const b1 = document.getElementById("btn-undo");
  const b2 = document.getElementById("btn-redo");
  b1.addEventListener("click", undo);
  b2.addEventListener("click", redo);
  const refresh = () => { b1.disabled = !canUndo(); b2.disabled = !canRedo(); };
  on("project-loaded", refresh);
  on("topology-changed", refresh);
  // A landmark gesture pushes onto this SAME stack but saves through
  // `saveContext`, which emits only "context-changed" — without this the
  // button stayed disabled after placing a house (Ctrl+Z still worked, since
  // it calls `undo()` directly), which is the reported bug: undo looked
  // broken because the on-screen control never noticed there was anything
  // to undo.
  on("context-changed", refresh);
  refresh();
}

async function main() {
  await initI18n();
  initUnits();      // display unit before the first render (i18n first: it labels it)
  initView();       // ...and who is looking, before anything is drawn for them
  initRoad();       // ...and the road they navigate by, before the panels load
  initEditor();
  initInspector();
  initTabs();
  initPublishedParts();
  initPanel();
  initModelEditor();
  initSectionDecisions();
  initSite();
  initStructureData();
  initStructure();
  initAssembly();
  initProfile();
  initJob();
  initContext();
  // Which gate, and what was promised about what. Both own a panel in the side
  // column and a surface the road's gates and notes steps scope to; both are
  // read-only until a project has loaded, so their place in this list only has
  // to be before the first `openProject` below.
  initGates();
  initNotes();
  initHandover();
  initEvidence();
  initAgentAdvice();
  setupHeader();
  setupUndoButtons();

  const health = await apiGet("/api/health");
  document.getElementById("ai-badge").textContent = `AI: ${health.interpreter}`;
  await refreshProjectList();
  if (!state.projectId) await createProject(t("project.demo_name"));
  else await openProject(state.projectId);
  await refreshProjectList();
}

main();
