"""The macro viewport's geometry (static/js/runview.js).

`runview.js` places a structure report as a fence standing up. It is checked
against the REAL report — generated here and interpolated into the script —
rather than a hand-written fixture, because the failure this guards is drift
between the two: a field renamed on the wire leaves a hand-written fixture
passing and the drawing empty.

What can go silently wrong, and why the browser suite cannot see it:

  * a bay drawn as a rectangle instead of a parallelogram. A raked bay's two
    ends sit at different elevations; a screenshot of a gentle rake looks very
    much like a screenshot of a level one;
  * a post drawn to the STOCK length rather than to the fence's top line, so
    every post stands proud by however much the installer cuts off — which
    still looks like a fence;
  * an embedded length drawn upward, or a footing drawn where there is no
    concrete. Both are below the ground line, where nothing else is;
  * two disconnected sections drawn on top of each other, or a second section's
    stations placed in the first one's coordinates.

Each of those is arithmetic on integers, so it is pinned here as arithmetic.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.demo import demo_knowledge
from fenceai.report.structure import build_structure
from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    BasePayload, ElevationSamplePayload, GatePayload, Node, Run, Topology,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = { getElementById: () => null, querySelectorAll: () => [],
                        documentElement: {} };

import {
  NOMINAL_POST_FACE_MM, SECTION_GAP_MM, footingShape, groundAt, macroDimensions,
  macroModel, macroPlacement,
} from "./js/runview.js";

const flat = %(flat)s;
const masonry = %(masonry)s;
const raked = %(raked)s;
const stepped = %(stepped)s;
const two = %(two)s;

const out = {};
const model = macroModel(flat, { faceWidths: { "POST-S": 100 } });
out.nominal_face = NOMINAL_POST_FACE_MM;
out.section_gap = SECTION_GAP_MM;
out.ground_line = {
  drawn: macroModel(stepped, { faceWidths: {} }).sections[0].ground,
  reported: (stepped.sections || [])[0].ground,
  station_count: (stepped.sections || [])[0].setting_out.length,
};
out.report_tops = (flat.sections || []).flatMap((s) => s.setting_out)
  .map((s) => [s.tag, s.top_z_mm ?? null, s.exposed_mm ?? null]);
out.flat = {
  posts: model.posts.map((p) => ({
    tag: p.tag, sku: p.sku, x: p.x_mm, face: p.face_mm, declared: p.declared_face,
    base: p.base_z_mm, top: p.top_z_mm, declared_top: p.declared_top,
    embed: p.embed_mm, footing: p.footing,
  })),
  bays: model.bays.map((b) => ({
    tag: b.tag, x0: b.x0_mm, x1: b.x1_mm, w: b.width_mm, h: b.height_mm,
    bottom: [b.bottom_start_z_mm, b.bottom_end_z_mm],
    top: [b.top_start_z_mm, b.top_end_z_mm],
    members: b.elevation?.members?.length || 0,
  })),
  member_counts: (flat.sections || []).flatMap((s) => s.bays)
    .map((b) => (b.elevation?.members || []).length),
  gates: model.gates.map((g) => ({
    tag: g.tag, x0: g.x0_mm, x1: g.x1_mm, h: g.height_mm,
    declared: g.declared_height,
  })),
  steps: model.steps.length,
  total: model.total_mm,
  z: [model.z_min_mm, model.z_max_mm],
};

// a post whose sku declares no face width falls back to the nominal AND says so
const bare = macroModel(flat, { faceWidths: {} });
out.bare_face = bare.posts.map((p) => [p.face_mm, p.declared_face]);

// a fence that FOLLOWS the grade: parallelogram bays, and no riser anywhere,
// because a raked run joins bay to bay continuously
const rakedModel = macroModel(raked, { faceWidths: {} });
const asShape = (m) => ({
  bays: m.bays.map((b) => ({
    tag: b.tag, vertical: b.vertical, h: b.height_mm,
    bottom: [b.bottom_start_z_mm, b.bottom_end_z_mm],
    top: [b.top_start_z_mm, b.top_end_z_mm],
  })),
  steps: m.steps.map((s) => ({ rise: s.rise_mm, from: s.from_z_mm, to: s.to_z_mm })),
  posts: m.posts.map((p) => ({ tag: p.tag, base: p.base_z_mm, top: p.top_z_mm })),
});
out.raked = asShape(rakedModel);
out.stepped = asShape(macroModel(stepped, { faceWidths: {} }));

// two disconnected runs: the second is offset by its own length plus the gap
const twoModel = macroModel(two, { faceWidths: {} });
out.two = {
  sections: twoModel.sections.map((s) => ({ tag: s.tag, x0: s.x0_mm,
                                            len: s.length_mm })),
  first_post_x: twoModel.posts.map((p) => p.x_mm),
  total: twoModel.total_mm,
};

// a wall-mounted section: nothing is buried and nothing is poured, so the
// negative case of "footings come from the report" is a real fixture rather
// than an absent one
const wall = macroModel(masonry, { faceWidths: {} });
out.masonry = wall.posts.map((p) => ({ tag: p.tag, embed: p.embed_mm,
                                       footing: p.footing }));

// dimensions: descriptors over report fields, never measurements of the drawing.
// The WHOLE descriptor, because "the embed dimension drawn upward" is failure
// mode 3 in this file's own docstring and `kind`+`value` cannot see it.
out.dims = macroDimensions(model).map((d) => ({
  kind: d.kind, value: d.value_mm, from: d.from_mm, to: d.to_mm,
  x: d.x_mm ?? null, axis: d.axis,
}));
out.stepped_dims = macroDimensions(macroModel(stepped, { faceWidths: {} }))
  .filter((d) => d.kind === "step")
  .map((d) => ({ value: d.value_mm, from: d.from_mm, to: d.to_mm }));
out.dims_off = macroDimensions(model, { bays: false, heights: false, embed: false,
                                        steps: false, total: false }).length;

// placement: one scale for both axes, z flipped
const place = macroPlacement(model, { maxWidth: 1000, maxHeight: 400 });
out.place = {
  scale: place.scale,
  top_is_smaller_y: place.pz(model.z_max_mm) < place.pz(model.z_min_mm),
  x_grows: place.px(model.total_mm) > place.px(0),
  viewbox: [place.viewBox.w, place.viewBox.h],
  // ONE scale means a metre along the run and a metre up the post are the same
  // number of drawing units. Asserting `scale > 0` says nothing about that.
  px_len: place.px(1000) - place.px(0),
  pz_len: place.pz(0) - place.pz(1000),
  fits: [place.width <= 1000, place.height <= 400],
};

// footing: a trapezoid wider at the bottom, only where there IS concrete
const withFooting = model.posts.find((p) => p.footing);
const shape = footingShape(withFooting);
out.footing = shape && {
  top_width: shape[1][0] - shape[0][0],
  bottom_width: shape[2][0] - shape[3][0],
  top_z: shape[0][1], bottom_z: shape[2][1],
};
out.footing_of_bare_post = footingShape({ footing: false, embed_mm: 600,
                                          face_mm: 80, x_mm: 0, base_z_mm: 0 });

// ground interpolation between the sampled stations, never past the ends
const stations = [{ station_mm: 0, ground_z_mm: 0 },
                  { station_mm: 1000, ground_z_mm: 500 }];
out.ground = [groundAt(stations, 0), groundAt(stations, 500), groundAt(stations, 1000),
              groundAt(stations, 4000), groundAt([], 10)];

// an empty report is an empty drawing, not an exception
out.empty = macroModel(null).posts.length + macroModel({ sections: [] }).posts.length;

console.log(JSON.stringify(out));
"""


def _report(topo, run_id="run-x"):
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    requirements = resolve_supply(requirements, catalog, None).requirements
    bom = fulfill(requirements, catalog, None)
    return build_structure(topo, result.strategy, requirements, bom,
                           run_id=run_id, catalog=catalog)


def _flat():
    """A straight level run with a gate — the ordinary case."""
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "ev_gate", 2000,
                    GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    return _report(topo)


def _raked():
    """Ground that rises evenly across the run: the fence FOLLOWS the grade, so
    every bay is a parallelogram and no bay steps."""
    topo = straight_topology(6000)
    topo.nodes[1].z_mm = 900          # the far end is 900 mm higher
    return _report(topo)


def _stepped():
    """A near-vertical break mid-run, which forces stepped mode: the bays sit at
    two levels with a riser between them, and the riser is what the drawing has
    to show."""
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "a", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "b", 2950, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "c", 3050, ElevationSamplePayload(z_mm=900))
    add_point_event(topo, "run1", "d", 6000, ElevationSamplePayload(z_mm=900))
    return _report(topo)


def _masonry():
    """A section built on a masonry wall: its posts are bracketed, not buried."""
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "ev_base", 0, 6000,
                       BasePayload(surface="masonry_wall"))
    return _report(topo)


def _two_runs():
    """Two runs that share no node: two sections, drawn one after the other."""
    topo = Topology(
        nodes=[Node(id="a1", x_mm=0, y_mm=0), Node(id="a2", x_mm=4000, y_mm=0),
               Node(id="b1", x_mm=0, y_mm=9000), Node(id="b2", x_mm=3000, y_mm=9000)],
        runs=[Run(id="runA", start_node_id="a1", end_node_id="a2"),
              Run(id="runB", start_node_id="b1", end_node_id="b2")],
    )
    return _report(topo)


@pytest.fixture(scope="module")
def view():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = SCRIPT % {
        "flat": _flat().model_dump_json(),
        "masonry": _masonry().model_dump_json(),
        "raked": _raked().model_dump_json(),
        "stepped": _stepped().model_dump_json(),
        "two": _two_runs().model_dump_json(),
    }
    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- posts ------------------------------------------------------------------

def test_the_post_top_is_the_reports_answer_not_a_second_one(view):
    """The same question is answered server-side by the length check — with a
    tilt correction this module does not have — and it is the number
    `insufficient_post_length` is computed from. A JS copy meant a run could warn
    "this post is 200 mm short" and draw a post that looks fine."""
    reported = {tag: top for tag, top, _ in view["report_tops"] if top is not None}
    assert reported, "the report must actually carry the top it measured"
    drawn = {p["tag"]: p["top"] for p in view["flat"]["posts"]}
    for tag, top in reported.items():
        assert drawn[tag] == top, (tag, drawn[tag], top)


def test_a_post_is_drawn_to_the_fence_top_not_to_the_stock_length(view):
    """`post_length_mm` is the bar that ARRIVES (2600 mm for POST-S). A post
    drawn to it stands proud of an 1800 mm fence by 800 mm and still looks like
    a fence, which is why this is arithmetic rather than a screenshot."""
    for post in view["flat"]["posts"]:
        assert post["declared_top"] is True
        assert post["top"] - post["base"] == 1800


def test_a_declared_face_width_is_used_and_an_undeclared_one_is_flagged(view):
    """Per SKU, not per drawing: this run's gate posts are POST-S-HD, which the
    map does not name, so they fall back — beside line posts drawn at their real
    100 mm. A nominal that does not say it is a nominal is a measured-looking
    guess, which is the rule the panel elevation already applies to member faces."""
    by_sku = {(p["sku"], p["face"], p["declared"]) for p in view["flat"]["posts"]}
    assert ("POST-S", 100, True) in by_sku
    assert ("POST-S-HD", view["nominal_face"], False) in by_sku
    # and with no catalog at all, every post falls back and says so
    assert all(face == view["nominal_face"] and declared is False
               for face, declared in view["bare_face"])


def test_embedment_and_footings_come_from_the_report(view):
    """A ground post carries the embedment generation resolved; the footing is
    drawn where the station actually carries concrete, never per post.

    The negative case is the load-bearing half: with only soil posts in the
    fixture, `hasFooting = () => true` passes every assertion. A wall-mounted
    section is bracketed, not buried, and neither pours nor embeds."""
    posts = view["flat"]["posts"]
    assert all(p["embed"] == 600 for p in posts), posts
    assert all(p["footing"] for p in posts), "every soil post here is set in concrete"
    assert view["masonry"], "the wall fixture must actually produce posts"
    assert not any(p["footing"] for p in view["masonry"]), view["masonry"]
    assert all(p["embed"] == 0 for p in view["masonry"]), view["masonry"]


# --- bays -------------------------------------------------------------------

def test_a_bay_spans_between_its_two_stations(view):
    bays = view["flat"]["bays"]
    assert bays, "a 6 m run with a gate still has bays"
    for bay in bays:
        assert bay["x1"] - bay["x0"] == bay["w"]
        assert bay["top"][0] - bay["bottom"][0] == bay["h"]
        assert bay["top"][1] - bay["bottom"][1] == bay["h"]


def test_a_bay_carries_the_panel_the_server_placed(view):
    """The macro view draws the bay's OWN members — the same rectangles the micro
    view draws — so the two viewports cannot show different panels.

    Per bay, not "some bay": keeping only the first bay's elevation satisfies
    `any(...)` and draws every other bay as an empty box."""
    bays = view["flat"]["bays"]
    assert bays
    assert all(bay["members"] > 0 for bay in bays), bays
    assert view["flat"]["member_counts"] == [b["members"] for b in bays]


def test_a_stepped_run_is_drawn_at_two_levels_with_the_riser_between_them(view):
    """A step is read off the BAYS' own bottoms, not off the ground: the layout
    decides where a fence steps, and it does not always step where the grade does."""
    bays = view["stepped"]["bays"]
    assert all(b["vertical"] == "stepped" for b in bays), bays
    assert len({tuple(b["bottom"]) for b in bays}) > 1
    steps = view["stepped"]["steps"]
    assert steps, "the level changes between bays, so there is a riser to show"
    for step in steps:
        assert step["rise"] == abs(step["to"] - step["from"]) > 0
    # A riser is drawn at every joint where the two bays' own bottoms disagree,
    # and at no other joint. Note what the report actually says here: a stepped
    # bay's bottom still follows the ground at its two ends, so most of this
    # run's 900 mm of fall is inside the bays and only the leftovers appear
    # between them. The drawing reports that rather than redistributing it —
    # a macro view that "tidied" the risers into equal steps would be drawing a
    # fence the cut list does not describe.
    joints = [(a, b) for a, b in zip(view["stepped"]["bays"],
                                     view["stepped"]["bays"][1:])]
    expected = [abs(b["bottom"][0] - a["bottom"][1]) for a, b in joints
                if b["bottom"][0] != a["bottom"][1]]
    assert sorted(s["rise"] for s in steps) == sorted(expected)


def test_a_raked_run_has_no_risers_at_all(view):
    """The counter-case, and the one a naive step-finder gets wrong: a fence that
    follows the grade joins bay to bay continuously. Inventing a riser at every
    joint would draw a staircase where the site has a slope."""
    assert all(b["vertical"] == "raked" for b in view["raked"]["bays"])
    assert view["raked"]["steps"] == []


def test_a_raked_or_stepped_bay_keeps_its_two_end_elevations(view):
    """Drawn as a parallelogram. Collapsing it to a rectangle erases the one
    thing a raked bay looks like, and a gentle rake photographs as level."""
    assert any(bay["bottom"][0] != bay["bottom"][1] for bay in view["raked"]["bays"])
    for bay in view["raked"]["bays"]:
        assert bay["top"][0] - bay["bottom"][0] == bay["h"]
        assert bay["top"][1] - bay["bottom"][1] == bay["h"]


# --- sections ---------------------------------------------------------------

def test_disconnected_sections_are_laid_end_to_end_with_a_gap(view):
    """Two runs that share no node are two fences. Drawn in one coordinate
    system they would sit on top of each other and read as one."""
    sections = view["two"]["sections"]
    assert len(sections) == 2
    first, second = sections
    assert first["x0"] == 0
    assert second["x0"] == first["len"] + view["section_gap"]
    assert view["two"]["total"] == second["x0"] + second["len"]


def test_stations_of_the_second_section_are_offset_into_the_chain(view):
    """The bug this pins: a second section's stations placed in the FIRST
    section's coordinates, so its posts land inside the first fence."""
    xs = view["two"]["first_post_x"]
    sections = view["two"]["sections"]
    assert min(xs) == 0
    # the LAST post of the second section, exactly — `>=` passed a doubled offset
    assert max(xs) == sections[1]["x0"] + sections[1]["len"]


# --- dimensions and placement ----------------------------------------------

def test_every_bay_is_dimensioned_and_the_total_is_stated_once(view):
    kinds = [d["kind"] for d in view["dims"]]
    assert kinds.count("total") == 1
    assert kinds.count("bay") == len(view["flat"]["bays"])
    assert kinds.count("height") == len(view["flat"]["bays"])
    assert kinds.count("embed") == len(view["flat"]["posts"])
    # the toggle really turns them all off — an annotation layer that cannot be
    # switched off is one more thing between the reader and the drawing
    assert view["dims_off"] == 0


def test_the_embed_dimension_measures_downward_from_the_base(view):
    """Failure mode 3 of this module's docstring, and it survived every earlier
    assertion because only `kind` and `value_mm` were exported: an embed drawn
    from the base UPWARD is the same 600 mm and the same word."""
    posts = {p["tag"]: p for p in view["flat"]["posts"]}
    for dim in [d for d in view["dims"] if d["kind"] == "embed"]:
        assert dim["axis"] == "z"
        post = next(p for p in posts.values() if p["x"] == dim["x"])
        assert dim["to"] == post["base"]
        assert dim["from"] == post["base"] - 600
        assert dim["value"] == 600


def test_every_riser_is_dimensioned_on_a_stepped_run(view):
    """`macroDimensions` was only ever called on the FLAT model, so deleting its
    whole step branch changed nothing any test could see."""
    steps = view["stepped"]["steps"]
    assert steps, "the stepped fixture must actually step"
    assert len(view["stepped_dims"]) == len(steps)
    assert sorted(d["value"] for d in view["stepped_dims"]) \
        == sorted(s["rise"] for s in steps)
    for dim in view["stepped_dims"]:
        assert dim["to"] > dim["from"]


def test_a_gate_is_placed_and_carries_the_height_it_interrupts(view):
    """The gate branch was exported and asserted by nothing: its placement, the
    neighbour-height fallback and its `declared_height` flag were all dead."""
    gates = view["flat"]["gates"]
    assert len(gates) == 1
    gate = gates[0]
    assert gate["x1"] - gate["x0"] == 1000     # the opening the topology asked for
    assert gate["h"] == 1800 and gate["declared"] is True


def test_the_drawing_extends_below_the_deepest_embedment(view):
    """The vertical extent has to cover what is buried, or the footings are
    clipped off the bottom of the sheet."""
    lowest_base = min(p["base"] for p in view["flat"]["posts"])
    assert view["flat"]["z"][0] == lowest_base - 600
    assert view["flat"]["z"][1] >= max(p["top"] for p in view["flat"]["posts"])


def test_a_dimension_reports_the_reports_own_number(view):
    """Not a measurement of the drawing: a dimension line that measured pixels
    and converted back would round, and disagree with the schedule beside it."""
    total = next(d for d in view["dims"] if d["kind"] == "total")
    assert total["value"] == view["flat"]["total"]
    bays = [d["value"] for d in view["dims"] if d["kind"] == "bay"]
    assert bays == [b["w"] for b in view["flat"]["bays"]]


def test_placement_flips_z_and_keeps_one_scale_for_both_axes(view):
    """The name of this test was previously the assertion of nothing: with
    `scale > 0` alone, stretching x three to one against z passes — which is
    exactly the distortion that makes a 600 mm footing and a 1800 mm panel look
    like the same thing."""
    place = view["place"]
    assert place["top_is_smaller_y"], "elevation grows up; SVG y grows down"
    assert place["x_grows"]
    assert place["scale"] > 0
    # float, so compared to the millimetre rather than to the bit
    assert abs(place["px_len"] - place["pz_len"]) < 1e-6
    assert abs(place["px_len"] - place["scale"] * 1000) < 1e-6
    assert all(place["fits"]), "the drawing must fit the box it was given"
    assert place["viewbox"][0] > 0 and place["viewbox"][1] > 0


# --- the small pure helpers -------------------------------------------------

def test_a_footing_is_wider_at_the_bottom_and_only_where_there_is_concrete(view):
    footing = view["footing"]
    assert footing["bottom_width"] > footing["top_width"] > 0
    assert footing["bottom_z"] < footing["top_z"], "a footing goes DOWN"
    assert view["footing_of_bare_post"] is None


def test_ground_interpolates_between_samples_and_never_past_the_ends(view):
    """The report samples the ground AT the stations. Extrapolating past the last
    one would hang a gate leaf below a ground line nobody surveyed."""
    assert view["ground"] == [0, 250, 500, 500, 0]


def test_an_empty_report_is_an_empty_drawing(view):
    assert view["empty"] == 0


def test_the_ground_line_is_the_one_the_layout_measured(view):
    """One z per post is not the ground: between two posts either side of a
    retaining step, a station-only line draws a smooth chord where the site has
    a wall — on the datum the footings and the embed hatch sit on. The stepped
    fixture puts a 900 mm break between two stations, which is exactly the case
    that vanishes."""
    ground = view["ground_line"]
    assert ground["reported"], "the report must carry the samples it measured"
    assert len(ground["drawn"]) == len(ground["reported"])
    assert [z for _, z in ground["drawn"]] == [z for _, z in ground["reported"]]
    # and it is genuinely finer than the stations, or the fix changed nothing
    assert len(ground["drawn"]) > ground["station_count"] or \
        any(z not in (0,) for _, z in ground["drawn"])
