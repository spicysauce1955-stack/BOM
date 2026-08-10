// Getting-started checklist (research: interactive checklists lift completion
// 20-30%; items complete by DOING, not reading). Auto-derived from project state;
// dismissible; never shown again once dismissed.

import { t } from "./i18n.js";
import { on, state } from "./state.js";

const DISMISS_KEY = "fenceai.checklist.dismissed";

const ITEMS = [
  { key: "checklist.draw", done: () => (state.project?.topology.runs.length || 0) > 0 },
  {
    key: "checklist.gate",
    done: () => (state.project?.topology.runs || []).some(
      (r) => r.point_events.some((e) => e.payload.kind === "gate")
    ),
  },
  { key: "checklist.compute", done: () => !!state.result },
];

export function initChecklist() {
  const box = document.getElementById("checklist");
  if (!box) return;
  document.getElementById("checklist-dismiss").addEventListener("click", () => {
    localStorage.setItem(DISMISS_KEY, "1");
    box.style.display = "none";
  });
  const render = () => {
    if (localStorage.getItem(DISMISS_KEY) || !state.project) {
      box.style.display = "none";
      return;
    }
    const states = ITEMS.map((item) => item.done());
    box.style.display = "";
    box.classList.toggle("all-done", states.every(Boolean));
    const list = document.getElementById("checklist-items");
    list.innerHTML = "";
    ITEMS.forEach((item, i) => {
      const row = document.createElement("div");
      row.className = "checklist-item" + (states[i] ? " done" : "");
      row.textContent = `${states[i] ? "✓" : "○"} ${t(item.key)}`;
      list.appendChild(row);
    });
  };
  on("project-loaded", render);
  on("topology-changed", render);
  on("result-changed", render);
  on("locale-changed", render);
  render();
}
