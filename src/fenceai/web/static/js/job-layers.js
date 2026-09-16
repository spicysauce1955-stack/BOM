// EMPHASIS ON THE PLAN — one fact at a time, and NEVER at the cost of another.
//
// The office job screen puts the plan in the middle and a card per stretch
// beside it. This module draws the optional overlays on that plan: what each
// stretch STANDS ON, and how TALL the fence on it is meant to be. Both are
// facts a card already states in words; drawn on the map they stop being a
// column of numbers and become a shape you can see the shape of the job in.
//
// ## `PROTECTED`, and why it is the load-bearing thing here
//
// A layer switch is one of the most natural controls to build and one of the
// easiest to build wrong. The wrong version is the one everybody has used: the
// switch turns a layer ON and, implicitly, turns everything competing with it
// OFF — the map "declutters" so the chosen fact reads cleanly. It feels like
// help. It is how a screen built for finding problems comes to hide them.
//
// The precedent is not a taste argument, it is regulation. Electronic marine
// charts define a **Display Base** that the operator cannot remove from the
// display at all, and require the standard display to be restorable by a single
// action. That exists because decluttering killed people: a 2016 grounding was
// traced to a standard chart view that had hidden the depth that mattered. The
// mariner was not careless — he was reading a screen that had quietly decided
// which facts he needed.
//
// This job has exactly that shape of fact in it. Section A of the demo job
// stands on a wall that steps up 1 120 mm at 4.0 m, and the fence top does not
// follow, so three of its six bays carry NO FENCE. If turning on "heights"
// dimmed the runs, or turning on "ground" dropped the flag marks, the one thing
// somebody opened this job to discover would be the thing the control removed.
//
// So §5 of the design (docs/superpowers/specs/2026-09-16-office-job-screen-design.md)
// names a protected base — the runs, the gates, the house, the street, the
// section letters and every flag — and `PROTECTED` below is that sentence
// transcribed into selectors. It is exported so the rule is ASSERTABLE: a test
// can take the list and check that no layer touched any of it, which is a
// check that survives a redesign of the drawing. A screenshot cannot make that
// promise, and a comment saying "do not hide the runs" is not a promise at all
// — it is the thing the next person disagrees with in good faith, six months
// from now, while making the screen simpler.
//
// The enforcement is structural as well as declarative: this module writes into
// `#g-layers` and reads nothing else, so it has no way to dim a run even if it
// wanted to. `PROTECTED` is what makes that a stated contract rather than an
// accident of the current implementation.
//
// ## What is drawn, and the rule behind the two shapes
//
//   * **Surface** is a NOMINAL fact — soil, concrete, masonry wall. There is no
//     more or less of it, so it gets a constant-width band and CSS gives it a
//     colour. A band that varied would imply a magnitude nobody measured.
//   * **Height** is a QUANTITY, so it is drawn as a quantity: the ribbon is as
//     wide as the fence is tall, at the plan's own scale — the fence laid flat
//     on the ground, both ways. That needs no legend and no key: the reader
//     measures it against the same drawing's gate opening or run length, which
//     are in the same millimetres. A palette of height bands would need a
//     legend, and a legend is a second place for the truth to live.
//
// Neither shape carries a word, and that is deliberate: shapes and colour
// belong on the map, sentences belong in the list beside it. This module
// therefore needs NO locale keys, which is also the only way an overlay can be
// safe in both directions — there is nothing here to mirror. The plan canvas is
// never mirrored in RTL (CLAUDE.md), and neither is anything drawn on it.
//
// ## DOM ownership
//
// `#g-layers`, a group in index.html between `#g-context` and `#g-topology` —
// so emphasis sits UNDER the fence line rather than over it — and NOTHING else.
// It is LOOKED UP, never created: absence disables this module silently rather
// than growing a host of its own (`js/notes.js`'s rule).
//
// The lookup happens BEFORE `clearGroup`, and that ordering is a real trap
// rather than a style point: `geom.clearGroup` walks `g.firstChild` with no null
// check, so an `if (!g) return;` written after the call never runs — the throw
// beat it there.
//
// ## Purity
//
// `surfaceBands` and `heightRibbon` touch no DOM and are testable in node, like
// `bayRects` in `js/section-elevation.js`. They take the run's polyline as an
// optional second argument and otherwise resolve it through `js/geom.js` — this
// module imports no state of its own, so the one coupling to the loaded project
// is `geom`'s own lookup, and a test can either inject points or populate
// `state.project` and call with a section alone.

import { clearGroup, el, runById, runPoints, toPx } from "./geom.js";

/** Every selector a layer control may never affect — §5's protected base,
 *  transcribed. Frozen, because a list whose whole job is to be un-negotiable
 *  should not be editable at runtime by whoever imports it.
 *
 *  Each entry is here for its own reason:
 *
 *   - `#g-topology` — the runs. The fence itself is the drawing; a layer that
 *     dimmed it to make its own band read would be emphasising by subtraction,
 *     which is the one move this module exists to refuse.
 *   - `.run-hit` — the invisible fat line that makes a run clickable
 *     (`js/editor.js`). Hiding a HANDLE is hiding: a run you can see and cannot
 *     select is a stretch whose card, elevation and decisions you cannot reach.
 *   - `.run-label` — the stretch's identity on the map, and where its section
 *     letter reads. The cards are lettered A, B, C; a map with the letters
 *     switched off cannot be matched to them, and the link between the two
 *     panes is the whole argument for the map being in the centre.
 *   - `#g-gates` — the gates. A standalone gate belongs to no section (§2), so
 *     the map is the ONLY surface that places it. Switch it off and it is gone
 *     from the screen entirely, not merely de-emphasised.
 *   - `#g-context` — the house, the street, the landmarks. They are what say
 *     WHERE the job is; a plan of three lines with no context is not a plan of
 *     anywhere.
 *   - `#g-flags` — every flag mark. §4 states it in four words: a flag is never
 *     on a layer. The findings are the reason the job was opened, and a control
 *     that could hide the blocking ones is a control that can make an unbuildable
 *     job look finished.
 *
 *  Deliberately NOT in the list: `#g-notes`. Notes are named in §5 as one of
 *  the layer switches, so protecting them here would contradict the design.
 *  Nothing in this module can touch them either way — the group belongs to
 *  `js/notes.js` — and that is the point of naming the omission rather than
 *  quietly leaving it out.
 *
 *  @type {readonly string[]}
 */
export const PROTECTED = Object.freeze([
  "#g-topology",
  ".run-hit",
  ".run-label",
  "#g-gates",
  "#g-context",
  "#g-flags",
]);

/** The group this module owns, and the only one it will ever write into. */
const HOST = "g-layers";

/** Half-width of a surface band, in world mm: about 23 px of band at the
 *  canvas's own scale, which is wide enough to read a colour off and narrow
 *  enough that the fence line stays the strongest mark on its own stretch.
 *
 *  A CONSTANT, because a surface is a nominal fact — see the header. */
const SURFACE_HALF_MM = 260;

/** The ribbon is the fence laid flat, so its half-width is half the stated
 *  height and its full width is the height itself, in the plan's millimetres.
 *
 *  Named rather than inlined because it is the whole readable rule: change it
 *  and the ribbon stops being measurable against the drawing it is on, which is
 *  the only reason it needs no legend. */
const HEIGHT_TO_HALF_WIDTH = 0.5;

/** Two points are the same vertex when they are within this, in mm. A run
 *  authored through a corner twice — or a segment whose ends snapped together —
 *  yields a zero-length segment with no direction, and a normal computed from
 *  it is a division by zero that propagates NaN through the whole band. */
const SAME_POINT_MM = 1;

// ---------- pure geometry ----------------------------------------------------

/** The run's polyline in world mm, or `null` when it cannot be had.
 *
 *  `null` covers every way this legitimately fails on THIS screen: a stretch
 *  whose run was deleted, a selection left over from the previous job, a
 *  topology half-swapped under a fetch still in flight. All three are ordinary
 *  moments here, none of them is an error, and every one of them must end in
 *  "draw nothing for that stretch" rather than in a throw that leaves the
 *  canvas half-painted. `js/flag-marks.js` makes the same refusal for the same
 *  reason, and the two halves of the map have to behave alike.
 */
function runPolyline(runId) {
  if (!runId) return null;
  try {
    const run = runById(runId);
    if (!run) return null;
    const pts = runPoints(run);
    return Array.isArray(pts) && pts.length >= 2 ? pts : null;
  } catch {
    // `geom`'s lookups assume a loaded project with whole geometry —
    // `runPoints` reads `.x_mm` off a node it did not find.
    return null;
  }
}

/** Consecutive duplicates removed, so every remaining segment has a direction.
 *  Everything below indexes segments against vertices, so this has to happen
 *  first and once. */
function cleaned(points) {
  const out = [];
  for (const p of points || []) {
    const x = Number(p?.[0]), y = Number(p?.[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const last = out[out.length - 1];
    if (last && Math.hypot(x - last[0], y - last[1]) <= SAME_POINT_MM) continue;
    out.push([x, y]);
  }
  return out;
}

/** Per-segment length, ROUNDED — the same arithmetic as `geom.runLength` and
 *  `geom.pointAtStation`, which mirror the backend's `run_length`. A station is
 *  only meaningful against one measure of the run, and a second measure here
 *  would put a surface boundary a few millimetres off the boundary the card,
 *  the setting-out sheet and the generator all agree on. */
function segmentLengths(points) {
  const lens = [];
  for (let i = 0; i + 1 < points.length; i++)
    lens.push(Math.round(Math.hypot(points[i + 1][0] - points[i][0],
                                    points[i + 1][1] - points[i][1])));
  return lens;
}

/** The piece of a polyline between two stations, endpoints interpolated and
 *  interior corners kept.
 *
 *  Stations are clamped to the DRAWING's own length, never to the section's
 *  `length_mm`. When the two disagree the drawing has moved since the read
 *  model was fetched, and the drawing is the thing being drawn on: a band
 *  running past the end of a run it was measured on would be a claim about
 *  ground that is not there.
 */
function subPolyline(points, startMm, endMm) {
  const lens = segmentLengths(points);
  const total = lens.reduce((a, b) => a + b, 0);
  const from = Math.max(0, Math.min(Number(startMm) || 0, total));
  const to = Math.max(0, Math.min(Number(endMm) || 0, total));
  if (!(to > from)) return [];

  const out = [];
  let acc = 0;
  for (let i = 0; i < lens.length; i++) {
    const segStart = acc, segEnd = acc + lens[i];
    acc = segEnd;
    if (segEnd <= from || segStart >= to || lens[i] <= 0) continue;
    const [ax, ay] = points[i], [bx, by] = points[i + 1];
    const at = (s) => {
      const t = (s - segStart) / lens[i];
      return [ax + (bx - ax) * t, ay + (by - ay) * t];
    };
    const head = at(Math.max(from, segStart));
    const tail = at(Math.min(to, segEnd));
    const last = out[out.length - 1];
    // A corner is shared by two segments: the second one's head IS the first
    // one's tail, and pushing it twice would leave a zero-length segment in the
    // slice — exactly what `cleaned` exists to keep out.
    if (!last || Math.hypot(head[0] - last[0], head[1] - last[1]) > SAME_POINT_MM)
      out.push(head);
    out.push(tail);
  }
  return out.length >= 2 ? out : [];
}

/** The polyline moved sideways by `dMm` — positive to the left of the direction
 *  of travel, in the world's y-up millimetres.
 *
 *  Corners take the AVERAGE of the two adjacent segment normals, with no miter
 *  compensation, and the omission is on purpose. A true miter divides by
 *  cos(θ/2), which goes to infinity as a run doubles back on itself — on a
 *  hairpin that draws a spike kilometres long across the whole plan. Averaging
 *  instead pinches the band slightly on the inside of a sharp corner. Both are
 *  wrong by a few millimetres at a corner; only one of them is wrong in a way
 *  that destroys the drawing, and this is emphasis, not a measurement anybody
 *  will cut material to.
 */
function offsetPolyline(points, dMm) {
  const n = points.length;
  if (n < 2) return [];
  const normals = [];
  for (let i = 0; i + 1 < n; i++) {
    const dx = points[i + 1][0] - points[i][0];
    const dy = points[i + 1][1] - points[i][1];
    const len = Math.hypot(dx, dy) || 1;
    normals.push([-dy / len, dx / len]);
  }
  return points.map((p, i) => {
    const before = normals[i - 1], after = normals[i];
    let nx, ny;
    if (!before) { [nx, ny] = after; }
    else if (!after) { [nx, ny] = before; }
    else {
      const sx = before[0] + after[0], sy = before[1] + after[1];
      const len = Math.hypot(sx, sy);
      // A segment that reverses exactly cancels its own normal; there is no
      // "average side" there, so the incoming one is kept rather than a NaN.
      if (len <= 1e-9) { [nx, ny] = before; } else { nx = sx / len; ny = sy / len; }
    }
    return [p[0] + nx * dMm, p[1] + ny * dMm];
  });
}

/** A closed ring `halfMm` either side of a polyline, in integer world mm.
 *
 *  Integers because that is what the world is measured in (ADR-0002): the float
 *  offsets above are transient, and rounding here keeps the ring addressable in
 *  the same units as everything else on the canvas.
 */
function ringAround(points, halfMm) {
  if (points.length < 2 || !(halfMm > 0)) return [];
  const left = offsetPolyline(points, halfMm);
  const right = offsetPolyline(points, -halfMm).reverse();
  return [...left, ...right].map((p) => [Math.round(p[0]), Math.round(p[1])]);
}

// ---------- the two layers ---------------------------------------------------

/** What this stretch stands on, as bands along the run.
 *
 *  One band per `SurfaceRun` — the half-open `[start_mm, end_mm)` stretches
 *  `report/sections.py` derives, which TILE the run including the remainder
 *  nobody stated, which stands on `soil`. That remainder is drawn like any
 *  other band on purpose: a silent default is reported, never hidden
 *  (`sections.py`'s own rule), and a gap in the band would read as "nobody has
 *  looked at this yet" when the truth is "this will be built on soil".
 *
 *  The scalar `base_surface` is deliberately not used here. `"mixed"` is an
 *  honest answer for a card and a meaningless one for a map: a stretch standing
 *  on two things is drawn as the two things, in the places they actually are.
 *
 *  @param {object} section — one `SectionFacts` from `GET /projects/{id}/sections`.
 *  @param {[number, number][]} [points] — the run's polyline in world mm.
 *         Defaults to the drawing's own; pass it to test with no project loaded.
 *  @returns {{runId: string, surface: string, startMm: number, endMm: number,
 *             ring: [number, number][]}[]}
 *    One entry per band, in station order. Empty when the run is gone, when the
 *    stretch has no surfaces, or when the drawing has no length to band.
 */
export function surfaceBands(section, points = runPolyline(section?.run_id)) {
  const pts = cleaned(points);
  if (!section || pts.length < 2) return [];
  const out = [];
  for (const s of section.surfaces || []) {
    if (!s) continue;
    const piece = subPolyline(pts, s.start_mm, s.end_mm);
    if (piece.length < 2) continue;
    const ring = ringAround(piece, SURFACE_HALF_MM);
    if (ring.length < 4) continue;
    out.push({
      runId: String(section.run_id ?? ""),
      surface: String(s.surface ?? ""),
      startMm: Number(s.start_mm) || 0,
      endMm: Number(s.end_mm) || 0,
      ring,
    });
  }
  return out;
}

/** How tall the fence along this stretch is MEANT to be, as a ribbon.
 *
 *  **`null` when nobody gave a single answer.** `height_intent_mm` is `null`
 *  both when nobody stated a height and when two people stated different ones
 *  (`sections.py`), and neither of those is a width. The tempting fill is the
 *  project default — 1 800 mm, which is exactly what the demo job is silently
 *  built at — and drawing it would put a measurement on the map that nobody
 *  took, in the one place a reader would trust it most. The fact that nobody
 *  stated a height is real, it is why `height_assumed` exists, and it is carried
 *  by the flag mark and the card's sentence. A layer's job is to emphasise what
 *  is known, and it emphasises nothing by inventing.
 *
 *  **Partial coverage is REPORTED, not drawn away.** A stated height may cover
 *  part of the stretch, and the read model says how much but not WHICH part —
 *  it is a merged length, not an interval list. So the ribbon runs the whole
 *  stretch and carries its coverage in the returned object (and, on the map, in
 *  `data-covered-mm` / `data-partial`, which is what CSS can render differently
 *  and what the card's sentence says in words). Drawing a shorter ribbon from
 *  station 0 would place the covered part somewhere nobody said it was, which
 *  is the same invention in a subtler shape.
 *
 *  @param {object} section — one `SectionFacts`.
 *  @param {[number, number][]} [points] — the run's polyline in world mm.
 *  @returns {{runId: string, heightMm: number, coveredMm: number,
 *             lengthMm: number, coveredPermille: number, partial: boolean,
 *             ring: [number, number][]} | null}
 */
export function heightRibbon(section, points = runPolyline(section?.run_id)) {
  const pts = cleaned(points);
  if (!section || pts.length < 2) return null;
  const heightMm = section.height_intent_mm == null ? 0 : Number(section.height_intent_mm);
  if (!Number.isFinite(heightMm) || heightMm <= 0) return null;
  const coveredMm = Math.max(0, Number(section.height_covered_mm) || 0);
  // No covered length is no ground for the claim. A ribbon over a stretch where
  // the stated height covers nothing would be the whole invention above, minus
  // only the honesty of `null`.
  if (coveredMm <= 0) return null;

  const lengthMm = segmentLengths(pts).reduce((a, b) => a + b, 0);
  const ring = ringAround(pts, Math.round(heightMm * HEIGHT_TO_HALF_WIDTH));
  if (ring.length < 4) return null;
  return {
    runId: String(section.run_id ?? ""),
    heightMm,
    coveredMm,
    lengthMm,
    // Against the section's own length, which is what the coverage was measured
    // against — not against the drawing's current one.
    coveredPermille: Number(section.length_mm) > 0
      ? Math.round((coveredMm * 1000) / Number(section.length_mm)) : 0,
    partial: Number(section.length_mm) > 0 && coveredMm < Number(section.length_mm),
    ring,
  };
}

// ---------- drawing ----------------------------------------------------------

/** A surface name as a CSS class suffix. The backend's set is closed —
 *  `soil | concrete | masonry_wall` — so this normally changes nothing; it
 *  exists so that a surface added to the enum before a stylesheet knows about
 *  it produces an unstyled class rather than a broken selector, and so nothing
 *  a document ever carried can end up as markup. */
function classSuffix(surface) {
  return String(surface || "").replace(/[^A-Za-z0-9_-]/g, "");
}

const points2Attr = (ring) => ring.map((p) => toPx(p).join(",")).join(" ");

/** Draw the enabled layers into `#g-layers`.
 *
 *  **Off means erased, and erased means only these shapes.** The group is
 *  cleared on every call, so switching a layer off removes what it drew — and
 *  because the group is the only thing this module can reach, "off" can never
 *  take anything else with it. That is the whole mechanism behind `PROTECTED`.
 *
 *  **Ribbons first, bands second**, and the order is the answer to "which one
 *  can you see where they overlap". SVG has no z-index: last painted wins. The
 *  height ribbon is the wider shape — as wide as the fence is tall — so a
 *  narrow surface band painted first would sit underneath it and be invisible
 *  exactly when both layers are on, which is the case somebody turns two
 *  switches on to look at. `js/flag-marks.js` and `js/gates.js` choose their
 *  passes the same way for the same reason.
 *
 *  **`pointer-events: none` throughout.** The canvas's click handling belongs
 *  to `js/editor.js`, and a mark that swallowed a click meant for the fence or
 *  for a flag would make the drawing harder to work with than it was before
 *  anything was emphasised. There is no opt-in here at all, unlike the flag
 *  marks: a band is not a thing to click — it is one stretch's card's fact,
 *  drawn where the fact is, and the stretch under it is already selectable.
 *
 *  @param {object[]} sections — `SectionFacts` from `GET /projects/{id}/sections`.
 *  @param {{ground?: boolean, heights?: boolean}} [layers] — which are on.
 *         Missing or absent means off, so a caller that has not built its
 *         controls yet draws nothing rather than everything.
 *  @returns {number} shapes drawn — NOT sections and NOT layers. Two layers on
 *          over a three-stretch job draws more than three. `0` when there is no
 *          document and when `#g-layers` is absent, which are the same answer
 *          to the caller: nothing was drawn.
 */
export function renderJobLayers(sections, layers) {
  // node imports this module to exercise the pure halves; there is no document
  // there, and reaching for one would make them untestable off-browser.
  if (typeof document === "undefined") return 0;
  // Looked up FIRST — see the header: `clearGroup` throws on a missing group,
  // so a guard written after it never runs.
  if (!document.getElementById(HOST)) return 0;
  const g = clearGroup(HOST);

  const wantGround = !!(layers && layers.ground);
  const wantHeights = !!(layers && layers.heights);
  if (!wantGround && !wantHeights) return 0;

  const list = Array.isArray(sections) ? sections : [];
  let drawn = 0;

  if (wantHeights) {
    for (const section of list) {
      const ribbon = heightRibbon(section);
      if (!ribbon || ribbon.ring.length < 4) continue;
      el("polygon", {
        points: points2Attr(ribbon.ring),
        class: "job-layer-height",
        "data-run": ribbon.runId,
        // `.num`'s concern, in attribute form: these are diagnostics and hooks
        // for a stylesheet and a smoke test, never text on the page — the
        // sentence about this height lives on the card beside the map.
        "data-height-mm": String(ribbon.heightMm),
        "data-covered-mm": String(ribbon.coveredMm),
        "data-partial": ribbon.partial ? "yes" : "no",
        "pointer-events": "none",
      }, g);
      drawn += 1;
    }
  }

  if (wantGround) {
    for (const section of list) {
      for (const band of surfaceBands(section)) {
        const suffix = classSuffix(band.surface);
        el("polygon", {
          points: points2Attr(band.ring),
          // The bare class carries the shape, the suffixed one the material, so
          // a stylesheet can say "every band" and "the wall ones" separately —
          // and a material with no rule of its own still reads as a band.
          class: `job-layer-surface${suffix ? ` job-layer-surface-${suffix}` : ""}`,
          "data-run": band.runId,
          "data-surface": band.surface,
          "data-start-mm": String(band.startMm),
          "data-end-mm": String(band.endMm),
          "pointer-events": "none",
        }, g);
        drawn += 1;
      }
    }
  }

  return drawn;
}
