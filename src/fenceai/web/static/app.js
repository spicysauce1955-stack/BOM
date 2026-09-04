// Fence AI frontend bootstrap — composition only (UI v2 scaffold).
// All behavior lives in js/* modules communicating via state.js events.

import { apiGet } from "./js/api.js";
import { initAssembly } from "./js/assembly.js";
import { initChecklist } from "./js/checklist.js";
import { initEditor } from "./js/editor.js";
import { initEvidence } from "./js/evidence.js";
import { currentLocale, initI18n, setLocale, t } from "./js/i18n.js";
import { canRedo, canUndo, redo, undo } from "./js/history.js";
import { initInspector } from "./js/inspector.js";
import { initModelEditor } from "./js/model-editor.js";
import { initPanel } from "./js/panel.js";
import { initProfile } from "./js/profile.js";
import {
  createProject, loadProjects, on, openProject, state,
} from "./js/state.js";
import { initSectionDecisions } from "./js/section-decisions.js";
import { initSite } from "./js/site.js";
import { initStructureData } from "./js/structure-data.js";
import { initStructure } from "./js/structure.js";
import { initTabs } from "./js/tabs.js";
import { initRole, setRole } from "./js/role.js";
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
  const role = document.getElementById("role-select");
  role.value = state.role;
  role.addEventListener("change", () => setRole(role.value));
  // the unit label itself is localized: relabel the button when the language flips
  on("locale-changed", updateUnitsButton);
}

async function refreshProjectList() {
  const list = await loadProjects();
  const sel = document.getElementById("project-select");
  sel.innerHTML = "";
  for (const p of list) {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = p.name;
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
  refresh();
}

async function main() {
  await initI18n();
  initUnits();      // display unit before the first render (i18n first: it labels it)
  initRole();       // ...and who is looking, before anything is drawn for them
  initEditor();
  initInspector();
  initTabs();
  initPanel();
  initModelEditor();
  initSectionDecisions();
  initSite();
  initStructureData();
  initStructure();
  initAssembly();
  initProfile();
  initChecklist();
  initEvidence();
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
