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
import { on, saveStated, setTool, state } from "./state.js";
import { setTab } from "./tabs.js";
import { panelFor, road } from "./road-model.js";
import { defaultToolForStep } from "./step-surfaces.js";
import { roadFor } from "./roads.js";

let current = "job";

function currentRoad() {
  return roadFor(currentRole());
}

/** Move to the next step in this road, or stay if this is the last.
 *
 *  NOT a wizard, and the difference is the whole design: a wizard REFUSES to
 *  let you leave a step, and the road forbids that — every step stays enterable
 *  at any time, because a salesperson works from paper and may hold the sketch
 *  and not the address. This only follows a COMPLETED gesture forward, the way
 *  a form's Enter key moves to the next field. Nothing is blocked; a click on
 *  any step still goes there. */
function advance() {
  const def = currentRoad();
  if (!def) return;
  const at = def.steps.findIndex((s) => s.key === current);
  const next = def.steps[at + 1];
  if (!next) return;
  current = next.key;
  showStep(current);
  render();
}

/** The "I have finished this step" control, in a host this module OWNS.
 *
 *  Created here rather than written into `index.html` for `job.js`'s and
 *  `context.js`'s reason: a module may never touch another module's DOM
 *  subtree, so the only element `road.js` may write into is one it made.
 *
 *  It sits in the canvas column and NOT in the band, because the band answers
 *  *where am I* and this answers *I am done here* — two different questions,
 *  and putting the second inside the first is how a navigation surface starts
 *  also being a form. It is deliberately absent from `step-surfaces.js`'s
 *  scoped list: every step needs it, so no step may hide it. */
function ensureDoneHost() {
  if (typeof document === "undefined") return null;
  let host = document.getElementById("step-done");
  if (host) return host;
  const col = document.querySelector(".canvas-col");
  if (!col) return null;
  host = document.createElement("div");
  host.id = "step-done";
  col.appendChild(host);
  return host;
}

/** Render the control for the step we are on.
 *
 *  Built once and only re-labelled after, the same discipline the band itself
 *  keeps: re-`innerHTML`ing drops keyboard focus to BODY, and with `#tabs`
 *  hidden for this role there is very little left to focus.
 *
 *  It does NOT gate. Pressing it on a step with work still missing advances
 *  anyway, and the badge goes on saying what is missing — because a step that
 *  REFUSED to be left is a wizard, and a wizard gets defeated by typing junk
 *  to get past it, which turns the completeness report the office relies on
 *  into a completeness lie (`road-model.js`'s own header). This button moves
 *  the salesperson on; it never certifies anything. */
function renderDone(def) {
  const host = ensureDoneHost();
  if (!host) return;
  const at = def.steps.findIndex((s) => s.key === current);
  const step = def.steps[at];
  const next = def.steps[at + 1];
  // Two reasons this control is absent, and they are different reasons.
  //
  // The last step has nowhere to go, so it gets no control rather than a dead
  // one. And a step marked `commits` already has its own "I am finished here"
  // button — step 1's Save, which saves the job and then calls `advance()`
  // through the `job-changed` subscription below. Showing the road's Done
  // beside it put two buttons on one screen that did one thing, which is what
  // the user asked to stop: the question a person is left with is not "which do
  // I press" but "does the other one save?".
  //
  // `hidden`, not removal: the host stays put so the column does not reflow
  // every time the salesperson reaches the end and steps back.
  host.hidden = !next || step?.commits === true;
  if (host.hidden) return;
  let btn = host.querySelector("#step-done-btn");
  if (!btn) {
    btn = document.createElement("button");
    btn.id = "step-done-btn";
    btn.className = "primary";
    // Listener on the BUTTON, not delegated from the host: there is exactly
    // one child, so delegation buys nothing. It also keeps this file's FIRST
    // click-listener registration the band's own, which is the anchor
    // `tests/web/test_road_render.py` searches for to check the skip
    // control's invariants — stopPropagation, and snapshot before mutate. A
    // second registration above it would silently steal that anchor and
    // leave both unchecked. (Do not spell that call literally in a comment
    // here either: the search is textual and a comment matches it.)
    btn.addEventListener("click", advance);
    host.appendChild(btn);
  }
  btn.textContent = t("road.done_next", { next: t(`road.${next.key}`) });
}

function showStep(stepKey) {
  const def = currentRoad();
  if (!def) return;
  const panel = panelFor(def, stepKey);
  if (panel) setTab(panel);
  // ...and arm this step's own tool, because a tool that survives the step
  // that offered it makes the drawing lie about what the next click will do:
  // the gate tool armed on step 6 was still armed on step 7, where clicking
  // the house to write a note on it placed a gate instead — on a step whose
  // rail does not show the gate button at all. Hiding a control never disarms
  // it (`role.js` says the same about hiding not being a permission), so the
  // arming has to be explicit and it belongs here, where the step changes.
  //
  // `step-surfaces.js` derives the answer from the tools the step KEEPS, so
  // this cannot drift from what the rail is showing.
  setTool(defaultToolForStep(stepKey));
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
  renderDone(def);
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
  // Step 1 is the only step with an explicit COMMIT — the other seven are
  // canvas gestures with no "done" button to press — so it is the only one
  // that can know the salesperson has finished. `job-changed` is what
  // `job.js` already announces on a successful save, so this reuses it rather
  // than inventing a second signal for one event.
  //
  // Guarded twice, and both guards matter: only in `sales` (no other role has
  // a road to advance along), and only FROM step 1. The event is global, so a
  // job saved while the salesperson is working on step 4 must not yank them
  // off what they are doing.
  on("job-changed", () => {
    if (currentRole() === "sales" && current === "job") advance();
  });
  on("role-changed", () => {
    render();
    // Entering sales from another role can leave a panel the road does not
    // claim active and visible — the BOM tab, say — while the band says step
    // 1. The band is this role's only navigation, so it must not describe a
    // screen the user is not on.
    if (currentRole() === "sales") showStep(current);
  });
}
