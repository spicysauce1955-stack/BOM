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
    face: Literal["front", "back"] = "front"
    sku: str = ""


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
    return out


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
                declared=declared, sku=slot.sku,
            )
        else:
            y = _clamp(position - thickness // 2, 0, max(height_mm - thickness, 0))
            yield ElevationMember(
                slot_key=slot.slot_key, role=slot.role, index=index,
                x_mm=0, y_mm=y, w_mm=width_mm, h_mm=thickness,
                declared=declared, sku=slot.sku,
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
    if slot.orientation == "vertical":
        return ElevationMember(
            slot_key=slot.slot_key, role=slot.role, index=i,
            x_mm=cursor, y_mm=0, w_mm=member_width, h_mm=height_mm,
            face=face, sku=slot.sku,
        )
    return ElevationMember(
        slot_key=slot.slot_key, role=slot.role, index=i,
        x_mm=0, y_mm=cursor, w_mm=width_mm, h_mm=member_width,
        face=face, sku=slot.sku,
    )


def _clamp(value: Mm, low: Mm, high: Mm) -> Mm:
    return max(low, min(value, high))
