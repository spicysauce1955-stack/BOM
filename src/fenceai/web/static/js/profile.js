// Side-view profile panel. Task 1: collapsible placeholder container only.
// Task 9 implements rendering + ground/wall editing per the plan contract.

import { t } from "./i18n.js";

export function initProfile() {
  const panel = document.getElementById("profile");
  const toggle = document.getElementById("profile-toggle");
  const open = localStorage.getItem("fenceai.profile.open") !== "false";
  panel.classList.toggle("collapsed", !open);
  toggle.addEventListener("click", () => {
    const collapsed = panel.classList.toggle("collapsed");
    localStorage.setItem("fenceai.profile.open", String(!collapsed));
  });
  const note = document.getElementById("profile-placeholder");
  if (note) note.textContent = t("profile.coming_soon");
}
