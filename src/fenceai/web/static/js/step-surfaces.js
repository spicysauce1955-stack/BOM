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
  // `#tool-other` is the one control behind which every property object that is
  // not the house or the street lives — a tree, a pool, a sidewalk, a boundary.
  // One entry here rather than five, which is the whole point of it.
  property: ["#tool-house", "#tool-street", "#tool-other"],
  layout: ["#tool-draw"],
  sideview: ["#tool-ground", "#tool-base", "#tool-height"],
  model: ["#tool-model"],
  gates: ["#tool-gate"],
  notes: ["#tool-note"],
  review: [],
};

// Panels each step KEEPS.
//
// `notes` used to have none — its surface was a different TAB, and the form on
// that tab asked a salesperson to pick "r2" out of a list of run ids. A promise
// is made ABOUT something, so it is attached by clicking the thing on the
// drawing now (`js/notes.js`), and this step keeps the map and the panel that
// reads the promises back.
const STEP_PANELS = {
  job: ["#job-panel"],
  property: ["#context-panel"],
  layout: [],
  sideview: ["#run-editing-panel", "#profile"],
  model: ["#model-row"],
  // Which gate comes before where it goes: `#gates-panel` is where the product
  // is chosen, and `#run-editing-panel` is where the placed ones are edited.
  gates: ["#gates-panel", "#run-editing-panel"],
  notes: ["#notes-panel"],
  review: ["#handover-panel", "#warnings", "#site-conditions"],
};

// The drawing itself, scoped like any other surface and kept by exactly the
// steps whose work happens ON it: the place, the fence, the ground under it,
// the model it is built to, where the gates go, and what was promised about any
// of them — steps 2 to 7.
//
// Steps 1 and 8 are a form and a summary. A map behind them is furniture: it
// invites a click that does nothing, and it makes step 1 read as "draw
// something" when the only thing to do is type an address. The user's
// instruction is the authority here, and it OVERRULES the earlier reading that
// the drawing must stay on screen throughout.
//
// Step 7 was on that list and has come back off it, by the same authority: a
// note is attached by CLICKING the thing it is about, so the map is not
// furniture there — it is the surface.
// `#statusbar` and `#strategy-summary` belong to the drawing and are scoped
// with it. Left unscoped they followed the salesperson everywhere: step 1 is a
// form with no canvas, and it still carried a status bar explaining what the
// select tool does and a line reading "No strategy yet — press ⚙ Generate
// strategy". Two captions for a picture that is not on the screen.
const DRAWING = ["#canvas", "#generate-toolbar", "#statusbar", "#strategy-summary"];
const STEP_DRAWING = {
  job: [],
  property: DRAWING,
  layout: DRAWING,
  sideview: DRAWING,
  model: DRAWING,
  gates: DRAWING,
  // The map, without the generate bar: this step attaches promises to what is
  // already drawn, and working out the fence is step 8's business, not this
  // one's.
  notes: ["#canvas", "#statusbar"],
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

/** The tool a step ARMS when you arrive on it.
 *
 *  A tool used to survive the step that offered it, and the result was a
 *  screen lying about what the next click would do: arm the gate tool on step
 *  6, walk to step 7, click the house to write a note on it, and a gate was
 *  placed instead — on a step whose rail does not even show the gate button.
 *  Hiding a control does not disarm it, exactly as `role.js` says hiding is
 *  never a permission.
 *
 *  DERIVED from `STEP_TOOLS`, not a second hand-written table: a step that
 *  keeps exactly ONE tool is a step whose whole job is that tool, so arriving
 *  there arms it (draw on the layout, gate on gates, note on notes). A step
 *  offering several — the property's house/street/other, the side view's
 *  ground/base/height — has no single answer and gets the neutral one, and so
 *  does a step with no tools at all. The invariant that matters either way is
 *  that the armed tool is one this step actually shows.
 *
 *  `#tool-select` is never in `STEP_TOOLS` (it is the default and no step
 *  hides it), so "select" can be returned for any step, known or not. */
export function defaultToolForStep(key) {
  const keep = STEP_TOOLS[key];
  if (!keep || keep.length !== 1) return "select";
  return keep[0].replace(/^#tool-/, "");
}
