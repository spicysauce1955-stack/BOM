"""Resolution is pure: the same context always gives the same panel, and it
needs no knowledge access because the params are already on the context."""

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FrameSlot, PanelSpec, PartRequirement,
)
from fenceai.fencemodel.resolve import PanelContext, resolve_panel

RAIL = PartRequirement(
    role="rail", qty=1, length_rule="centre_to_centre",
    eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
)
LEGACY = PanelSpec(frame=[FrameSlot(
    key="rail", orientation="horizontal",
    placement=Distributed(count=2, count_param="rails_per_span"), requirement=RAIL,
)])


def _ctx(**kw) -> PanelContext:
    base = dict(centre_width_mm=1500, clear_width_mm=1420, height_mm=1800,
                vertical="level", length_basis="width", params={"rails_per_span": 2},
                options={})
    return PanelContext(**{**base, **kw})


def test_distributed_count_comes_from_the_knowledge_param_not_the_default():
    """The model contributes a default of 2; knowledge said 3, and knowledge wins
    — otherwise a company rule scoped to a project would lose with no contest."""
    panel = resolve_panel(LEGACY, _ctx(params={"rails_per_span": 3}))
    rail = next(s for s in panel.slots if s.slot_key == "rail")
    assert rail.qty == 3


def test_missing_param_falls_back_to_the_models_default():
    panel = resolve_panel(LEGACY, _ctx(params={}))
    assert next(s for s in panel.slots if s.slot_key == "rail").qty == 2


def test_centre_to_centre_length_rule_uses_the_centre_width():
    panel = resolve_panel(LEGACY, _ctx())
    assert next(s for s in panel.slots if s.slot_key == "rail").length_mm == 1500


def test_clear_between_posts_length_rule_uses_the_clear_width():
    spec = LEGACY.model_copy(deep=True)
    spec.frame[0].requirement.length_rule = "clear_between_posts"
    panel = resolve_panel(spec, _ctx())
    assert next(s for s in panel.slots if s.slot_key == "rail").length_mm == 1420


def test_a_slot_carries_its_eligibility_forward_and_no_sku():
    """The panel says what must exist and which items may supply it. WHICH item
    is chosen is fulfillment's decision, coupled to the cut plan."""
    slot = resolve_panel(LEGACY, _ctx()).slots[0]
    assert slot.sku == ""
    assert [m.sku for m in slot.eligibility.members] == ["RAIL-3000"]


def test_resolution_is_deterministic():
    assert resolve_panel(LEGACY, _ctx()) == resolve_panel(LEGACY, _ctx())


def test_infill_slot_reports_its_fit_and_one_aggregate_quantity():
    """Quantities aggregate per slot; geometry enumerates later. A 40-slat bay is
    ONE requirement line of 40, not 40 lines."""
    from fenceai.fencemodel.model import InfillSpec, Member

    spec = PanelSpec(infill=InfillSpec(
        orientation="vertical",
        pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                        requirement=PartRequirement(
                            role="infill", qty=1, length_rule="centre_to_centre",
                            eligibility=Eligibility(members=[
                                EligibleItem(sku="RAIL-3000", priority=1)])))],
    ))
    panel = resolve_panel(spec, _ctx())
    slat = next(s for s in panel.slots if s.slot_key == "slat")
    assert slat.qty == slat.fit.count > 1
    assert len(panel.slots) == 1
    assert max(slat.fit.gaps_mm) - min(slat.fit.gaps_mm) <= 1
