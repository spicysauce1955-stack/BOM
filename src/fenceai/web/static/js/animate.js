// The assembly animation's ORDER and CLOCK: when each drawn part arrives.
//
// A fence is not built all at once, and the two viewports on the Assembly tab
// draw it as if it were. This module answers the one question that turns a
// finished drawing into a build: given the parts that are ALREADY on screen and
// what each one is, in what order and at what moment does each appear.
//
// It PLACES nothing and computes no geometry — it does not know what an SVG is,
// where a post stands, or how wide a slat is. It is handed a list of
// `{ id, role }` and hands back a list of `{ id, stage, at_ms }`. Every
// rectangle it schedules was positioned by the server and drawn by
// `runview.js` / `elevation.js`; an animation that moved a part would be a
// third opinion about where that part goes, and the first one to disagree with
// the cut list.
//
// Pure: no DOM, no state, no fetch, no timers. `assembly.js` owns the interval
// and the class toggling. (Same split as `base-top.js` / `profile.js` and
// `runview.js` / `assembly.js`, for the same reason — the ordering is testable
// under node, and "posts before slats" is a claim about THIS file.)

/** The build order, coarsest first. A crew pours, stands, frames, fills, then
 *  fixes; the drawing is uncovered in the same order, which is the whole point
 *  of watching it rather than reading it. */
export const STAGES = ["groundworks", "posts", "frame", "infill", "fixings"];

/** Role -> stage. The roles are the app's existing vocabulary (`role.*` in the
 *  locale bundles, `RequirementLine.role` on the wire) plus `bay` for the panel
 *  outline the macro view draws around a bay's members.
 *
 *  Anything unrecognised lands in `fixings` — LAST, never dropped. A part with
 *  a role this table has not met is still a part somebody paid for, and a
 *  drawing that quietly left it out at the end of the animation would be a
 *  drawing that disagrees with the BOM. */
const STAGE_OF_ROLE = {
  concrete: "groundworks",
  post: "posts",
  bay: "frame",
  rail: "frame",
  infill: "infill",
  cap: "fixings",
  spacer: "fixings",
  screw: "fixings",
  gate_kit: "fixings",
};

export function stageOf(role) {
  return STAGE_OF_ROLE[role] || "fixings";
}

/** The clock, in milliseconds.
 *
 *  `leadMs` is the pause before a stage's first part lands — the beat that makes
 *  five stages read as five stages rather than as one long fade. It is >=
 *  `fadeMs` on purpose, so consecutive stages never overlap and "which stage is
 *  this" always has one answer.
 *
 *  `maxMs` is a TARGET, not a ceiling: a 1200-member run divided into 4 ms
 *  steps would be a strobe, so `minItemMs` wins and the animation simply runs
 *  longer. Better long than unreadable. */
export const TIMING = {
  leadMs: 240,      // before a stage's first part
  itemMs: 90,       // between two parts of the same stage, at most
  minItemMs: 5,     // …and at least, however many parts there are
  fadeMs: 200,      // how long one part takes to arrive
  maxMs: 6000,      // the length the step size is fitted to
};

/** The reveal schedule for a list of already-drawn parts.
 *
 * `items` is `[{ id, role }]` in the order they were DRAWN. Within a stage that
 * order is kept, which is why nothing here sorts by position: the macro view
 * draws posts along the run and the panel draws its members in the fit's own
 * order, so document order already is build order. Reading coordinates back off
 * the drawing to re-sort it would be measuring the picture.
 *
 * Returns:
 *   stages   — `[{ key, index, count, start_ms, end_ms }]`, only the stages that
 *              have parts, contiguous and non-overlapping
 *   steps    — `[{ id, stage, index, at_ms }]`, ascending by `at_ms`
 *   duration_ms — when the last part has finished arriving
 */
export function assemblyPlan(items, timing = {}) {
  const T = { ...TIMING, ...timing };
  const rows = (items || [])
    .filter((it) => it && it.id !== undefined && it.id !== null)
    .map((it) => ({ id: String(it.id), stage: stageOf(it.role) }));
  const used = STAGES.filter((key) => rows.some((r) => r.stage === key));

  // One step size for the whole animation, fitted to the target length. Per
  // stage would make a 200-slat panel crawl while its four posts flew past —
  // the eye reads the rhythm, and a rhythm that changes per stage reads as a
  // stutter rather than as a different kind of part.
  const gaps = Math.max(rows.length - used.length, 1);
  const room = Math.max(T.maxMs - T.fadeMs - used.length * T.leadMs, 0);
  const step = Math.max(T.minItemMs, Math.min(T.itemMs, Math.round(room / gaps)));

  const steps = [];
  const stages = [];
  let clock = 0;
  for (const key of used) {
    const mine = rows.filter((r) => r.stage === key);
    const start = clock + T.leadMs;
    mine.forEach((row, index) => {
      steps.push({ id: row.id, stage: key, index, at_ms: start + index * step });
    });
    const last = start + (mine.length - 1) * step;
    stages.push({ key, index: stages.length, count: mine.length,
                  start_ms: start, end_ms: last + T.fadeMs });
    clock = last;
  }
  return {
    timing: T,
    stages,
    steps,
    duration_ms: stages.length ? stages[stages.length - 1].end_ms : 0,
  };
}

/** How many parts have arrived by `ms`.
 *
 * The number `assembly.js` paints from: `steps` is ascending, so a frame is a
 * cursor into it and moving the clock forward one tick reveals the parts
 * between two cursors rather than re-examining every rectangle on screen. */
export function placedCount(plan, ms) {
  const steps = plan?.steps || [];
  let lo = 0;
  let hi = steps.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (steps[mid].at_ms <= ms) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** The ids on screen at `ms`. The straightforward reading of the schedule, and
 *  what the node tests assert against — `placedCount` is the same claim in the
 *  shape the painter wants. */
export function revealedIds(plan, ms) {
  return (plan?.steps || []).filter((s) => s.at_ms <= ms).map((s) => s.id);
}

export function clampMs(plan, ms) {
  const end = plan?.duration_ms || 0;
  if (!Number.isFinite(ms)) return end;
  return Math.max(0, Math.min(ms, end));
}

/** Everything the control strip says about one moment.
 *
 * `stage` is the stage being PLACED — null once the last part has arrived,
 * which is how the caption says "fully assembled" rather than naming a stage
 * that finished a second ago. */
export function frameAt(plan, ms) {
  const at = clampMs(plan, ms);
  const stage = (plan?.stages || []).find((s) => at < s.end_ms) || null;
  return {
    at_ms: at,
    stage: stage ? stage.key : null,
    placed: placedCount(plan, at),
    total: plan?.steps?.length || 0,
    done: at >= (plan?.duration_ms || 0),
  };
}

// The scrub slider works in permille of the whole animation rather than in
// milliseconds: the duration changes with every run (a fence of 200 parts and a
// fence of 20 are not the same length of film), and a slider whose range moved
// under the user's thumb would jump.
export const SCRUB_MAX = 1000;

export function permilleAt(plan, ms) {
  const end = plan?.duration_ms || 0;
  if (!(end > 0)) return SCRUB_MAX;
  return Math.round((clampMs(plan, ms) / end) * SCRUB_MAX);
}

export function msAtPermille(plan, permille) {
  const end = plan?.duration_ms || 0;
  const p = Math.max(0, Math.min(Number(permille) || 0, SCRUB_MAX));
  return Math.round((p / SCRUB_MAX) * end);
}
