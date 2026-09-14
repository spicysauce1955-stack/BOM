// WHICH VIEW is on screen — a PRESENTATION preference, exactly like `units.js`,
// and emphatically not a permission.
//
// It was called `role` until accounts arrived, and the rename is the point of
// this file's existence rather than tidiness. `role` already meant two other
// things here: the job a part does (`RequirementLine.role`, `units.js:roleWord`,
// and the integration contract's own Roles REGISTRY — "the job a part does, ten
// to start"), and the ARIA attribute. The four preference keys were literally
// squatting in the part-role locale namespace beside `role.rail` and
// `role.screw`, so `roleWord("all")` would have rendered "Everything". A
// `User.capacity` — an actual permission — was about to become the fourth
// meaning. Two unrelated things under one word is the defect this repo already
// paid for once and named B03, and it is the same argument that made the sales
// road's step 2 "the property" rather than "the site".
//
// So: `view` is what is SHOWN, `capacity` is what an account may DO, and
// `role` is what a part is FOR. Three words, three meanings, no overlap.
//
// Nothing here is a security boundary. Switching to `sales` hides surfaces; it
// does not revoke anything, and the API is unchanged. A mode that merely hides
// must never be described as one that protects, or somebody will eventually rely
// on it to.
//
// The three views are named for the company's three people — COMPANY roles
// rather than positions in our pipeline: a salesperson (non-technical, records what was sold), an
// office person (holds the inventory and the installation knowledge), and a
// super user (alters and customises). `tools/persona_lab`'s older roster names
// pipeline positions instead and contains nobody non-technical — which is the
// likeliest reason the UI drifted into naming stations and spans at a person
// whose job is to sell fences.
//
// Hiding is CSS keyed on `<html data-view>`. This module owns only the LIST,
// which is what lets `tests/web/test_view_module.py` check every selector
// against the real page in node — a hide-list is the one kind of list that fails
// SILENTLY, since a selector nothing matches hides nothing and looks fine.

import { applyStatic } from "./i18n.js";
import { emit, state } from "./state.js";

export const VIEWS = ["sales", "office", "all"];

// Tabs a salesperson keeps. The canvas is where the job is drawn; annotations
// are where a PROMISE lives — `Annotation.target_ref` already accepts
// `run:<id>`, so "a post clear of that window" is recordable as a sentence the
// office person must read, rather than as an override that would quietly reach
// generation.
export const SALES_TABS = ["canvas", "annotations"];

const ALL_TABS = ["canvas", "annotations", "knowledge", "review", "structure",
                  "assembly", "panel", "models", "bom", "inventory"];

// Everything on this list answers "how is this fence BUILT?" — which is the
// office person's question and the super user's, never the salesperson's.
//
//   #tool-pin          placing a post is not a thing that is sold
//   #override-list     an override is a technical patch to a generated output
//   #choices           bay widths: two right answers, neither of them a sale
//   #agent-advice      the agent's suggestion is advice about HOW the fence is
//                      built, and slice 1 has no keep/reverse for a salesperson
//                      to act on anyway (advisory spec §11)
//   #section-decisions the decision graph — the explanation, not the agreement
//   #inspector         "Click a generated post, span, or gate"
//   #gaps              NOT about this job at all: what the knowledge behind
//                      EVERY job cannot answer. To a salesperson it reads as a
//                      fault in the sale they just made.
//   #chk-overlay-label whether to draw generated posts is not their decision
//   #profile-exag      vertical exaggeration is a drafting control
//   #model-row-hint    "Change it on the Panel tab" — and the Panel tab is on
//                      this very list. Audit B03: the row sent a salesperson to
//                      a surface their own view hides. What was sold is set from
//                      the canvas, so with the hint gone the row still tells
//                      them what the fence is built to.
const SALES_HIDDEN = [
  //   #tabs             the strip itself. The road is the navigation for this
  //                     view (spec, "The road IS the navigation"), and two
  //                     navigations on one screen is the smaller version of the
  //                     fault the road exists to fix. The eight per-tab entries
  //                     below STAY: they are what keeps the strip correct if it
  //                     is ever shown, and `test_sales_tabs_and_the_hidden_tabs_
  //                     partition_the_page` requires them.
  "#tabs",
  "#tool-pin",
  "#override-list",
  "#choices",
  "#agent-advice",
  "#section-decisions",
  "#inspector",
  "#gaps",
  "#chk-overlay-label",
  "#profile-exag",
  "#model-row-hint",
  ...ALL_TABS.filter((t) => !SALES_TABS.includes(t)).map((t) => `[data-tab="${t}"]`),
];

// The office person holds the inventory and the items; AUTHORING RULES is the
// super user's bench. This is the weakest of the three definitions — it is the
// one most likely to be wrong, so it is asserted in the tests to make changing
// it a decision rather than a drift.
const OFFICE_HIDDEN = [
  '[data-tab="knowledge"]',
  '[data-tab="review"]',
];

const HIDDEN = { sales: SALES_HIDDEN, office: OFFICE_HIDDEN, all: [] };

/** The selectors a view hides. An unrecognised view hides NOTHING rather than
 *  everything: a preference stored by a future version, or a typo, must degrade
 *  to the whole app — presenting a stranger with a stripped UI and no way to
 *  tell why is the worse failure. */
export function hiddenFor(view) {
  return HIDDEN[view] ? [...HIDDEN[view]] : [];
}

export function currentView() {
  return state.view;
}

export function setView(view) {
  if (!VIEWS.includes(view)) return;
  state.view = view;
  localStorage.setItem("fenceai.view", view);
  document.documentElement.dataset.view = view;
  // The words, not only the visibility. `t()` resolves `sales.<key>` ahead of
  // `<key>` while this mode is on, so every rendered label is stale the instant
  // the view changes — and the browser smoke caught exactly that: hiding worked,
  // but the labels lagged one switch behind, so switching BACK to the full app
  // left a salesperson's vocabulary on an engineer's screen.
  //
  // `applyStatic()` is sufficient today and deliberately not more: every sales
  // override is a `data-i18n` attribute in index.html, which is precisely what
  // this pass walks. `tests/web/test_locale_bundles.py` holds that property, so
  // the first sales override on a JS-rendered string fails there rather than
  // silently rendering the wrong words until the next language toggle.
  applyStatic();
  emit("view-changed", view);
}

/** Default `all` — today's app, unchanged.
 *
 *  Deliberate, and worth stating because the MVP argues the opposite: sales is
 *  the front door we are building toward. But making it the default now would
 *  change what 307 passing browser-smoke checks are looking at, in the same
 *  commit that introduces the mechanism. Flip it once the sales path is the one
 *  we trust, as its own change, with the smoke updated on purpose. */
export function initView() {
  const stored = localStorage.getItem("fenceai.view");
  state.view = VIEWS.includes(stored) ? stored : "all";
  document.documentElement.dataset.view = state.view;
  // The same `applyStatic()` `setView` needs, for the same reason and one path
  // further back — audit observation 2. `initI18n` runs first and applies the
  // static pass while the view is still the default, so a reload in sales mode
  // hid the right surfaces and then showed "Topology & Strategy" and "Generate
  // strategy" on them. Switching view or language reapplied the wording, which
  // is what made it look like a rendering hiccup rather than a missing call.
  applyStatic();
}
