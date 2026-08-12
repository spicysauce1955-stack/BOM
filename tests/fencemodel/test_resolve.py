"""Resolution is pure: the same context always gives the same panel, and it
needs no knowledge access because the params are already on the context."""

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, Variant,
)
from fenceai.fencemodel.resolve import PanelContext, resolve_panel, select_variant
from fenceai.knowledge.ast import Cmp, FieldRef, Lit

RAIL = PartRequirement(
    role="rail", qty=1, length_rule="centre_to_centre",
    eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
)
LEGACY = PanelSpec(frame=[FrameSlot(
    key="rail", orientation="horizontal",
    placement=Distributed(count=2, count_param="rails_per_span"), requirement=RAIL,
)])
TALLER = PanelSpec(frame=[FrameSlot(
    key="rail2", orientation="horizontal",
    placement=Distributed(count=4, count_param="rails_per_span"), requirement=RAIL,
)])

# Real paths off PanelContext.condition_ctx(): {"panel": {"width_mm", "height_mm",
# "vertical"}}. _ctx()'s defaults (centre_width_mm=1500, height_mm=1800) make
# WIDTH_1500 and HEIGHT_1800 both true against the default context.
WIDTH_1500 = Cmp(cmp="==", left=FieldRef(path="panel.width_mm"), right=Lit(value=1500))
HEIGHT_1800 = Cmp(cmp="==", left=FieldRef(path="panel.height_mm"), right=Lit(value=1800))
WIDTH_9999 = Cmp(cmp="==", left=FieldRef(path="panel.width_mm"), right=Lit(value=9999))
# "panel.color" is not a key condition_ctx() ever populates, so this always
# raises MissingField rather than evaluating to True or False.
MISSING_FIELD = Cmp(cmp="==", left=FieldRef(path="panel.color"), right=Lit(value="red"))


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


def test_select_variant_with_no_variants_returns_the_default():
    model = FenceModel(id="basic", version=1, default_spec=LEGACY)
    assert select_variant(model, _ctx()) == (LEGACY, None)


def test_select_variant_first_satisfied_condition_wins_in_authored_order():
    """Both conditions are true against the default context; authored order
    decides, not specificity — a bare Expr has no scope dict to count."""
    model = FenceModel(
        id="basic", version=1, default_spec=PanelSpec(),
        variants=[Variant(condition=WIDTH_1500, spec=LEGACY),
                  Variant(condition=HEIGHT_1800, spec=TALLER)],
    )
    spec, index = select_variant(model, _ctx())
    assert spec == LEGACY
    assert index == 0


def test_select_variant_skips_an_unsatisfied_earlier_variant():
    model = FenceModel(
        id="basic", version=1, default_spec=PanelSpec(),
        variants=[Variant(condition=WIDTH_9999, spec=LEGACY),
                  Variant(condition=WIDTH_1500, spec=TALLER)],
    )
    spec, index = select_variant(model, _ctx())
    assert spec == TALLER
    assert index == 1


def test_select_variant_skips_a_condition_that_raises_missing_field():
    """A condition referencing a field the context never supplies is treated
    as 'not applicable', not as satisfied."""
    model = FenceModel(
        id="basic", version=1, default_spec=PanelSpec(),
        variants=[Variant(condition=MISSING_FIELD, spec=LEGACY),
                  Variant(condition=WIDTH_1500, spec=TALLER)],
    )
    spec, index = select_variant(model, _ctx())
    assert spec == TALLER
    assert index == 1


def test_select_variant_returns_default_when_every_variant_is_inapplicable():
    model = FenceModel(
        id="basic", version=1, default_spec=LEGACY,
        variants=[Variant(condition=MISSING_FIELD, spec=TALLER),
                  Variant(condition=WIDTH_9999, spec=TALLER)],
    )
    assert select_variant(model, _ctx()) == (LEGACY, None)


def test_select_variant_and_resolve_panel_pin_together():
    """The spec select_variant hands back is exactly what resolve_panel then
    resolves against — the two functions are a pair, not just independently
    correct."""
    model = FenceModel(
        id="basic", version=1, default_spec=PanelSpec(),
        variants=[Variant(condition=WIDTH_1500, spec=LEGACY)],
    )
    ctx = _ctx()
    spec, index = select_variant(model, ctx)
    assert index == 0
    assert resolve_panel(spec, ctx) == resolve_panel(LEGACY, ctx)
