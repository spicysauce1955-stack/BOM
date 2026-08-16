"""The panel, drawn: rectangles in the panel's own frame.

A pure function of a `ResolvedPanel` and the bay it was resolved into, so it
stays a derived read model (foundation §15) — nothing here is stored, and the
picture cannot drift from the numbers because both come from the same slots.

Served from the SERVER rather than mirrored in JS. The codebase has mirrored
maths across that boundary before (`geom.anchorFor` mirrors `make_anchor`), but
that is a two-line formula; this is a fit algorithm with a justification x excess
matrix behind it. One implementation, one set of tests.

Coordinates follow the fence-model spec: **x runs 0 -> clear width, y runs
0 -> panel height, origin at the bottom-left of the OPENING**. y = 0 is the panel
bottom, not the ground — height intent stays ground-to-top, so a future ground
clearance reduces the panel and never moves the top line.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.fencemodel.resolve import ResolvedPanel, ResolvedSlot

# What a member with no declared face height is drawn as, as a permille of the
# panel's short side. A `FrameSlot` carries no thickness — a rail's face height
# is product data (`attrs.face_width_mm`) that the catalog does not hold yet — so
# rather than invent a millimetre value and have it read as measured, the read
# model reports `declared=False` and the renderer draws a nominal band. The
# fitted things on this drawing (slat widths, gap sizes, rail heights) are all
# real; this one is explicitly not, and says so.
NOMINAL_THICKNESS_PERMILLE = 40


class ElevationMember(BaseModel):
    """One drawn rectangle, in panel coordinates."""

    slot_key: str
    role: str
    index: int                     # which of this slot's N members
    x_mm: Mm
    y_mm: Mm
    w_mm: Mm
    h_mm: Mm
    declared: bool = True          # False = h_mm (or w_mm) is a nominal, not data
    kind: str = ""                 # frame | infill — which half of the panel drew it
    face: Literal["front", "back"] = "front"
    # how far off the panel's face this member sits (+ front, - back). `face`
    # alone says which side; a shadowbox has a DEPTH, and a client that can only
    # order two layers cannot draw one at its real offset.
    face_offset_mm: int = 0
    sku: str = ""
    joint: str = "butt"            # how this member meets the one it lands on
    # the sub-range of this member, along its OWN axis and in the same panel
    # coordinates as the rectangle, that is inside a frame member rather than
    # seen. `None` when the member seats into nothing — which is every member of
    # every model that does not declare `between_frame`, so a renderer drawing
    # hatching on the presence of these two fields draws none for them.
    seat_start_mm: Mm | None = None
    seat_end_mm: Mm | None = None


class JointDetail(BaseModel):
    """One end of one member, where it lands — the numbers a section is drawn from.

    Per (member slot, end) rather than per drawn rectangle: every slat of a slot
    seats identically, so twenty details for twenty slats would be twenty copies
    of one fact and a client comparing them for differences would find none.
    `member_slot` says which rectangles it applies to.

    Nothing here is computed. Every field was decided during resolution and is
    reported — the read model must never recompute a quantity (foundation §15),
    and the engagement on this detail is the same integer that already shortened
    the member on the cut list.
    """

    # "<member_slot>@<frame_slot>", as the design declares it. It is not unique
    # by itself for the one shape that can repeat the pair: a member naming the
    # same rail SET at both ends, which `_between_frame_extent` supports on
    # purpose (bottom rail to top rail of one `Distributed` slot). A client
    # selecting a detail therefore keys on `end` beside it.
    key: str
    member_slot: str
    frame_slot: str
    end: Literal["base", "top"]
    # the MEMBER's kind — "how a member meets the one it lands on", which is what
    # `JointKind` is defined as. The receiving slot's own kind describes its
    # housing, and the housing is on this detail as the numbers a section can be
    # drawn from (`channel_depth_mm`, `margin_mm`) rather than as a second word.
    kind: str
    member_thickness_mm: Mm        # 0 = undeclared (a nominal), as elsewhere
    frame_thickness_mm: Mm
    channel_depth_mm: Mm
    engagement_mm: Mm
    margin_mm: Mm
    declared: bool


class PanelElevation(BaseModel):
    span_id: str = ""
    bay_tag: str = ""
    model_ref: str = ""
    width_mm: Mm = 0               # the opening: what the drawing spans
    height_mm: Mm = 0
    members: list[ElevationMember] = []
    # the fitted gaps, clear (face to face) — the number the sphere test measures
    # and the reason `fit_pattern` returns a LIST rather than one rounded value
    gaps_mm: list[Mm] = []
    # the joints worth drawing, riding on the elevation rather than on an endpoint
    # of their own — so the panel preview and a stored run's `Bay.elevation` carry
    # them by the same code path, and the detail beside a panel cannot say
    # something different from the detail beside the bay built to it.
    details: list[JointDetail] = []


def panel_elevation(
    panel: ResolvedPanel,
    width_mm: Mm,
    height_mm: Mm,
    span_id: str = "",
    bay_tag: str = "",
) -> PanelElevation:
    out = PanelElevation(
        span_id=span_id, bay_tag=bay_tag, model_ref=panel.model_ref,
        width_mm=width_mm, height_mm=height_mm,
    )
    nominal = max(1, (min(width_mm, height_mm) * NOMINAL_THICKNESS_PERMILLE) // 1000)

    for slot in panel.slots:
        if slot.fit is not None:
            out.members.extend(_infill(slot, width_mm, height_mm, nominal))
            if not out.gaps_mm:
                out.gaps_mm = list(slot.fit.gaps_mm)
        elif slot.positions_mm:
            out.members.extend(_frame(slot, width_mm, height_mm, nominal))
        # a slot with neither — a fixing — has no extent of its own to draw:
        # screws are counted, not drawn, and a dot per screw would bury the panel
    out.details = list(_details(panel))
    return out


def _details(panel: ResolvedPanel):
    """The joints this panel has, one per member end that is worth a section.

    Two ways to have nothing to draw, and both produce no detail rather than an
    empty drawing:

      * a member naming no frame slot at that end — there is no second piece for
        a section to cut through, and the length rule that reads the refs is the
        only one that gives a member an end at all;
      * a butt landing: no engagement AND no channel. The section would be two
        rectangles touching, which is what every member on the elevation already
        looks like, so the inset would add a frame around a fact the panel drawing
        states better.

    A ref naming a slot this panel does not have is likewise silent. It is
    refused at load (`validate_model`), so reaching here means an unvalidated
    document, and inventing a receiving member for it would put a dimension on a
    drawing with nothing to measure it from.
    """
    frame = {slot.slot_key: slot for slot in panel.slots if slot.slot_kind == "frame"}
    for slot in panel.slots:
        for end, ref, engagement in (
            ("base", slot.base_ref, slot.base_engagement_mm),
            ("top", slot.top_ref, slot.top_engagement_mm),
        ):
            target = frame.get(ref or "")
            if target is None or not (engagement or target.channel_depth_mm):
                continue
            yield JointDetail(
                key=f"{slot.slot_key}@{target.slot_key}",
                member_slot=slot.slot_key, frame_slot=target.slot_key,
                end=end, kind=slot.joint,
                # An undeclared thickness reports 0 and says so, exactly as a
                # frame member's face height does on the drawing above: a section
                # is a dimensioned thing, and a nominal in one of its dimensions
                # would read as measured beside four numbers that are.
                member_thickness_mm=slot.thickness_mm or 0,
                frame_thickness_mm=target.thickness_mm or 0,
                declared=slot.thickness_mm is not None and target.thickness_mm is not None,
                channel_depth_mm=target.channel_depth_mm,
                engagement_mm=engagement,
                margin_mm=target.insertion_margin_mm,
            )


def _frame(slot: ResolvedSlot, width_mm: Mm, height_mm: Mm, nominal: Mm):
    declared = slot.thickness_mm is not None
    thickness = slot.thickness_mm or nominal
    for index, position in enumerate(slot.positions_mm):
        if slot.orientation == "vertical":
            # centred on its position, and clamped inside the opening so a member
            # placed at 0 or at the full width still reads as inside the panel
            x = _clamp(position - thickness // 2, 0, max(width_mm - thickness, 0))
            yield ElevationMember(
                slot_key=slot.slot_key, role=slot.role, index=index,
                x_mm=x, y_mm=0, w_mm=thickness, h_mm=height_mm,
                declared=declared, kind="frame", sku=slot.sku, joint=slot.joint,
            )
        else:
            y = _clamp(position - thickness // 2, 0, max(height_mm - thickness, 0))
            yield ElevationMember(
                slot_key=slot.slot_key, role=slot.role, index=index,
                x_mm=0, y_mm=y, w_mm=width_mm, h_mm=thickness,
                declared=declared, kind="frame", sku=slot.sku, joint=slot.joint,
            )


def _infill(slot: ResolvedSlot, width_mm: Mm, height_mm: Mm, nominal: Mm):
    """Walk the fitted sequence and hand back only THIS member's rectangles.

    The walk covers every placed member of the pattern, not only this slot's,
    because a position depends on everything before it — a two-member pattern's
    second slat sits where it does because of the first one's width and gap.
    """
    fit = slot.fit
    assert fit is not None
    cycle = slot.cycle_widths_mm or [slot.member_width_mm or nominal]
    cursor = fit.edge_margin_start_mm
    for i in range(fit.count):
        member_width = cycle[i % len(cycle)]
        if i % len(cycle) == slot.pattern_index:
            yield _rect(slot, i, cursor, member_width, width_mm, height_mm)
        cursor += member_width + (fit.gaps_mm[i] if i < len(fit.gaps_mm) else 0)


def _rect(slot, i, cursor, member_width, width_mm, height_mm) -> ElevationMember:
    face = "back" if slot.face_offset_mm < 0 else "front"
    # A member spans the whole opening unless the resolver said where it starts
    # and stops. `between_frame` does: a slat seated 15 mm into a bottom channel
    # and stopping under a top rail is 135 mm shorter than the bay, and drawing
    # it full height would put the piece the BOM buys and the piece on the
    # drawing 135 mm apart — on the very model whose reason to exist is that
    # 135 mm. Both come from one calculation in `_between_frame_extent`.
    start, extent = 0, height_mm if slot.orientation == "vertical" else width_mm
    seat_start, seat_end = None, None
    if slot.span_start_mm is not None and slot.length_mm is not None:
        start, extent = slot.span_start_mm, slot.length_mm
        seat_start, seat_end = _seat(slot, start, extent)
    if slot.orientation == "vertical":
        return ElevationMember(
            slot_key=slot.slot_key, role=slot.role, index=i,
            x_mm=cursor, y_mm=start, w_mm=member_width, h_mm=extent,
            kind="infill", face=face, face_offset_mm=slot.face_offset_mm,
            sku=slot.sku, joint=slot.joint,
            seat_start_mm=seat_start, seat_end_mm=seat_end,
        )
    return ElevationMember(
        slot_key=slot.slot_key, role=slot.role, index=i,
        x_mm=start, y_mm=cursor, w_mm=extent, h_mm=member_width,
        kind="infill", face=face, face_offset_mm=slot.face_offset_mm,
        sku=slot.sku, joint=slot.joint,
        seat_start_mm=seat_start, seat_end_mm=seat_end,
    )


def _seat(slot: ResolvedSlot, start: Mm, extent: Mm) -> tuple[Mm | None, Mm | None]:
    """Which part of this member is buried, given where it starts and how long
    it is.

    Read off the SAME `(start, extent)` the rectangle is drawn from — the
    resolver's one calculation, already spent — rather than re-derived from the
    frame positions. A second derivation of the extent is how the hatched band
    and the piece it is hatching end up a millimetre apart, which is exactly the
    drift `_between_frame_extent` exists to prevent. Called only where the
    resolver fixed an extent, so a member drawn at its fallback full height is
    never hatched against a length this bay never resolved.

    A member CAN seat at both ends, and one range cannot say so without claiming
    the middle is buried too. So the pair names the base seat where there is one
    and the top seat otherwise, and a member engaged at both ends states both
    ends exactly on `details`, which is per-end by construction. The drawing then
    under-hatches: a band that is missing is a smaller lie than a band drawn
    through solid timber.
    """
    if slot.base_engagement_mm:
        return start, start + slot.base_engagement_mm
    if slot.top_engagement_mm:
        return start + extent - slot.top_engagement_mm, start + extent
    return None, None


def _clamp(value: Mm, low: Mm, high: Mm) -> Mm:
    return max(low, min(value, high))
