"""Every problem on the job, drawn where it actually is (static/js/flag-marks.js).

`report/flags.py` places a finding; this module is what turns "placed" into a
field somebody can see. Until now it had no test of any kind: a test review ran
nine mutations against it and all nine survived both `pytest -q` and the browser
smoke suite, because the browser fixture happens not to contain the shapes the
module argues hardest about — it has no gate at all, so `gatePoint` was reached
by nothing in the repo, and it has no finding sitting at station 0.

The fixture here is chosen so that a WRONG implementation gives a different
answer from a right one:

  * station **0** of run1 is `(0, 0)` and run1's MIDPOINT is `(5000, 0)` — two
    different places, so "station 0 was treated as no station" cannot hide
    behind a coincidence;
  * node `n2` is shared, so one point on the drawing is reachable as a node
    (no run), as station 10000 of run1, and as station 0 of run2 — which is the
    only way to see WHICH run a mark offers to select;
  * the gate stands beside the fence on two nodes of its own, so its mark has
    no station anywhere and must come from the gate lookup or not at all;
  * one point carries an `open` finding BEFORE a `blocking` one, so a mark that
    showed the first severity rather than the worst draws a `?` over a blocker.

The renderer is exercised too, through the minimum SVG DOM that
`tests/web/test_elevation_module.py` established for the same reason: paint
order and the glyph are the two things this module's own header calls
load-bearing, and neither is observable from `markGroups` alone.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { state } from "./js/state.js";
import { markGroups, pointForPlace, renderFlagMarks } from "./js/flag-marks.js";

const out = {};

// ---------- the drawing under the flags --------------------------------------
// Two runs meeting at a shared node `n2`, and a gate standing BESIDE the fence
// on two nodes of its own. Station 0 of run1 is (0,0) while run1's midpoint is
// (5000,0): deliberately far apart, so "0 was read as absent" cannot pass by
// landing on the same pixel as something else.
const TOPOLOGY = {
  nodes: [
    {id: "n1",  x_mm: 0,     y_mm: 0,    z_mm: 0},
    {id: "n2",  x_mm: 10000, y_mm: 0,    z_mm: 0},   // run1's end AND run2's start
    {id: "n3",  x_mm: 10000, y_mm: 6000, z_mm: 0},
    {id: "ng1", x_mm: 20000, y_mm: 0,    z_mm: 0},
    {id: "ng2", x_mm: 20000, y_mm: 4000, z_mm: 0},
  ],
  runs: [
    {id: "run1", start_node_id: "n1", end_node_id: "n2", interior_vertices: []},
    {id: "run2", start_node_id: "n2", end_node_id: "n3", interior_vertices: []},
  ],
  gates: [{id: "gate1", start_node_id: "ng1", end_node_id: "ng2"}],
};
state.project = {id: "p1", topology: TOPOLOGY};

const P = (place) => pointForPlace(place);

// ---------- resolving one place ----------------------------------------------
out.job_place = P({kind: "job"});
out.run_place = P({kind: "run", run_id: "run1"});          // midpoint, not the start
out.run2_place = P({kind: "run", run_id: "run2"});
out.node_place = P({kind: "node", node_id: "n2"});
out.gate_place = P({kind: "element", element_id: "gate@gate1"});

// Station ZERO. `flags.py` is emphatic that `None` and `0` are different claims,
// and this is the line where a falsy test quietly merges them.
out.station_zero = P({kind: "station", run_id: "run1", station_mm: 0});
out.element_at_zero = P({kind: "element", element_id: "post@run1:0",
                         run_id: "run1", station_mm: 0});
// ...and the other half of the same rule: no station is NOT station 0.
out.station_missing = P({kind: "station", run_id: "run1", station_mm: null});
out.station_undefined = P({kind: "station", run_id: "run1"});

out.station_mid = P({kind: "station", run_id: "run1", station_mm: 2500});
out.station_end = P({kind: "station", run_id: "run1", station_mm: 10000});
out.run2_start = P({kind: "station", run_id: "run2", station_mm: 0});
// A span is carried at its START (`flags.py: _place_element`).
out.element_span = P({kind: "element", element_id: "span@run1:2000-4000",
                      run_id: "run1", station_mm: 2000});

// ---------- things that are gone, or were never resolvable --------------------
out.ghost_run = P({kind: "run", run_id: "run9"});
out.ghost_node = P({kind: "node", node_id: "n99"});
out.ghost_gate = P({kind: "element", element_id: "gate@gate9"});
out.ghost_station = P({kind: "station", run_id: "run9", station_mm: 1000});
out.element_bare = P({kind: "element", element_id: "post@node:n2"});
out.unknown_kind = P({kind: "wall", run_id: "run1"});
out.nan_station = P({kind: "station", run_id: "run1", station_mm: "later"});
out.no_place = P(null);

// A gate whose node was dragged away: the gate is still listed, its node is not.
state.project.topology.gates.push(
  {id: "gate2", start_node_id: "ng1", end_node_id: "gone"});
out.gate_half_missing = P({kind: "element", element_id: "gate@gate2"});
state.project.topology.gates.pop();

// A run whose end node was deleted — `geom.runPoints` dereferences a node it did
// not find, so the resolver's own try/catch is the only thing between a stale id
// and a blank canvas.
state.project.topology.runs.push(
  {id: "run3", start_node_id: "n1", end_node_id: "gone", interior_vertices: []});
out.broken_run = (() => {
  try { return P({kind: "run", run_id: "run3"}); }
  catch (err) { return "threw: " + err.message; }
})();
state.project.topology.runs.pop();

// ---------- the flags, in the order `flags.py` hands them over ----------------
const F_ZERO = {code: "post_at_start", severity: "open", source: "strategy",
                places: [{kind: "station", run_id: "run1", station_mm: 0}]};
const F_NODE = {code: "corner_unresolved", severity: "open", source: "strategy",
                places: [{kind: "node", node_id: "n2"}]};
const F_RUN1_END = {code: "end_post_clash", severity: "open", source: "strategy",
                    places: [{kind: "station", run_id: "run1", station_mm: 10000}]};
const F_RUN2_START = {code: "start_post_clash", severity: "open", source: "strategy",
                      places: [{kind: "station", run_id: "run2", station_mm: 0}]};
const F_GATE_OPEN = {code: "gate_swing_unstated", severity: "open", source: "readiness",
                     places: [{kind: "element", element_id: "gate@gate1"}]};
const F_GATE_BLOCK = {code: "gate_leaf_unsupported", severity: "blocking",
                      source: "handover",
                      places: [{kind: "element", element_id: "gate@gate1"}]};
const F_ANSWERED = {code: "height_confirmed", severity: "answered", source: "readiness",
                    places: [{kind: "node", node_id: "n3"}]};
const F_JOB = {code: "plan_stale", severity: "open", source: "readiness",
               places: [{kind: "job"}]};
const F_MULTI = {code: "height_assumed", severity: "open", source: "strategy",
                 places: [{kind: "run", run_id: "run1"}, {kind: "run", run_id: "run2"}]};

const FLAGS = [F_ZERO, F_NODE, F_RUN1_END, F_RUN2_START, F_GATE_OPEN,
               F_GATE_BLOCK, F_ANSWERED, F_JOB, F_MULTI];

const groups = markGroups(FLAGS);
out.group_keys = groups.map((g) => g.key);
out.group_severities = groups.map((g) => g.severity);
out.group_counts = groups.map((g) => g.count);
out.group_runs = groups.map((g) => g.runId);
const at = (key) => groups.find((g) => g.key === key) || null;
out.gate_group = (() => { const g = at("20000|2000");
  return g && {sev: g.severity, count: g.count, run: g.runId,
               codes: g.flags.map((f) => f.code)}; })();
out.shared_node_group = (() => { const g = at("10000|0");
  return g && {sev: g.severity, count: g.count, run: g.runId,
               codes: g.flags.map((f) => f.code)}; })();
out.zero_group = (() => { const g = at("0|0");
  return g && {count: g.count, run: g.runId}; })();
out.answered_group = at("10000|6000");
out.multi_marks = groups.filter((g) => g.flags.includes(F_MULTI)).map((g) => g.key);

// Two places of ONE flag landing on one point is one mark with a count of one.
const DUPE = {code: "corner", severity: "open", source: "strategy", places: [
  {kind: "node", node_id: "n2"},
  {kind: "station", run_id: "run1", station_mm: 10000},
]};
const dupe = markGroups([DUPE]);
out.dupe_groups = dupe.length;
out.dupe_count = dupe[0].count;

out.empty_in = [markGroups([]).length, markGroups(null).length,
                markGroups([null, undefined]).length];

// ---------- the minimum SVG DOM ----------------------------------------------
// Paint order and the glyph are what this module's header calls load-bearing,
// and neither is visible from `markGroups`. `test_elevation_module.py` shims the
// same way and for the same reason.
function makeEl(tag) {
  return {
    tagName: tag, children: [], attrs: {}, textContent: "", listeners: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    appendChild(child) { this.children.push(child); return child; },
    removeChild(child) {
      this.children = this.children.filter((c) => c !== child); return child;
    },
    get firstChild() { return this.children[0] || null; },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
  };
}
let HOST = makeEl("g");
globalThis.document = {
  getElementById: (id) => (id === "g-flags" ? HOST : null),
  createElementNS: (_ns, tag) => makeEl(tag),
  querySelectorAll: () => [],
  documentElement: {},
};

/** One record per mark, in PAINT order: drawMark appends its circle, then the
 *  glyph, then the count when there is one. */
function marks() {
  const list = [];
  for (const child of HOST.children) {
    const cls = child.attrs.class || "";
    if (child.tagName === "circle") {
      list.push({sev: child.attrs["data-sev"], run: child.attrs["data-run"],
                 count: child.attrs["data-count"], r: Number(child.attrs.r),
                 pe: child.attrs["pointer-events"], glyph: null, label: null,
                 circle: child});
    } else if (cls.includes("flag-mark-glyph")) {
      list[list.length - 1].glyph = child.textContent;
    } else if (cls.includes("flag-mark-count")) {
      list[list.length - 1].label = child.textContent;
    }
  }
  return list;
}

out.drawn = renderFlagMarks(FLAGS);
const painted = marks();
out.paint_sev = painted.map((m) => m.sev);
out.paint_glyph = painted.map((m) => m.glyph);
out.paint_run = painted.map((m) => m.run);
out.paint_count_attr = painted.map((m) => m.count);
out.paint_labels = painted.map((m) => m.label);
out.paint_radii = painted.map((m) => m.r);
out.paint_inert = painted.map((m) => m.pe);
out.glyph_classes = HOST.children
  .filter((c) => (c.attrs.class || "").includes("flag-mark-glyph"))
  .map((c) => c.attrs.class);

// Re-rendering replaces the marks rather than stacking a second set on them.
renderFlagMarks(FLAGS);
out.second_render_children = HOST.children.length;
out.first_render_children = painted.length ? HOST.children.length : 0;

// Interactivity is opt-in, and the click STOPS at the mark.
let stopped = false;
const chosen = [];
renderFlagMarks(FLAGS, {onSelect: (runId) => chosen.push(runId)});
const live = marks();
out.live_pe = live.map((m) => m.pe);
// Guarded rather than indexed: a mark that is MISSING is one of the failures
// this file exists to report, and it must arrive as a wrong answer below rather
// than as a thrown script that makes every assertion here unreadable at once.
const clickMark = (pred, onStop) => {
  const mark = live.find(pred);
  if (!mark || !(mark.circle.listeners.click || [])[0]) return false;
  mark.circle.listeners.click[0]({stopPropagation: onStop});
  return true;
};
out.clicked_shared = clickMark((m) => m.run === "run1", () => { stopped = true; });
out.clicked_gate = clickMark((m) => m.sev === "blocking", () => {});
out.click_stopped = stopped;
out.clicked_runs = chosen;

// No host, no marks, no throw — the group is looked up, never created.
HOST = null;
out.hostless = (() => {
  try { return renderFlagMarks(FLAGS); }
  catch (err) { return "threw: " + err.message; }
})();
HOST = makeEl("g");

// ---------- no project at all -------------------------------------------------
state.project = null;
out.unloaded_point = P({kind: "run", run_id: "run1"});
out.unloaded_groups = markGroups(FLAGS).length;

// A finding on ONE point whose first place names no run and whose second does.
// The mark must offer the run the row offers.
//
// The drawing is put BACK first: the block above deliberately clears it to
// prove an unloaded page resolves nothing, and appending after that without
// restoring it made this read `null` — a test failing for the fixture's reason
// rather than the code's.
state.project = {id: "p1", topology: TOPOLOGY};
const twoPlace = [{
  code: "node_surface_disagreement", severity: "open", source: "strategy",
  params: {}, places: [
    {kind: "node", run_id: "", station_mm: null, node_id: "n2", element_id: ""},
    {kind: "element", run_id: "run1", station_mm: 10000, node_id: "",
     element_id: "post@run1:10000"},
  ],
}];
out.two_place_group_runid = (markGroups(twoPlace)[0] || {}).runId ?? null;

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def fm():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------- resolving a place -------------------------------------------------

def test_station_zero_is_a_real_station_and_not_a_missing_one(fm):
    """`station_mm == null`, never `!station_mm`.

    Station 0 is the START of a stretch — a specific claim about where a problem
    is — and `flags.py` refuses to invent it for exactly that reason. A falsy
    test merges "at the very beginning of run1" into "nowhere", and the finding
    loses its mark while the list still claims it has a place.

    The fixture puts station 0 at (0, 0) and run1's midpoint at (5000, 0), so a
    resolver that fell through to some other branch cannot land on the right
    answer by accident.
    """
    assert fm["station_zero"] == [0, 0]
    assert fm["element_at_zero"] == [0, 0]


def test_a_place_with_no_station_is_not_station_zero(fm):
    """The other half of the same rule, and the reason the guard is `== null`
    rather than `=== null`: `undefined` must refuse too."""
    assert fm["station_missing"] is None
    assert fm["station_undefined"] is None
    assert fm["nan_station"] is None


def test_a_node_place_resolves_to_the_node_and_not_to_a_run_it_touches(fm):
    """`n2` is the end of run1 and the start of run2. A resolver that guessed
    from whichever field was non-empty would put this at station 0 of a run the
    node happens to touch — the failure `flags.py: Place` names in its own
    docstring."""
    assert fm["node_place"] == [10000, 0]
    assert fm["ghost_node"] is None


def test_a_gate_beside_the_fence_is_marked_between_its_two_nodes(fm):
    """A `GateSpan` has no station on any run — it IS the element — so the only
    place it has is the midpoint of the two nodes it joins, which is where
    `js/gates.js` draws the leaf. The browser fixture has no gate, so this
    resolution was exercised by nothing in the repo and returning `null` from it
    kept the whole suite green."""
    assert fm["gate_place"] == [20000, 2000]


def test_a_gate_whose_node_was_dragged_away_draws_nothing(fm):
    assert fm["ghost_gate"] is None
    assert fm["gate_half_missing"] is None


def test_a_whole_run_is_marked_at_its_midpoint(fm):
    assert fm["run_place"] == [5000, 0]
    assert fm["run2_place"] == [10000, 3000]


def test_an_element_is_placed_from_the_station_the_backend_already_parsed(fm):
    """Re-parsing `span@run1:2000-4000` here would be a second parser for one
    string format, which is how two surfaces come to disagree about where a span
    is. A span is carried at its START, where the setting-out sheet measures."""
    assert fm["element_span"] == [2000, 0]
    assert fm["element_bare"] is None, "`post@node:n2` names no run and no station"


def test_a_finding_about_the_whole_job_has_no_place_on_the_drawing(fm):
    """`null` is an answer, not a failure: `plan_stale` is about the plan, and
    dropping it at the world origin would invent a spot nobody pointed at. It
    keeps its row in the list beside the map."""
    assert fm["job_place"] is None


def test_a_stale_id_is_reported_rather_than_thrown(fm):
    """This drawing is what somebody opens in order to find out what is wrong, so
    a stale id must not be the condition that blanks it. `geom.runPoints` reads
    `.x_mm` off a node it did not find; only the resolver's try/catch stands
    between a half-swapped topology and an empty canvas."""
    assert fm["ghost_run"] is None
    assert fm["ghost_station"] is None
    assert fm["broken_run"] is None, "a run with a deleted node must not throw"
    assert fm["unknown_kind"] is None, "an unfamiliar kind is not a malformed one"
    assert fm["no_place"] is None


def test_nothing_resolves_before_a_project_is_loaded(fm):
    assert fm["unloaded_point"] is None
    assert fm["unloaded_groups"] == 0


# ---------- grouping ----------------------------------------------------------

def test_one_mark_per_point_worst_first(fm):
    """Three findings on one gate are one thing to look at; three marks stacked
    on one pixel are a blob that also lies about how many there are."""
    assert fm["group_keys"] == ["20000|2000", "0|0", "10000|0", "5000|0", "10000|3000"]
    assert fm["group_severities"] == ["blocking", "open", "open", "open", "open"]


def test_a_mark_shows_the_worst_severity_on_its_point(fm):
    """The gate carries an `open` finding BEFORE a `blocking` one, and the order
    is the point of the fixture: a mark that showed the FIRST severity would draw
    a `?` over a stack containing a blocker, which is the one reading error this
    screen exists to prevent. Every other fixture in the repo has one severity
    per point, so dropping the comparison changed nothing anywhere."""
    assert fm["gate_group"] is not None, "the gate must have a mark at all"
    assert fm["gate_group"]["sev"] == "blocking"
    assert fm["gate_group"]["codes"] == ["gate_swing_unstated", "gate_leaf_unsupported"]


def test_the_count_on_a_mark_is_how_many_findings_are_under_it(fm):
    """Two findings on one gate, and the mark says 2. A hard-coded 1 is invisible
    on every single-finding point, which is most of them."""
    assert fm["group_counts"] == [2, 1, 3, 1, 1]
    assert fm["gate_group"]["count"] == 2


def test_a_group_keeps_the_first_run_named_on_it_and_borrows_no_other(fm):
    """The shared node is reachable three ways: as `n2` (no run), as station
    10000 of run1, and as station 0 of run2. The run offered for selection is the
    FIRST one named there, matching `job-screen.js: flagRun`. Without that, the
    last flag to land on the pixel decides, and a click sends the reader to a
    stretch nothing pointed at.

    Only a point that carries TWO DIFFERENT run ids can tell the two apart, which
    is why the fixture needs a shared node.
    """
    assert fm["shared_node_group"]["run"] == "run1"
    assert fm["shared_node_group"]["count"] == 3
    assert fm["group_runs"] == ["", "run1", "run1", "run1", "run2"], (
        "a gate beside the fence sits on no run and says so")


def test_an_answered_finding_asks_for_nothing_and_gets_no_mark(fm):
    """`answered` means *requires nothing from you*, and a mark is a demand for
    attention. It is not DROPPED — it keeps its row in the list beside the map —
    but drawing it turns the map back into the dialog of a thousand warnings that
    `flags.py` exists to avoid."""
    assert fm["answered_group"] is None
    assert len(fm["group_keys"]) == 5
    assert "answered" not in fm["group_severities"]


def test_one_finding_across_several_stretches_draws_a_mark_on_each(fm):
    """`height_assumed` on a two-run job is one thing nobody said, and it belongs
    at both stretches. The marks do not tally the list in either direction."""
    assert fm["multi_marks"] == ["5000|0", "10000|3000"]


def test_two_places_of_one_finding_on_one_point_count_it_once(fm):
    """A flag that names a corner twice — once as the node, once as a station on
    a run that ends there — is one problem, and the mark must say 1.

    Unasserted, because it is a defect rather than a contract: the membership
    `continue` that stops the double count also skips the `runId` line below it,
    so this mark offers NO run while the same flag's row in the list offers
    `run1` (`job-screen.js: flagRun` reads every place). Pinning the current
    answer here would make the divergence look intended.
    """
    assert fm["dupe_groups"] == 1
    assert fm["dupe_count"] == 1


def test_nothing_to_group_is_not_an_error(fm):
    assert fm["empty_in"] == [0, 0, 0]


# ---------- the marks ---------------------------------------------------------

def test_a_blocking_mark_is_painted_last_so_it_is_never_buried(fm):
    """SVG has no z-index: last painted wins. `flags.py` sorts worst FIRST — that
    is reading order, for the list — and handing that order straight to a painter
    buries every blocker under the open marks around it, which is a sorted list
    quietly producing the opposite of what it sorted for.

    Asserted on the painted sequence rather than on `markGroups`, because the
    grouping's order is deliberately the other one and both are correct.
    """
    assert fm["paint_sev"] == ["open", "open", "open", "open", "blocking"]
    assert fm["drawn"] == 5, "the return is marks drawn, not findings"


def test_every_mark_carries_a_glyph_and_a_blocker_is_not_a_question(fm):
    """`!` for blocking, `?` for open, on every mark, always. Roughly one man in
    twelve cannot separate the red from the amber, and the office is not a
    population this app gets to choose — so the glyph, not the colour, is the
    channel that is always there. A glyph that is the same on both says nothing
    at all, and says it most loudly where two marks sit together."""
    assert fm["paint_glyph"] == ["?", "?", "?", "?", "!"]
    assert fm["glyph_classes"][-1].endswith("flag-mark-glyph-blocking")
    assert fm["paint_radii"] == [8, 8, 8, 8, 9], "size is the third agreeing channel"


def test_a_count_is_shown_only_where_there_is_one_to_report(fm):
    """A "1" beside every mark is noise on the common case. The attribute is
    always there for the stylesheet and the smoke test; the drawn label is not."""
    assert fm["paint_count_attr"] == ["1", "3", "1", "1", "2"]
    assert fm["paint_labels"] == [None, "3", None, None, "2"]


def test_a_mark_carries_the_run_its_click_would_select(fm):
    assert fm["paint_run"] == ["run1", "run1", "run1", "run2", ""]


def test_marks_are_inert_until_somebody_asks_for_clicks(fm):
    """`js/editor.js` owns the canvas's click handling. A mark that swallowed a
    click meant for the fence in front of it would make the drawing harder to
    work with than it was before anything was marked."""
    assert fm["paint_inert"] == ["none"] * 5
    assert fm["live_pe"] == ["auto"] * 5


def test_a_click_selects_the_run_and_stops_there(fm):
    """Without `stopPropagation` the same gesture also reaches the canvas handler
    and does two things at once — select-and-frame here, plus whatever tool is
    armed. A gate's mark reports `""`, because it sits on no run."""
    assert fm["clicked_shared"] and fm["clicked_gate"], "both marks must be there"
    assert fm["click_stopped"]
    assert fm["clicked_runs"] == ["run1", ""]


def test_rendering_twice_replaces_the_marks_rather_than_stacking_them(fm):
    assert fm["second_render_children"] == fm["first_render_children"]


def test_a_missing_host_disables_the_layer_instead_of_taking_the_page_down(fm):
    """`#g-flags` is LOOKED UP, never created — `js/notes.js`'s rule for the same
    canvas. The lookup has to come before `clearGroup`, which walks `g.firstChild`
    without checking."""
    assert fm["hostless"] == 0


def test_a_finding_whose_first_place_names_no_run_still_offers_its_second(fm):
    """The mark and the row must agree about which stretch a finding is on.

    `markGroups` took the run id AFTER the guard that stops one finding being
    counted twice on a point — so a shared-corner warning carrying
    `post@node:n2` and then `post@run1:10000` skipped the assignment on its
    second place and produced a mark with no run: unclickable, while the same
    finding's row in the list offered `run1`, because `job-screen.js: flagRun`
    scans every place. Two surfaces disagreeing about one finding, from a
    `continue`.
    """
    assert fm["two_place_group_runid"] == "run1"
