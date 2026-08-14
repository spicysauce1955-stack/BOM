"""`between_frame`: what a member is CUT to when it lands in a joint.

Every expected length below is derived by hand in the test that asserts it, from
the positions and thicknesses the fixture states, and written as a literal
integer. A test that recomputes the formula agrees with the implementation by
construction and would agree with a wrong one just as happily — and the number
this rule produces goes onto a cut list, where being self-consistent is not the
property anyone needs.
"""

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FrameSlot, FromBottom, FromTop,
    InfillSpec, Member, PanelSpec, PartRequirement,
)
from fenceai.fencemodel.resolve import PanelContext, resolve_panel

# One bay, stated once: 2500 c/c, 2400 clear, 1800 tall, level.
BAY = PanelContext(
    centre_width_mm=2500, clear_width_mm=2400, height_mm=1800,
    vertical="level", length_basis="width",
)


def _frame(key: str, placement, **kw) -> FrameSlot:
    return FrameSlot(
        key=key, orientation="horizontal", placement=placement,
        requirement=PartRequirement(
            role="rail", qty=1, length_rule="centre_to_centre",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),
        ),
        **kw,
    )


def _slat(**kw) -> Member:
    return Member(
        key="slat", width_mm=100, gap_after_mm=20,
        requirement=PartRequirement(
            role="infill", qty=1, length_rule="between_frame",
            eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")]),
        ),
        **kw,
    )


def _resolve(frame: list[FrameSlot], member: Member, ctx: PanelContext = BAY):
    spec = PanelSpec(frame=frame,
                     infill=InfillSpec(orientation="vertical", pattern=[member]))
    return {s.slot_key: s for s in resolve_panel(spec, ctx).slots}


# --- the arithmetic ----------------------------------------------------------

def test_a_slat_seated_at_both_ends_is_cut_to_the_opening_plus_its_engagements():
    """By hand, for the fixture below:

        bottom channel centreline  100   face height 60  ->  30 above centre
        top rail centreline       1700   face height 40  ->  20 below centre

        centre to centre   1700 - 100 = 1600
        face to face       1600 - (20 + 30) = 1550     the OPENING
        seated             1550 + 15 + 8 = 1573        the piece that is CUT

    1573 mm, and not one of the numbers standing next to it: the opening is
    1550, the panel height is 1800, and a member cut to either would be wrong in
    a way nobody sees until a slat is offered up to the fence.
    """
    by_key = _resolve(
        [_frame("bottom_channel", FromBottom(offset_mm=100), thickness_mm=60,
                joint="channel", channel_depth_mm=20, insertion_margin_mm=3),
         _frame("top_rail", FromTop(offset_mm=100), thickness_mm=40,
                joint="groove", channel_depth_mm=12, insertion_margin_mm=2)],
        _slat(base_ref="bottom_channel", top_ref="top_rail",
              joint="channel", base_engagement_mm=15, top_engagement_mm=8),
    )

    assert by_key["slat"].length_mm == 1573
    assert by_key["slat"].length_mm != BAY.height_mm


def test_the_engagements_are_the_only_difference_from_a_butt_joint():
    """The claim the whole wave rests on: the joint is not decoration, it is
    23 mm of steel. Same frame, same panel, one member butted and one seated —
    1550 against 1573.
    """
    frame = [_frame("bottom_channel", FromBottom(offset_mm=100), thickness_mm=60,
                    joint="channel", channel_depth_mm=20, insertion_margin_mm=3),
             _frame("top_rail", FromTop(offset_mm=100), thickness_mm=40,
                    joint="groove", channel_depth_mm=12, insertion_margin_mm=2)]
    butted = _resolve(frame, _slat(base_ref="bottom_channel", top_ref="top_rail"))
    seated = _resolve(frame, _slat(base_ref="bottom_channel", top_ref="top_rail",
                                   joint="channel", base_engagement_mm=15,
                                   top_engagement_mm=8))

    assert butted["slat"].length_mm == 1550
    assert seated["slat"].length_mm == 1573


def test_an_odd_face_height_rounds_down_at_each_half_and_nowhere_else():
    """Two odd thicknesses, so both halves round:

        centre to centre   1700 - 100 = 1600
        halves             45 // 2 = 22   and   25 // 2 = 12
        face to face       1600 - 34 = 1566

    Not 1565 (which is what halving the SUM, 70 // 2 = 35, would give). The
    difference is one millimetre on every slat of every bay, and the rounding is
    integer division per member because that is what a face is measured from —
    floats at rest are forbidden (ADR-0002), and a member's own half is the only
    place a half exists.
    """
    by_key = _resolve(
        [_frame("bottom_rail", FromBottom(offset_mm=100), thickness_mm=45),
         _frame("top_rail", FromTop(offset_mm=100), thickness_mm=25)],
        _slat(base_ref="bottom_rail", top_ref="top_rail"),
    )

    assert by_key["slat"].length_mm == 1566
    assert isinstance(by_key["slat"].length_mm, int)


def test_an_undeclared_face_height_corrects_nothing_rather_than_guessing():
    """`thickness_mm=0` means undeclared, and the elevation already reports such
    a member as `declared=False`. So the correction it contributes is 0 and the
    length is the plain centre-to-centre 1600 — a number an author can look at
    and see the missing thickness in, where a nominal 40 mm would have produced
    1580: measured-looking, and wrong.
    """
    by_key = _resolve(
        [_frame("bottom_rail", FromBottom(offset_mm=100)),
         _frame("top_rail", FromTop(offset_mm=100))],
        _slat(base_ref="bottom_rail", top_ref="top_rail"),
    )

    assert by_key["slat"].length_mm == 1600


def test_between_two_distributed_rails_it_is_the_lowest_and_the_highest():
    """One `Distributed` slot at both ends — "between the rails" of a three-rail
    ladder, which is what an author naming one slot twice is asking for.

        three rails over 1800, no insets   ->   0, 900, 1800
        outermost pair                     ->   1800 - 0 = 1800
        halves of a 50 mm rail             ->   1800 - (25 + 25) = 1750
        seated 15 into each channel        ->   1750 + 30 = 1780

    1780, and the mid rail at 900 contributes nothing. Had the top ref taken the
    FIRST position instead of the highest, the answer would have been 30 — a
    slat a fiftieth of its true length, on every bay.
    """
    by_key = _resolve(
        [_frame("rail", Distributed(count=3), thickness_mm=50,
                joint="channel", channel_depth_mm=20, insertion_margin_mm=2)],
        _slat(base_ref="rail", top_ref="rail", joint="channel",
              base_engagement_mm=15, top_engagement_mm=15),
    )

    assert by_key["rail"].positions_mm == [0, 900, 1800]
    assert by_key["slat"].length_mm == 1780


def test_a_raked_bay_does_not_stretch_a_between_frame_member():
    """The slope factor corrects a HORIZONTAL member for running along the grade.
    `between_frame` measures a VERTICAL distance between two frame members that
    slope together, so it keeps its length exactly as `panel_height` does — while
    the rail beside it follows the grade to 2600.
    """
    raked = BAY.model_copy(update={
        "vertical": "raked", "length_basis": "slope", "slope_len_mm": 2600})
    by_key = _resolve(
        [_frame("bottom_channel", FromBottom(offset_mm=100), thickness_mm=60,
                joint="channel", channel_depth_mm=20, insertion_margin_mm=3),
         _frame("top_rail", FromTop(offset_mm=100), thickness_mm=40)],
        _slat(base_ref="bottom_channel", top_ref="top_rail", joint="channel",
              base_engagement_mm=15),
        raked,
    )

    assert by_key["slat"].length_mm == 1565     # 1600 - (20 + 30) + 15
    assert by_key["top_rail"].length_mm == 2600, "the rail still follows the grade"


def test_a_knowledge_param_that_empties_the_referenced_rail_set_cuts_nothing():
    """`rails_per_span=0` leaves the slot with no placed member, so there is
    nothing in this bay to measure between. The panel reports no cut length
    rather than substituting the panel height: a length measured between things
    that are not there would reach the cut planner as an ordinary integer.
    """
    ctx = BAY.model_copy(update={"params": {"rails_per_span": 0}})
    by_key = _resolve(
        [_frame("rail", Distributed(count=2, count_param="rails_per_span"),
                thickness_mm=50)],
        _slat(base_ref="rail", top_ref="rail"),
        ctx,
    )

    assert by_key["rail"].positions_mm == []
    assert by_key["slat"].length_mm is None


def test_resolution_stays_deterministic_with_a_joint_in_the_panel():
    spec = PanelSpec(
        frame=[_frame("bottom_channel", FromBottom(offset_mm=100), thickness_mm=60,
                      joint="channel", channel_depth_mm=20),
               _frame("top_rail", FromTop(offset_mm=100), thickness_mm=40)],
        infill=InfillSpec(orientation="vertical", pattern=[
            _slat(base_ref="bottom_channel", top_ref="top_rail",
                  joint="channel", base_engagement_mm=15)]),
    )
    assert resolve_panel(spec, BAY) == resolve_panel(spec, BAY)
