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


class ElevationFixing(BaseModel):
    """Where one fixing rule's fasteners land, in panel coordinates.

    A PLACE, never a screw: `qty` is `qty_per_basis` times the number of parts
    this place stands for — a figure the resolver DECIDED, never a share of the
    slot's total spread over whatever places happened to be found. Anything the
    drawing cannot place lands on `PanelElevation.fixings_unplaced` instead, so
    a slot's places plus its unplaced count come to exactly its `qty`.

    That is why this is derived here rather than drawn by the client: a dot count
    worked out in the browser would eventually say twelve beside a BOM line
    buying eight, on the one surface built so an author can see what
    `per_member_crossing` does.

    "A dot per screw would bury the panel" still holds, and this is not that: a
    panel taking 96 screws is 32 places reading ×3.
    """

    slot_key: str
    role: str
    basis: str
    index: int
    x_mm: Mm
    y_mm: Mm
    qty: int


class ElevationPost(BaseModel):
    """A post flanking the bay, and the cap on top of it.

    NOT part of the panel, and that is why the drawing has never had one: the
    panel spans the CLEAR OPENING between two posts, because that is what the
    boards are fitted into. The posts stand outside it.

    They are handed IN rather than derived here, and the reason is the cycle
    rule `resolve.py` is built around — a bay's opening is measured to the post
    faces, so a bay that worked out its own posts would be choosing them by a
    width they decide. Which post stands at each end is settled by the RUN, and
    the caller that knows the run passes it.

    `x_mm` is in panel coordinates, so the start post's is NEGATIVE: it occupies
    the millimetres before the opening begins. A client that clamps it to zero
    draws the post inside the panel and every board a post-width to the right.
    """

    side: Literal["start", "end"]
    kind: str = ""                 # end | line | corner | gate — from the run
    x_mm: Mm                       # negative on the start side (outside the opening)
    y_mm: Mm = 0
    w_mm: Mm                       # the post's face width
    h_mm: Mm
    sku: str = ""
    # `declared=False` says the size is a NOMINAL the read model invented rather
    # than product data, exactly as a rail's face height already does.
    declared: bool = True
    cap_sku: str = ""
    cap_h_mm: Mm = 0
    # The post's FACE is product data; a cap's height is not — the catalog does
    # not carry one. Two flags rather than one, because collapsing them would
    # either call a measured face invented or call an invented cap measured, and
    # this drawing's whole contract is that it says which of the two a size is.
    cap_declared: bool = True


class UnplacedFixing(BaseModel):
    """Fasteners this bay buys that the drawing cannot put anywhere.

    `per_member_crossing` is counted arithmetically — members x frame members —
    so a panel with vertical stiles beside vertical slats is counted for
    crossings that do not exist. The drawing can only mark the crossings that
    are there, and the honest answer to the rest is to say how many were left
    over, not to fold them into the ones that are (foundation §15: represent
    unknowns instead of fabricating certainty).

    A slot appears here only when something is left: an empty list is a panel
    whose fixings are entirely accounted for on the drawing.
    """

    slot_key: str
    role: str
    basis: str
    qty: int


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
    # ... and the two ends of the same fit: how much clear axis is left between
    # the opening's edge and the first (last) member. Reported because they were
    # DECIDED — `justification` folds the residual into them, so `center` puts
    # the whole slack against the posts — and a client measuring them off the
    # drawn rectangles instead was deriving a fitted number from a picture of
    # itself (review finding 10).
    #
    # `residual_mm` is the axis nobody claimed: `start`/`spread_to_fit` leave it
    # beyond the end margin, so the real clear distance at the far end is
    # `edge_margin_end_mm + residual_mm` — the same sum `FitResult.openings_mm`
    # makes, and the reason it travels beside them rather than being folded in
    # here, where it would stop being the fit's own number.
    edge_margin_start_mm: Mm = 0
    edge_margin_end_mm: Mm = 0
    residual_mm: Mm = 0
    # the joints worth drawing, riding on the elevation rather than on an endpoint
    # of their own — so the panel preview and a stored run's `Bay.elevation` carry
    # them by the same code path, and the detail beside a panel cannot say
    # something different from the detail beside the bay built to it.
    details: list[JointDetail] = []
    # where the fasteners land, with a DECIDED count on each place. Empty for a
    # panel with no fixing rule, and for a run stored before the basis rode on
    # the slot.
    fixings: list[ElevationFixing] = []
    # ... and the ones no place could be found for. Per fixing slot,
    # `sum(place.qty) + unplaced.qty == slot.qty` exactly, for every basis and
    # every geometry — which is what stops the drawing from ever stating a
    # different number of fasteners from the BOM line beside it.
    fixings_unplaced: list[UnplacedFixing] = []
    # the posts this bay stands between, when the caller knows them. Empty is
    # the honest answer for a model-scoped drawing with no run behind it — and
    # for every stored run generated before this existed.
    posts: list[ElevationPost] = []


def panel_elevation(
    panel: ResolvedPanel,
    width_mm: Mm,
    height_mm: Mm,
    span_id: str = "",
    bay_tag: str = "",
    posts: "list[ElevationPost] | None" = None,
) -> PanelElevation:
    out = PanelElevation(
        span_id=span_id, bay_tag=bay_tag, model_ref=panel.model_ref,
        width_mm=width_mm, height_mm=height_mm,
        posts=list(posts or []),
    )
    nominal = max(1, (min(width_mm, height_mm) * NOMINAL_THICKNESS_PERMILLE) // 1000)

    # every infill slot of one panel carries the SAME `FitResult` — one fit is
    # run across the pattern and handed to each member of it — so the fitted
    # numbers are read from the first slot that has one and never re-read
    fitted = False
    for slot in panel.slots:
        if slot.fit is not None:
            out.members.extend(_infill(slot, width_mm, height_mm, nominal))
            if not fitted:
                fitted = True
                out.gaps_mm = list(slot.fit.gaps_mm)
                out.edge_margin_start_mm = slot.fit.edge_margin_start_mm
                out.edge_margin_end_mm = slot.fit.edge_margin_end_mm
                out.residual_mm = slot.fit.residual_mm
        elif slot.positions_mm:
            out.members.extend(_frame(slot, width_mm, height_mm, nominal))
        # a slot with neither — a fixing — has no extent of its own to draw:
        # screws are counted, not drawn, and a dot per screw would bury the
        # panel. Where they LAND is a place with a count on it, below.
    out.details = list(_details(panel))
    out.fixings, out.fixings_unplaced = _fixings(
        panel, out.members, width_mm, height_mm)
    return out


def _fixings(panel: ResolvedPanel, members: list[ElevationMember],
             width_mm: Mm, height_mm: Mm):
    """The fastener places of every fixing slot, and what could not be placed.

    Each place carries a DECIDED count — `qty_per_basis` times the number of
    parts that place stands for — never a share of the slot's total spread over
    whatever places happened to be found. The difference matters, and it is the
    whole reason `qty_per_basis` rides on the slot:

      `per_member_crossing` counts crossings ARITHMETICALLY (members x frame
      members, `resolve.py`), which on a panel with vertical stiles beside
      vertical slats counts pairs that never meet. The drawing can only place
      the crossings that are THERE. Apportioning the arithmetic total across
      those would put a plausible "x2" on real crossings to absorb pairs that do
      not exist — a number nothing decided, on the one surface built to explain
      what the basis does.

    So the fasteners a place cannot be found for are REPORTED (foundation §15:
    represent unknowns instead of fabricating certainty), and the sum over a
    slot's places plus its unplaced count is exactly the slot's `qty` — by
    construction, for every basis and every geometry.

    Nothing is recomputed: the places are read off the rectangles this same
    function has already placed.
    """
    frame = [m for m in members if m.kind == "frame"]
    infill = sorted((m for m in members if m.kind == "infill"),
                    key=lambda m: (m.x_mm, m.y_mm))
    parts = _parts_per_rect(panel, members)
    placed: list[ElevationFixing] = []
    unplaced: list[UnplacedFixing] = []
    for slot in panel.slots:
        if slot.slot_kind != "fixing" or not slot.basis or not slot.qty_per_basis:
            continue
        drawn = 0
        for index, (x, y, weight) in enumerate(
                _places(slot.basis, frame, infill, width_mm, height_mm, parts)):
            qty = slot.qty_per_basis * weight
            if qty <= 0:
                continue      # a place holding no fastener is not a place
            drawn += qty
            placed.append(ElevationFixing(
                slot_key=slot.slot_key, role=slot.role, basis=slot.basis,
                index=index, x_mm=x, y_mm=y, qty=qty,
            ))
        if slot.qty - drawn > 0:
            unplaced.append(UnplacedFixing(
                slot_key=slot.slot_key, role=slot.role, basis=slot.basis,
                qty=slot.qty - drawn,
            ))
    return placed, unplaced


def _parts_per_rect(panel: ResolvedPanel, members: list[ElevationMember]) -> dict:
    """How many physical pieces each drawn rectangle stands for.

    A slot with `qty=2` is two pieces at one position — a batten pair, a board
    front and back — and the elevation draws ONE rectangle for them. The bases
    that count PARTS (`per_member`, `per_frame_member`, and the crossings between
    them) must therefore weight a place by what stands there, or a panel whose
    rails come in pairs would draw half its fixings and report the other half
    unplaceable. The bases that count POSITIONS (`per_end_member`, `per_gap`)
    weight 1, because that is what the resolver counted.

    Keyed by `(slot_key, index)` — the pair that names a rectangle on the wire.
    """
    counts: dict[str, int] = {}
    for m in members:
        counts[m.slot_key] = counts.get(m.slot_key, 0) + 1
    per_slot = {
        slot.slot_key: max(1, slot.qty // counts[slot.slot_key])
        for slot in panel.slots
        if slot.slot_kind in ("frame", "infill") and counts.get(slot.slot_key)
    }
    return {(m.slot_key, m.index): per_slot.get(m.slot_key, 1) for m in members}


def _places(basis: str, frame: list[ElevationMember], infill: list[ElevationMember],
            width_mm: Mm, height_mm: Mm, parts: dict):
    """Where one basis puts its fasteners: (x, y, weight) in panel coordinates.

    The infill list arrives sorted along the axis it was fitted on, which is
    what makes `per_gap` read across a vertical pattern and up a horizontal one
    without either being special-cased.
    """
    def centre(m: ElevationMember) -> tuple[Mm, Mm]:
        return (m.x_mm + m.w_mm // 2, m.y_mm + m.h_mm // 2)

    def weight(m: ElevationMember) -> int:
        return parts.get((m.slot_key, m.index), 1)

    if basis == "per_panel":
        return [(width_mm // 2, height_mm // 2, 1)]
    if basis == "per_frame_member":
        return [(*centre(m), weight(m)) for m in frame]
    if basis == "per_member":
        return [(*centre(m), weight(m)) for m in infill]
    if basis == "per_end_member":
        # first and last ALONG THE AXIS — a placement question, so one each, and
        # one member is one end rather than two
        ends = [infill[0]] if len(infill) == 1 else infill[:1] + infill[-1:]
        return [(*centre(m), 1) for m in ends]
    if basis == "per_gap":
        return [((a.x_mm + a.w_mm + b.x_mm) // 2,
                 (a.y_mm + a.h_mm + b.y_mm) // 2, 1)
                for a, b in zip(infill, infill[1:])]
    if basis == "per_member_crossing":
        return [(*place, weight(m) * weight(f))
                for m in infill for f in frame
                if (place := _overlap_centre(m, f)) is not None]
    return []


def _overlap_centre(a: ElevationMember, b: ElevationMember) -> tuple[Mm, Mm] | None:
    """Where two drawn members cross, or None when they do not touch.

    A crossing that is not on the drawing is not a place to put a screw: a slat
    seated between two rails crosses both, one stopping short of the top rail
    crosses one, and two parallel members cross nowhere at all. The last case is
    not hypothetical — `resolve.py` counts crossings as members x frame members,
    so a panel with vertical stiles beside vertical slats is counted for
    crossings that do not exist. They come back as UNPLACED rather than as a
    heavier count on the crossings that do.
    """
    x0, x1 = max(a.x_mm, b.x_mm), min(a.x_mm + a.w_mm, b.x_mm + b.w_mm)
    y0, y1 = max(a.y_mm, b.y_mm), min(a.y_mm + a.h_mm, b.y_mm + b.h_mm)
    if x1 < x0 or y1 < y0:
        return None
    return ((x0 + x1) // 2, (y0 + y1) // 2)


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

    And a third, which is about THIS bay rather than about the model: a member
    whose extent never resolved. `_between_frame_extent` returns nothing when a
    `count_param` collapses the referenced set or the refs invert at this bay's
    height, and `_rect` then draws the member across the whole opening with no
    seat. A detail beside that rectangle would dimension a 20 mm channel and a
    15 mm engagement into a member the drawing shows sitting in neither (review
    finding 13). The bay says so through the `panel_length_unresolved` warning,
    which is a sentence rather than a section.
    """
    frame = {slot.slot_key: slot for slot in panel.slots if slot.slot_kind == "frame"}
    for slot in panel.slots:
        if slot.length_unresolved or slot.span_start_mm is None:
            continue
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
