"""The panel as rectangles.

The governing property is that the drawing is DERIVED from the same slots the
BOM is derived from, so the picture and the numbers cannot disagree. Everything
fitted on it — slat widths, gap sizes, rail heights — is real data; the one
nominal (a frame member's face height, which the catalog does not carry) is
flagged as such rather than passed off as measured.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT, M_SLAT_V2
from fenceai.fencemodel.model import (
    Distributed, EligibleItem, Eligibility, FrameSlot, FromBottom, FromTop,
    Fraction, PartRequirement, validate_model,
)
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.fencemodel.resolve import PanelContext, placement_positions, resolve_panel
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary, SpecField
from fenceai.parts.resolve import resolve_model_parts
from fenceai.report.elevation import ElevationMember, panel_elevation

BAY = PanelContext(centre_width_mm=2500, clear_width_mm=2400, height_mm=1800)


# A member's width and a frame member's face height are the PART's now, so a
# drawing made from an authored document draws 0 mm bands. Resolution is where those
# numbers arrive, and it is upstream of `resolve_panel` exactly as it is in
# `generate` — a model naming no part passes through it untouched.
PARTS = PartLibrary(parts=demo_parts())
SLAT = resolve_model_parts(M_SLAT, PARTS)[0]
SLAT_V2 = resolve_model_parts(M_SLAT_V2, PARTS)[0]


def elevation_of(model, ctx=BAY):
    resolved, _ = resolve_model_parts(model, PARTS)
    return panel_elevation(resolve_panel(resolved.default_spec, ctx),
                           ctx.clear_width_mm, ctx.height_mm)


def by_slot(elevation, key):
    return [m for m in elevation.members if m.slot_key == key]


# --- placement ----------------------------------------------------------------

def test_two_distributed_members_are_a_top_rail_and_a_bottom_rail():
    """Not two rails floating in the middle. `distributed` spreads inclusive of
    both ends, which is what a fence frame is."""
    assert placement_positions(Distributed(count=2), 2, 1800) == [0, 1800]


def test_three_distributed_members_include_the_ends_and_the_middle():
    assert placement_positions(Distributed(count=3), 3, 1800) == [0, 900, 1800]


def test_a_lone_distributed_member_centres():
    """There is no pair of ends for it to be one of."""
    assert placement_positions(Distributed(count=1), 1, 1800) == [900]


def test_insets_move_the_band_not_the_spacing_rule():
    assert placement_positions(
        Distributed(count=2, bottom_inset_mm=100, top_inset_mm=200), 2, 1800
    ) == [100, 1600]


def test_the_other_placements_read_from_the_end_they_name():
    assert placement_positions(FromBottom(offset_mm=150), 1, 1800) == [150]
    assert placement_positions(FromTop(offset_mm=150), 1, 1800) == [1650]
    assert placement_positions(Fraction(permille=500), 1, 1800) == [900]


def test_placement_is_integer_and_rounds_exactly_once():
    """ADR-0002: nothing upstream rounds and nothing downstream re-rounds. Two
    implementations differing by a millimetre would move a rail — and the fixing
    count that depends on crossings with it."""
    positions = placement_positions(Distributed(count=4), 4, 1000)
    assert positions == [0, 333, 666, 1000]
    assert all(isinstance(p, int) for p in positions)


# --- the drawing --------------------------------------------------------------

def test_the_slat_panel_draws_every_slat_it_bought():
    elevation = elevation_of(M_SLAT)
    slats = by_slot(elevation, "slat")
    resolved = next(s for s in resolve_panel(SLAT.default_spec, BAY).slots
                    if s.slot_key == "slat")
    assert len(slats) == resolved.qty, "the drawing and the BOM disagree on count"
    assert all(m.w_mm == 100 for m in slats), "the slats are drawn at their real width"
    assert all(m.h_mm == 1800 and m.y_mm == 0 for m in slats)


def test_the_slats_do_not_overlap_and_stay_inside_the_opening():
    slats = sorted(by_slot(elevation_of(M_SLAT), "slat"), key=lambda m: m.x_mm)
    assert slats[0].x_mm >= 0
    assert slats[-1].x_mm + slats[-1].w_mm <= 2400
    for a, b in zip(slats, slats[1:]):
        assert b.x_mm >= a.x_mm + a.w_mm, "two slats occupy the same millimetres"


def test_the_drawn_gaps_are_the_fitted_gaps_exactly():
    """The gap is what the sphere test measures, which is why fit_pattern returns
    a LIST — a single rounded value would let a limit pass while several real
    openings exceeded it."""
    elevation = elevation_of(M_SLAT)
    slats = sorted(by_slot(elevation, "slat"), key=lambda m: m.x_mm)
    drawn = [b.x_mm - (a.x_mm + a.w_mm) for a, b in zip(slats, slats[1:])]
    assert drawn == elevation.gaps_mm[:len(drawn)]
    assert max(drawn) - min(drawn) <= 1


def test_the_rails_are_drawn_across_the_opening_at_their_resolved_heights():
    rails = by_slot(elevation_of(M_SLAT), "rail")
    assert len(rails) == 2
    assert all(m.x_mm == 0 and m.w_mm == 2400 for m in rails)
    assert sorted(m.y_mm for m in rails) == [0, 1800 - rails[0].h_mm]


def test_an_undeclared_face_height_is_flagged_not_passed_off_as_measured():
    """A FrameSlot carries no thickness — a rail's face height is product data
    the catalog does not hold. The read model says so rather than inventing a
    millimetre value that would read as fitted."""
    rails = by_slot(elevation_of(M_SLAT), "rail")
    assert all(m.declared is False for m in rails)
    assert all(m.declared is True for m in by_slot(elevation_of(M_SLAT), "slat"))


def test_screws_are_counted_not_drawn():
    """A dot per screw would bury the panel it is fixing.

    Fasteners are not MEMBERS: they have no extent, so they get no rectangle.
    Where they land is a separate list with a count on each point — see below."""
    assert by_slot(elevation_of(M_SLAT), "screw") == []


# --- fasteners: places, never screws ------------------------------------------
#
# What the canvas needs to make `per_member_crossing` mean something, and the
# reason it is derived HERE rather than drawn by the client: a dot count worked
# out in JS would eventually say twelve beside a BOM line buying eight, on the
# one surface built so an author can see what a basis does.


def _fixing_model(basis: str, qty_per_basis: int = 1):
    """M_SLAT with its screw rule re-based, so one fixture exercises all six."""
    model = M_SLAT.model_copy(deep=True)
    rule = model.default_spec.fixings[0]
    model.default_spec.fixings[0] = rule.model_copy(
        update={"basis": basis, "qty_per_basis": qty_per_basis, "qty_param": None})
    return model


def _fixing_slot(panel, key="screw"):
    return next(s for s in panel.slots if s.slot_key == key)


@pytest.mark.parametrize("basis", [
    "per_panel", "per_frame_member", "per_member", "per_end_member", "per_gap",
    "per_member_crossing",
])
def test_the_drawn_fasteners_total_exactly_what_the_resolver_counted(basis):
    """The property the points exist to keep: a drawing showing twelve dots
    beside a BOM line buying eight screws would be a picture disagreeing with
    the numbers it is derived from. On THIS panel every counted fastener has a
    place, so nothing is left over — the geometry that does leave some over is
    the test below."""
    model = _fixing_model(basis, qty_per_basis=3)
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    drawn = [f for f in elevation.fixings if f.slot_key == "screw"]
    assert drawn, basis
    assert sum(f.qty for f in drawn) == _fixing_slot(panel).qty
    assert elevation.fixings_unplaced == []
    assert all(f.basis == basis for f in drawn)
    # a place holds a DECIDED count, never a share: three per occurrence of the
    # basis is three at each place, not "three times the count, spread about"
    assert all(f.qty % 3 == 0 for f in drawn), [f.qty for f in drawn]


def _stiled(basis: str, qty_per_basis: int = 1):
    """M_SLAT with a pair of vertical stiles added beside its vertical slats.

    The geometry `per_member_crossing` cannot honestly draw: `resolve.py` counts
    crossings as members x frame members, and a stile parallel to a slat crosses
    it nowhere. Half the counted crossings do not exist on the drawing.
    """
    model = _fixing_model(basis, qty_per_basis)
    model.default_spec.frame.append(FrameSlot(
        key="stile", orientation="vertical", placement=Distributed(count=2),
        requirement=PartRequirement(
            role="rail", qty=1, length_rule="panel_height",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])),
    ))
    return model


def test_each_basis_puts_its_fasteners_where_its_name_says():
    """The totals reconcile by construction, so they cannot see a place that is
    in the wrong POSITION — swapping two bases' place sets leaves every sum
    exactly right and teaches the author the opposite of the truth, on the one
    surface built to teach it."""
    rails = by_slot(elevation_of(_fixing_model("per_frame_member")), "rail")
    on_rails = elevation_of(_fixing_model("per_frame_member")).fixings
    bands = [(r.y_mm, r.y_mm + r.h_mm) for r in rails]
    assert len(on_rails) == len(rails)
    assert all(any(lo <= f.y_mm <= hi for lo, hi in bands) for f in on_rails)

    boards = by_slot(elevation_of(_fixing_model("per_member")), "slat")
    on_boards = elevation_of(_fixing_model("per_member")).fixings
    spans = [(m.x_mm, m.x_mm + m.w_mm) for m in boards]
    assert len(on_boards) == len(boards)
    assert all(any(lo <= f.x_mm <= hi for lo, hi in spans) for f in on_boards)
    # ... and NOT on a rail line, which is what per_member_crossing would give
    assert {f.y_mm for f in on_boards} == {900}     # the boards' own centre

    middle = elevation_of(_fixing_model("per_panel")).fixings
    assert [(f.x_mm, f.y_mm) for f in middle] == [(1200, 900)]


def test_a_member_that_only_touches_a_rail_is_still_fixed_to_it():
    """The boundary the fixture geometry hides: M_SLAT's slats run the full
    height and genuinely overlap both rails, so nothing exercises a board whose
    end lands exactly ON a rail face — which is what `between_frame` with no
    engagement produces. A crossing test that demanded a strict overlap would
    draw no fasteners at all for that panel."""
    from fenceai.report.elevation import _overlap_centre

    rail = ElevationMember(slot_key="rail", role="rail", index=0, kind="frame",
                           x_mm=0, y_mm=0, w_mm=2400, h_mm=60)
    seated = ElevationMember(slot_key="slat", role="infill", index=0, kind="infill",
                             x_mm=100, y_mm=60, w_mm=100, h_mm=1680)
    assert _overlap_centre(seated, rail) == (150, 60), "a touching end is a landing"
    apart = seated.model_copy(update={"y_mm": 61})
    assert _overlap_centre(apart, rail) is None


def test_a_single_board_has_one_end_not_two():
    """`per_end_member` counts `min(placed_count, 2)`: one board is one end. Two
    places on the same board would be the drawing claiming a fastener the
    resolver never counted — and, with both at the same point, invisibly."""
    model = _fixing_model("per_end_member")
    # one board, as wide as the opening: the fit places exactly one
    model.default_spec.infill.pattern[0].width_mm = 2000
    model.default_spec.infill.pattern[0].gap_after_mm = 2000
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    assert len(by_slot(elevation, "slat")) == 1
    assert len(elevation.fixings) == 1
    assert sum(f.qty for f in elevation.fixings) == _fixing_slot(panel).qty
    assert elevation.fixings_unplaced == []


def test_a_basis_that_counts_nothing_buys_nothing_and_draws_nothing():
    """The zero case, and the reason it needs no `unplaced` entry: a panel with
    no frame has no crossings to COUNT, so `resolve_panel` never makes the slot
    — the fence buys no screws and the drawing shows none. The two agree by
    never having disagreed, which is the shape worth pinning: an `unplaced`
    line here would report fasteners nobody bought."""
    model = _fixing_model("per_member_crossing")
    model.default_spec.frame = []
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    assert not [s for s in panel.slots if s.slot_kind == "fixing"]
    assert elevation.fixings == []
    assert elevation.fixings_unplaced == []


def test_a_fastener_with_nowhere_to_go_is_reported_not_spread_over_the_others():
    """The failure this design exists to refuse.

    A panel with vertical stiles beside vertical slats is COUNTED for crossings
    between them, and those crossings are nowhere on the drawing. Sharing the
    total across the crossings that ARE there would put a plausible "x2" on each
    one — a number nothing decided, on the one surface built to explain what the
    basis does. So the leftovers are stated (foundation §15: represent unknowns
    rather than fabricate certainty), and the two still reconcile exactly.
    """
    panel = resolve_panel(_stiled("per_member_crossing").default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    slot = _fixing_slot(panel)
    drawn = sum(f.qty for f in elevation.fixings)
    left = [u for u in elevation.fixings_unplaced if u.slot_key == "screw"]
    assert left, "the stile crossings do not exist and must be reported"
    assert drawn + left[0].qty == slot.qty
    assert left[0].basis == "per_member_crossing"
    # every drawn place is a REAL crossing: one fastener each, none inflated to
    # absorb a crossing that is not there
    assert {f.qty for f in elevation.fixings} == {1}


def test_a_place_stands_for_every_piece_that_is_there():
    """A slot with `qty=2` is two pieces at one position — a batten pair, a board
    front and back — and the elevation draws ONE rectangle for them. The bases
    that count PARTS have to weight the place by what stands there, or a panel
    whose rails come in pairs draws half its fixings and calls the rest
    unplaceable."""
    model = _fixing_model("per_frame_member")
    model.default_spec.frame[0].requirement.qty = 2
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    assert elevation.fixings_unplaced == []
    assert sum(f.qty for f in elevation.fixings) == _fixing_slot(panel).qty


def test_a_fixing_that_buys_nothing_places_nothing():
    """`qty_per_basis` has no lower bound and a `qty_param` may resolve to 0. A
    dot holding no fastener draws exactly like one that does."""
    panel = resolve_panel(_fixing_model("per_member", qty_per_basis=0)
                          .default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    assert elevation.fixings == []
    assert elevation.fixings_unplaced == []


def test_a_fastener_point_sits_inside_the_opening():
    elevation = elevation_of(_fixing_model("per_member_crossing"))
    for f in elevation.fixings:
        assert 0 <= f.x_mm <= BAY.clear_width_mm
        assert 0 <= f.y_mm <= BAY.height_mm


def test_per_crossing_puts_a_point_where_a_board_meets_a_rail():
    """The basis nobody can picture from its name. Two rails and N slats is 2N
    crossings, and every point is on a rail's own band."""
    model = _fixing_model("per_member_crossing")
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    slats = by_slot(elevation, "slat")
    rails = by_slot(elevation, "rail")
    points = [f for f in elevation.fixings if f.slot_key == "screw"]
    assert len(points) == len(slats) * len(rails)
    bands = [(r.y_mm, r.y_mm + r.h_mm) for r in rails]
    assert all(any(lo <= f.y_mm <= hi for lo, hi in bands) for f in points)


def test_per_gap_puts_a_point_between_two_boards_and_never_on_one():
    model = _fixing_model("per_gap")
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    slats = sorted(by_slot(elevation, "slat"), key=lambda m: m.x_mm)
    points = sorted(elevation.fixings, key=lambda f: f.x_mm)
    assert len(points) == len(slats) - 1
    for point, left, right in zip(points, slats, slats[1:]):
        assert left.x_mm + left.w_mm <= point.x_mm <= right.x_mm


def test_a_panel_with_no_fixing_rule_draws_no_fasteners():
    model = M_SLAT.model_copy(deep=True)
    model.default_spec.fixings = []
    assert elevation_of(model).fixings == []


def test_a_resolved_panel_that_predates_the_basis_draws_no_fasteners():
    """A run stored before `basis` rode on the slot carries "" — and a drawing
    that guessed a basis for it would put screws where that fence has none."""
    panel = resolve_panel(SLAT.default_spec, BAY)
    for slot in panel.slots:
        if slot.slot_kind == "fixing":
            slot.basis = ""
    assert panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm).fixings == []


def test_fasteners_are_deterministic():
    model = _fixing_model("per_member_crossing")
    assert elevation_of(model) == elevation_of(model)


def test_the_legacy_panel_draws_its_two_rails_and_no_infill():
    elevation = elevation_of(M_LEGACY)
    assert len(by_slot(elevation, "rail")) == 2
    assert elevation.gaps_mm == []


def test_a_taller_bay_lengthens_the_slats_without_changing_their_number():
    short = elevation_of(M_SLAT, BAY.model_copy(update={"height_mm": 1200}))
    tall = elevation_of(M_SLAT, BAY.model_copy(update={"height_mm": 2000}))
    assert len(by_slot(short, "slat")) == len(by_slot(tall, "slat"))
    assert by_slot(short, "slat")[0].h_mm == 1200
    assert by_slot(tall, "slat")[0].h_mm == 2000


def test_drawing_is_deterministic():
    assert elevation_of(M_SLAT) == elevation_of(M_SLAT)


# --- through the preview ------------------------------------------------------

def test_the_preview_hands_back_a_drawing_that_names_its_products():
    """A rectangle and its price are the same part, so the drawing carries the
    sku the preview resolved rather than making the client join them."""
    preview = preview_panel(M_SLAT, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    slats = [m for m in preview.elevation.members if m.slot_key == "slat"]
    assert slats and all(m.sku == "SLAT-100" for m in slats)
    part = next(p for p in preview.parts if p.slot_key == "slat")
    assert len(slats) == part.qty, "the drawing shows a different count from the price"


# --- what the wire says about itself ------------------------------------------

def test_every_drawn_member_says_which_half_of_the_panel_drew_it():
    """A vertical FRAME slot and a vertical INFILL slot are the same shape on the
    wire, so a client had to guess which one a `gaps_mm` list belonged to — and
    the renderer confirmed its gap dimension geometrically rather than by
    indexing, which is guesswork dressed as arithmetic."""
    elevation = elevation_of(M_SLAT)
    kinds = {m.slot_key: m.kind for m in elevation.members}
    assert kinds["rail"] == "frame"
    assert kinds["slat"] == "infill"
    assert all(m.kind for m in elevation.members), "a member with no kind is a guess"


def test_a_shadowbox_member_carries_its_depth_not_just_its_side():
    """`face` alone says which side; a shadowbox has a DEPTH, and a client that
    can only order two layers cannot draw one at its real offset."""
    model = M_SLAT.model_copy(deep=True)
    model.default_spec.infill.pattern[0].face_offset_mm = -18
    ctx = BAY
    elevation = panel_elevation(resolve_panel(model.default_spec, ctx),
                               ctx.clear_width_mm, ctx.height_mm)
    slats = [m for m in elevation.members if m.slot_key == "slat"]
    assert slats and all(m.face == "back" for m in slats)
    assert all(m.face_offset_mm == -18 for m in slats)


# --- a member that does not span the opening ----------------------------------

def test_a_seated_slat_is_drawn_as_the_piece_the_bom_buys():
    """The property this module opens by claiming, tested where it was breaking.

    M-SLAT@v2's slat is cut to 1665 in an 1800 mm bay: it starts inside a bottom
    channel whose face is 50 + 30 = 80 up, less the 15 mm it seats into it, and
    stops under the top rail's face at 1750 − 20. Drawn full height it would
    have run through the channel and out past the rail, 135 mm longer than the
    part on the cut list — on the model whose whole reason to exist is that
    135 mm.
    """
    from fenceai.fencemodel.demo import M_SLAT_V2

    panel = resolve_panel(SLAT_V2.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    slat_slot = next(s for s in panel.slots if s.slot_key == "slat")

    drawn = by_slot(elevation, "slat")
    assert drawn, "the slats must still be drawn"
    for member in drawn:
        assert member.y_mm == 65           # 50 + 60//2 − 15
        assert member.h_mm == 1665         # (1750 − 20) − 65
        assert member.h_mm == slat_slot.length_mm, \
            "the drawn member and the bought member are one number"
    # it starts INSIDE the channel and stops short of the top rail's centreline
    assert drawn[0].y_mm < 80 and drawn[0].y_mm + drawn[0].h_mm < 1750


def test_a_full_height_member_is_still_drawn_across_the_whole_opening():
    """The extent is used only where the resolver fixed one. Every model that
    cuts to `panel_height` must draw exactly as it did before."""
    for member in by_slot(elevation_of(M_SLAT), "slat"):
        assert (member.y_mm, member.h_mm) == (0, BAY.height_mm)


# --- the joint, drawn ---------------------------------------------------------

def top_seated_model():
    """M-SLAT@v2 turned upside down: the housing is in the TOP rail.

    Authored here rather than in `demo.py` because it demonstrates nothing a
    product line would — it exists so the top-engagement branch is reached by a
    test instead of by a customer.
    """
    # RESOLVED first: the faces and widths this drawing measures are the parts',
    # and the edits below are about JOINTS, which stay the panel's.
    model = resolve_model_parts(M_SLAT_V2, PARTS)[0]
    channel, rail = model.default_spec.frame
    channel.joint, channel.channel_depth_mm, channel.insertion_margin_mm = "butt", 0, 0
    rail.joint, rail.channel_depth_mm, rail.insertion_margin_mm = "groove", 20, 2
    slat = model.default_spec.infill.pattern[0]
    slat.joint, slat.base_engagement_mm, slat.top_engagement_mm = "groove", 0, 15
    return model


def test_a_seated_member_says_which_part_of_itself_is_buried():
    """M-SLAT@v2's slat runs 65 -> 1730 (see the extent test above), and the
    first 15 mm of it are inside the channel: 65 -> 80. 80 is the channel's own
    top face — 50 up plus half its 60 mm face height — which is the check that
    the hatched band stops exactly where the timber becomes visible.
    """
    from fenceai.fencemodel.demo import M_SLAT_V2

    drawn = by_slot(elevation_of(M_SLAT_V2), "slat")
    assert drawn
    for member in drawn:
        assert (member.seat_start_mm, member.seat_end_mm) == (65, 80)
        assert member.seat_start_mm == member.y_mm, "the seat starts at the member"
        assert member.seat_end_mm == 50 + 60 // 2, "the channel's own top face"
        assert member.joint == "channel"


def test_a_member_housed_at_the_top_is_hatched_at_the_top():
    """Same arithmetic from the other end: the slat starts at the channel's face
    with nothing buried (50 + 30 = 80) and runs to 1750 - 20 + 15 = 1745, so it
    is 1665 long again and its last 15 mm — 1730 -> 1745 — are in the groove.
    1730 is the top rail's bottom face, which is where the groove begins.
    """
    ctx = BAY
    elevation = panel_elevation(
        resolve_panel(top_seated_model().default_spec, ctx),
        ctx.clear_width_mm, ctx.height_mm)
    drawn = by_slot(elevation, "slat")
    assert drawn
    for member in drawn:
        assert (member.y_mm, member.h_mm) == (80, 1665)
        assert (member.seat_start_mm, member.seat_end_mm) == (1730, 1745)
        assert member.seat_end_mm == member.y_mm + member.h_mm


def test_a_butted_member_seats_into_nothing_and_says_so():
    """Every model that does not declare `between_frame` — which is every model
    in the repo but one — must draw with no seat at all, or a renderer keyed on
    the presence of these fields hatches a band through solid timber."""
    for member in elevation_of(M_SLAT).members:
        assert member.seat_start_mm is None and member.seat_end_mm is None
        assert member.joint == "butt"


def test_a_real_joint_yields_one_detail_per_member_end_not_per_member():
    """Twenty slats seat identically, so twenty copies of one fact would be a
    list a client has to de-duplicate to read.

    M-SLAT@v2 has one end worth drawing: the slat's base, 15 mm into a 20 mm
    channel with 3 mm of insertion clearance, inside a 60 mm channel member.
    """
    from fenceai.fencemodel.demo import M_SLAT_V2

    elevation = elevation_of(M_SLAT_V2)
    assert len(by_slot(elevation, "slat")) > 5, "a lone slat pins little"
    assert len(elevation.details) == 1
    detail = elevation.details[0]
    assert (detail.key, detail.member_slot, detail.frame_slot, detail.end) == \
        ("slat@bottom_channel", "slat", "bottom_channel", "base")
    assert detail.kind == "channel"
    assert (detail.channel_depth_mm, detail.engagement_mm, detail.margin_mm) == \
        (20, 15, 3)
    assert detail.frame_thickness_mm == 60
    assert all(isinstance(mm, int) for mm in (
        detail.channel_depth_mm, detail.engagement_mm, detail.margin_mm,
        detail.frame_thickness_mm, detail.member_thickness_mm))


def test_a_butt_landing_and_a_member_with_no_refs_produce_no_detail():
    """M-SLAT@v2's slat ALSO lands on the top rail, and that end has no
    engagement and no channel — a section through it would be two rectangles
    touching, which is what the elevation already draws. M-SLAT@v1's slat names
    no frame slot at either end, so there is no second piece to cut through.
    """
    from fenceai.fencemodel.demo import M_SLAT_V2

    assert [d.frame_slot for d in elevation_of(M_SLAT_V2).details] == ["bottom_channel"]
    assert elevation_of(M_SLAT).details == []
    assert elevation_of(M_LEGACY).details == []


def test_a_detail_with_a_nominal_thickness_is_not_declared():
    """M-SLAT@v2's slat carries no `thickness_mm` — how thick the piece in the
    channel is, is product data nothing has authored — so the detail reports 0
    and flags itself, exactly as a frame member's face height does on the
    drawing. Declaring it is what makes the section measurable.
    """
    from fenceai.fencemodel.demo import M_SLAT_V2

    detail = elevation_of(M_SLAT_V2).details[0]
    assert detail.member_thickness_mm == 0 and detail.declared is False

    # How thick the piece is, is the PART's fact — the same move the face height
    # made — so declaring it means publishing a part that declares it, not writing
    # a number onto the panel that names one.
    thick = PartLibrary(parts=[
        p.model_copy(deep=True, update={
            "spec": [*p.spec, SpecField(key="thickness_mm", value=18, agree="==",
                                        unit="mm")]})
        if p.id == "infill-slat-100" else p
        for p in demo_parts()])
    measured = panel_elevation(
        resolve_panel(resolve_model_parts(M_SLAT_V2, thick)[0].default_spec, BAY),
        BAY.clear_width_mm, BAY.height_mm).details[0]
    assert measured.member_thickness_mm == 18 and measured.declared is True


def test_the_joint_fixtures_are_documents_the_loader_would_accept():
    """A test fixture that `validate_model` refuses proves the drawing works on a
    model nobody can save."""
    from fenceai.fencemodel.demo import M_SLAT_V2

    catalog = demo_catalog()
    assert validate_model(M_SLAT_V2, catalog) == []
    assert validate_model(top_seated_model(), catalog) == []


def test_the_details_are_deterministic():
    from fenceai.fencemodel.demo import M_SLAT_V2

    assert elevation_of(M_SLAT_V2) == elevation_of(M_SLAT_V2)


def test_the_preview_carries_the_joint_details_it_priced():
    """The detail rides on `PanelElevation`, so the panel tab and a stored bay
    get it from one code path — this is half of the proof, and
    `tests/report/test_structure.py` is the other half."""
    from fenceai.fencemodel.demo import M_SLAT_V2

    preview = preview_panel(M_SLAT_V2, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    assert [d.key for d in preview.elevation.details] == ["slat@bottom_channel"]
    assert preview.elevation.details[0].engagement_mm == 15
    slats = [m for m in preview.elevation.members if m.slot_key == "slat"]
    assert slats and all(
        (m.seat_start_mm, m.seat_end_mm) == (65, 80) for m in slats)


# --- the two-tier visualizer review -------------------------------------------

def test_a_member_drawn_unseated_is_given_no_section_to_be_seated_in():
    """MINOR 13. `_details` yielded from the spec fields alone, so a bay where
    `_between_frame_extent` resolved nothing — the refs invert at this height —
    drew the slat as a full-height rectangle with no seat while `details` still
    claimed a 20 mm channel with a 15 mm engagement, which the joint inset then
    dimensioned.

    Hand-derived at a 120 mm panel height: the channel sits 50 up, the top rail
    120 − 50 = 70 up, so the slat would start at 50 + 30 − 15 = 65 and end at
    70 − 20 = 50 — fifteen millimetres of nothing.
    """
    from fenceai.fencemodel.demo import M_SLAT_V2

    low = PanelContext(centre_width_mm=2500, clear_width_mm=2400, height_mm=120)
    panel = resolve_panel(SLAT_V2.default_spec, low)
    slat_slot = next(s for s in panel.slots if s.slot_key == "slat")
    assert slat_slot.length_unresolved and slat_slot.span_start_mm is None

    elevation = panel_elevation(panel, low.clear_width_mm, low.height_mm)
    drawn = by_slot(elevation, "slat")
    assert drawn, "the slats are still drawn — at the fallback full height"
    assert all((m.y_mm, m.h_mm) == (0, 120) for m in drawn)
    assert all(m.seat_start_mm is None and m.seat_end_mm is None for m in drawn)
    assert elevation.details == [], "nothing to cut a section through"


def test_the_clearance_against_the_post_is_the_fit_s_own_number():
    """MINOR 10. `PanelElevation` carried the fitted gaps but not the fitted edge
    margins, so a client dimensioning the clearance measured it off the drawn
    rectangles — deriving a fitted number from a picture of itself.

    Hand-derived over a 2400 mm opening of 100 mm slats with 20 mm gaps:
    12 * 100 + 11 * 20 would leave room for more, and 20 members with 19 gaps
    take 2000 + 380 = 2380, leaving 20 mm. M-SLAT spreads that into the gaps
    (`excess="space"`), so both margins are 0; justified `center` with the
    residual kept, the same 20 mm splits into 10 mm against each post.
    """
    spread = elevation_of(M_SLAT)
    assert len(by_slot(spread, "slat")) == 20
    assert (spread.edge_margin_start_mm, spread.edge_margin_end_mm) == (0, 0)
    assert spread.residual_mm == 0
    assert by_slot(spread, "slat")[0].x_mm == 0

    model = M_SLAT.model_copy(deep=True)
    model.default_spec.infill.justification = "center"
    model.default_spec.infill.excess = "truncate"
    centred = elevation_of(model)
    assert len(by_slot(centred, "slat")) == 20
    assert (centred.edge_margin_start_mm, centred.edge_margin_end_mm) == (10, 10)
    assert centred.residual_mm == 0
    assert centred.gaps_mm == [20] * 19, "the slack went to the ends, not the gaps"
    # the drawing agrees with the number, which is the point of reporting it
    slats = by_slot(centred, "slat")
    assert slats[0].x_mm == centred.edge_margin_start_mm
    assert (2400 - (slats[-1].x_mm + slats[-1].w_mm)
            == centred.edge_margin_end_mm + centred.residual_mm)


# --- the posts the bay stands between ----------------------------------------
#
# The panel spans the CLEAR OPENING, so the posts have never been on the
# drawing — which also means the two parts of a fence with no editor were the
# two parts with nowhere to click. They are handed in rather than derived: which
# post stands at each end is settled by the run, and a bay that worked its own
# posts out would be choosing them by a width they decide (resolve.py's cycle).


def _posts(width_mm=2400, face=90, height=1800):
    from fenceai.report.elevation import ElevationPost

    return [
        ElevationPost(side="start", kind="line", x_mm=-face, w_mm=face,
                      h_mm=height, sku="POST-V-1800", cap_sku="CAP-V-90",
                      cap_h_mm=40),
        ElevationPost(side="end", kind="corner", x_mm=width_mm, w_mm=face,
                      h_mm=height, sku="POST-V-1800", cap_sku="CAP-V-90",
                      cap_h_mm=40),
    ]


def test_a_drawing_with_no_run_behind_it_has_no_posts():
    """The honest answer for a model-scoped preview, and for every run stored
    before this existed. Inventing a post would draw a part nobody bought."""
    assert elevation_of(M_SLAT).posts == []


def test_the_start_post_sits_OUTSIDE_the_opening():
    """x is negative on the start side, and that is the whole contract: the post
    occupies the millimetres BEFORE the panel begins. A renderer that clamped it
    to zero would draw the post over the first board and shift the bay."""
    elevation = panel_elevation(resolve_panel(SLAT.default_spec, BAY),
                                BAY.clear_width_mm, BAY.height_mm,
                                posts=_posts(BAY.clear_width_mm))
    start = next(p for p in elevation.posts if p.side == "start")
    end = next(p for p in elevation.posts if p.side == "end")
    assert start.x_mm + start.w_mm == 0, "the start post ends where the panel begins"
    assert end.x_mm == BAY.clear_width_mm, "the end post begins where the panel ends"
    assert start.x_mm < 0


def test_the_posts_span_the_bay_at_its_centres():
    """Face to face across both posts is the centre-to-centre width the run was
    laid out at — the number the drawing must not disagree with."""
    elevation = panel_elevation(resolve_panel(SLAT.default_spec, BAY),
                                BAY.clear_width_mm, BAY.height_mm,
                                posts=_posts(BAY.clear_width_mm))
    start = next(p for p in elevation.posts if p.side == "start")
    end = next(p for p in elevation.posts if p.side == "end")
    drawn = (end.x_mm + end.w_mm) - start.x_mm
    assert drawn == BAY.clear_width_mm + 2 * start.w_mm


def test_a_post_carries_which_post_it_is():
    """`kind` is the fact a vinyl line is ordered by — end, line and corner posts
    are routed on different faces and are different SKUs. It rides on the
    drawing so the surface can name the part it is showing."""
    elevation = panel_elevation(resolve_panel(SLAT.default_spec, BAY),
                                BAY.clear_width_mm, BAY.height_mm,
                                posts=_posts(BAY.clear_width_mm))
    assert [p.kind for p in elevation.posts] == ["line", "corner"]
    assert all(p.cap_sku == "CAP-V-90" for p in elevation.posts)


def test_posts_do_not_disturb_anything_else_on_the_drawing():
    """The panel is unchanged by what stands beside it — the boards were fitted
    into the opening, and the opening did not move."""
    without = elevation_of(M_SLAT)
    with_posts = panel_elevation(resolve_panel(SLAT.default_spec, BAY),
                                 BAY.clear_width_mm, BAY.height_mm,
                                 posts=_posts(BAY.clear_width_mm))
    assert with_posts.members == without.members
    assert with_posts.gaps_mm == without.gaps_mm
    assert with_posts.fixings == without.fixings
