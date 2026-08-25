"""How a panel goes together, in an order a person can actually work in.

`FenceModel.assembly` says which slots are fitted at which step. This turns that
into what a fitter and a drawing actually need: each step with the PARTS it
places, taken from the panel that was resolved for this bay — never recomputed,
exactly as `report/structure.py` inverts pegs rather than re-deriving quantities.

**The governing property, and the reason the steps name slots at all**: every
member of the panel is placed by exactly ONE step, or it is reported as
`unplaced`. A model that describes how it goes together while quietly leaving out
half its parts is worse than one that says nothing, because a fitter reading it
would believe the panel finished. That is the same shape as `Σ(parts) ≡ BOM`, and
`unplaced` is this view's `unassigned`. A LONG `unplaced` list is a correct
outcome and not a to-do list (contract obligation 9): nothing here may invent a
placement to shorten it, because that converts a visible gap into an invisible
error.

A model with no steps gets no plan at all — `None`, not an empty one. "No opinion"
and "an empty instruction sheet" are different facts, and the assembly film needs
to tell them apart to know whether to fall back to its role-based build order.

---

**"The order" is a choice, and this read model says so.** Steps carry `requires`
— edges with a kind, never list position (contract obligation 11) — and a partial
order has no single sequence. So `AssemblyPlan.order` carries the SHAPE beside the
sequence: which steps sit in the same stage (unordered with respect to each
other), whether the sequence returned is the only valid one, and whether the
document asserted any dependency at all or this is merely its print order.
`fencemodel/step_order.py` owns that computation and `validate_model` calls the
same function, so there is one ordering implementation rather than two free to
disagree. A caller that reads `steps` and ignores `order` gets a sensible,
deterministic sequence; a caller that renders `order` can tell the reader the
truth, which is that several sequences would have been equally right.

**Two vocabularies, because there are two owners.** `slots` are the PANEL's
members and are this document's to name. `bay_parts` are the post, its cap and its
footing — what stands beside the panel — and which post stands at a station is
the RUN's answer, so the model names the KIND and this function is handed the
instances. That is the input the old note said was missing: an installation step
about posts used to be prose because there was nothing here for it to name.

The two invariants stay separate on purpose. `unplaced` is the panel's, exactly as
obligation 9 defines it. `unplaced_bay` is the bay's, and it is populated only
when the model names at least one bay part somewhere — a document that says
nothing about the bay is not making an incomplete claim about it, and reporting
every legacy model's posts as unplaced would turn silence into a defect and bury
the real ones. A model that places the post and forgets the cap is the case this
catches.

**The assembly FILM is still on its role heuristic**, and this slice made the case
for rewiring it weaker rather than stronger. `animate.js` reveals a whole RUN —
posts along the line, then each bay's members — while this plan is per-panel and
its steps now carry `run` and `site` scopes the film has no vocabulary for.
Feeding one panel's linearisation into a run-wide reveal needs a second ordering
concept (how do five bays' stage-1s interleave?) that nothing has asked for. The
motivating case is the one it always was: a model whose authored order and the
role heuristic genuinely disagree.

**Still not placeable**, and named rather than left to be rediscovered: parts
contained inside other parts (build-order item 10). When containment lands, a
contained part becomes a member like any other and joins `unplaced` by the same
rule — this function needs no new concept for it, only the panel to carry them.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.errors import ReadRefused
from fenceai.core.units import Mm
from fenceai.fencemodel.model import FenceModel
from fenceai.fencemodel.resolve import ResolvedPanel
from fenceai.fencemodel.step_order import StepOrder, step_order
from fenceai.report.elevation import ElevationPost


class StepPart(BaseModel):
    """One placeable's worth of a step — the panel's own numbers, not new ones."""

    slot_key: str
    role: str
    qty: int
    length_mm: Mm | None = None
    # panel | bay. Which invariant this row belongs to, and which vocabulary the
    # key above is drawn from. A flag rather than a naming convention on
    # `slot_key`, because a convention would be a second meaning smuggled into a
    # string every existing reader already treats as opaque.
    belongs_to: str = "panel"
    # No `sku`, deliberately. A `ResolvedSlot.sku` is "resolved by fulfillment,
    # never here" (`fencemodel/resolve.py`), so a field copied from it would be
    # empty on every step of every plan — a column that always falls back, and a
    # value no test could ever pin. The parts table beside the sheet names the
    # products; this says which SLOT is fitted when.


class ResolvedStep(BaseModel):
    key: str
    kind: str                      # assembly | installation
    # panel | bay | post | run | site. All five of the contract's scopes are
    # published; the panel sheet renders three of them and leaves `run` and
    # `site` present-and-unrendered, which is obligation 12's own wording.
    scope: str = "panel"
    # which stage of `AssemblyPlan.order.stages` this step landed in. Two steps
    # sharing a stage are unordered with respect to each other: the number is
    # what turns "here is a list" into "here is one of several valid lists".
    stage: int = 0
    text_i18n: dict[str, str] = {}
    parts: list[StepPart] = []


class AssemblyPlan(BaseModel):
    model_ref: str = ""
    # in ONE valid linearisation of `order`. Deterministic, and not the only one
    # — `order` is how a reader finds that out.
    steps: list[ResolvedStep] = []
    order: StepOrder = StepOrder()
    # slots of this panel that no step fits. Reported, never hidden: an
    # instruction sheet that silently omits a part reads as a finished panel.
    unplaced: list[StepPart] = []
    # the bay's own placeables that no step names — populated only once the model
    # has started naming them at all. See the module docstring.
    unplaced_bay: list[StepPart] = []


# What a bay part is, structurally, in the vocabulary demand already uses.
# `footing` -> `concrete` because that is the role `derive_requirements` stamps on
# the line that buys it, and one thing carrying two names across two read models
# is the drift this mapping exists to prevent.
BAY_PART_ROLES = {"post": "post", "cap": "cap", "footing": "concrete"}


def bay_parts_from_posts(posts: list[ElevationPost]) -> list[StepPart]:
    """The bay's placeables, INVERTED from the posts the caller already has.

    Counting, not computing: the caller settled which posts stand at this bay's
    ends, and this reads that list back. The same discipline `report/structure.py`
    keeps with pegs — a read model that worked out for itself how many posts a bay
    has would be a second opinion competing with the run's.

    **`footing` is absent here, and that is the honest answer rather than a
    missing feature.** A footing exists because a post is GROUND-mounted, and an
    `ElevationPost` is a drawing rectangle that does not carry mounting. A step
    may name `footing`; against this input it places nothing, exactly as a step
    naming a slot this variant lacks places nothing. The seam is narrow and
    named: a caller holding the run's own `Post` objects — which do carry
    `mounting` — can build the row here and every reader downstream gets it for
    free, because nothing above this function knows where the rows came from.
    """
    if not posts:
        return []
    out = [StepPart(slot_key="post", role="post", qty=len(posts),
                    belongs_to="bay")]
    capped = [p for p in posts if p.cap_sku]
    if capped:
        out.append(StepPart(slot_key="cap", role="cap", qty=len(capped),
                            belongs_to="bay"))
    return out


def assembly_plan(
    model: FenceModel,
    panel: ResolvedPanel,
    bay: list[StepPart] | None = None,
) -> AssemblyPlan | None:
    """`(model, the panel resolved for one bay, the bay's own parts)` -> the steps.

    `None` when the model states no order — which is not the same as a plan with
    no steps, and the caller needs the difference.

    `bay` is optional and empty is not the same as absent for the AUTHOR's
    purposes but is here: a caller that knows nothing about the bay and a bay with
    no posts both leave a step about posts placing nothing, and neither is a
    reason to invent one.
    """
    if panel.model_ref and model.ref != panel.model_ref:
        # The same refusal the structure sheet makes for a moved topology, and
        # for the same reason: this is a read model over a document, and laying
        # v2's steps over a v1 panel produces a plausible sheet whose slots land
        # in `unplaced` under a version they never came from. A stored run pins
        # its model ref precisely so a reader can check.
        raise ReadRefused(
            # spelled `code=` like every other refusal in the codebase, and not
            # only for symmetry: `tests/web/test_locale_bundles.py` greps for
            # that literal to prove every emitted code has a sentence in both
            # bundles, and a positional argument is invisible to it
            code="model_changed",
            message=f"assembly steps are {model.ref}'s and this panel was "
                    f"resolved from {panel.model_ref}",
            model_ref=model.ref, panel_model_ref=panel.model_ref,
        )
    if not model.assembly:
        return None
    order = step_order(model.assembly)
    # A cyclic draft is refused at AUTHORING (`validate_model`) and still has to
    # render, because a document being typed is invalid by definition and the
    # author is looking at it. `step_order` collapses the loop into one stage and
    # reports it; nothing here raises over it.
    stage_of = {key: i for i, stage in enumerate(order.stages) for key in stage}
    by_key = {step.key: step for step in model.assembly}

    by_slot = {slot.slot_key: slot for slot in panel.slots}
    by_bay_key = {part.slot_key: part for part in (bay or [])}
    placed: set[str] = set()
    bay_placed: set[str] = set()
    names_bay = any(step.bay_parts for step in model.assembly)

    steps: list[ResolvedStep] = []
    # the returned sequence IS the linearisation, so it is read off the stages
    # rather than off the document. Authored order survives as the tie-break
    # inside a stage, which is where a print order is a presentation choice
    # rather than a claim.
    for stage_index, stage in enumerate(order.stages):
        for key in stage:
            step = by_key[key]
            parts = []
            for slot_key in step.slots:
                slot = by_slot.get(slot_key)
                if slot is None:
                    # This bay is built to a variant that has no such slot. Not an
                    # error — `validate_model` already proved the slot exists in
                    # SOME spec of this model — and not a phantom part either.
                    continue
                placed.add(slot_key)
                parts.append(StepPart(
                    slot_key=slot.slot_key, role=slot.role, qty=slot.qty,
                    length_mm=slot.length_mm,
                ))
            for bay_key in step.bay_parts:
                part = by_bay_key.get(bay_key)
                if part is None:
                    # The same rule as a missing slot, one level out: this bay has
                    # no such thing (or the caller does not know), so the step
                    # places nothing rather than a part nobody bought.
                    continue
                bay_placed.add(bay_key)
                parts.append(part.model_copy())
            steps.append(ResolvedStep(
                key=step.key, kind=step.kind, scope=step.scope,
                stage=stage_of.get(step.key, stage_index),
                text_i18n=dict(step.text_i18n), parts=parts,
            ))

    unplaced = [
        StepPart(slot_key=s.slot_key, role=s.role, qty=s.qty,
                 length_mm=s.length_mm)
        for s in panel.slots if s.slot_key not in placed
    ]
    unplaced_bay = [
        part.model_copy()
        for part in (bay or []) if part.slot_key not in bay_placed
    ] if names_bay else []
    return AssemblyPlan(model_ref=panel.model_ref, steps=steps, order=order,
                        unplaced=unplaced, unplaced_bay=unplaced_bay)
