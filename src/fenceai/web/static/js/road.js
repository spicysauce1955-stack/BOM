// The road, rendered. `road-model.js` decides WHAT the six steps are and which
// is missing something; this file only draws it and switches panels — the
// `base-top.js` / `profile.js` split, applied again.
//
// It reaches no panel's DOM. `setTab` is the one path that moves the `active`
// class, so the road and the strip can never disagree about which panel shows.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { currentRole } from "./role.js";
import { on, state } from "./state.js";
import { setTab } from "./tabs.js";
import { STEPS, panelFor, road } from "./road-model.js";

let current = "job";

function showStep(stepKey) {
  const panel = panelFor(stepKey);
  if (panel) setTab(panel);
}

/** Build the band ONCE, then only toggle attributes.
 *
 *  Re-`innerHTML`ing on every state change drops keyboard focus to BODY — and
 *  with `#tabs` hidden this band is the only navigation on the screen, so
 *  losing focus here strands a keyboard user completely. The buttons are always
 *  enabled: the road is a map, not a wizard. */
function build(host) {
  if (host.children.length) return;
  host.innerHTML = STEPS.map((s, i) => `<button data-step="${esc(s.key)}">`
    + `<span class="road-index">${String(i + 1).padStart(2, "0")}</span>`
    + `<span class="road-name">${esc(t(`road.${s.key}`))}</span>`
    + `<span class="road-state"></span></button>`).join("");
  host.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-step]");
    if (!btn) return;
    current = btn.dataset.step;
    showStep(current);
    render();
  });
}

/** `"unknown"` (handover not yet loaded, or the fetch failed) renders the step
 *  with no state claim at all: no badge text, no `data-state` for the amber
 *  styling to key on. Audit B01's lesson applies here exactly as it does in
 *  `road-model.js` — a step that reads "nothing missing" before the response
 *  is back is the bug, not a stricter one. */
export function render() {
  const host = document.getElementById("road");
  if (!host) return;
  const steps = road(state.project, state.handover, currentRole());
  // A role with no road shows none — and the tab strip is what it navigates by.
  host.hidden = steps === null;
  if (steps === null) return;
  build(host);
  for (const step of steps) {
    const btn = host.querySelector(`[data-step="${step.key}"]`);
    if (!btn) continue;
    if (step.state === "unknown") btn.removeAttribute("data-state");
    else btn.dataset.state = step.state;
    if (step.key === current) btn.setAttribute("aria-current", "step");
    else btn.removeAttribute("aria-current");
    btn.querySelector(".road-name").textContent = t(`road.${step.key}`);
    btn.querySelector(".road-state").textContent = step.state === "unknown" ? ""
      : step.gaps.length ? t("road.state.missing", { n: step.gaps.length })
      : t(`road.state.${step.state}`);
  }
}

export function initRoad() {
  render();
  on("project-loaded", render);
  on("handover-changed", render);
  on("locale-changed", render);
  on("role-changed", render);
}
