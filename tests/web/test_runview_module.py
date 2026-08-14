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
    ElevationSamplePayload, GatePayload, Node, Run, Topology,
)
from tests.conftest import add_point_event, straight_topology

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
const raked = %(raked)s;
const stepped = %(stepped)s;
const two = %(two)s;

const out = {};
const model = macroModel(flat, { faceWidths: { "POST-S": 100 } });
out.nominal_face = NOMINAL_POST_FACE_MM;
out.section_gap = SECTION_GAP_MM;
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

// dimensions: descriptors over report fields, never measurements of the drawing
out.dims = macroDimensions(model).map((d) => ({ kind: d.kind, value: d.value_mm }));
out.dims_off = macroDimensions(model, { bays: false, heights: false, embed: false,
                                        steps: false, total: false }).length;

// placement: one scale for both axes, z flipped
const place = macroPlacement(model, { maxWidth: 1000, maxHeight: 400 });
out.place = {
  scale: place.scale,
  top_is_smaller_y: place.pz(model.z_max_mm) < place.pz(model.z_min_mm),
  x_grows: place.px(model.total_mm) > place.px(0),
  viewbox: [place.viewBox.w, place.viewBox.h],
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
    drawn where the station actually carries concrete, never per post."""
    posts = view["flat"]["posts"]
    assert all(p["embed"] == 600 for p in posts), posts
    assert all(p["footing"] for p in posts), "every soil post here is set in concrete"


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
    view draws — so the two viewports cannot show different panels."""
    assert any(bay["members"] > 0 for bay in view["flat"]["bays"])


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
    assert max(xs) >= sections[1]["x0"]


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


def test_a_dimension_reports_the_reports_own_number(view):
    """Not a measurement of the drawing: a dimension line that measured pixels
    and converted back would round, and disagree with the schedule beside it."""
    total = next(d for d in view["dims"] if d["kind"] == "total")
    assert total["value"] == view["flat"]["total"]
    bays = [d["value"] for d in view["dims"] if d["kind"] == "bay"]
    assert bays == [b["w"] for b in view["flat"]["bays"]]


def test_placement_flips_z_and_keeps_one_scale_for_both_axes(view):
    place = view["place"]
    assert place["top_is_smaller_y"], "elevation grows up; SVG y grows down"
    assert place["x_grows"]
    assert place["scale"] > 0
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
