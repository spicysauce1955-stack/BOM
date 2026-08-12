"""M-LEGACY exists to prove the mechanism can reproduce what the two integers on
Span already do. If it cannot, the mechanism is not right yet."""

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY
from fenceai.fencemodel.model import validate_model
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import DefaultComponent, KnowledgeVersion
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def test_legacy_model_validates_against_the_demo_catalog():
    assert validate_model(M_LEGACY, demo_catalog()) == []


def test_every_span_gets_a_panel_whose_slots_match_its_legacy_counts():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    assert result.strategy.spans
    for span in result.strategy.spans:
        assert span.panel is not None
        rails = next(s for s in span.panel.slots if s.role == "rail")
        screws = next(s for s in span.panel.slots if s.role == "screw")
        assert rails.qty == span.rail_count
        assert screws.qty == span.screws_count
        assert rails.length_mm == span.width_mm       # centre_to_centre, as today
        assert rails.length_basis == span.rail_cut_basis


def test_the_panel_names_no_sku_and_carries_the_runs_resolved_default():
    """The DefaultComponent fallback is frozen onto the requirement at GENERATION,
    so fulfillment never has to look anything up in knowledge.

    The knowledge base here names POST-S for the rail role — deliberately NOT
    the RAIL-3000 that both `DEMAND_ROLE_DEFAULTS` and `legacy_model()`'s own
    default argument would produce. Asserting `== ["RAIL-3000"]` against the
    demo KB (which the previous version of this test did) could not distinguish
    "the seeding mechanism works" from "the hardcoded default is showing", so it
    passed just as happily when `legacy_model()` ignored `demand_skus`
    altogether.
    """
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-RAIL-PRODUCT", version=1, type="fact",
        title="rails come from POST-S stock",
        actions=[DefaultComponent(role="rail", sku="POST-S")],
    ))
    result = generate(straight_topology(3000), kb, demo_catalog())
    assert result.run.demand_skus["rail_sku"] == "POST-S"

    rails = next(s for s in result.strategy.spans[0].panel.slots if s.role == "rail")
    assert rails.sku == ""                                  # never named here
    assert [m.sku for m in rails.eligibility.members] == ["POST-S"]


def test_the_screw_slot_follows_its_knowledge_default_too():
    """Both seeded roles, so a half-wired `legacy_model()` call cannot pass."""
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-SCREW-PRODUCT", version=1, type="fact",
        title="a different fastener",
        actions=[DefaultComponent(role="screw", sku="LATCH")],
    ))
    result = generate(straight_topology(3000), kb, demo_catalog())
    screws = next(s for s in result.strategy.spans[0].panel.slots if s.role == "screw")
    assert [m.sku for m in screws.eligibility.members] == ["LATCH"]


def test_without_a_rule_the_panel_falls_back_to_the_demo_default():
    """The fallback still has to work — the point is that it is a FALLBACK."""
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    rails = next(s for s in result.strategy.spans[0].panel.slots if s.role == "rail")
    assert [m.sku for m in rails.eligibility.members] == ["RAIL-3000"]


# ---- validate_model has a production caller (phase 1 open finding) -----------

def test_generation_validates_the_model_it_resolved():
    """`validate_model` had no production caller: models are only ever built by
    `legacy_model()`, which bypassed it, so every load-time gate on this branch
    — the unbuilt-feature refusals, the per-member advance bound, the SKU and
    length checks — was enforced by tests alone.

    A knowledge DefaultComponent seeds the model's eligibility, so a SKU that is
    not in the catalog is reachable from the knowledge editor. That model cannot
    produce a correct BOM, which is a hard constraint, not a note: 422, loudly,
    rather than a run that quietly prices a phantom product at zero."""
    import pytest

    from fenceai.core.errors import GenerationFailure

    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-RAIL-GHOST", version=1, type="fact",
        title="rail default nobody stocks",
        actions=[DefaultComponent(role="rail", sku="NOT-IN-CATALOG")],
    ))
    with pytest.raises(GenerationFailure, match="NOT-IN-CATALOG"):
        generate(straight_topology(3000), kb, demo_catalog())


def test_the_shipped_model_still_generates_clean():
    """The other half of the contract: the gate must refuse an unusable model
    WITHOUT refusing the only one that ships."""
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    assert result.strategy.spans and all(s.panel for s in result.strategy.spans)
