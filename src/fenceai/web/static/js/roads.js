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
  view: "sales",
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
    // `gate_swing_unstated` belongs HERE and not on the review step: it is
    // answered by one click on the gate's own marker, which is on this step's
    // screen. A gap reported where it cannot be closed is a gap that gets
    // carried to the office.
    { key: "gates", panel: "canvas",
      requires: ["gates_contradicted", "gate_swing_unstated"],
      wants: [], satisfiedBy: "no_gates" },
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
/** The backoffice's road. Seven steps, and **not one is a rename of hers**.
 *
 *  Her road captures what was sold; this one decides how it gets built. The
 *  keys are deliberately different words from the sales road's — not for
 *  tidiness, but because `step-surfaces.js` is keyed by `(road, step)` and a
 *  shared key hands one road the other's tools. `test_step_keys_are_unique_
 *  across_roads` is what holds it.
 *
 *  `view: "backoffice"` and the `ROADS` key are the SAME WORD on purpose:
 *  `road.js` hands `step-surfaces.js` a road's own `view` as the road key,
 *  because a module that imports nothing cannot look one up. Registered under
 *  anything else, that handoff asks for surfaces nobody defined and every step
 *  shows everything. `test_a_road_key_is_its_view_key` pins it.
 *
 *  `panel` names a TAB here, where every sales step named the canvas. The
 *  office works across the app — the cut plan is on the BOM tab and the
 *  setting-out sheet is its own — and `road.js` already calls `setTab` with
 *  whatever a step names, so this needed no engine change.
 *
 *  Steps 6 and 7 cannot read `done` until `commit_plan` exists. That is the
 *  road reporting something genuinely undone rather than a defect, and it is
 *  written here so the next reader does not go looking for a bug.
 */
export const OFFICE_ROAD = {
  view: "backoffice",
  anchor: "no_fence_drawn",
  steps: [
    // `no_fence_drawn` is the anchor AND claimed here, which is not a
    // contradiction: the anchor makes every step read `empty`, and a step that
    // also REQUIRES it is the one that says why. Sales does the same on its
    // `layout` step. Unclaimed, it fell to the orphan bucket — one line at the
    // bottom of the last step, on the job where nothing else is true yet.
    //
    // The four job fields are `wants`: the office cares that the address is
    // blank and is not stopped by it. Required-ness belongs to the STEP, which
    // is the whole reason a second road can read the same sheet differently —
    // `sold_by_missing` gates her handover and not his planning.
    // `commits` is FALSE deliberately. It suppresses the road's own Done
    // button on the grounds that the step "already has its own control" — and
    // the acknowledge buttons are not built yet, so claiming it left the step
    // with no way to be finished at all. It flips to true in the commit that
    // ships the button, not before.
    // `commits: true` now that each of these steps has its own control:
    // "I have read the sale", "I have read these warnings", "Commit this plan"
    // (`js/desk-actions.js`). The road's own Done button steps aside rather than
    // sitting beside a button that does the real thing.
    { key: "sale", panel: "canvas", commits: true,
      requires: ["no_fence_drawn", "sale_unread", "promises_contradicted",
                 "gates_contradicted"],
      wants: ["customer_missing", "address_missing", "sold_by_missing",
              "sold_on_missing", "no_property_context"], satisfiedBy: null },
    { key: "blanks", panel: "canvas",
      requires: ["height_assumed", "base_assumed", "no_model_chosen",
                 "gate_swing_unstated"],
      wants: [], satisfiedBy: null },
    { key: "questions", panel: "canvas",
      requires: ["choices_unanswered"], wants: [], satisfiedBy: null },
    // Generate itself is this step's control, but "I have read the warnings"
    // is not built — same reasoning as step 1.
    { key: "generate", panel: "canvas", commits: true,
      requires: ["no_run", "warnings_unreviewed"], wants: [], satisfiedBy: null },
    { key: "materials", panel: "bom",
      requires: ["supply_unresolved", "supply_unknown"], wants: [],
      satisfiedBy: null },
    { key: "plan", panel: "structure", commits: true,
      requires: ["no_plan_committed", "plan_stale"], wants: [], satisfiedBy: null },
    { key: "price", panel: "bom", commits: false,
      requires: ["not_priced"], wants: [], satisfiedBy: null },
  ],
};

export const ROADS = { sales: SALES_ROAD, backoffice: OFFICE_ROAD };

/** The road for a role, or `null` for a role that has no road.
 *
 *  `Object.hasOwn`, not `ROADS[role] || null` — the latter resolves through
 *  the prototype and hands back `Object` for `roadFor("constructor")`, a
 *  truthy non-road whose `.steps` is undefined. `road()` guards gap codes the
 *  same way, for the same reason: both keys come from data. */
export function roadFor(view) {
  return Object.hasOwn(ROADS, view) ? ROADS[view] : null;
}
