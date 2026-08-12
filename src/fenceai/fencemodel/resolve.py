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
    Distributed, Eligibility, FenceModel, PanelSpec, PartRequirement,
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


class ResolvedPanel(BaseModel):
    model_ref: str = ""
    variant_index: int | None = None
    slots: list[ResolvedSlot] = []


def select_variant(model: FenceModel, ctx: PanelContext) -> tuple[PanelSpec, int | None]:
    """Authored order, first satisfied condition wins — deliberately not
    'specificity', which is undefined for a bare Expr and would have two
    implementers counting different things.

    NOT WIRED UP in phase 1: the generator resolves `model.default_spec`
    directly, so this has no production caller and `validate_model` refuses a
    model that declares variants. It is kept (and tested) as the resolution rule
    phase 2 turns on, not as behaviour any run gets today.
    """
    for index, variant in enumerate(model.variants):
        try:
            if evaluate_expr(variant.condition, ctx.condition_ctx()):
                return variant.spec, index
        except MissingField:
            continue
    return model.default_spec, None


def _length_for(req: PartRequirement, ctx: PanelContext) -> Mm | None:
    if req.length_rule is None:
        return None
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


def resolve_panel(spec: PanelSpec, ctx: PanelContext, model_ref: str = "") -> ResolvedPanel:
    slots: list[ResolvedSlot] = []

    for frame_slot in spec.frame:
        req = frame_slot.requirement
        count = (_qty(frame_slot.placement.count, frame_slot.placement.count_param, ctx)
                 if isinstance(frame_slot.placement, Distributed) else 1)
        slots.append(ResolvedSlot(
            slot_key=frame_slot.key, role=req.role, qty=count * req.qty,
            length_mm=_length_for(req, ctx), length_basis=ctx.length_basis,
            eligibility=req.eligibility,
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
            slots.append(ResolvedSlot(
                slot_key=member.key, role=member.requirement.role,
                qty=n * member.requirement.qty,
                length_mm=_length_for(member.requirement, ctx),
                length_basis=ctx.length_basis,
                eligibility=member.requirement.eligibility, fit=fit,
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
        slots.append(ResolvedSlot(
            slot_key=rule.key, role=rule.requirement.role, qty=per * basis,
            eligibility=rule.requirement.eligibility,
        ))

    return ResolvedPanel(model_ref=model_ref, slots=slots)
