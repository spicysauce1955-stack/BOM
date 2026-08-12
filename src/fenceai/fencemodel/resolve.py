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
    Distributed, Eligibility, FenceModel, HeightSupport, PanelSpec, PartRequirement,
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
    sku: str = ""                    # resolved by fulfillment, never here
    eligibility: Eligibility = Eligibility()
    fit: FitResult | None = None
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


def _length_for(req: PartRequirement, ctx: PanelContext) -> Mm | None:
    if req.length_rule is None:
        return None
    if req.length_rule == "panel_height":
        # A member spanning the panel's full height — a picket, a slat, a baluster.
        # Constant in every vertical mode: a raked bay's top follows the grade and
        # its bottom follows the ground, so the two datums stay parallel, and a
        # stepped bay is a rectangle. Only a member constrained to a frame slot
        # (base_ref/top_ref) can vary along the bay, and that is not resolved yet.
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

    for frame_slot in spec.frame:
        req = frame_slot.requirement
        count = (_qty(frame_slot.placement.count, frame_slot.placement.count_param, ctx)
                 if isinstance(frame_slot.placement, Distributed) else 1)
        eligibility, option_axis, option_value = _chosen_option(req, ctx)
        slots.append(ResolvedSlot(
            slot_key=frame_slot.key, role=req.role, qty=count * req.qty,
            length_mm=_length_for(req, ctx), length_basis=ctx.length_basis,
            eligibility=eligibility,
            option_axis=option_axis, option_value=option_value,
        ))

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
            slots.append(ResolvedSlot(
                slot_key=member.key, role=member.requirement.role,
                qty=n * member.requirement.qty,
                length_mm=_length_for(member.requirement, ctx),
                length_basis=ctx.length_basis,
                eligibility=eligibility, fit=fit,
                option_axis=option_axis, option_value=option_value,
            ))

    frame_count = sum(s.qty for s in slots if s.fit is None)
    member_count = sum(s.qty for s in slots if s.fit is not None)
    for rule in spec.fixings:
        per = _qty(rule.qty_per_basis, rule.qty_param, ctx)
        basis = {
            "per_panel": 1,
            "per_frame_member": frame_count,
            "per_member": member_count,
            "per_end_member": min(member_count, 2),
            "per_gap": max(member_count - 1, 0),
            "per_member_crossing": member_count * frame_count,
        }[rule.basis]
        if not basis:
            continue
        eligibility, option_axis, option_value = _chosen_option(rule.requirement, ctx)
        slots.append(ResolvedSlot(
            slot_key=rule.key, role=rule.requirement.role, qty=per * basis,
            eligibility=eligibility,
            option_axis=option_axis, option_value=option_value,
        ))

    return ResolvedPanel(model_ref=model_ref, variant_index=variant_index, slots=slots)
