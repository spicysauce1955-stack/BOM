// The road DEFINITIONS. Data, not behaviour: `road-model.js` is the engine and
// imports nothing, so everything role-specific lives here.
//
// See docs/superpowers/specs/2026-09-07-eight-step-road-design.md.
//
// Adding a role is one entry in `ROADS` and touches no engine code — the
// registry idiom this project uses everywhere: adding an entry is never a
// breaking change.

/** The salesperson's road. Eight steps, one responsibility each.
 *
 *  `anchor` is the check meaning THIS JOB HAS NOT STARTED. It replaces the
 *  hardcoded `!drawn` test the engine used to compute from the project, which
 *  is the whole reason the engine no longer needs one.
 *
 *  `requires` drives a step's state; `wants` is carried and rendered but never
 *  stops a step reading `done` — a nice-to-have that is absent is not
 *  incompleteness. Required-ness is a property of the STEP, not the check:
 *  `sold_by_missing` matters to a salesperson's handover and not to an office
 *  person's road over the same gaps.
 *
 *  `satisfiedBy` names the `Stated` fact that answers a step nothing can
 *  check. A step is skippable exactly when it has one.
 *
 *  `commits` marks a step that already HAS an explicit "I have finished this"
 *  control of its own — step 1's Save, which saves the job and then advances.
 *  The road's own Done button is suppressed there rather than shown beside it:
 *  two buttons that do one thing is not a choice, it is a question about which
 *  one really saves, and the user asked for it to stop. Every other step is a
 *  canvas gesture with nothing to press, which is why the Done button exists at
 *  all. */
export const SALES_ROAD = {
  role: "sales",
  anchor: "no_fence_drawn",
  steps: [
    { key: "job", panel: "canvas", commits: true,
      requires: ["customer_missing", "address_missing"],
      wants: ["sold_by_missing", "sold_on_missing"], satisfiedBy: null },
    { key: "property", panel: "canvas",
      requires: ["no_property_context"], wants: [], satisfiedBy: null },
    { key: "layout", panel: "canvas",
      requires: ["no_fence_drawn"], wants: [], satisfiedBy: null },
    { key: "sideview", panel: "canvas",
      requires: ["height_assumed", "base_assumed"], wants: [], satisfiedBy: null },
    { key: "model", panel: "canvas",
      requires: ["no_model_chosen"], wants: [], satisfiedBy: null },
    { key: "gates", panel: "canvas",
      requires: ["gates_contradicted"], wants: [], satisfiedBy: "no_gates" },
    // The drawing, not the Annotations tab. A promise is made ABOUT something —
    // the house, that stretch, the ground by the gate — and the tab's form asked
    // a salesperson to pick "r2" from a list of run ids. It is attached by
    // clicking the thing itself now, so this step's surface is the map
    // (`js/notes.js` owns the popover and the side panel beside it).
    { key: "notes", panel: "canvas",
      requires: ["promises_contradicted"], wants: [], satisfiedBy: "no_promises" },
    { key: "review", panel: "canvas",
      requires: [], wants: [], satisfiedBy: null },
  ],
};

/** Roads by role. A role absent here has no road, and `roadFor` returns null
 *  rather than defaulting to the salesperson's: showing an office person a
 *  salesperson's map would be worse than showing them none. */
export const ROADS = { sales: SALES_ROAD };

/** The road for a role, or `null` for a role that has no road.
 *
 *  `Object.hasOwn`, not `ROADS[role] || null` — the latter resolves through
 *  the prototype and hands back `Object` for `roadFor("constructor")`, a
 *  truthy non-road whose `.steps` is undefined. `road()` guards gap codes the
 *  same way, for the same reason: both keys come from data. */
export function roadFor(role) {
  return Object.hasOwn(ROADS, role) ? ROADS[role] : null;
}
