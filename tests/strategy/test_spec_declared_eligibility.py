"""A slot that declares what it needs, as a run actually experiences it.

`tests/fencemodel/test_match.py` pins the matcher in isolation. What is pinned
here is the wiring — that a predicate reaches generation at all, that what it
selects is FROZEN onto the stored run, and that the BOM buys it. A matcher
nothing calls is the defect `_UNSUPPORTED` exists to catch.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, FenceModel, FrameSlot, PanelSpec, PartRequirement,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

MODEL_ID = "M-SPEC"

# What a rail slot actually needs: aluminium, and bought by the LENGTH so it can
# be cut to the bay. In demo_catalog() that is RAIL-3000 and nothing else —
# POST-CAP is aluminium but indivisible, SLAT-100 is bar stock but cedar.
A_RAIL = And(items=[
    Cmp(cmp="==", left=FieldRef(path="item.material"), right=Lit(value="aluminium")),
    Cmp(cmp="==", left=FieldRef(path="item.consumption"),
        right=Lit(value="divisible_linear")),
])


def _model() -> FenceModel:
    return FenceModel(
        id=MODEL_ID, version=1, name_i18n={"en": "Spec-declared"},
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal",
            placement=Distributed(count=2),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(predicate=A_RAIL),
            ),
        )]),
    )


def _run():
    return generate(
        straight_topology(3000), demo_knowledge(), demo_catalog(),
        models=FenceModelLibrary(models=[_model()]),
        default_model=FenceModelChoice(model_id=MODEL_ID),
    )


def _rail_slot(span):
    return next(s for s in span.panel.slots if s.slot_key == "rail")


def test_a_predicate_slot_resolves_to_the_items_that_cover_it():
    result = _run()
    assert result.strategy.spans
    for span in result.strategy.spans:
        skus = [m.sku for m in _rail_slot(span).eligibility.members]
        assert skus == ["RAIL-3000"]
        # both halves of the predicate do work: an aluminium product that cannot
        # be cut, and a cuttable product that is not aluminium, are BOTH out
        assert "POST-CAP" not in skus and "SLAT-100" not in skus


def test_what_the_predicate_selected_is_frozen_onto_the_run():
    """The candidate set a run may choose among is recorded, which is what makes
    `catalog_hash` narrowing safe: a product added later can never change what an
    already-generated run meant."""
    for span in _run().strategy.spans:
        assert _rail_slot(span).eligibility.predicate is None


def test_the_bom_buys_something_the_predicate_chose():
    result = _run()
    priced = price_strategy(result.strategy, demo_catalog(),
                            demand_skus=result.run.demand_skus,
                            preset=result.run.objective_preset)
    rails = [line for line in priced.requirements if line.role == "rail"]
    assert rails, "the panel bought no rail at all"
    assert all(line.sku == "RAIL-3000" for line in rails)
    assert not priced.unresolved
