"""Resolving a PanelSpec against one span (fence-model spec §resolve_panel).

Pure and deterministic, and it takes NO knowledge access: every param it needs
was resolved during generation and arrives on the context, exactly as
Span.rail_count does today.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.fencemodel.fit import FitResult, fit_pattern
from fenceai.fencemodel.model import (
    Distributed, Eligibility, FenceModel, Fraction, FromBottom, FromTop,
    HeightSupport, Member, PanelSpec, PartRequirement,
)
from fenceai.knowledge.ast import MissingField, evaluate_expr


class PanelContext(BaseModel):
    """Everything a panel needs to know about the bay it is being laid into."""

    centre_width_mm: Mm
    clear_width_mm: Mm
    height_mm: Mm
    vertical: str = "level"
    length_basis: str = "width"      # "width" | "slope" — from the span
    slope_len_mm: Mm | None = None
    params: dict[str, int] = {}      # knowledge-resolved: rails_per_span, ...
    options: dict[str, str | int] = {}

    def condition_ctx(self) -> dict:
        return {"panel": {
            "width_mm": self.centre_width_mm, "height_mm": self.height_mm,
            "vertical": self.vertical,
        }}


class ResolvedSlot(BaseModel):
    slot_key: str
    role: str
    qty: int
    length_mm: Mm | None = None
    length_basis: str | None = None
    # This slot declares a length rule and the rule produced no length in THIS
    # bay. Recorded rather than left as a bare `length_mm is None`, which a
    # fixing and a cap share and mean nothing by: a divisible product asked for
    # with no cut length plans no bars, so the panel would price that member at
    # zero and the parts ledger would read the gap as demand covered from stock —
    # a panel that silently costs nothing rather than one that visibly costs the
    # wrong amount. `validate_model` closes that at authoring for the rules it
    # can; `between_frame` depends on the bay, so the generator warns instead.
    length_unresolved: bool = False
    sku: str = ""                    # resolved by fulfillment, never here
    eligibility: Eligibility = Eligibility()
    fit: FitResult | None = None
    # --- geometry PARAMETERS, never rectangles -------------------------------
    # The elevation is a pure function of these (foundation §15: read models are
    # derived, never stored). Storing a list of rectangles would freeze one
    # drawing into the run and make the panel's picture a thing that could
    # disagree with the panel's numbers.
    # frame | infill | fixing. On the wire a vertical FRAME slot and a vertical
    # INFILL slot are the same shape, so a client had to guess which one a
    # `gaps_mm` list belonged to — the elevation renderer confirmed its gap
    # dimension geometrically rather than by indexing, which is guesswork
    # dressed as arithmetic. Said outright instead.
    slot_kind: str = ""
    orientation: str = ""            # horizontal | vertical, in the panel's frame
    positions_mm: list[Mm] = []      # frame slots: where along the cross axis
    member_width_mm: Mm | None = None   # infill: the member's own width
    thickness_mm: Mm | None = None   # face height in elevation; None = undeclared
    face_offset_mm: int = 0          # + front / - back, for shadowbox
    pattern_index: int = 0           # which member of the repeating cycle
    # every member of the cycle, in order. A slot knows its own width, but a
    # position depends on everything BEFORE it — a two-member pattern's second
    # member sits where it does because of the first one's width and gap — so the
    # whole cycle has to travel with each slot or the walk cannot be exact.
    cycle_widths_mm: list[Mm] = []
    cycle_gaps_mm: list[Mm] = []     # the AUTHORED gaps; the fitted ones are on `fit`
    # which option answer narrowed this slot's eligibility, if one did. Recorded
    # rather than re-derived: the generator writes the `select_product` node from
    # it, and a second pass matching skus back to axes would be a second, quietly
    # divergent implementation of the narrowing rule.
    option_axis: str | None = None
    option_value: str | None = None


class ResolvedPanel(BaseModel):
    model_ref: str = ""
    variant_index: int | None = None
    slots: list[ResolvedSlot] = []


class VariantChoice(BaseModel):
    """Which variant a bay is built to, and what was tried on the way there.

    `failed` and `not_reached` are separate because they are different facts and
    the decision node says both: a condition that was evaluated and not satisfied
    lost the contest, while a variant AFTER the winner was never asked at all
    (first satisfied condition wins). Recording the second group as failures
    would put a claim in the graph that nothing ever checked.
    """

    spec: PanelSpec
    index: int | None = None
    failed: list[int] = []        # evaluated: False, or MissingField
    not_reached: list[int] = []   # authored after the winner, never evaluated


def choose_variant(model: FenceModel, ctx: PanelContext) -> VariantChoice:
    """Authored order, first satisfied condition wins — deliberately not
    'specificity', which is undefined for a bare Expr and would have two
    implementers counting different things.

    This evaluation happens OUTSIDE the knowledge evaluator: a variant is
    product structure, not a defeasible rule, so it produces no firing and no
    `defeated` edge. Its own decision node is the whole trace (fence-model spec
    §"The shape of the thing"), which is why the losers are reported here rather
    than left to be reconstructed by a second evaluation somewhere else.
    """
    failed: list[int] = []
    for index, variant in enumerate(model.variants):
        try:
            satisfied = evaluate_expr(variant.condition, ctx.condition_ctx())
        except MissingField:
            # a condition naming a field this context never supplies is "not
            # applicable", exactly as it is in the knowledge evaluator
            satisfied = False
        if satisfied:
            return VariantChoice(
                spec=variant.spec, index=index, failed=failed,
                not_reached=list(range(index + 1, len(model.variants))),
            )
        failed.append(index)
    return VariantChoice(spec=model.default_spec, index=None, failed=failed)


def select_variant(model: FenceModel, ctx: PanelContext) -> tuple[PanelSpec, int | None]:
    """The two-value view of `choose_variant`, for callers with no graph to
    write to (the panel preview)."""
    choice = choose_variant(model, ctx)
    return choice.spec, choice.index


def height_supported(support: HeightSupport, height_mm: Mm) -> bool:
    """Can this model be built at this panel height?

    Pure and per-BAY, because a height is a property of a bay; the aggregation
    that turns several unsupported bays into ONE warning per section belongs to
    the caller that knows what a section is (fence-model spec §warnings).
    """
    if support.kind == "discrete":
        return height_mm in support.heights_mm
    if not support.min_mm <= height_mm <= support.max_mm:
        return False
    # step 0 (or 1) states no ladder — every millimetre inside the band is a
    # height you can order, which is what the permissive default means
    if support.step_mm <= 1:
        return True
    return (height_mm - support.min_mm) % support.step_mm == 0


def _between_frame_length(
    member: Member, frame: dict[str, "ResolvedSlot"]
) -> Mm | None:
    """A member cut to fit between two frame members, plus what disappears into
    them:

        (top_position - base_position)
        - (top_thickness//2 + base_thickness//2)   # centreline to facing faces
        + base_engagement + top_engagement          # what the joint swallows

    The positions are READ off the frame slots this same panel already resolved,
    never re-derived: `placement_positions` is THE rounding point for placement
    (ADR-0002), and a second call here — over a span this function would have to
    reconstruct from the orientation — is exactly how two implementations end up
    a millimetre apart and move a rail out from under its own slats.

    A placement gives a member's CENTRELINE, so half of each frame member's face
    height is what stands between the two centrelines and the opening. An
    undeclared thickness contributes 0 rather than a nominal: the elevation
    already reports such a member as `declared=False`, and inventing a face
    height here would put a measured-looking number on a cut list.

    A frame slot with several positions is a rail SET (a `Distributed` ladder),
    and "between the rails" means between the outermost two: the bottom rail is
    the lowest position and the top rail the highest, which is what an author
    naming one slot at both ends is asking for. Picking a middle rail would cut
    every slat short by a bay's worth of ladder.
    """
    base_slot = frame.get(member.base_ref or "")
    top_slot = frame.get(member.top_ref or "")
    if base_slot is None or top_slot is None:
        return None
    if not base_slot.positions_mm or not top_slot.positions_mm:
        # A `count_param` resolved the referenced set to nothing, so in THIS bay
        # there is no member to seat into. Substituting the panel height would
        # hand the cut list a length measured between things that are not there.
        return None
    length = (
        (max(top_slot.positions_mm) - min(base_slot.positions_mm))
        - ((top_slot.thickness_mm or 0) // 2 + (base_slot.thickness_mm or 0) // 2)
        + member.base_engagement_mm + member.top_engagement_mm
    )
    if length <= 0:
        # NOT clamped, and not returned. Two ways to arrive here and neither is
        # decidable when the model is authored: refs the wrong way round (the
        # editor offers both selects and which member is higher depends on the
        # BAY's height), and a knowledge param collapsing a `Distributed` set to
        # one position, where both ends become the same member and the face
        # correction eats what is left. A negative number is not a shorter piece
        # — `plan_cuts` packs it into a bar and certifies the plan optimal — so
        # this bay has no resolvable length, and the caller says so.
        return None
    return length


def _length_for(
    req: PartRequirement,
    ctx: PanelContext,
    member: Member | None = None,
    frame: dict[str, "ResolvedSlot"] | None = None,
) -> Mm | None:
    """`member` and `frame` are passed in rather than reached for: `between_frame`
    is the one rule that measures against the rest of the panel, and a resolver
    that read the frame off module state would stop being a pure function of its
    arguments."""
    if req.length_rule is None:
        return None
    if req.length_rule == "between_frame":
        # Same as `panel_height` below, for the same reason: this measures a
        # VERTICAL distance inside the panel, between two frame members that
        # slope together in a raked bay, so the slope factor must not stretch it.
        if member is None or frame is None:
            # only an infill member carries the refs, and `validate_model`
            # refuses the rule anywhere else
            return None
        return _between_frame_length(member, frame)
    if req.length_rule == "panel_height":
        # A member spanning the panel's full height — a picket, a slat, a baluster.
        # Constant in every vertical mode: a raked bay's top follows the grade and
        # its bottom follows the ground, so the two datums stay parallel, and a
        # stepped bay is a rectangle. A member constrained to a frame slot
        # (base_ref/top_ref) can vary along the bay, which is what `between_frame`
        # above is for.
        #
        # The slope factor below deliberately does NOT apply: it corrects a
        # HORIZONTAL member for running along the grade, and a vertical member
        # does not run along the grade at all.
        return ctx.height_mm
    if req.length_rule == "clear_between_posts":
        base = ctx.clear_width_mm
    elif req.length_rule == "overlap":
        base = ctx.centre_width_mm + req.overlap_mm
    else:
        base = ctx.centre_width_mm
    if ctx.length_basis == "slope" and ctx.slope_len_mm is not None:
        # the slope factor applies to the same rule, not to a raw width
        return base + (ctx.slope_len_mm - ctx.centre_width_mm)
    return base


def _qty(count: int, param: str | None, ctx: PanelContext) -> int:
    return ctx.params.get(param, count) if param else count


def placement_positions(placement, count: int, span_mm: Mm) -> list[Mm]:
    """Where a frame slot's members sit along the axis it crosses.

    `span_mm` is the panel height for a horizontal member and the clear width for
    a vertical one. THE one rounding point for placement (ADR-0002): integer
    division here, and nothing upstream or downstream rounds again — two
    implementations differing by a millimetre would move a rail, and the fixing
    count that depends on crossings with it.

    `distributed` spreads INCLUSIVE of both ends, which is what a fence frame is:
    two rails means a top rail and a bottom rail, not two rails floating in the
    middle. A single distributed member centres, because there is no pair of ends
    for it to be one of.
    """
    if isinstance(placement, FromBottom):
        return [placement.offset_mm]
    if isinstance(placement, FromTop):
        return [span_mm - placement.offset_mm]
    if isinstance(placement, Fraction):
        return [(span_mm * placement.permille) // 1000]
    low = placement.bottom_inset_mm
    high = span_mm - placement.top_inset_mm
    if count <= 0:
        return []
    if count == 1:
        return [(low + high) // 2]
    return [low + ((high - low) * i) // (count - 1) for i in range(count)]


def _chosen_option(
    req: PartRequirement, ctx: PanelContext
) -> tuple[Eligibility, str | None, str | None]:
    """(eligibility for this slot, the axis that narrowed it, the value it took).

    The axis comes back rather than being read off the requirement by the caller
    because "bound to an axis" and "narrowed by one" are different states, and a
    slot bound to an unanswered axis must not read as governed by it.

    An enum axis NARROWS eligibility; it never bypasses it. `sku_by_option`
    names a member of the slot's OWN set — a value naming a non-member is a
    load-time model error (`validate_model`), so by the time resolution runs the
    named sku is guaranteed to be one of the candidates and narrowing can only
    ever remove alternatives. Everything the slot said about that member — its
    priority, its `suggest_only` approval — is carried through untouched, so a
    colour choice cannot promote a product past an approval it still needs.

    Three ways to narrow nothing, all of them ordinary: the slot binds no axis,
    the axis was not answered, or the answer names no sku for THIS slot (one
    axis may govern the rails and say nothing about the screws).
    """
    unnarrowed = (req.eligibility, None, None)
    if req.option_axis is None or req.option_axis not in ctx.options:
        return unnarrowed
    # options are `str | int` (a numeric axis answers with a number) while
    # sku_by_option is keyed by the axis value's key, which is a string
    value = str(ctx.options[req.option_axis])
    sku = req.sku_by_option.get(value)
    if sku is None:
        return unnarrowed
    members = [m for m in req.eligibility.members if m.sku == sku]
    if not members:
        # unreachable through a validated model; a resolver that silently
        # emptied the slot here would turn an authoring error into a panel with
        # a part nothing can supply
        return unnarrowed
    return (req.eligibility.model_copy(update={"members": members}),
            req.option_axis, value)


def resolve_panel(
    spec: PanelSpec,
    ctx: PanelContext,
    model_ref: str = "",
    variant_index: int | None = None,
) -> ResolvedPanel:
    """`variant_index` is recorded, never chosen here: which spec applies is
    `choose_variant`'s answer, and a resolver that re-derived it from `spec`
    would be a second implementation of the precedence rule."""
    slots: list[ResolvedSlot] = []
    # The frame loop runs first and the infill loop reads its answer, because a
    # `between_frame` member is measured against frame members that are already
    # placed. Keyed by slot key, which is unique within a spec (`validate_model`).
    frame: dict[str, ResolvedSlot] = {}

    for frame_slot in spec.frame:
        req = frame_slot.requirement
        count = (_qty(frame_slot.placement.count, frame_slot.placement.count_param, ctx)
                 if isinstance(frame_slot.placement, Distributed) else 1)
        eligibility, option_axis, option_value = _chosen_option(req, ctx)
        # a horizontal member is placed up the HEIGHT; a vertical one across the
        # clear width
        span = (ctx.height_mm if frame_slot.orientation == "horizontal"
                else ctx.clear_width_mm)
        resolved = ResolvedSlot(
            slot_key=frame_slot.key, role=req.role, qty=count * req.qty,
            slot_kind="frame",
            length_mm=_length_for(req, ctx), length_basis=ctx.length_basis,
            eligibility=eligibility,
            option_axis=option_axis, option_value=option_value,
            orientation=frame_slot.orientation,
            thickness_mm=frame_slot.thickness_mm or None,
            positions_mm=placement_positions(frame_slot.placement, count, span),
        )
        slots.append(resolved)
        frame[frame_slot.key] = resolved

    if spec.infill and spec.infill.pattern:
        axis = (ctx.clear_width_mm if spec.infill.orientation == "vertical"
                else ctx.height_mm)
        fit = fit_pattern(
            axis,
            [m.width_mm for m in spec.infill.pattern],
            [m.gap_after_mm for m in spec.infill.pattern],
            justification=spec.infill.justification,
            excess=spec.infill.excess,
            edge_margin_mm=spec.infill.edge_margin_mm,
        )
        for offset, member in enumerate(spec.infill.pattern):
            # how many of THIS member of the repeating sequence were placed
            n = sum(1 for i in range(fit.count) if i % len(spec.infill.pattern) == offset)
            if not n:
                continue
            eligibility, option_axis, option_value = _chosen_option(
                member.requirement, ctx)
            length = _length_for(member.requirement, ctx, member, frame)
            slots.append(ResolvedSlot(
                slot_key=member.key, role=member.requirement.role,
                slot_kind="infill", qty=n * member.requirement.qty,
                length_mm=length,
                length_unresolved=(member.requirement.length_rule is not None
                                   and length is None),
                # `between_frame` measures a vertical distance INSIDE the panel,
                # so the slope factor never applied to it (`_length_for`) — and
                # stamping "slope" beside a number that ignores the slope says
                # the opposite to every reader of the structure sheet.
                length_basis=("width"
                              if member.requirement.length_rule == "between_frame"
                              else ctx.length_basis),
                eligibility=eligibility, fit=fit,
                option_axis=option_axis, option_value=option_value,
                orientation=spec.infill.orientation,
                member_width_mm=member.width_mm,
                cycle_widths_mm=[m.width_mm for m in spec.infill.pattern],
                cycle_gaps_mm=[m.gap_after_mm for m in spec.infill.pattern],
                thickness_mm=member.thickness_mm or None,
                face_offset_mm=member.face_offset_mm,
                pattern_index=offset,
            ))

    frame_count = sum(s.qty for s in slots if s.fit is None)
    # Two different counts, and conflating them over-orders. `member_count` is
    # PARTS: a member with `qty=2` is two physical pieces at one position (a
    # batten pair, a board front and back), and each of them takes its own screw
    # and makes its own crossing. `placed_count` is POSITIONS along the axis,
    # which is what the fit produced — and a gap is between two positions, not
    # between two pieces that share one. With `qty=2` the two differ by a factor.
    member_count = sum(s.qty for s in slots if s.fit is not None)
    placed_count = next((s.fit.count for s in slots if s.fit is not None), 0)
    for rule in spec.fixings:
        per = _qty(rule.qty_per_basis, rule.qty_param, ctx)
        basis = {
            "per_panel": 1,
            "per_frame_member": frame_count,
            "per_member": member_count,
            # first and last ALONG THE AXIS: a placement question
            "per_end_member": min(placed_count, 2),
            "per_gap": max(placed_count - 1, 0),
            "per_member_crossing": member_count * frame_count,
        }[rule.basis]
        if not basis:
            continue
        eligibility, option_axis, option_value = _chosen_option(rule.requirement, ctx)
        slots.append(ResolvedSlot(
            slot_key=rule.key, role=rule.requirement.role, slot_kind="fixing",
            qty=per * basis,
            eligibility=eligibility,
            option_axis=option_axis, option_value=option_value,
        ))

    return ResolvedPanel(model_ref=model_ref, variant_index=variant_index, slots=slots)
