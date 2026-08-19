"""How a panel goes together, in the order a person does it.

`FenceModel.assembly` says which slots are fitted at which step. This turns that
into what a fitter and a drawing actually need: each step with the PARTS it
places, taken from the panel that was resolved for this bay — never recomputed,
exactly as `report/structure.py` inverts pegs rather than re-deriving quantities.

**The governing property, and the reason the steps name slots at all**: every
member of the panel is placed by exactly ONE step, or it is reported as
`unplaced`. A model that describes how it goes together while quietly leaving out
half its parts is worse than one that says nothing, because a fitter reading it
would believe the panel finished. That is the same shape as `Σ(parts) ≡ BOM`, and
`unplaced` is this view's `unassigned`.

A model with no steps gets no plan at all — `None`, not an empty one. "No opinion"
and "an empty instruction sheet" are different facts, and the assembly film needs
to tell them apart to know whether to fall back to its role-based build order.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.fencemodel.model import FenceModel
from fenceai.fencemodel.resolve import ResolvedPanel


class StepPart(BaseModel):
    """One slot's worth of a step — the panel's own numbers, not new ones."""

    slot_key: str
    role: str
    qty: int
    length_mm: Mm | None = None
    sku: str = ""


class ResolvedStep(BaseModel):
    key: str
    kind: str                      # assembly | installation
    text_i18n: dict[str, str] = {}
    parts: list[StepPart] = []


class AssemblyPlan(BaseModel):
    model_ref: str = ""
    steps: list[ResolvedStep] = []
    # slots of this panel that no step fits. Reported, never hidden: an
    # instruction sheet that silently omits a part reads as a finished panel.
    unplaced: list[StepPart] = []


def assembly_plan(model: FenceModel, panel: ResolvedPanel) -> AssemblyPlan | None:
    """`(model, the panel resolved for one bay)` -> the steps, with their parts.

    `None` when the model states no order — which is not the same as a plan with
    no steps, and the caller needs the difference.
    """
    if not model.assembly:
        return None
    by_slot = {slot.slot_key: slot for slot in panel.slots}
    placed: set[str] = set()
    steps: list[ResolvedStep] = []
    for step in model.assembly:
        parts = []
        for key in step.slots:
            slot = by_slot.get(key)
            if slot is None:
                # This bay is built to a variant that has no such slot. Not an
                # error — `validate_model` already proved the slot exists in SOME
                # spec of this model — and not a phantom part either.
                continue
            placed.add(key)
            parts.append(StepPart(
                slot_key=slot.slot_key, role=slot.role, qty=slot.qty,
                length_mm=slot.length_mm, sku=slot.sku,
            ))
        steps.append(ResolvedStep(key=step.key, kind=step.kind,
                                  text_i18n=dict(step.text_i18n), parts=parts))
    unplaced = [
        StepPart(slot_key=s.slot_key, role=s.role, qty=s.qty,
                 length_mm=s.length_mm, sku=s.sku)
        for s in panel.slots if s.slot_key not in placed
    ]
    return AssemblyPlan(model_ref=panel.model_ref, steps=steps, unplaced=unplaced)
