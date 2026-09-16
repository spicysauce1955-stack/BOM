// EVERY PROBLEM ON THIS JOB, DRAWN WHERE IT ACTUALLY IS.
//
// `report/flags.py` already placed them. Its own header names the failure it
// exists to prevent: a review dialog that accumulates thousands of unlinked
// warnings, where the volume is what hides the critical ones. The fix is not
// fewer warnings — it is that every one of them points at the thing it is
// about. The list beside the map (`js/job-screen.js`) is half of that; this
// module is the other half, and without it "placed" is a field nobody can see.
//
// **It draws a glyph, not a colour.** `!` for blocking, `?` for open, on every
// mark, always. A palette where red means stop and amber means ask is a palette
// that says nothing to the roughly one man in twelve who cannot separate those
// two hues — and the office is not a population this app gets to choose. The
// colour is real and it is the fast channel; the glyph is the one that is
// always there. This is why the glyph is never dropped on small marks and never
// made conditional on the count: the moment it is optional it is absent exactly
// where two marks sit together and telling them apart matters most.
//
// **It never invents a place.** A place that cannot be resolved — a run since
// deleted, a gate whose node was dragged away, a station on nothing — draws
// NOTHING, and `pointForPlace` says `null` rather than guessing. Station 0 is
// the most tempting guess and the worst one: it is the START of a stretch,
// which is a specific claim about where a problem is, and a mark sitting there
// would send somebody to the wrong end of the wrong wall. `flags.py` makes the
// same refusal on its own side of the wire (`_place_element`, "inventing station
// 0 would put it at the start of a stretch it is not on"), and the two halves
// have to agree or the refusal is only half made.
//
// **Nothing here throws.** This drawing is what somebody OPENS in order to find
// out what is wrong; a stale id is precisely the condition it exists to report,
// so a stale id must not be the condition that blanks it. Every resolution is
// wrapped, and a place that fails is skipped rather than propagated.
//
// DOM ownership: `#g-flags`, a group already in index.html inside `#canvas`,
// and NOTHING else. It is LOOKED UP, never created and never moved, and its
// absence silently disables this module rather than growing a host of its own
// (`js/notes.js`'s rule, and the reason it is stated there too). In particular
// it must never write into `#g-notes`: that subtree belongs to `js/notes.js`,
// which paints promises a person made, and the two concerns share a canvas and
// nothing else. There is no import of that module in either direction — this
// one talks to the app through `js/state.js` and `js/geom.js` alone.

import {
  clearGroup, el, nodeById, pointAtStation, runById, runLength, toPx,
} from "./geom.js";
import { state } from "./state.js";

/** `element_id` prefix for the gate that is its own element — a `GateSpan`
 *  standing beside the runs rather than inside one (`topology/model.py`).
 *  `strategy/generator.py` writes `gate@{gate.id}` for it and
 *  `gate@{run.id}:{start}-{end}` for the older kind, the opening punched inside
 *  a run. The two are told apart by the station, never by the prefix: the
 *  second kind arrives with `station_mm` already parsed out and is placed like
 *  any other element, and only the first reaches the lookup below. */
const GATE_PREFIX = "gate@";

/** Worst first — the order `report/flags.py` sorted the findings in, and the
 *  order `js/job-screen.js` lists them in. Restated here rather than imported
 *  because nothing crosses that boundary but JSON; the value of the constant is
 *  that this module never invents a THIRD opinion about which is worse. */
const RANK = { blocking: 0, open: 1, answered: 2 };

// ---------- resolving a place ------------------------------------------------

/** The midpoint of a `GateSpan`'s two nodes, or `null`.
 *
 *  A gate beside the fence has no station on any run — it IS the element — so
 *  the only place it has on the drawing is between the two nodes it joins. That
 *  is also where `js/gates.js` draws the gate itself (`placedGates`, which
 *  measures the opening from the same two nodes), so the mark lands on the leaf
 *  rather than near it.
 *
 *  Either node missing means the drawing moved under this flag; `null`, and the
 *  finding keeps its row in the list with no mark on the map. */
function gatePoint(gateId) {
  const gate = (state.project?.topology?.gates || []).find((g) => g.id === gateId);
  if (!gate) return null;
  const a = nodeById(gate.start_node_id), b = nodeById(gate.end_node_id);
  if (!a || !b) return null;
  return [Math.round((a.x_mm + b.x_mm) / 2), Math.round((a.y_mm + b.y_mm) / 2)];
}

/** Where one `Place` belongs, in world millimetres (y-up), or `null`.
 *
 *  `null` is an ANSWER and not a failure, and it means two different true
 *  things that are both "do not draw this here":
 *
 *    - `kind: "job"` — the finding is about the whole job and has no place on
 *      the drawing. `readiness.plan_stale` is about the plan, not about a post.
 *      A mark for it would have to sit somewhere, and every "somewhere" on a
 *      map is a claim; dropping it at the world origin would invent a spot
 *      nobody pointed at. It still belongs in the list beside the map, which is
 *      the surface that can say "this job" without pointing.
 *    - the referent is gone, or was never resolvable — see the header.
 *
 *  @param {{kind: string, run_id?: string, station_mm?: number|null,
 *           node_id?: string, element_id?: string}} place
 *  @returns {[number, number] | null} `[x_mm, y_mm]`, integer mm.
 */
export function pointForPlace(place) {
  if (!place || !state.project) return null;
  // Every field but `kind` is optional and the five kinds carry different
  // handles — `flags.py: Place` says so and says why. Switching on `kind` (and
  // never on "whichever field is non-empty") is what keeps a `node` place from
  // being drawn at station 0 of a run the node happens to touch.
  const kind = place.kind;
  // `null`, never `0`. `station_mm == null` catches both `null` and `undefined`
  // and nothing else: `0` is a real station and must survive this line.
  const station = place.station_mm == null ? null : Number(place.station_mm);
  try {
    if (kind === "job") return null;
    if (kind === "run") {
      const run = runById(place.run_id);
      if (!run) return null;
      // The midpoint: the one point that is ON the stretch whatever shape it
      // is, including an L with interior vertices. `js/notes.js` places a
      // whole-run note the same way, and the two marks landing together on the
      // same stretch is correct — they are about the same stretch.
      return pointAtStation(run.id, Math.round(runLength(run) / 2));
    }
    if (kind === "node") {
      const n = nodeById(place.node_id);
      return n ? [n.x_mm, n.y_mm] : null;
    }
    if (kind === "station") {
      // A station with no station is not station 0 — see the header.
      if (station === null || !Number.isFinite(station)) return null;
      return pointAtStation(place.run_id, station);
    }
    if (kind === "element") {
      // The common case: `flags.py: _place_element` already pulled the run and
      // the station out of `post@run1:4000` / `span@run1:1334-2667`, and a span
      // is carried at its START because that is where the setting-out sheet
      // measures from. Re-parsing the ref here would be a second parser for one
      // string format, which is how the two surfaces come to disagree about
      // where a span is.
      if (station !== null && Number.isFinite(station) && place.run_id)
        return pointAtStation(place.run_id, station);
      const ref = String(place.element_id ?? "");
      if (ref.startsWith(GATE_PREFIX)) return gatePoint(ref.slice(GATE_PREFIX.length));
      return null;
    }
  } catch {
    // `geom`'s lookups assume a loaded project with whole geometry — `runPoints`
    // reads `.x_mm` off a node it did not find. A half-swapped topology is a
    // normal moment on this screen (the office opens a job while a fetch is in
    // flight), and it is never worth a throw that leaves the canvas half-drawn.
    return null;
  }
  // A `kind` this version does not know. The set is closed on the backend
  // today, and treating an unknown one as "no place" rather than as an error is
  // the same choice `flags.py: _place_scope` makes about a scope it cannot
  // place: a handle we do not recognise is not a malformed handle.
  return null;
}

// ---------- grouping ---------------------------------------------------------

/** Which flags get a mark, gathered by the point they land on.
 *
 *  **One mark per POINT, not one per flag.** Three findings about the same gate
 *  are one thing to look at with a 3 on it; three marks stacked on one pixel are
 *  an illegible blob that also lies about how many there are —
 *  `js/notes.js: markerGroups` states the same rule for the same canvas, and the
 *  two surfaces have to behave alike or the map has two grammars.
 *
 *  **Two things are deliberately NOT here.** A flag with `severity: "answered"`
 *  gets no mark: `answered` means *requires nothing from you* (`flags.py`), and
 *  a mark is a demand for attention. A `kind: "job"` place gets no mark: it has
 *  no place on the drawing. Neither is DROPPED — both still have their row in
 *  the list beside the map, which is the surface that can carry a finding
 *  without pointing at a spot. This function is about the map only, and the
 *  count it produces is a count of MARKS.
 *
 *  That last point is worth being blunt about, because it is the tempting bug:
 *  the marks do not tally the list, in either direction. A flag with three
 *  places draws three marks — `height_assumed` on a three-run job is one thing
 *  nobody said and it belongs at all three stretches — while several flags on
 *  one gate draw one. Anything that renders "N problems" must count the FLAGS.
 *
 *  @param {object[]} flags — `JobFlag`s straight off `GET /projects/{id}/flags`.
 *  @returns {{key: string, at: [number, number], runId: string,
 *             severity: string, count: number, flags: object[]}[]}
 *    Worst first, stable within a band by first appearance — the order the list
 *    beside the map reads in. `count` is `flags.length`; `runId` is `""` when
 *    no place on this point named a run (a node, or a gate beside the fence).
 */
export function markGroups(flags) {
  const byPoint = new Map();
  for (const flag of flags || []) {
    if (!flag) continue;
    // Read, never inferred from the code. `flags.py` is emphatic that severity
    // comes from the rule that fired, and a table here mapping codes to
    // severities would be a second opinion held by the surface with the least
    // reasoning behind it.
    if (flag.severity === "answered") continue;
    // A flag genuinely covers several stretches, so each of its places gets its
    // own mark — but two of its places landing on the SAME point must not count
    // it twice, which is why membership is tested before the count moves.
    for (const place of flag.places || []) {
      const at = pointForPlace(place);
      if (!at) continue;
      const key = `${at[0]}|${at[1]}`;
      let group = byPoint.get(key);
      if (!group) {
        group = { key, at, runId: "", severity: flag.severity, count: 0, flags: [] };
        byPoint.set(key, group);
      }
      // The run to select from this mark, taken BEFORE the double-count guard
      // below. Left under it, a finding whose FIRST place on this point names
      // no run — a shared-corner warning carrying `post@node:n2` and then
      // `post@run1:10000` — skipped this line on its second place and produced
      // a mark with no run at all: unclickable, while the same finding's ROW in
      // the list offered `run1`, because `job-screen.js: flagRun` scans every
      // place. Two surfaces disagreeing about one finding, from a `continue`.
      if (!group.runId && place.run_id) group.runId = String(place.run_id);
      if (group.flags.includes(flag)) continue;
      group.flags.push(flag);
      group.count = group.flags.length;
      // The worst severity on the point. A mark that showed the FIRST one would
      // draw a `?` over a stack that contains a blocker, which is the one
      // reading error this whole screen is built to prevent.
      if ((RANK[flag.severity] ?? RANK.open) < (RANK[group.severity] ?? RANK.open))
        group.severity = flag.severity;
    }
  }
  return [...byPoint.values()].sort(
    (a, b) => (RANK[a.severity] ?? RANK.open) - (RANK[b.severity] ?? RANK.open));
}

// ---------- the marks --------------------------------------------------------

/** Circle radius by severity. A blocker is bigger on purpose: size is a third
 *  channel after glyph and colour, and the three agree. */
const R = { blocking: 9, open: 8 };

/** Inline colours are a FALLBACK, exactly as an English `message` is a fallback
 *  behind a warning's `code + params`. The stylesheet owns the palette — CSS
 *  beats a presentation attribute, always, so `.flag-mark-blocking` wins over
 *  everything set here — and these values are the ones `.job-flag[data-sev]`
 *  already uses in style.css, so a mark and its row in the list are the same
 *  colour from the first frame rather than after somebody notices. */
const FALLBACK = {
  blocking: { fill: "#f8e2e2", stroke: "#a93636" },
  open: { fill: "#f7ecd8", stroke: "#9a6410" },
};

/** Draw every drawable flag into `#g-flags`.
 *
 *  **Two passes, open then blocking**, and the order is the answer to "which
 *  mark is on top where two of them nearly touch" (`js/gates.js` chooses its
 *  three passes the same way, for the same reason). SVG has no z-index: last
 *  painted wins, so the worst mark has to be painted LAST to sit on top.
 *  `flags.py` sorts worst FIRST — that is reading order, for the list — and
 *  handing that order straight to a painter would bury every blocker under the
 *  open marks around it, which is the sorted list quietly producing the
 *  opposite of what it sorted for.
 *
 *  **Interactivity is OPT-IN** (`js/elevation.js`'s contract, and
 *  `js/section-elevation.js`'s). Without `onSelect` every mark is
 *  `pointer-events: none` and the drawing underneath keeps every click —
 *  `js/editor.js` owns the canvas's click handling, and a mark that swallowed a
 *  click meant for the fence in front of it would make the drawing HARDER to
 *  work with than it was before anything was marked. This is `js/notes.js`'s
 *  rule and it is the canvas's rule, not this module's preference.
 *
 *  There is no keyboard path ON THE MARK, and that is deliberate rather than
 *  missing: the accessible route to a finding is its row in `#job-flags`, which
 *  `job-screen.js` already gives `tabindex="0"` and `role="button"` and which
 *  carries the finding's SENTENCE. A tab stop here would offer the same targets
 *  a second time, in paint order, labelled with a glyph.
 *
 *  @param {object[]} flags — `JobFlag`s from `GET /projects/{id}/flags`.
 *  @param {{onSelect?: (runId: string) => void}} [opts] — `onSelect` is called
 *         with the run id the mark sits on, or `""` when it sits on no run.
 *  @returns {number} marks drawn — NOT findings; see `markGroups`. `0` when
 *          there is no document and when `#g-flags` is absent, which are the
 *          same answer to the caller: nothing was drawn.
 */
export function renderFlagMarks(flags, opts = {}) {
  // node imports this module to exercise the pure halves; there is no document
  // there, and reaching for one would make the resolvers untestable off-browser.
  if (typeof document === "undefined") return 0;
  // Looked up FIRST: `geom.clearGroup` assumes the group is there and walks
  // `g.firstChild` without checking, so a `!g` test after calling it never runs.
  // This module never creates a host it was not given.
  if (!document.getElementById("g-flags")) return 0;
  const g = clearGroup("g-flags");

  const groups = markGroups(flags);
  for (const group of groups) if (group.severity !== "blocking") drawMark(g, group, opts);
  for (const group of groups) if (group.severity === "blocking") drawMark(g, group, opts);
  return groups.length;
}

function drawMark(g, group, opts) {
  const [x, y] = toPx(group.at);
  const sev = group.severity === "blocking" ? "blocking" : "open";
  const r = R[sev];
  const interactive = typeof opts.onSelect === "function";
  // `none` unless somebody asked for clicks — see `renderFlagMarks`. The circle
  // is the only part that ever takes one, so the glyph sitting on top of it
  // stays transparent to the pointer and a click on the `!` still lands on the
  // mark rather than on nothing.
  const inert = { "pointer-events": "none" };

  const circle = el("circle", {
    cx: x, cy: y, r,
    ...FALLBACK[sev],
    "stroke-width": sev === "blocking" ? 2.5 : 1.5,
    opacity: 0.95,
    class: `flag-mark flag-mark-${sev}`,
    // Mirrors the list's own hooks (`.job-flag[data-sev]`, `[data-run]`), so a
    // stylesheet and a smoke test address a mark and its row the same way.
    "data-sev": sev,
    "data-run": group.runId,
    "data-count": String(group.count),
    "pointer-events": interactive ? "auto" : "none",
  }, g);
  if (interactive) // The click STOPS HERE. Without this it also reaches `editor.js`'s canvas
    // handler and one gesture does two things: select-and-frame from this
    // listener, plus whatever tool is armed — placing a ground sample, opening
    // an event popover — from the canvas. `notes.js` keeps its markers
    // pointer-events:none for the same reason; this layer wants the click, so
    // it has to end it.
    circle.addEventListener("click", (ev) => {
      ev.stopPropagation();
      opts.onSelect(group.runId);
    });

  // The glyph, and it is never conditional — see the header. `!` and `?` are
  // punctuation rather than words: they need no locale entry, and adding one
  // would invite a translation of a mark that has no sentence in it.
  el("text", {
    x, y: y + 3.5, "font-size": 11, "font-weight": 700, "text-anchor": "middle",
    fill: FALLBACK[sev].stroke, class: `flag-mark-glyph flag-mark-glyph-${sev}`, ...inert,
  }, g).textContent = sev === "blocking" ? "!" : "?";

  // The count only when there IS one to report: a "1" beside every mark is
  // noise on the common case, and it is the case this screen is mostly in.
  // `.num` for the same reason every id and dimension carries it — a Latin
  // numeral inside a Hebrew page needs its own direction (CLAUDE.md).
  if (group.count > 1) {
    el("text", {
      x: x + r + 2, y: y - r + 2, "font-size": 9, "text-anchor": "start",
      fill: FALLBACK[sev].stroke, class: "flag-mark-count num", ...inert,
    }, g).textContent = String(group.count);
  }
}
