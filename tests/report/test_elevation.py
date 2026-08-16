"""The panel as rectangles.

The governing property is that the drawing is DERIVED from the same slots the
BOM is derived from, so the picture and the numbers cannot disagree. Everything
fitted on it — slat widths, gap sizes, rail heights — is real data; the one
nominal (a frame member's face height, which the catalog does not carry) is
flagged as such rather than passed off as measured.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT
from fenceai.fencemodel.model import (
    Distributed, FromBottom, FromTop, Fraction, validate_model,
)
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.fencemodel.resolve import PanelContext, placement_positions, resolve_panel
from fenceai.report.elevation import panel_elevation

BAY = PanelContext(centre_width_mm=2500, clear_width_mm=2400, height_mm=1800)


def elevation_of(model, ctx=BAY):
    return panel_elevation(resolve_panel(model.default_spec, ctx),
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
    resolved = next(s for s in resolve_panel(M_SLAT.default_spec, BAY).slots
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
    """A dot per screw would bury the panel it is fixing."""
    assert by_slot(elevation_of(M_SLAT), "screw") == []


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
                            demo_catalog())
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

    panel = resolve_panel(M_SLAT_V2.default_spec, BAY)
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
    from fenceai.fencemodel.demo import M_SLAT_V2

    model = M_SLAT_V2.model_copy(deep=True)
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

    model = M_SLAT_V2.model_copy(deep=True)
    model.default_spec.infill.pattern[0].thickness_mm = 18
    measured = elevation_of(model).details[0]
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
                            demo_catalog())
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
    panel = resolve_panel(M_SLAT_V2.default_spec, low)
    slat_slot = next(s for s in panel.slots if s.slot_key == "slat")
    assert slat_slot.length_unresolved and slat_slot.span_start_mm is None

    elevation = panel_elevation(panel, low.clear_width_mm, low.height_mm)
    drawn = by_slot(elevation, "slat")
    assert drawn, "the slats are still drawn — at the fallback full height"
    assert all((m.y_mm, m.h_mm) == (0, 120) for m in drawn)
    assert all(m.seat_start_mm is None and m.seat_end_mm is None for m in drawn)
    assert elevation.details == [], "nothing to cut a section through"


