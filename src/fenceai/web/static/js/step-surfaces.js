// Which of a sales step's controls are visible — a scoping list built exactly
// like `role.js`'s hide-list, and for the same reason: CSS cannot read a JS
// array, so this module owns the LIST and `style.css` repeats it, and the two
// copies are checked for EQUALITY (not overlap) by
// `tests/web/test_step_surfaces.py`, mirroring the check already made for
// `role.js` against its own stylesheet copy.
//
// Built as navigation alone, the road moved an underline while the screen
// underneath stayed identical: in `sales` every step showed all nine tools
// and every side panel at once (docs/superpowers/specs/2026-09-06-
// salesperson-road-design.md, "A step SHOWS only its own work"). This module
// is the fix — each step names what it KEEPS, and hides everything else that
// is scoped to a step.
//
// The eight keys below are the real ones `js/roads.js: SALES_ROAD` defines
// (docs/superpowers/specs/2026-09-07-eight-step-road-design.md), which is
// what `document.documentElement.dataset.step` is actually ever set to. They
// are NOT the six names in the design doc's surface table, which was written
// against the road as it stood before that split and was never reconciled
// with it. The correspondence is direct: the doc's "job", "gates", "notes"
// and "review" rows map straight across; its "layout" row (Select, Draw,
// House, Street) is this file's `property` (House, Street) plus `layout`
// (Draw) once the fence-drawing step and the landmark step split apart; its
// "details" row (Select, Ground, Base, Height, Model) is this file's
// `sideview` (Ground, Base, Height) plus `model` (Model) once which-model
// became its own step. Keying this file on the doc's stale six names instead
// would leave `property`, `sideview` and `model` unscoped — every tool and
// panel on those three steps left visible everywhere, which is the exact
// defect this file exists to close, on three of eight steps, silently.
//
// Deliberately no imports, for `road-model.js`'s reason: it must be
// node-testable with no DOM.

// Tools each step KEEPS. `#tool-select` is never listed — it is the default
// tool and stays visible in every step, so it is never part of the scoped
// union below (the same split `role.js` makes for tabs versus `ALL_TABS`).
const STEP_TOOLS = {
  job: [],
  property: ["#tool-house", "#tool-street"],
  layout: ["#tool-draw"],
  sideview: ["#tool-ground", "#tool-base", "#tool-height"],
  model: ["#tool-model"],
  gates: ["#tool-gate"],
  notes: [],
  review: [],
};

// Panels each step KEEPS. `notes` has none: its surface is a different TAB
// (`js/tabs.js: setTab("annotations")`), never a panel inside the canvas tab
// this list scopes.
const STEP_PANELS = {
  job: ["#job-panel"],
  property: ["#context-panel"],
  layout: [],
  sideview: ["#run-events", "#profile"],
  model: ["#model-row"],
  gates: ["#run-events"],
  notes: [],
  review: ["#handover-panel", "#warnings", "#site-conditions"],
};

// The drawing itself, scoped like any other surface and kept by exactly the
// steps whose work happens ON it: the place, the fence, the ground under it,
// the model it is built to, and where the gates go — steps 2 to 6.
//
// Steps 1, 7 and 8 are a form, a note and a summary. A map behind them is
// furniture: it invites a click that does nothing, and it makes step 1 read as
// "draw something" when the only thing to do is type an address. The user's
// instruction is the authority here, and it OVERRULES the earlier reading that
// the drawing must stay on screen throughout — kept in `notes` too so this
// list and its stylesheet copy stay equal, though `notes` switches to the
// annotations TAB and never shows the canvas anyway.
const STEP_DRAWING = {
  job: [],
  property: ["#canvas"],
  layout: ["#canvas"],
  sideview: ["#canvas"],
  model: ["#canvas"],
  gates: ["#canvas"],
  notes: [],
  review: [],
};

const STEP_KEYS = Object.keys(STEP_TOOLS);

// The union of everything ANY step scopes. Deriving each step's hidden list
// by subtracting its own keeps from this union — rather than hand-writing
// eight hidden lists — is what stops adding a tool to one step from silently
// leaving it visible in the other seven: a new surface only ever needs to be
// named once, as a KEEP.
const ALL_SCOPED = [...new Set(STEP_KEYS.flatMap(
  (key) => [...STEP_TOOLS[key], ...STEP_PANELS[key], ...STEP_DRAWING[key]]))];

/** `{step key: [selector, ...]}` — what each step hides, derived rather than
 *  hand-written. `#road` is never in `ALL_SCOPED`, so it can never appear
 *  here: the band is the only navigation this mode has, and hiding it strands
 *  a keyboard user completely. `#canvas` IS scoped — see `STEP_DRAWING`. */
export const STEP_HIDDEN = Object.fromEntries(STEP_KEYS.map((key) => {
  const keep = new Set(
    [...STEP_TOOLS[key], ...STEP_PANELS[key], ...STEP_DRAWING[key]]);
  return [key, ALL_SCOPED.filter((selector) => !keep.has(selector))];
}));

/** The selectors a step hides, or `[]` for a step this list does not know —
 *  the same degrade-to-nothing rule as `role.js: hiddenFor`, and for the same
 *  reason: an unrecognised step must not blank the screen. */
export function hiddenForStep(key) {
  return STEP_HIDDEN[key] ? [...STEP_HIDDEN[key]] : [];
}
