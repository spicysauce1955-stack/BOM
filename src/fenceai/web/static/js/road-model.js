// The salesperson's road: six steps, and which of them is still missing
// something. See docs/superpowers/specs/2026-09-06-salesperson-road-design.md.
//
// The MODEL half. No imports, no DOM, no state — `road.js` renders this, the
// way `profile.js` renders `base-top.js`. That split is what lets the step
// model be tested in node without stubbing a document, and it is the rule
// CLAUDE.md states for new frontend logic.
//
// **A map, never a wizard.** Every step is enterable at any time. The
// salesperson works on a laptop after the visit, from paper — they may hold the
// sketch and not the address, or do the gates first because the gates are what
// the customer talked about. A wizard demanding order would be defeated by
// typing junk to get past a step, which turns a completeness report into a
// completeness LIE, and that is the one failure this MVP exists to prevent.
// It is `report/handover.py`'s own rule: reported, never enforced.
//
// **It computes no completeness of its own.** Three surfaces already answered
// "what is left" and disagreed: checklist.js's three hardcoded items, the
// handover panel, and `#gaps` — which answers a different question entirely
// (what the KNOWLEDGE cannot answer, for any job). A fourth would be the B03
// defect at a larger scale. So this module GROUPS `handover_gaps()` and never
// recomputes it.

/** The six steps, in the order the job is actually done, each with the panel it
 *  shows. `notes` is the only one whose panel is not the canvas, and it is the
 *  reason the tab strip goes: with the strip kept, a promise made during the
 *  sale would be the one thing the road could not report on. */
export const STEPS = [
  { key: "job", panel: "canvas" },
  { key: "layout", panel: "canvas" },
  { key: "details", panel: "canvas" },
  { key: "gates", panel: "canvas" },
  { key: "notes", panel: "annotations" },
  { key: "review", panel: "canvas" },
];

/** Which step owns each handover code. TOTAL over `HANDOVER_CODES` — a code
 *  with no entry here would vanish from the road while the API still reported
 *  it, so `tests/web/test_road_module.py` asserts the mapping covers the list.
 *
 *  A registry in `handover.py`'s sense: adding a code and its step is a one-line
 *  change and needs no discussion.
 *
 *  `gates`, `notes` and `review` own no codes here, on purpose — the spec:
 *  "no gap reports a missing gate, because a fence with no gate is a fence
 *  with no gate." Those three steps can therefore currently only ever read
 *  `done` (or `empty`/`unknown`): a green tick on one is a claim that no code
 *  is mapped to it YET, not that anything about it was checked. */
export const GAP_STEPS = {
  customer_missing: "job",
  address_missing: "job",
  sold_by_missing: "job",
  sold_on_missing: "job",
  no_fence_drawn: "layout",
  no_property_context: "layout",
  height_assumed: "details",
  base_assumed: "details",
  no_model_chosen: "details",
};

/** Where a code with no step goes. Never reached while the totality test
 *  passes; it exists so that if one ever does reach a browser, it is visible to
 *  the person who can act on it rather than silently dropped. */
const ORPHAN_STEP = "review";

/** The road for a role, or `null` for a role that has no road.
 *
 *  Refusing rather than defaulting is deliberate: the office person's road and
 *  the super user's are unwritten, and showing them the salesperson's map would
 *  be worse than showing them none.
 *
 *  `handover` is the payload of `GET /api/projects/{id}/handover` — passed in
 *  rather than fetched here, so this stays pure and so there is exactly one
 *  request behind the road and the estimate.
 *
 *  Each step's `state` is one of `"blocked" | "missing" | "done" | "empty" |
 *  "unknown"`. `"unknown"` is deliberately not folded into the `null` return:
 *  `null` already means "no road for this role", and a `handover` that has not
 *  loaded yet must not read as "nothing missing" — this repo shipped that bug
 *  once (audit B01, `cache = null` painting a clean bill of health; `js/
 *  handover.js: readinessShown` exists so readiness is only established by a
 *  SUCCESSFUL check) — so every step reads `"unknown"` until `handover`
 *  arrives, rather than defaulting to `done`.
 *
 *  The `gaps` arrays below hold the SAME gap objects passed in via
 *  `handover.gaps`, not copies — a caller that tags one writes through into
 *  the handover payload the caller still holds. */
export function road(project, handover, role = "sales") {
  if (role !== "sales") return null;
  if (handover == null)
    return STEPS.map((step) => (
      { key: step.key, panel: step.panel, state: "unknown", gaps: [] }));

  const gaps = handover.gaps || [];
  const drawn = (project?.topology?.runs || []).length > 0;

  const owned = Object.fromEntries(STEPS.map((s) => [s.key, []]));
  for (const gap of gaps)
    owned[Object.hasOwn(GAP_STEPS, gap.code) ? GAP_STEPS[gap.code] : ORPHAN_STEP]
      .push(gap);

  return STEPS.map((step) => {
    const mine = owned[step.key];
    let state;
    // Nothing drawn: `job` gets no carve-out. Reporting `job: "done"` over
    // four blank fields because it happens to own zero gaps THIS run is the
    // completeness LIE this module's own header forbids — a completed tick
    // on the first screen a salesperson sees. `layout` still resolves to
    // `blocked` first because it owns `no_fence_drawn` and the blocking
    // check runs before this one.
    if (mine.some((g) => g.blocking)) state = "blocked";
    else if (mine.length) state = "missing";
    else if (!drawn) state = "empty";
    else state = "done";
    return { key: step.key, panel: step.panel, state, gaps: mine };
  });
}

/** The panel a step shows, or `null` for a step nobody defined. `road.js` hands
 *  this to `tabs.js: setTab` — the model never switches anything itself. */
export function panelFor(stepKey) {
  return STEPS.find((s) => s.key === stepKey)?.panel || null;
}
