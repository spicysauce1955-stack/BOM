"""What a drag on the panel canvas WRITES (static/js/panel-canvas-geom.js).

The canvas's pure half, tested the way `base-top.js` is: a browser can only show
that a rail moved, and what breaks silently is which authored number moved with
it — a `from_top` rail whose offset is measured from the bottom is a drag that
works perfectly until the bay height changes.

Two rules here are load-bearing and neither is visible in a screenshot:

  * a WIDTH is read absolutely and a GAP as a DELTA. Under `excess: "space"` the
    fit spreads the leftover across the gaps, so the gap on the drawing is not
    the gap that was authored; reading the drawn distance back would make every
    drag of a spread pattern jump by the spread;
  * a drag may not author what the publish gate then refuses. `validate_model`
    bounds the member's net advance, so the overlap a handle can reach is
    bounded to it — the author meets the rule at the handle, where it is a
    limit, rather than at the gate, where it is a rejection.

Nothing here computes the DRAWING. Every rectangle comes from the server's
`PanelElevation`; what this module owns is the inverse.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import {
  SNAP_MM, gapForOverlap, gapFromDrag, handlesFor, marginFromDrag, overlapOf,
  placementFromDrag, snap, widthFromDrag,
} from "./js/panel-canvas-geom.js";

const out = {};
const H = 1800, W = 2400;

// --- placement: each kind reads from the end it names ----------------------
const at = (placement, extra) => placementFromDrag(placement, {
  orientation: "horizontal", index: 0, count: 1, height_mm: H, width_mm: W,
  x_mm: 0, y_mm: 0, ...extra,
});
out.from_bottom = at({kind: "from_bottom", offset_mm: 100}, {y_mm: 640});
out.from_top = at({kind: "from_top", offset_mm: 100}, {y_mm: 640});
out.fraction = at({kind: "fraction", permille: 500}, {y_mm: 900});
out.fraction_top = at({kind: "fraction", permille: 500}, {y_mm: 1800});

// distributed: only the OUTER rails are placeable, and each moves its own inset
const dist = {kind: "distributed", count: 3, count_param: null,
              bottom_inset_mm: 0, top_inset_mm: 0};
out.dist_bottom = at(dist, {index: 0, count: 3, y_mm: 200});
out.dist_top = at(dist, {index: 2, count: 3, y_mm: 1600});
out.dist_middle = at(dist, {index: 1, count: 3, y_mm: 900});
// ... and neither inset may cross the other, or leave the panel
out.dist_clamped = at({...dist, top_inset_mm: 1700}, {index: 0, count: 3, y_mm: 1750});
out.dist_negative = at(dist, {index: 0, count: 3, y_mm: -300});

// a VERTICAL frame slot reads x, not y
out.vertical = placementFromDrag({kind: "from_bottom", offset_mm: 0}, {
  orientation: "vertical", index: 0, count: 1, height_mm: H, width_mm: W,
  x_mm: 600, y_mm: 0,
});

// the input is never mutated — EVERY arm, not only the one that returns early.
// Undo/redo restores a snapshot of the document, and a transform that edited its
// argument has already spent the value that snapshot holds.
out.untouched = ["from_bottom", "from_top", "fraction", "distributed"].map((kind) => {
  const before = {kind: "distributed", count: 3, count_param: null,
                  bottom_inset_mm: 11, top_inset_mm: 22,
                  offset_mm: 33, permille: 44};
  before.kind = kind;
  placementFromDrag(before, {orientation: "horizontal", index: 0, count: 3,
                             height_mm: H, width_mm: W, x_mm: 700, y_mm: 700});
  return before;
});
out.placement_input_untouched = dist;

// --- width is absolute -----------------------------------------------------
const member = {key: "slat", width_mm: 100, gap_after_mm: 20};
out.width = widthFromDrag(member, {x_mm: 445, member_x_mm: 300});
out.width_min = widthFromDrag(member, {x_mm: 299, member_x_mm: 300});
// narrowing past the overlap that would swallow it is refused, not authored
const overlapping = {key: "board", width_mm: 140, gap_after_mm: -120};
out.width_vs_overlap = widthFromDrag(overlapping, {x_mm: 400, member_x_mm: 300});

// --- gap and margin are DELTAS --------------------------------------------
out.gap_wider = gapFromDrag(member, {delta_mm: 30});
out.gap_to_overlap = gapFromDrag(member, {delta_mm: -75});
// the bound that IS real: width + gap must still advance
out.gap_clamped = gapFromDrag(member, {delta_mm: -400});
out.margin = marginFromDrag({edge_margin_mm: 40}, {delta_mm: 25});
out.margin_floor = marginFromDrag({edge_margin_mm: 40}, {delta_mm: -200});

// --- the sign is the control's business, not the author's -----------------
out.overlap_of = [overlapOf({gap_after_mm: 20}), overlapOf({gap_after_mm: -40}),
                  overlapOf({gap_after_mm: 0})];
out.gap_for_overlap = [gapForOverlap(false, 20), gapForOverlap(true, 40),
                       gapForOverlap(true, -40)];

// --- what a drag at its limit AUTHORS, for the gate to judge ---------------
// The floors above are re-statements of the arithmetic. What matters is that the
// document they produce is one `validate_model` accepts, and that one step past
// them is one it refuses — the two are joined by a comment today and by pytest
// below.
const AT_THE_FLOOR = (() => {
  const m = {key: "board", width_mm: 140, gap_after_mm: -120};
  return {
    width_mm: widthFromDrag(m, {x_mm: 0, member_x_mm: 300}),   // driven far under
    gap_after_mm: gapFromDrag({key: "board", width_mm: 100, gap_after_mm: 20},
                              {delta_mm: -9999}),
  };
})();
out.at_the_floor = AT_THE_FLOOR;

// --- handles: one per authored number a drag can reach --------------------
const ELEV = {
  width_mm: W, height_mm: H,
  members: [
    {slot_key: "rail", role: "rail", kind: "frame", index: 0,
     x_mm: 0, y_mm: 0, w_mm: W, h_mm: 60},
    {slot_key: "rail", role: "rail", kind: "frame", index: 1,
     x_mm: 0, y_mm: 1740, w_mm: W, h_mm: 60},
    {slot_key: "slat", role: "infill", kind: "infill", index: 0,
     x_mm: 40, y_mm: 0, w_mm: 100, h_mm: H},
    {slot_key: "slat", role: "infill", kind: "infill", index: 1,
     x_mm: 160, y_mm: 0, w_mm: 100, h_mm: H},
  ],
};
const SPEC = {
  frame: [{key: "rail", orientation: "horizontal",
           placement: {kind: "distributed", count: 2, bottom_inset_mm: 0,
                       top_inset_mm: 0}}],
  infill: {orientation: "vertical", edge_margin_mm: 40,
           pattern: [{key: "slat", width_mm: 100, gap_after_mm: 20}]},
  fixings: [],
};
const handles = handlesFor(ELEV, SPEC);
out.handle_kinds = handles.map((h) => `${h.kind}:${h.slot_key}#${h.index}`);
out.handle_at = Object.fromEntries(handles.map((h) => [h.id, [h.x_mm, h.y_mm]]));

// a three-rail distributed slot offers handles on the ENDS only
const three = {...ELEV, members: [
  ...ELEV.members.slice(0, 2),
  {slot_key: "rail", role: "rail", kind: "frame", index: 2,
   x_mm: 0, y_mm: 870, w_mm: W, h_mm: 60},
]};
out.three_rail_handles = handlesFor(three, SPEC)
  .filter((h) => h.kind === "placement").map((h) => h.index);

// ... and one placed at an exact height offers a handle on every member of it
const exact = {...SPEC, frame: [{...SPEC.frame[0],
  placement: {kind: "from_bottom", offset_mm: 0}}]};
out.exact_handles = handlesFor(ELEV, exact)
  .filter((h) => h.kind === "placement").map((h) => h.index);

// a single board has a width and a margin but no gap after it
const lone = {...ELEV, members: [ELEV.members[0], ELEV.members[1], ELEV.members[2]]};
out.lone_board_handles = handlesFor(lone, SPEC)
  .filter((h) => h.slot_key === "slat").map((h) => h.kind);

// a TWO-member pattern (board-on-board): the margin is one number on the
// infill, so it gets one handle however many members there are
const PAIR_ELEV = {...ELEV, members: [
  ...ELEV.members.slice(0, 2),
  {slot_key: "back", role: "infill", kind: "infill", index: 0,
   x_mm: 40, y_mm: 0, w_mm: 100, h_mm: H},
  {slot_key: "front", role: "infill", kind: "infill", index: 0,
   x_mm: 110, y_mm: 0, w_mm: 100, h_mm: H},
]};
const PAIR_SPEC = {...SPEC, infill: {orientation: "vertical", edge_margin_mm: 40,
  pattern: [{key: "back", width_mm: 100, gap_after_mm: -30},
            {key: "front", width_mm: 100, gap_after_mm: -30}]}};
out.pair_margins = handlesFor(PAIR_ELEV, PAIR_SPEC)
  .filter((h) => h.kind === "margin").map((h) => [h.slot_key, h.x_mm]);

out.snap = [snap(103), snap(107), snap(-103), SNAP_MM];

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def g():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_each_placement_kind_reads_from_the_end_it_names(g):
    """A `from_top` rail dragged to 640 mm above the panel bottom is 1160 mm
    down from the top — and stays there when the bay gets taller, which is the
    whole reason the kinds are different things rather than four spellings of a
    height."""
    assert g["from_bottom"] == {"kind": "from_bottom", "offset_mm": 640}
    assert g["from_top"] == {"kind": "from_top", "offset_mm": 1160}
    assert g["fraction"]["permille"] == 500
    assert g["fraction_top"]["permille"] == 1000


def test_only_the_outer_rails_of_a_distributed_slot_are_placeable(g):
    """`distributed` spreads N members between two insets: the ends are the two
    numbers there ARE, and an interior rail has no authored position to move.
    Returning the placement unchanged is what makes the canvas honest about it —
    no handle is drawn, and the inspector says why in words."""
    assert g["dist_bottom"]["bottom_inset_mm"] == 200
    assert g["dist_bottom"]["top_inset_mm"] == 0
    assert g["dist_top"]["top_inset_mm"] == 200
    assert g["dist_middle"] == {"kind": "distributed", "count": 3,
                                "count_param": None, "bottom_inset_mm": 0,
                                "top_inset_mm": 0}


def test_the_insets_may_not_cross_each_other_or_leave_the_panel(g):
    assert g["dist_clamped"]["bottom_inset_mm"] == 100    # 1800 - 1700
    assert g["dist_negative"]["bottom_inset_mm"] == 0


def test_a_vertical_frame_slot_is_placed_across_the_panel(g):
    assert g["vertical"] == {"kind": "from_bottom", "offset_mm": 600}


def test_no_placement_arm_edits_the_object_it_was_handed(g):
    """Undo/redo restores a snapshot of the document; a transform that edited
    its argument has already spent the value the snapshot holds.

    EVERY arm, because only one of the four returns its argument early and a
    fixture that exercised that one alone would pass with the other three
    writing through."""
    for kind, before in zip(["from_bottom", "from_top", "fraction", "distributed"],
                            g["untouched"]):
        assert before["offset_mm"] == 33, kind
        assert before["permille"] == 44, kind
        assert before["bottom_inset_mm"] == 11, kind
        assert before["top_inset_mm"] == 22, kind
    assert g["placement_input_untouched"] == {
        "kind": "distributed", "count": 3, "count_param": None,
        "bottom_inset_mm": 0, "top_inset_mm": 0}


def _judge(width_mm: int, gap_after_mm: int) -> list[str]:
    """One board of that width and that gap, through the real publish gate."""
    from fenceai.catalog.demo import demo_catalog
    from fenceai.fencemodel.model import FenceModel, validate_model

    model = FenceModel.model_validate({
        "id": "M-DRAG", "version": 1,
        "default_spec": {"infill": {
            "orientation": "vertical",
            "pattern": [{"key": "board", "width_mm": width_mm,
                         "gap_after_mm": gap_after_mm,
                         # a real product, so the only thing left for the gate
                         # to object to is the advance this test is about
                         "requirement": {"role": "infill",
                                         "length_rule": "panel_height",
                                         "eligibility": {"members": [
                                             {"kind": "catalog_item",
                                              "sku": "SLAT-100"}]}}}],
        }},
    })
    return validate_model(model, demo_catalog())


def test_a_drag_at_its_limit_authors_a_model_the_publish_gate_accepts(g):
    """The rule the module header calls load-bearing, joined to the gate that
    states it rather than to a constant copied out of the JS.

    `validate_model` bounds a member's net advance and the floors in
    `widthFromDrag`/`gapFromDrag` exist to stop a handle reaching past it.
    Asserting 121 and -99 only re-states the arithmetic; asserting that the
    document those produce is one the gate TAKES, and that one millimetre
    further is one it REFUSES, is what fails if either side moves alone."""
    floor = g["at_the_floor"]
    assert _judge(floor["width_mm"], -120) == [], (
        "a drag stopped at the width floor must author a publishable panel")
    assert any("never advance" in e for e in _judge(floor["width_mm"] - 1, -120)), (
        "one millimetre past the floor must be what the gate refuses — if it is "
        "not, the floor is in the wrong place")

    assert _judge(100, floor["gap_after_mm"]) == []
    assert any("never advance" in e for e in _judge(100, floor["gap_after_mm"] - 1))


def test_a_width_is_read_absolutely(g):
    assert g["width"] == 145
    assert g["width_min"] == 1, "a board of no width is not a board"


def test_a_width_may_not_be_dragged_under_its_own_overlap(g):
    """`validate_model` bounds the member's net advance: a board 120 mm inside
    its neighbour may not be narrowed to 100, because that pattern never
    advances and `fit_pattern` cannot lay it out at all."""
    assert g["width_vs_overlap"] == 121


def test_a_gap_moves_by_the_drag_and_not_to_it(g):
    """The fit spreads the leftover across the gaps under `excess: space`, so
    the drawn gap is not the authored one. A drag adds what the pointer moved,
    or the first pixel of every drag would jump by the spread."""
    assert g["gap_wider"] == 50
    assert g["gap_to_overlap"] == -55, "a negative gap is an overlap, and reachable"
    assert g["gap_clamped"] == -99, "width + gap must still advance"


def test_a_margin_moves_by_the_drag_and_never_below_zero(g):
    assert g["margin"] == 65
    assert g["margin_floor"] == 0


def test_the_overlap_control_hides_the_sign(g):
    """"Overlaps next board" plus a positive amount. The author never has to
    remember that a minus means an overlap; the control means it."""
    assert g["overlap_of"] == [
        {"overlaps": False, "amount_mm": 20},
        {"overlaps": True, "amount_mm": 40},
        {"overlaps": False, "amount_mm": 0},
    ]
    assert g["gap_for_overlap"] == [20, -40, -40]


def test_there_is_one_handle_per_authored_number_a_drag_can_reach(g):
    """Twenty slats of one pattern member share ONE width, so there is one width
    handle and it rides the first drawn board — a handle per rectangle would be
    twenty ways to set the same number."""
    assert sorted(g["handle_kinds"]) == sorted([
        "placement:rail#0", "placement:rail#1",
        "width:slat#0", "gap:slat#0", "margin:slat#0",
    ])


def test_a_handle_sits_on_the_thing_it_moves(g):
    at = g["handle_at"]
    assert at["placement:rail:0"] == [1200, 30]      # centre of the bottom rail
    assert at["width:slat:0"] == [140, 900]          # the board's trailing edge
    assert at["gap:slat:0"] == [150, 900]            # the middle of the gap after
    assert at["margin:slat:0"] == [40, 900]          # the board's leading edge


def test_three_rails_still_offer_two_handles(g):
    assert sorted(g["three_rail_handles"]) == [0, 2]


def test_a_slot_placed_at_an_exact_height_offers_a_handle_on_each_member(g):
    """The contrast case: `from_bottom` places every member at ONE authored
    offset, so any of them may be grabbed to set it."""
    assert sorted(g["exact_handles"]) == [0, 1]


def test_a_lone_board_has_a_width_and_a_margin_but_no_gap(g):
    """There is nothing after it for the gap to be to, and a handle for a number
    that does not affect the drawing is a control that does nothing."""
    assert sorted(g["lone_board_handles"]) == ["margin", "width"]


def test_snapping_is_five_millimetres(g):
    assert g["snap"] == [105, 105, -105, 5]


def test_a_two_board_pattern_gets_one_margin_handle_not_two(g):
    """`edge_margin_mm` lives on the INFILL, not on a member. One handle per
    NUMBER is the module's own rule, and a board-on-board pattern was getting
    one per member — both writing the same value, and the second sitting
    nowhere near the margin it moved.

    It rides the OUTERMOST board, because that is the edge the margin measures
    to."""
    assert len(g["pair_margins"]) == 1, g["pair_margins"]
    assert g["pair_margins"][0] == ["back", 40], "the margin belongs to the outer board"
