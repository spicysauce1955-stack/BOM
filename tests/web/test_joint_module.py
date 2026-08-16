"""The joint section (static/js/joint.js).

A 15 mm engagement on an 1800 mm panel is eight thousandths of the drawing. At
that scale a slat seated into a channel and a slat butted onto a rail are the
same picture — and 135 mm apart on the cut list — so the joint gets its own view
at its own scale. What that view must not do:

  * draw a section for a joint that is not one. A butt landing with no housing
    and no engagement is two faces meeting, which the elevation already shows;
    an empty detail box invites the reader to look for something that is absent;
  * put the member's tip in the wrong place. The engagement is measured from the
    MOUTH of the housing inward, so 15 mm into a 20 mm channel leaves the tip
    5 mm above the floor — the clearance the margin is about. Measuring it from
    the floor instead puts the tip through the bottom of the channel;
  * stretch one axis. A section whose depth filled its box would make a 3 mm
    clearance and a 20 mm housing look like the same gap.

The details come from the REAL read model — `preview_panel` over M-SLAT@v2,
whose slats seat into a bottom channel — so a field renamed on the wire fails
here rather than emptying the inset in a browser nobody is watching.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import demo_model_versions
from fenceai.fencemodel.preview import PreviewRequest, preview_panel

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = { getElementById: () => null, querySelectorAll: () => [],
                        documentElement: {} };

import { jointSection, sectionPlacement, sectionsFor } from "./js/joint.js";
import { elevationRects, seatRect } from "./js/elevation.js";

const ELEV = %(elev)s;

const out = {};
out.details = (ELEV.details || []).map((d) => ({
  key: d.key, slot: d.member_slot, end: d.end, kind: d.kind,
  depth: d.channel_depth_mm, engagement: d.engagement_mm, margin: d.margin_mm,
  declared: d.declared,
}));

const sections = sectionsFor(ELEV, "slat");
out.section_count = sections.length;
out.section_slot = sections[0]?.member_slot;
// a slot that is housed in nothing gets nothing: without this, deleting the
// slot filter in sectionsFor passes every other assertion in this file
out.sections_of_rail = sectionsFor(ELEV, "rail").length;
out.sections_of_nothing = sectionsFor(ELEV, "no-such-slot").length;
const s = sections[0];
out.section = s && {
  end: s.end, kind: s.kind, tip: s.tip_mm, extent: s.extent_mm,
  declared: s.declared, member: s.member_thickness_mm,
  bands: s.bands.map((b) => [b.role, b.from_mm, b.to_mm]),
  dims: s.dims.map((d) => [d.kind, d.value_mm]),
};

// a butt landing with nothing housing it is not a section
out.butt = jointSection({
  key: "a@b", member_slot: "a", frame_slot: "b", end: "top", kind: "butt",
  member_thickness_mm: 20, frame_thickness_mm: 40, channel_depth_mm: 0,
  engagement_mm: 0, margin_mm: 0, declared: true,
});
out.nothing = jointSection(null);

// a declared member thickness is used; an undeclared one becomes a nominal and
// says so
out.declared = jointSection({
  key: "a@b", member_slot: "a", frame_slot: "b", end: "base", kind: "channel",
  member_thickness_mm: 18, frame_thickness_mm: 60, channel_depth_mm: 20,
  engagement_mm: 15, margin_mm: 3, declared: true,
});
out.undeclared = jointSection({
  key: "a@b", member_slot: "a", frame_slot: "b", end: "base", kind: "channel",
  member_thickness_mm: 0, frame_thickness_mm: 60, channel_depth_mm: 20,
  engagement_mm: 15, margin_mm: 3, declared: true,
});

// both ends of one member, base first, which is also how the ambiguous
// JointDetail.key is settled — the pair (slot, end) is what a reader selects on
out.both_ends = sectionsFor({
  details: [
    { key: "a@b", member_slot: "a", frame_slot: "b", end: "top", kind: "channel",
      member_thickness_mm: 18, frame_thickness_mm: 40, channel_depth_mm: 12,
      engagement_mm: 10, margin_mm: 2, declared: true },
    { key: "a@b", member_slot: "a", frame_slot: "b", end: "base", kind: "channel",
      member_thickness_mm: 18, frame_thickness_mm: 60, channel_depth_mm: 20,
      engagement_mm: 15, margin_mm: 3, declared: true },
  ],
}, "a").map((x) => x.end);

// placement: one scale for both axes, and the axis runs UP the box
const place = sectionPlacement(out.declared);
out.place = {
  scale: place.scale,
  floor_below_mouth: place.py(0) > place.py(out.declared.extent_mm),
  viewbox: [place.viewBox.w > 0, place.viewBox.h > 0],
  // one scale: 10 mm across the section and 10 mm along it are the same number
  // of drawing units. Stretching one axis is what makes a 3 mm clearance and a
  // 20 mm housing look like the same gap — the thing this view exists to avoid.
  px_len: place.px(10) - place.px(0),
  py_len: place.py(0) - place.py(10),
};

// the elevation's own seat band, flipped into SVG y
const seated = elevationRects(ELEV).find((r) => r.seat);
out.seat = seated && { slot: seated.slot_key, h: seated.seat.h_mm,
                       inside: seated.seat.y_mm >= seated.y_mm };
// a range that fits neither axis is drawn as nothing, not as a band across the
// wrong dimension
out.seat_impossible = seatRect(
  { x_mm: 0, y_mm: 0, w_mm: 100, h_mm: 100, seat_start_mm: 500,
    seat_end_mm: 600 }, 1000);
out.seat_absent = seatRect({ x_mm: 0, y_mm: 0, w_mm: 100, h_mm: 100 }, 1000);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def joint():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    # M-SLAT@v2 is a DRAFT, so it is not in `demo_models()` (one document per
    # line, the one an unpinned project gets) — it is in the seed list
    model = next(m for m in demo_model_versions()
                 if m.id == "M-SLAT" and m.version == 2)
    preview = preview_panel(model, PreviewRequest(height_mm=1800, width_mm=2400),
                            demo_catalog())
    proc = subprocess.run(
        [node, "--input-type=module", "-e",
         SCRIPT % {"elev": preview.elevation.model_dump_json()}],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_read_model_really_carries_the_joint(joint):
    """If this fails the inset is empty for a reason that has nothing to do with
    the drawing: the wire stopped saying it."""
    assert joint["details"], "M-SLAT@v2 seats its slats into a bottom channel"
    base = next(d for d in joint["details"] if d["end"] == "base")
    assert base["kind"] == "channel"
    assert (base["depth"], base["engagement"]) == (20, 15)


def test_the_tip_sits_where_the_engagement_puts_it(joint):
    """Engaged from the MOUTH inward: 15 into a 20 mm channel leaves the tip
    5 mm above the floor. Measuring from the floor instead drives the member
    through the bottom of the channel."""
    assert joint["section"]["tip"] == 5
    assert joint["declared"]["tip_mm"] == 5


def test_the_bands_are_the_void_the_seat_and_the_exposed_run(joint):
    bands = dict((role, (a, b)) for role, a, b in joint["section"]["bands"])
    assert bands["clearance"] == (0, 5)
    assert bands["seated"] == (5, 20)
    assert bands["exposed"][0] == 20 and bands["exposed"][1] > 20


def test_every_number_on_the_section_is_dimensioned(joint):
    dims = dict(joint["section"]["dims"])
    assert dims["channel"] == 20
    assert dims["engagement"] == 15
    assert dims["margin"] == 3


def test_a_butt_landing_gets_no_section(joint):
    """Two faces meeting is what the elevation already shows; an empty detail box
    invites the reader to look for something that is not there."""
    assert joint["butt"] is None
    assert joint["nothing"] is None


def test_an_undeclared_member_thickness_becomes_a_nominal_that_says_so(joint):
    assert joint["declared"]["member_thickness_mm"] == 18
    assert joint["declared"]["declared"] is True
    assert joint["undeclared"]["member_thickness_mm"] > 0
    assert joint["undeclared"]["declared"] is False


def test_both_ends_are_shown_base_first(joint):
    """A member can be housed at both ends, and one of the two is not "the"
    joint. Showing both also settles the ambiguous JointDetail.key: the pair
    (member_slot, end) is what a reader selects on."""
    assert joint["both_ends"] == ["base", "top"]


def test_the_section_is_drawn_to_one_scale_with_the_floor_at_the_bottom(joint):
    """`scale > 0` was the whole assertion, and it holds while x is stretched
    three to one against y — the exact distortion the module docstring says
    makes a 3 mm clearance and a 20 mm housing look like the same gap."""
    place = joint["place"]
    assert place["scale"] > 0
    assert place["floor_below_mouth"], "a bottom channel is looked at from below"
    assert abs(place["px_len"] - place["py_len"]) < 1e-6
    assert abs(place["px_len"] - place["scale"] * 10) < 1e-6
    assert all(place["viewbox"])


def test_a_section_belongs_to_the_member_it_was_asked_for(joint):
    """Deleting the slot filter in `sectionsFor` returned every joint on the
    panel and passed everything else in this file."""
    assert joint["section_count"] == 1
    assert joint["section_slot"] == "slat"
    assert joint["sections_of_rail"] == 0
    assert joint["sections_of_nothing"] == 0


def test_the_elevation_hatches_the_housed_end_of_the_member(joint):
    """The one thing the panel drawing can honestly say about a joint at its own
    scale — "that part is inside something"."""
    assert joint["seat"], "M-SLAT@v2's slats are seated, so a band is drawn"
    assert joint["seat"]["h"] == 15
    assert joint["seat"]["inside"], "the band lies within the member it belongs to"


def test_a_seat_that_fits_neither_axis_is_drawn_as_nothing(joint):
    """Rather than as a band across the wrong dimension. The wire does not say
    which axis the range is stated along, so the pair has to prove it."""
    assert joint["seat_impossible"] is None
    assert joint["seat_absent"] is None
