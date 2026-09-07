// The road, rendered. `road-model.js` decides WHAT the eight steps are and
// which is missing something; this file only draws it and switches panels — the
// `base-top.js` / `profile.js` split, applied again.
//
// It reaches no panel's DOM. `setTab` is the one path that moves the `active`
// class, so the road and the strip can never disagree about which panel shows.

import { esc } from "./api.js";
import { pushSnapshot } from "./history.js";
import { t } from "./i18n.js";
import { currentRole } from "./role.js";
import { on, saveStated, state } from "./state.js";
import { setTab } from "./tabs.js";
import { panelFor, road } from "./road-model.js";
import { roadFor } from "./roads.js";

let current = "job";

function currentRoad() {
  return roadFor(currentRole());
}

function showStep(stepKey) {
  const def = currentRoad();
  if (!def) return;
  const panel = panelFor(def, stepKey);
  if (panel) setTab(panel);
}

/** Build the band ONCE, then only toggle attributes.
 *
 *  Re-`innerHTML`ing on every state change drops keyboard focus to BODY — and
 *  with `#tabs` hidden this band is the only navigation on the screen, so
 *  losing focus here strands a keyboard user completely. The buttons are always
 *  enabled: the road is a map, not a wizard. */
function build(host, def) {
  if (host.children.length) return;
  host.innerHTML = def.steps.map((s, i) => `<button data-step="${esc(s.key)}">`
    + `<span class="road-index">${String(i + 1).padStart(2, "0")}</span>`
    + `<span class="road-name">${esc(t(`road.${s.key}`))}</span>`
    + `<span class="road-state"></span></button>`).join("");
  host.addEventListener("click", (ev) => {
    const skip = ev.target.closest(".road-skip");
    if (skip) {
      ev.stopPropagation();          // stating a fact is not navigating
      const fact = skip.dataset.fact;
      pushSnapshot("state-fact");     // as undoable as any other job edit
      state.project.stated = { ...state.project.stated,
                               [fact]: !state.project.stated?.[fact] };
      saveStated();
      return;
    }
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
  const def = currentRoad();
  // `data-step` exists only while `sales` has a step to show; every other
  // role gets the attribute REMOVED rather than left stale, because an
  // absent attribute matches no `html[data-step="X"]` rule in style.css — so
  // `office`/`all` sit under no step rule at all (step-surfaces.js's header
  // comment, "Only `sales` has steps").
  if (currentRole() === "sales") document.documentElement.dataset.step = current;
  else delete document.documentElement.dataset.step;
  // A role with no road shows none — and the tab strip is what it navigates by.
  host.hidden = def === null;
  if (def === null) return;
  const steps = road(def, state.handover?.gaps ?? null,
                     state.project?.stated ?? {});
  build(host, def);
  // Set every render, not in `build()`: `build()` runs once, so freezing the
  // label there would leave it in whatever locale was active on the FIRST
  // render — `i18n.js: applyStatic` has no aria walker, so this is the only
  // path that can ever translate it, and it must follow `locale-changed`.
  host.setAttribute("aria-label", t("road.aria"));
  for (const step of steps) {
    const btn = host.querySelector(`[data-step="${step.key}"]`);
    if (!btn) continue;
    if (step.state === "unknown") btn.removeAttribute("data-state");
    else btn.dataset.state = step.state;
    if (step.key === current) btn.setAttribute("aria-current", "step");
    else btn.removeAttribute("aria-current");
    btn.querySelector(".road-name").textContent = t(`road.${step.key}`);
    btn.querySelector(".road-state").textContent = step.state === "unknown" ? ""
      : step.state === "skipped" ? t("road.state.skipped")
      : step.gaps.length ? t("road.state.missing", { n: step.gaps.length })
      : t(`road.state.${step.state}`);

    // Only a step nothing can check offers this, and the wording is a
    // STATEMENT rather than a "skip": the office reads it as a fact the
    // salesperson asserted, not as a step somebody bypassed.
    if (step.skippable) {
      let btn2 = btn.querySelector(".road-skip");
      if (!btn2) {
        btn2 = document.createElement("span");
        btn2.className = "road-skip";
        btn2.dataset.fact = def.steps.find((s) => s.key === step.key).satisfiedBy;
        btn.appendChild(btn2);
      }
      btn2.textContent = t(step.skipped ? "road.unskip" : "road.skip");
    }
  }
}

export function initRoad() {
  render();
  on("project-loaded", render);
  on("handover-changed", render);
  on("locale-changed", render);
  on("role-changed", () => {
    render();
    // Entering sales from another role can leave a panel the road does not
    // claim active and visible — the BOM tab, say — while the band says step
    // 1. The band is this role's only navigation, so it must not describe a
    // screen the user is not on.
    if (currentRole() === "sales") showStep(current);
  });
}
