// The road ENGINE. See docs/superpowers/specs/2026-09-07-eight-step-road-design.md.
//
// No imports, no DOM, no state — `road.js` renders this, the way `profile.js`
// renders `base-top.js`. That split is what lets the step model be tested in
// node without stubbing a document, and it is the rule CLAUDE.md states for
// new frontend logic.
//
// **A map, never a wizard.** Every step is enterable at any time. The
// salesperson works on a laptop after the visit, from paper — they may hold
// the sketch and not the address, or do the gates first because the gates are
// what the customer talked about. A wizard demanding order would be defeated
// by typing junk to get past a step, which turns a completeness report into a
// completeness LIE.
//
// **It computes no completeness of its own.** It GROUPS what `handover_gaps()`
// already returned and never recomputes it. Three surfaces once answered
// "what is left" and disagreed; a fourth would be the B03 defect at a larger
// scale. The moment this file computes coverage arithmetic there are two
// answers to *is this job complete?*
//
// **It does not know what a project is.** The old signature took one solely to
// compute `!drawn`; a road now names that check as its `anchor`, so this is a
// pure function of three plain values and a role whose "not started" means
// something else changes no code here.

/** The six states, most severe first after the two that are not judgements.
 *  Exported so a renderer cannot invent a seventh by typo. */
export const STATES = ["unknown", "empty", "skipped", "blocked", "missing",
                       "done"];

/** Where a gap no step claims goes. Never reached while the totality test
 *  passes; it exists so that if one ever does reach a browser, it is visible
 *  to the person who can act on it rather than silently dropped. */
const ORPHAN_STEP = "review";

/** The panel a step shows, or `null` for a step this road does not define.
 *  Road-scoped, so two roads may each have a `review` step — a search over one
 *  global list would silently return the first match. */
export function panelFor(roadDef, stepKey) {
  return roadDef.steps.find((s) => s.key === stepKey)?.panel || null;
}

/** The road, as steps with state.
 *
 *  `gaps` is `handover.gaps` — passed in rather than fetched, so this stays
 *  pure and so one request is behind both the road and the estimate. `null`
 *  means the answer has not arrived: every step then reads `unknown` rather
 *  than defaulting to `done`. This repo shipped that bug once (audit B01, a
 *  `cache = null` painting a clean bill of health), which is why
 *  `js/handover.js: readinessShown` exists.
 *
 *  The `gaps` arrays returned hold the SAME gap objects passed in, not copies:
 *  a caller that tags one writes through into the payload it still holds. */
export function road(roadDef, gaps, stated) {
  const blank = (step) => ({
    key: step.key, panel: step.panel, state: "unknown", gaps: [],
    skippable: step.satisfiedBy !== null, skipped: false,
  });
  if (gaps == null) return roadDef.steps.map(blank);

  // Two maps, deliberately: code -> step key, and step key -> its gaps. One
  // map holding both would collide the day a code is spelled like a step key,
  // and `Object.hasOwn` is what keeps a code named `constructor` from
  // resolving through the prototype.
  const ownerOf = {};
  for (const step of roadDef.steps)
    for (const code of [...step.requires, ...step.wants]) ownerOf[code] = step.key;

  const held = Object.fromEntries(roadDef.steps.map((s) => [s.key, []]));
  for (const gap of gaps)
    held[Object.hasOwn(ownerOf, gap.code) ? ownerOf[gap.code] : ORPHAN_STEP]
      .push(gap);

  const started = !gaps.some((g) => g.code === roadDef.anchor);
  const facts = stated || {};

  return roadDef.steps.map((step) => {
    const mine = held[step.key];
    const required = new Set(step.requires);
    const open = mine.filter((g) => required.has(g.code));
    const skippable = step.satisfiedBy !== null;
    const claimed = skippable && facts[step.satisfiedBy] === true;

    let state;
    if (!started && !step.requires.includes(roadDef.anchor)) state = "empty";
    // A stated fact answers a step nothing can check — but only while it holds.
    // A claim the drawing contradicts arrives as a required gap, and then this
    // rung must not match: a skip that has stopped being true is not a skip.
    else if (claimed && open.length === 0) state = "skipped";
    else if (open.some((g) => g.blocking)) state = "blocked";
    else if (open.length) state = "missing";
    else state = "done";

    return { key: step.key, panel: step.panel, state, gaps: mine,
             skippable, skipped: claimed };
  });
}
