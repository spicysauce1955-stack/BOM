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
  createProject, emit, loadProjects, on, openProject, state,
} from "./js/state.js";
import { initSectionDecisions } from "./js/section-decisions.js";
import { initSite } from "./js/site.js";
import { initStructureData } from "./js/structure-data.js";
import { initStructure } from "./js/structure.js";
import { initTabs, setTab } from "./js/tabs.js";
import { initView, setView } from "./js/view.js";
import { lastProjectKey, loadMe, pickProject, signIn, signOut } from "./js/session.js";
import { initQueue } from "./js/queue.js";
import { initMyJobs } from "./js/my-jobs.js";
import { initDeskActions } from "./js/desk-actions.js";
import { initUnits, toggleUnits, updateUnitsButton } from "./js/units.js";

function setupHeader() {
  // A new job starts untitled on purpose: who it is for and where is step 1 of
  // the road (`js/job.js`), and a second name box up here was a second place to
  // type it that disagreed with the first.
  document.getElementById("btn-new-project").addEventListener("click", async () => {
    await createProject(t("project.untitled"));
    // ...and SHOW it: pressed from a home screen, creating a job behind the list
    // did nothing visible, and every press made another one.
    setTab("canvas");
    emit("road-go", "job");
  });
  document.getElementById("btn-locale").addEventListener("click",
    () => setLocale(currentLocale() === "he" ? "en" : "he"));
  document.getElementById("btn-units").addEventListener("click", toggleUnits);
  const viewSelect = document.getElementById("view-select");
  viewSelect.value = state.view;
  viewSelect.addEventListener("change", () => setView(viewSelect.value));
  initQueue();
  initMyJobs();
  initDeskActions();
  wireIdentity();
  // the unit label itself is localized: relabel the button when the language flips
  on("locale-changed", updateUnitsButton);
}

/** The login screen and the who-am-I chip.
 *
 *  Signed out, the login form is the whole page (`html[data-auth="out"]`). The
 *  account decides the view — `session.js` applies `/api/me`'s answer — so
 *  nobody picks a role on the way in.
 *
 *  Signing out RELOADS rather than hiding the workspace again: the open job,
 *  its undo stack and every panel's cached answers belong to the person who
 *  just left, and the next person to sign in on this browser must not inherit
 *  them.
 */
function wireIdentity() {
  const form = document.getElementById("sign-in");
  const chip = document.getElementById("signed-in-as");
  const err = document.getElementById("sign-in-error");
  const unreachable = document.getElementById("sign-in-unreachable");

  const render = () => {
    const me = state.me;
    document.documentElement.dataset.auth = me ? "in" : "out";
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
    unreachable.hidden = true;
    const outcome = await signIn(document.getElementById("sign-in-email").value,
                                 document.getElementById("sign-in-password").value);
    // One message for a wrong password and for an address with no account — the
    // server already refuses both identically, and a kinder message here would
    // undo that by telling somebody which half they got right.
    if (outcome === "refused") err.hidden = false;
    else if (outcome === "unreachable") unreachable.hidden = false;
    else document.getElementById("sign-in-password").value = "";
  });
  document.getElementById("sign-out").addEventListener("click", async () => {
    await signOut();
    location.reload();
  });

  on("signed-in", async () => { render(); await openWorkspace(); });
  on("signed-out", render);
  // Remembered per account, so the next sign-in reopens this job.
  on("project-opened", (id) => {
    if (!state.me) return;
    try { localStorage.setItem(lastProjectKey(state.me.id), id); } catch { /* storage off */ }
  });
}

/** Load a job onto the screen, only for somebody signed in.
 *
 *  Nothing is fetched before sign-in: the login screen is the whole page, and a
 *  project loaded behind it would be a job shown to nobody in particular. It
 *  runs once per page because `signed-in` fires once per page — signing out
 *  reloads. Opens the job this person last had open (`pickProject`). */
async function openWorkspace() {
  const health = await apiGet("/api/health");
  document.getElementById("ai-badge").textContent = `AI: ${health.interpreter}`;
  let remembered = null;
  try { remembered = localStorage.getItem(lastProjectKey(state.me.id)); } catch { /* storage off */ }
  const id = pickProject(await loadProjects(), remembered);
  if (id) await openProject(id);
  else await createProject(t("project.demo_name"));
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
  // Last: `signed-in` opens the workspace, so every panel must already be
  // listening for the project it loads.
  if (!(await loadMe()))
    document.getElementById("sign-in-unreachable").hidden = false;
}

main();
