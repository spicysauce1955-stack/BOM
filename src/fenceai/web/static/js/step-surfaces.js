// Which of a road step's controls are visible — a scoping list built exactly
// like `view.js`'s hide-list, and for the same reason: CSS cannot read a JS
// array, so this module owns the LIST and `style.css` repeats it, and the two
// copies are checked for EQUALITY (not overlap) by
// `tests/web/test_step_surfaces.py`, mirroring the check already made for
// `view.js` against its own stylesheet copy.
//
// Built as navigation alone, the road moved an underline while the screen
// underneath stayed identical: in `sales` every step showed all nine tools
// and every side panel at once (docs/superpowers/specs/2026-09-06-
// salesperson-road-design.md, "A step SHOWS only its own work"). This module
// is the fix — each step names what it KEEPS, and hides everything else that
// is scoped to a step.
//
// THE MAPS ARE KEYED `{road key: {step key: [...]}}`, AND THE OUTER LEVEL IS
// LOAD-BEARING. Keyed on the step alone, as they were while `sales` was the
// only road, two things break the moment a second road exists and neither
// announces itself:
//
//   * a step key both roads use resolves to whichever map was written first —
//     the office road's step 4 would have been called `layout` but for this,
//     and `layout` is already the salesperson's draw step. `road-model.js`'s
//     `panelFor` has been road-scoped from the day it was written for exactly
//     this reason ("a search over one global list would silently return the
//     first match"); this module arrived at it late.
//   * a step key only ONE road has gets an empty keep list subtracted from the
//     union of BOTH roads' surfaces — so it hides every tool and panel the
//     other road scopes. A hide-list that is wrong by omission hides nothing
//     and looks fine; a hide-list that is wrong by inheritance blanks the
//     screen. The union below is therefore taken PER ROAD.
//
// A road key is the road's own `view` (`js/roads.js: ROADS`, and each road
// carries it): this module imports nothing and cannot look one up, so
// `road.js` hands it over and `test_a_road_key_is_its_view_key` pins that the
// two spellings can never drift apart.
//
// The eight sales keys below are the real ones `js/roads.js: SALES_ROAD`
// defines (docs/superpowers/specs/2026-09-07-eight-step-road-design.md), which
// is what `document.documentElement.dataset.step` is actually ever set to. They
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
// union below (the same split `view.js` makes for tabs versus `ALL_TABS`).
const STEP_TOOLS = {
  sales: {
    job: [],
    // `#tool-other` is the one control behind which every property object that
    // is not the house or the street lives — a tree, a pool, a sidewalk, a
    // boundary. One entry here rather than five, which is the whole point of it.
    property: ["#tool-house", "#tool-street", "#tool-other"],
    layout: ["#tool-draw"],
    sideview: ["#tool-ground", "#tool-base", "#tool-height"],
    model: ["#tool-model"],
    gates: ["#tool-gate"],
    notes: ["#tool-note"],
    review: [],
  },
  // The office road's surfaces land with the office road; this key lands now,
  // empty, so the two-level shape is proven by a test before anything depends
  // on it. Empty is the safe state and an ABSENT key is not: both answer every
  // lookup with nothing, but a key that is present says the module has heard
  // of this road, and a key that is missing says only that nobody noticed —
  // and the two read identically right up to the day the surfaces are added
  // under a spelling this module does not carry.
  backoffice: {
    // Reading, not drawing. No tool armed: `#tool-select` is the default and is
    // never scoped, so a step that keeps nothing still lets somebody click a
    // note to read it.
    sale: [],
    // Her work, finished — the one office step that borrows the salesperson's
    // tools, because these four checks are hers and these are the tools that
    // close them.
    // ...plus the note tool: a blank the office cannot fill is a QUESTION, and
    // it is pinned on the thing it is about so the salesperson finds it there.
    blanks: ["#tool-ground", "#tool-base", "#tool-height", "#tool-model", "#tool-gate",
             "#tool-note"],
    questions: [],
    // A promise becomes an instruction here: "a post clear of that window" is
    // a pin, and the pin is the only tool this step offers.
    generate: ["#tool-pin"],
    materials: [],
    plan: [],
    price: [],
  },
};

// Panels each step KEEPS.
//
// `notes` used to have none — its surface was a different TAB, and the form on
// that tab asked a salesperson to pick "r2" out of a list of run ids. A promise
// is made ABOUT something, so it is attached by clicking the thing on the
// drawing now (`js/notes.js`), and this step keeps the map and the panel that
// reads the promises back.
const STEP_PANELS = {
  sales: {
    job: ["#job-panel"],
    property: ["#context-panel"],
    layout: [],
    sideview: ["#run-editing-panel", "#profile"],
    model: ["#model-row"],
    // Which gate comes before where it goes: `#gates-panel` is where the
    // product is chosen, and `#run-editing-panel` is where the placed ones are
    // edited.
    gates: ["#gates-panel", "#run-editing-panel"],
    notes: ["#notes-panel"],
    // The notes, because what the office asked is read here beside the map it
    // was pinned on, and `#finish-job` — send it, or go back to her jobs.
    review: ["#handover-panel", "#warnings", "#site-conditions", "#notes-panel",
             "#finish-job"],
  },
  backoffice: {
    // `#handover-panel` is scoped to this road and kept by NO step. It renders
    // the salesperson's answer to "what is left" — including the sentence
    // "nothing missing, this job is ready to hand over" — and unscoped it sat
    // on every office step contradicting the band above it, beside an estimate
    // that is not the quote step 7 is about. Two surfaces answering one
    // question is the defect `road-model.js`'s header was written against; the
    // band is the office's answer, so the panel is not on this road at all.
    // `#desk-actions` — send the job back to the salesperson with a question —
    // on the two steps where the office finds out something is missing.
    sale: ["#notes-panel", "#desk-actions"],
    blanks: ["#run-editing-panel", "#profile", "#notes-panel", "#desk-actions"],
    questions: ["#choices"],
    // `#site-conditions` rides here as a COLLAPSED disclosure rather than a step
    // of its own: the dimensions published rules key on matter the day a real
    // snapshot arrives, and on a job today they are a field nobody fills in. A
    // step amber on every job for a reason nobody can act on is the
    // completeness lie inverted (spec §8).
    // `#btn-generate` is kept by THIS step and no other, on either road. It
    // sat in the drawing's toolbar and so followed the drawing onto every step
    // that showed a map — a "work out the fence" button on the property step,
    // the layout, the side view, the gates. The user's verdict: it should not
    // be static throughout the steps. Working it out is this step's job.
    generate: ["#warnings", "#inspector", "#override-list", "#site-conditions",
               "#btn-generate", "#desk-actions"],
    materials: [],
    // Saying which run is the real one is this step's whole act — and it is read
    // on the structure sheet, so its host is the one that lives there.
    plan: ["#desk-actions-plan"],
    price: [],
  },
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
  sales: {
    job: [],
    property: DRAWING,
    layout: DRAWING,
    sideview: DRAWING,
    model: DRAWING,
    gates: DRAWING,
    // The map, without the toolbar above it: this step attaches promises to
    // what is already drawn.
    notes: ["#canvas", "#statusbar"],
    // The map is back on the last step: "he should look at it and figure out if
    // he made mistakes". The toolbar comes with it for fit-to-view; the generate
    // button inside it is hidden on this road regardless (ROAD_HIDES_ENTIRELY).
    // Not `#strategy-summary`: a line about a strategy she cannot generate is a
    // caption for something that is not hers.
    review: ["#canvas", "#generate-toolbar", "#statusbar"],
  },
  backoffice: {
    sale: ["#canvas", "#statusbar"],
    blanks: DRAWING,
    questions: ["#canvas", "#statusbar"],
    generate: DRAWING,
    // The materials, the sheet and the price are read on their own tabs. A map
    // behind them is furniture — it invites a click that does nothing.
    materials: [],
    plan: [],
    price: [],
  },
};

/** `map[key]`, or `null` — never `map[key] || null`, which resolves through the
 *  prototype and hands back `Object` for a road or a step called
 *  `"constructor"`. Both keys here come from data, which is the same reason
 *  `road-model.js: road()` guards its gap codes this way. */
function own(map, key) {
  return Object.hasOwn(map, key) ? map[key] : null;
}

/** Everything one step of one road KEEPS, across all three maps. */
function keptBy(roadKey, stepKey) {
  return [STEP_TOOLS, STEP_PANELS, STEP_DRAWING].flatMap((map) => {
    const steps = own(map, roadKey);
    return (steps && own(steps, stepKey)) || [];
  });
}

const ROAD_KEYS = Object.keys(STEP_TOOLS);

/** `{road key: [selector, ...]}` — the union of everything ANY of that road's
 *  steps scopes.
 *
 *  Deriving each step's hidden list by subtracting its own keeps from this
 *  union — rather than hand-writing a hidden list per step — is what stops
 *  adding a tool to one step from silently leaving it visible in the other
 *  seven: a new surface only ever needs to be named once, as a KEEP.
 *
 *  Exported because the PER-ROAD part of that is otherwise invisible while one
 *  road's maps are still empty: a shared union would show up as the empty road
 *  hiding the other road's whole screen, and there is no step of the empty road
 *  to observe it on until its steps land. This is the handle the test holds. */
/** Surfaces a road scopes and NO step of it keeps — hidden on every step.
 *
 *  `#handover-panel` renders the salesperson's answer to "what is left",
 *  including "nothing missing — this job is ready to hand over" and an estimate
 *  that is not the quote step 7 is about. Unscoped, it sat on every office step
 *  contradicting the band above it. Two surfaces answering one question is the
 *  defect `road-model.js`'s header was written against, and the band is this
 *  road's answer.
 *
 *  A keep-list cannot express "scoped by nobody", because the union is derived
 *  FROM the keeps — so it is named here, which is also the honest place: it
 *  says what the road hides rather than burying it in six empty arrays. */
const ROAD_HIDES_ENTIRELY = {
  // The salesperson records what was sold; working out the fence is the
  // office's step 4. No sales step keeps the button, so without this entry it
  // would not be in the sales union at all and would show on every map step.
  sales: ["#btn-generate", "#desk-actions", "#desk-actions-plan"],
  backoffice: ["#handover-panel", "#finish-job"],
};

export const STEP_SCOPED = Object.fromEntries(ROAD_KEYS.map((roadKey) => [
  roadKey,
  [...new Set([
    ...Object.keys(STEP_TOOLS[roadKey])
      .flatMap((stepKey) => keptBy(roadKey, stepKey)),
    ...(ROAD_HIDES_ENTIRELY[roadKey] || []),
  ])],
]));

/** `{road key: {step key: [selector, ...]}}` — what each step hides, derived
 *  rather than hand-written. `#road` is never in `STEP_SCOPED`, so it can never
 *  appear here: the band is the only navigation this mode has, and hiding it
 *  strands a keyboard user completely. `#canvas` IS scoped — see
 *  `STEP_DRAWING`. */
export const STEP_HIDDEN = Object.fromEntries(ROAD_KEYS.map((roadKey) => [
  roadKey,
  Object.fromEntries(Object.keys(STEP_TOOLS[roadKey]).map((stepKey) => {
    const keep = new Set(keptBy(roadKey, stepKey));
    return [stepKey, STEP_SCOPED[roadKey].filter((sel) => !keep.has(sel))];
  })),
]));

/** The selectors a step of a road hides, or `[]` for a road or a step this
 *  module does not know — the same degrade-to-nothing rule as `view.js:
 *  hiddenFor`, and for the same reason: an unrecognised key must not blank the
 *  screen. There are two keys to get wrong now, and both degrade the same way. */
export function hiddenForStep(roadKey, stepKey) {
  const steps = own(STEP_HIDDEN, roadKey);
  const hidden = steps && own(steps, stepKey);
  return hidden ? [...hidden] : [];
}

/** The tool a step ARMS when you arrive on it.
 *
 *  A tool used to survive the step that offered it, and the result was a
 *  screen lying about what the next click would do: arm the gate tool on step
 *  6, walk to step 7, click the house to write a note on it, and a gate was
 *  placed instead — on a step whose rail does not even show the gate button.
 *  Hiding a control does not disarm it, exactly as `view.js` says hiding is
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
 *  Road-scoped for the same reason the hide-lists are: a road that has no
 *  `layout` must not arm the salesperson's draw tool on a step of its own that
 *  happens to be spelled that way.
 *
 *  `#tool-select` is never in `STEP_TOOLS` (it is the default and no step
 *  hides it), so "select" can be returned for any step, known or not. */
export function defaultToolForStep(roadKey, stepKey) {
  const steps = own(STEP_TOOLS, roadKey);
  const keep = steps && own(steps, stepKey);
  if (!keep || keep.length !== 1) return "select";
  return keep[0].replace(/^#tool-/, "");
}
