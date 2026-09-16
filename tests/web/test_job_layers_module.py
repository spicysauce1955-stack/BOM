"""The plan's emphasis layers (static/js/job-layers.js).

Two overlays on the office job screen's map — what each stretch STANDS ON, and
how TALL its fence is meant to be — plus the rule that makes a layer switch safe
to build at all: `PROTECTED`, the list of things no layer may ever affect.

This module had no tests. A mutation run found four survivors, and every one of
them is a lie the drawing would tell confidently:

  * `PROTECTED` lost `#g-flags` and nothing noticed, because NOTHING IMPORTED
    IT. The module's own header says it is exported "so the rule is ASSERTABLE:
    a test can take the list and check that no layer touched any of it" — and
    that test did not exist. A list nobody reads is a comment.
  * the ribbon filled a missing `height_intent_mm` with 1800 — the project
    default, which is exactly what the demo job is silently built at — and so
    painted a MEASURED-looking ribbon over a stretch nobody stated a height for.
  * the "covered nothing" guard came out, so a stated height that covers no part
    of the stretch drew the full ribbon anyway.
  * every band on a MIXED stretch was painted with the scalar `base_surface`,
    i.e. `mixed`, which `surfaceBands`' own docstring forbids: "a stretch
    standing on two things is drawn as the two things, in the places they
    actually are".

The browser smoke could not catch any of the middle three, and the reason is the
fixture: the smoke job has no base events and no stated heights, so its heights
layer draws ZERO shapes and only a single `soil` band ever renders. Every
fixture below is built to be the opposite — a genuinely mixed stretch, a stated
height with partial coverage, a contradicted height, an uncovered height — and
no true stated height here is 1800, so a fabricated default can never be
accidentally right.

Both pure halves take the run's polyline as an optional second argument
precisely so a test needs no `state.project`; the render half is driven through
a minimal DOM shim, which is what makes the "writes into `#g-layers` and nothing
else" promise checkable without a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = r"""
// ---------- a DOM small enough to reason about --------------------------------
// Only what `geom.el` and `geom.clearGroup` actually touch. `firstChild` is a
// getter because `clearGroup` drains the group with
// `while (g.firstChild) g.removeChild(g.firstChild)`.
function makeEl(tag) {
  return {
    tag, attrs: {}, children: [],
    get firstChild() { return this.children[0] || null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) {
      const i = this.children.indexOf(c);
      if (i >= 0) this.children.splice(i, 1);
      return c;
    },
  };
}

// The plan's groups as index.html has them. Every group EXCEPT `#g-layers`
// starts with one sentinel child, so "untouched" is observable: a render that
// cleared or drew into one would change its count.
const GROUP_IDS = ["g-context", "g-layers", "g-topology", "g-gates", "g-flags",
                   "g-notes"];
const GROUPS = {};
for (const id of GROUP_IDS) {
  GROUPS[id] = makeEl("g");
  if (id !== "g-layers") GROUPS[id].appendChild(makeEl("sentinel"));
}

// Every selector the module asks the document for, in order.
const lookups = [];
globalThis.document = {
  documentElement: {},
  getElementById(id) { lookups.push(id); return GROUPS[id] || null; },
  querySelector(sel) { lookups.push(sel); return null; },
  querySelectorAll(sel) { lookups.push(sel); return []; },
  createElementNS(_ns, tag) { return makeEl(tag); },
};

import { PROTECTED, heightRibbon, renderJobLayers, surfaceBands }
  from "./js/job-layers.js";
import { state } from "./js/state.js";

const out = {};
const layers = () => GROUPS["g-layers"].children;
const bbox = (ring) => ({
  x0: Math.min(...ring.map((p) => p[0])), x1: Math.max(...ring.map((p) => p[0])),
  y0: Math.min(...ring.map((p) => p[1])), y1: Math.max(...ring.map((p) => p[1])),
});

// ---------- the world ---------------------------------------------------------
// One straight 8 000 mm run along +x, so every ring coordinate below can be
// read by hand: a half-width of h puts the ring at y = +/-h.
const STRAIGHT = [[0, 0], [8000, 0]];

// A stretch standing on TWO things, with a stated height covering part of it.
// 2 200 mm rather than 1 800, so the project default can never be right by
// accident; 5 000 of 8 000 covered, so "partial" is not the same number as
// anything else here.
const MIXED = {
  run_id: "r1", tag: "A", length_mm: 8000,
  base_surface: "mixed",
  surfaces: [
    {start_mm: 0,    end_mm: 3000, surface: "masonry_wall"},
    {start_mm: 3000, end_mm: 8000, surface: "soil"},
  ],
  height_intent_mm: 2200, height_covered_mm: 5000,
};

// One surface, one height, covering the whole stretch. 1 200 mm, so the ribbon's
// own width is a number no default could supply.
const PLAIN = {
  run_id: "r1", tag: "B", length_mm: 8000,
  base_surface: "soil",
  surfaces: [{start_mm: 0, end_mm: 8000, surface: "soil"}],
  height_intent_mm: 1200, height_covered_mm: 8000,
};

// TWO PEOPLE STATED DIFFERENT HEIGHTS. `report/sections.py` sets
// `height_intent_mm = None` for that and leaves `height_covered_mm` at the
// merged covered length — so this is the real shape in which a null intent
// arrives WITH coverage, and the only fixture in which fabricating the default
// is not masked by the coverage guard below.
const CONTRADICTED = {
  run_id: "r1", tag: "C", length_mm: 8000,
  base_surface: "soil", surfaces: [],
  height_intent_mm: null, height_covered_mm: 6000,
};

// Nobody stated anything: null intent, nothing covered.
const UNSTATED = {
  run_id: "r1", tag: "D", length_mm: 8000,
  base_surface: "soil", surfaces: [],
  height_intent_mm: null, height_covered_mm: 0,
};

// A height on the books that covers NO part of the stretch.
const UNCOVERED = {
  run_id: "r1", tag: "E", length_mm: 8000,
  base_surface: "soil", surfaces: [],
  height_intent_mm: 2200, height_covered_mm: 0,
};

// ---------- PROTECTED ---------------------------------------------------------
out.protected = [...PROTECTED];
out.protected_frozen = Object.isFrozen(PROTECTED);
out.protected_push_refused = (() => {
  try { PROTECTED.push("#g-anything"); } catch { /* strict-mode throw */ }
  return PROTECTED.length;
})();

// ---------- surfaceBands: the pure half ---------------------------------------
const bands = surfaceBands(MIXED, STRAIGHT);
out.band_count = bands.length;
out.band_surfaces = bands.map((b) => b.surface);
out.band_spans = bands.map((b) => [b.startMm, b.endMm]);
out.band_run_ids = bands.map((b) => b.runId);
out.band_boxes = bands.map((b) => bbox(b.ring));
// A nominal fact gets a CONSTANT width: both bands are the same across, however
// different they are along.
out.band_widths = bands.map((b) => bbox(b.ring).y1 - bbox(b.ring).y0);
out.band_lengths = bands.map((b) => bbox(b.ring).x1 - bbox(b.ring).x0);
out.band_ints = bands.every((b) =>
  b.ring.every((p) => Number.isInteger(p[0]) && Number.isInteger(p[1])));

// The bands TILE: the second starts where the first ends, with no gap for the
// eye to read as "nobody has looked at this yet".
out.bands_tile = bands[0].endMm === bands[1].startMm;

// A stretch with no surfaces at all, and a stretch whose run is gone.
out.no_surfaces = surfaceBands({...PLAIN, surfaces: []}, STRAIGHT).length;
out.no_section = surfaceBands(null, STRAIGHT).length;
out.no_points = surfaceBands(MIXED, [[0, 0]]).length;

// A surface interval stated past the end of the drawing is CLAMPED to the
// drawing, not to the section's `length_mm`: a band running off the end of the
// run would be a claim about ground that is not there.
out.overlong = bbox(surfaceBands(
  {...MIXED, surfaces: [{start_mm: 0, end_mm: 20000, surface: "concrete"}]},
  STRAIGHT)[0].ring);

// ---------- heightRibbon: the pure half ---------------------------------------
const ribbon = heightRibbon(MIXED, STRAIGHT);
out.ribbon_height = ribbon.heightMm;
out.ribbon_covered = ribbon.coveredMm;
out.ribbon_length = ribbon.lengthMm;
out.ribbon_permille = ribbon.coveredPermille;
out.ribbon_partial = ribbon.partial;
out.ribbon_run_id = ribbon.runId;
// The fence laid flat: across the run it is exactly as wide as the fence is
// tall, in the plan's own millimetres. That is the whole reason it needs no
// legend.
const rb = bbox(ribbon.ring);
out.ribbon_width = rb.y1 - rb.y0;
// ...and it runs the WHOLE stretch even though only 5 000 of 8 000 is covered:
// the read model says how much, never which part.
out.ribbon_span = rb.x1 - rb.x0;

const full = heightRibbon(PLAIN, STRAIGHT);
out.full_width = bbox(full.ring).y1 - bbox(full.ring).y0;
out.full_partial = full.partial;
out.full_permille = full.coveredPermille;

out.contradicted = heightRibbon(CONTRADICTED, STRAIGHT);
out.unstated = heightRibbon(UNSTATED, STRAIGHT);
out.uncovered = heightRibbon(UNCOVERED, STRAIGHT);
out.zero_height = heightRibbon(
  {...PLAIN, height_intent_mm: 0}, STRAIGHT);
out.negative_height = heightRibbon(
  {...PLAIN, height_intent_mm: -900}, STRAIGHT);
out.ribbon_no_points = heightRibbon(PLAIN, [[0, 0]]);

// ---------- degenerate geometry -----------------------------------------------
// A run authored through one corner twice, and a run that doubles back exactly:
// both compute a normal from a zero-length or self-cancelling direction, which
// is a division by zero that would propagate NaN through a whole band.
const DOUBLED = [[0, 0], [0, 0], [4000, 0]];
const HAIRPIN = [[0, 0], [4000, 0], [0, 0]];
const finite = (ring) => ring.every((p) =>
  Number.isFinite(p[0]) && Number.isFinite(p[1]));
out.doubled_finite = finite(surfaceBands(PLAIN, DOUBLED)[0].ring);
out.hairpin_finite = finite(heightRibbon(PLAIN, HAIRPIN).ring);
// ...and the hairpin does not draw a miter spike kilometres across the plan.
const hb = bbox(heightRibbon(PLAIN, HAIRPIN).ring);
out.hairpin_extent = Math.max(hb.x1 - hb.x0, hb.y1 - hb.y0);

// ---------- purity ------------------------------------------------------------
const before = JSON.stringify(MIXED);
surfaceBands(MIXED, STRAIGHT);
heightRibbon(MIXED, STRAIGHT);
out.input_untouched = JSON.stringify(MIXED) === before;
out.bands_stable =
  JSON.stringify(surfaceBands(MIXED, STRAIGHT)) === JSON.stringify(bands);
out.ribbon_stable =
  JSON.stringify(heightRibbon(MIXED, STRAIGHT)) === JSON.stringify(ribbon);

// ---------- the render half, through the shim ---------------------------------
// `renderJobLayers` resolves the polyline through `geom`, so the project has to
// be loaded for this half — the same run, as the drawing.
state.project = {
  topology: {
    nodes: [{id: "n1", x_mm: 0, y_mm: 0}, {id: "n2", x_mm: 8000, y_mm: 0}],
    runs: [{id: "r1", start_node_id: "n1", end_node_id: "n2",
            interior_vertices: []}],
  },
};

const snapshot = () => layers().map((c) => ({
  tag: c.tag, cls: c.attrs.class,
  surface: c.attrs["data-surface"] ?? null,
  start: c.attrs["data-start-mm"] ?? null,
  end: c.attrs["data-end-mm"] ?? null,
  height: c.attrs["data-height-mm"] ?? null,
  covered: c.attrs["data-covered-mm"] ?? null,
  partial: c.attrs["data-partial"] ?? null,
  run: c.attrs["data-run"] ?? null,
  events: c.attrs["pointer-events"] ?? null,
}));

out.drawn_ground = renderJobLayers([MIXED], {ground: true});
out.after_ground = snapshot();

out.drawn_heights = renderJobLayers([MIXED], {heights: true});
out.after_heights = snapshot();

out.drawn_both = renderJobLayers([MIXED], {ground: true, heights: true});
out.after_both = snapshot();

// Rendering the same thing again must not accumulate: the group is CLEARED on
// every call.
out.drawn_again = renderJobLayers([MIXED], {ground: true, heights: true});
out.after_again_count = layers().length;

// OFF MEANS ERASED. The early return for "no layers on" happens AFTER the
// clear, so switching both off empties the group.
out.drawn_off = renderJobLayers([MIXED], {});
out.after_off_count = layers().length;

// ...and so does an absent `layers` argument entirely.
renderJobLayers([MIXED], {ground: true});
out.drawn_undefined = renderJobLayers([MIXED], undefined);
out.after_undefined_count = layers().length;

// A stretch nobody stated a height for draws no ribbon, but its bands still
// draw — one layer's silence is not the other's.
out.drawn_unstated_both = renderJobLayers(
  [{...UNSTATED, surfaces: MIXED.surfaces}], {ground: true, heights: true});
out.after_unstated = snapshot().map((c) => c.cls);

// No sections, and a caller that passed something that is not a list.
out.drawn_none = renderJobLayers([], {ground: true, heights: true});
out.drawn_garbage = renderJobLayers(null, {ground: true, heights: true});

// ---------- DOM ownership ------------------------------------------------------
// Every selector this module ever asked the document for, across all of the
// renders above.
out.lookups = [...new Set(lookups)];
// ...and the state of every OTHER group: one sentinel child each, still there.
out.other_groups = Object.fromEntries(GROUP_IDS
  .filter((id) => id !== "g-layers")
  .map((id) => [id, GROUPS[id].children.length]));

// The module with its host removed draws nothing rather than throwing — the
// header's ordering trap: `clearGroup` dereferences before an `if (!g)` written
// after it could run.
const saved = GROUPS["g-layers"];
delete GROUPS["g-layers"];
out.hostless = (() => {
  try { return renderJobLayers([MIXED], {ground: true, heights: true}); }
  catch (err) { return "threw: " + err.message; }
})();
GROUPS["g-layers"] = saved;

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def jl():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------- PROTECTED, the thing the module asked for ------------------------

def test_protected_is_exactly_the_six_selectors_it_documents(jl):
    """The list the module's header exists to make assertable — and which
    nothing imported, so a mutation that deleted `#g-flags` survived the whole
    suite and the browser smoke.

    Each entry is here for its own reason, transcribed from §5 of the design:

      * `#g-topology` — the runs. The fence IS the drawing; a layer that dimmed
        it to make its own band read would be emphasising by subtraction, the
        one move this module exists to refuse.
      * `.run-hit` — the invisible fat line that makes a run clickable. HIDING A
        HANDLE IS HIDING: a run you can see and cannot select is a stretch whose
        card, elevation and decisions you cannot reach.
      * `.run-label` — the section letter on the map. The cards are lettered A,
        B, C; a map with the letters off cannot be matched to them, and that
        link is the whole argument for the map being in the centre.
      * `#g-gates` — a standalone gate belongs to no section, so the map is the
        ONLY surface that places it. Switch it off and it is gone from the
        screen, not merely de-emphasised.
      * `#g-context` — the house, the street, the landmarks: what say WHERE the
        job is. A plan of three lines with no context is a plan of nowhere.
      * `#g-flags` — every flag mark. A flag is never on a layer: the findings
        are why the job was opened, and a control that could hide the blocking
        ones can make an unbuildable job look finished.

    `#g-notes` is deliberately ABSENT — notes are named in §5 as one of the
    layer switches, so protecting them here would contradict the design. The
    equality below pins the omission as firmly as the six inclusions.
    """
    assert jl["protected"] == [
        "#g-topology",
        ".run-hit",
        ".run-label",
        "#g-gates",
        "#g-context",
        "#g-flags",
    ]


def test_protected_cannot_be_edited_by_whoever_imports_it(jl):
    """A list whose whole job is to be un-negotiable must not be editable at
    runtime — otherwise the promise lasts until the first module that wants a
    tidier map."""
    assert jl["protected_frozen"]
    assert jl["protected_push_refused"] == 6


def test_no_layer_ever_reaches_for_anything_protected(jl):
    """The check the header describes in words: take the list, and confirm no
    layer touched any of it.

    Driven from the exported list itself rather than from a hand-written copy,
    so adding a selector to `PROTECTED` automatically extends the check. Across
    every render the fixture performs — ground on, heights on, both, off, a
    hostless page — the module asked the document for exactly ONE thing.
    """
    asked = set(jl["lookups"])
    for selector in jl["protected"]:
        bare = selector.lstrip("#.")
        assert selector not in asked, f"a layer reached for {selector}"
        assert bare not in asked, f"a layer reached for {selector}"
    assert asked == {"g-layers"}, (
        "this module writes into #g-layers and reads nothing else — that "
        "structural fact is what makes PROTECTED a promise rather than a hope")


def test_rendering_leaves_every_other_group_untouched(jl):
    """The same promise from the other side: the protected groups were on the
    page, each holding a child, and every one of them still holds it.

    `#g-notes` is in here too even though it is not protected — this module must
    not touch it either way; the group belongs to `js/notes.js`.
    """
    assert jl["other_groups"] == {
        "g-context": 1, "g-topology": 1, "g-gates": 1, "g-flags": 1,
        "g-notes": 1,
    }


# ---------- surfaceBands -----------------------------------------------------

def test_a_mixed_stretch_is_drawn_as_the_things_it_stands_on(jl):
    """`"mixed"` is an honest answer for a card and a meaningless one for a map.

    The scalar `base_surface` reads `mixed` on this stretch; painting every band
    with it — a one-word mutation — draws a stretch standing on a masonry wall
    for its first 3 m as an unstyled `mixed` colour along its whole length, and
    the survivable part is that it still draws TWO polygons, so a count check
    alone passes. The surfaces themselves are the assertion.
    """
    assert jl["band_count"] == 2
    assert jl["band_surfaces"] == ["masonry_wall", "soil"]
    assert "mixed" not in jl["band_surfaces"]
    assert jl["band_spans"] == [[0, 3000], [3000, 8000]]
    assert jl["band_run_ids"] == ["r1", "r1"]


def test_the_bands_tile_the_stretch_with_no_gap(jl):
    """The remainder nobody stated stands on `soil` and is drawn like any other
    band: a silent default is reported, never hidden. A gap in the band would
    read as "nobody has looked at this yet" when the truth is "this will be
    built on soil"."""
    assert jl["bands_tile"]


def test_a_band_is_a_constant_width_because_a_surface_is_a_nominal_fact(jl):
    """There is no more or less of soil. A band whose width varied would imply
    a magnitude nobody measured — so both bands are 520 mm across (the module's
    260 mm half-width, either side) however different their lengths are."""
    assert jl["band_widths"] == [520, 520]
    assert jl["band_lengths"] == [3000, 5000], (
        "and along the run each band is exactly as long as its own interval")


def test_a_band_lands_where_its_interval_is(jl):
    """A band drawn from station 0 regardless, or one whose ends were swapped,
    covers the same total length and the same total area. Where it STARTS is
    the fact."""
    first, second = jl["band_boxes"]
    assert (first["x0"], first["x1"]) == (0, 3000)
    assert (second["x0"], second["x1"]) == (3000, 8000)


def test_band_rings_are_integer_world_millimetres(jl):
    """ADR-0002: int mm at rest, float only transient. The offsets inside are
    floats; what comes out is addressable in the same units as everything else
    on the canvas."""
    assert jl["band_ints"]


def test_a_surface_stated_past_the_end_is_clamped_to_the_drawing(jl):
    """When the read model and the drawing disagree about length, the drawing is
    the thing being drawn on. A band running past the end of its own run is a
    claim about ground that is not there."""
    assert jl["overlong"]["x0"] == 0
    assert jl["overlong"]["x1"] == 8000


def test_nothing_to_band_draws_nothing(jl):
    assert jl["no_surfaces"] == 0
    assert jl["no_section"] == 0
    assert jl["no_points"] == 0, "a single point has no direction to offset from"


# ---------- heightRibbon -----------------------------------------------------

def test_the_ribbon_is_the_fence_laid_flat(jl):
    """As wide across the run as the fence is tall, at the plan's own scale.

    That is the entire reason this layer needs no legend and no key: the reader
    measures it against the same drawing's gate opening and run length, which
    are in the same millimetres. A palette of height bands would need a legend,
    and a legend is a second place for the truth to live.

    Two different heights are checked because one is satisfied by any constant.
    """
    assert jl["ribbon_width"] == 2200
    assert jl["full_width"] == 1200


def test_a_null_height_is_never_filled_in_with_the_project_default(jl):
    """The mutation that survived everything, and the one the module's docstring
    names outright: `height_intent_mm == null ? 0` becoming `? 1800`.

    1 800 is the project default the demo job is silently built at, so the
    fabricated ribbon looks exactly like a real one — a measurement nobody took,
    drawn on the map, in the one place a reader would trust it most.

    `CONTRADICTED` is the fixture that makes this visible: two people stated
    DIFFERENT heights, so `sections.py` reports `height_intent_mm = None` with
    `height_covered_mm` at the merged 6 000 mm. Coverage is non-zero, so the
    "covered nothing" guard cannot mask the invention — which is why the
    ordinary nobody-said-anything fixture is not enough on its own.

    What is missing is real, it is why `height_assumed` exists, and the flag
    mark and the card's sentence already carry it. A layer emphasises what is
    known; it emphasises nothing by inventing.
    """
    assert jl["contradicted"] is None, (
        "two people stating different heights is not a width")
    assert jl["unstated"] is None, "and neither is nobody stating one"


def test_a_height_that_covers_nothing_draws_no_ribbon(jl):
    """Deleting `if (coveredMm <= 0) return null;` is the same invention minus
    only the honesty of `null`: a height on the books that covers no part of the
    stretch would paint the full-length ribbon anyway.

    The stated height here is 2 200 — a real number, genuinely present in the
    section — so nothing but the coverage tells the two cases apart.
    """
    assert jl["uncovered"] is None


def test_a_nonsense_height_draws_no_ribbon(jl):
    assert jl["zero_height"] is None
    assert jl["negative_height"] is None
    assert jl["ribbon_no_points"] is None


def test_partial_coverage_is_reported_rather_than_drawn_away(jl):
    """The read model says HOW MUCH of the stretch a stated height covers, never
    WHICH PART — it is a merged length, not an interval list.

    So the ribbon runs the whole stretch and carries its coverage in the
    returned object. Drawing a shorter ribbon from station 0 would place the
    covered part somewhere nobody said it was: the same invention in a subtler
    shape, and one that looks like precision.
    """
    assert jl["ribbon_covered"] == 5000
    assert jl["ribbon_length"] == 8000
    assert jl["ribbon_span"] == 8000, "the ribbon runs the WHOLE stretch"
    assert jl["ribbon_permille"] == 625
    assert jl["ribbon_partial"] is True
    assert jl["ribbon_run_id"] == "r1"


def test_full_coverage_is_not_flagged_partial(jl):
    assert jl["full_partial"] is False
    assert jl["full_permille"] == 1000


# ---------- geometry that would otherwise poison a whole band ----------------

def test_a_doubled_vertex_does_not_poison_the_band_with_nan(jl):
    """A run authored through a corner twice — or a segment whose ends snapped
    together — is a zero-length segment with no direction, and a normal computed
    from it is a division by zero that propagates NaN through the entire ring."""
    assert jl["doubled_finite"]


def test_a_hairpin_does_not_draw_a_spike_across_the_plan(jl):
    """A true miter divides by cos(θ/2), which goes to infinity as a run doubles
    back on itself. The module averages the adjacent normals instead: wrong by a
    few millimetres on the inside of a sharp corner, rather than wrong by
    kilometres of spike across the whole drawing."""
    assert jl["hairpin_finite"]
    assert jl["hairpin_extent"] < 10000, (
        "a 4 m hairpin with a 1.2 m ribbon cannot produce a 10 m shape")


def test_both_pure_halves_are_pure(jl):
    assert jl["input_untouched"]
    assert jl["bands_stable"]
    assert jl["ribbon_stable"]


# ---------- the render half --------------------------------------------------

def test_each_layer_draws_its_own_shapes_and_only_when_it_is_on(jl):
    assert jl["drawn_ground"] == 2, "one polygon per band"
    assert [c["cls"] for c in jl["after_ground"]] == [
        "job-layer-surface job-layer-surface-masonry_wall",
        "job-layer-surface job-layer-surface-soil",
    ]
    assert jl["drawn_heights"] == 1
    assert [c["cls"] for c in jl["after_heights"]] == ["job-layer-height"]


def test_the_ribbon_is_painted_before_the_bands(jl):
    """SVG has no z-index: last painted wins. The ribbon is the wider shape — as
    wide as the fence is tall — so a narrow band painted first would sit
    underneath it and be invisible exactly when both layers are on, which is the
    case somebody turns two switches on to look at."""
    assert jl["drawn_both"] == 3
    assert [c["cls"] for c in jl["after_both"]] == [
        "job-layer-height",
        "job-layer-surface job-layer-surface-masonry_wall",
        "job-layer-surface job-layer-surface-soil",
    ]


def test_off_means_erased(jl):
    """`const g = clearGroup(HOST)` quietly becoming `document.getElementById`
    is the mutation the browser smoke does catch — asserted here as well so the
    promise does not depend on a browser being available.

    Two ways round: switching both layers off must empty the group (the early
    return happens AFTER the clear), and rendering the same thing twice must not
    stack a second copy of every shape on the first.
    """
    assert jl["drawn_again"] == 3
    assert jl["after_again_count"] == 3, "a re-render replaces, never accumulates"
    assert jl["drawn_off"] == 0
    assert jl["after_off_count"] == 0, "switching a layer off removes what it drew"
    assert jl["drawn_undefined"] == 0
    assert jl["after_undefined_count"] == 0, (
        "a caller that has not built its controls yet draws nothing, and "
        "erases what a previous call drew")


def test_the_shapes_carry_their_facts_as_attributes_not_as_words(jl):
    """Diagnostics and hooks for a stylesheet and a smoke test — never text on
    the page. This module carries NO locale keys at all, which is the only way
    an overlay can be safe in both directions: there is nothing here to mirror.
    """
    assert len(jl["after_both"]) == 3
    ribbon, wall, soil = jl["after_both"]
    assert ribbon["height"] == "2200"
    assert ribbon["covered"] == "5000"
    assert ribbon["partial"] == "yes"
    assert wall["surface"] == "masonry_wall"
    assert (wall["start"], wall["end"]) == ("0", "3000")
    assert soil["surface"] == "soil"
    assert (soil["start"], soil["end"]) == ("3000", "8000")
    assert all(c["run"] == "r1" for c in jl["after_both"])


def test_nothing_drawn_here_can_swallow_a_click(jl):
    """The canvas's click handling belongs to `js/editor.js`. A band that ate a
    click meant for the fence or for a flag would make the drawing harder to
    work with than it was before anything was emphasised — and a run you can see
    and cannot select is the `.run-hit` failure by another route."""
    assert all(c["events"] == "none" for c in jl["after_both"])


def test_one_layers_silence_is_not_the_others(jl):
    """A stretch nobody stated a height for still has ground under it."""
    assert jl["drawn_unstated_both"] == 2
    assert jl["after_unstated"] == [
        "job-layer-surface job-layer-surface-masonry_wall",
        "job-layer-surface job-layer-surface-soil",
    ]


def test_nothing_to_draw_is_zero_not_a_throw(jl):
    assert jl["drawn_none"] == 0
    assert jl["drawn_garbage"] == 0


def test_a_page_without_the_host_group_disables_the_module_silently(jl):
    """`geom.clearGroup` used to walk `g.firstChild` with no null check, so an
    `if (!g) return;` written after the call never ran — the throw beat it
    there. The lookup happens FIRST here, and a missing host means "nothing was
    drawn", not a half-painted canvas."""
    assert jl["hostless"] == 0
