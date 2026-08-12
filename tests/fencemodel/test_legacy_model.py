"""M-LEGACY exists to prove the mechanism can reproduce what the two integers on
Span already do. If it cannot, the mechanism is not right yet."""

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY
from fenceai.fencemodel.model import validate_model
from fenceai.knowledge.demo import demo_knowledge
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
    so fulfillment never has to look anything up in knowledge."""
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    rails = next(s for s in result.strategy.spans[0].panel.slots if s.role == "rail")
    assert rails.sku == ""
    assert [m.sku for m in rails.eligibility.members] == ["RAIL-3000"]
