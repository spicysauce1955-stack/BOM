// Which of the company's three people is looking — a PRESENTATION preference,
// exactly like `units.js`, and emphatically not a permission.
//
// Nothing here is a security boundary. Switching to `sales` hides surfaces; it
// does not revoke anything, and the API is unchanged. A mode that merely hides
// must never be described as one that protects, or somebody will eventually rely
// on it to.
//
// Fence AI serves three roles, and they are COMPANY roles rather than positions
// in our pipeline: a salesperson (non-technical, records what was sold), an
// office person (holds the inventory and the installation knowledge), and a
// super user (alters and customises). `tools/persona_lab`'s older roster names
// pipeline positions instead and contains nobody non-technical — which is the
// likeliest reason the UI drifted into naming stations and spans at a person
// whose job is to sell fences.
//
// Hiding is CSS keyed on `<html data-role>`. This module owns only the LIST,
// which is what lets `tests/web/test_role_module.py` check every selector
// against the real page in node — a hide-list is the one kind of list that fails
// SILENTLY, since a selector nothing matches hides nothing and looks fine.

import { applyStatic } from "./i18n.js";
import { emit, state } from "./state.js";

export const ROLES = ["sales", "office", "all"];

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
//   #section-decisions the decision graph — the explanation, not the agreement
//   #inspector         "Click a generated post, span, or gate"
//   #gaps              NOT about this job at all: what the knowledge behind
//                      EVERY job cannot answer. To a salesperson it reads as a
//                      fault in the sale they just made.
//   #chk-overlay-label whether to draw generated posts is not their decision
//   #profile-exag      vertical exaggeration is a drafting control
const SALES_HIDDEN = [
  "#tool-pin",
  "#override-list",
  "#choices",
  "#section-decisions",
  "#inspector",
  "#gaps",
  "#chk-overlay-label",
  "#profile-exag",
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

/** The selectors a role hides. An unrecognised role hides NOTHING rather than
 *  everything: a preference stored by a future version, or a typo, must degrade
 *  to the whole app — presenting a stranger with a stripped UI and no way to
 *  tell why is the worse failure. */
export function hiddenFor(role) {
  return HIDDEN[role] ? [...HIDDEN[role]] : [];
}

export function currentRole() {
  return state.role;
}

export function setRole(role) {
  if (!ROLES.includes(role)) return;
  state.role = role;
  localStorage.setItem("fenceai.role", role);
  document.documentElement.dataset.role = role;
  // The words, not only the visibility. `t()` resolves `sales.<key>` ahead of
  // `<key>` while this mode is on, so every rendered label is stale the instant
  // the role changes — and the browser smoke caught exactly that: hiding worked,
  // but the labels lagged one switch behind, so switching BACK to the full app
  // left a salesperson's vocabulary on an engineer's screen.
  //
  // `applyStatic()` is sufficient today and deliberately not more: every sales
  // override is a `data-i18n` attribute in index.html, which is precisely what
  // this pass walks. `tests/web/test_locale_bundles.py` holds that property, so
  // the first sales override on a JS-rendered string fails there rather than
  // silently rendering the wrong words until the next language toggle.
  applyStatic();
  emit("role-changed", role);
}

/** Default `all` — today's app, unchanged.
 *
 *  Deliberate, and worth stating because the MVP argues the opposite: sales is
 *  the front door we are building toward. But making it the default now would
 *  change what 307 passing browser-smoke checks are looking at, in the same
 *  commit that introduces the mechanism. Flip it once the sales path is the one
 *  we trust, as its own change, with the smoke updated on purpose. */
export function initRole() {
  const stored = localStorage.getItem("fenceai.role");
  state.role = ROLES.includes(stored) ? stored : "all";
  document.documentElement.dataset.role = state.role;
}
