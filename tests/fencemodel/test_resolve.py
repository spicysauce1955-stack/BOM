"""Resolution is pure: the same context always gives the same panel, and it
needs no knowledge access because the params are already on the context."""

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, Variant,
)
from fenceai.fencemodel.resolve import (
    PanelContext, choose_variant_by, rail_positions_mm, resolve_panel, select_variant,
)
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


def test_choose_variant_reports_the_losers_and_the_ones_never_asked():
    """The two groups are different facts: a condition that was evaluated and
    failed lost, while a variant after the winner was never evaluated at all."""
    from fenceai.fencemodel.resolve import choose_variant

    model = FenceModel(
        id="basic", version=1, default_spec=PanelSpec(),
        variants=[Variant(condition=MISSING_FIELD, spec=TALLER),
                  Variant(condition=WIDTH_9999, spec=TALLER),
                  Variant(condition=WIDTH_1500, spec=LEGACY),
                  Variant(condition=HEIGHT_1800, spec=TALLER)],
    )
    choice = choose_variant(model, _ctx())
    assert (choice.index, choice.failed, choice.not_reached) == (2, [0, 1], [3])
    assert choice.spec == LEGACY


def test_choose_variant_reports_every_variant_as_failed_when_none_applies():
    from fenceai.fencemodel.resolve import choose_variant

    model = FenceModel(
        id="basic", version=1, default_spec=LEGACY,
        variants=[Variant(condition=MISSING_FIELD, spec=TALLER),
                  Variant(condition=WIDTH_9999, spec=TALLER)],
    )
    choice = choose_variant(model, _ctx())
    assert (choice.index, choice.failed, choice.not_reached) == (None, [0, 1], [])


def test_select_variant_returns_default_when_every_variant_is_inapplicable():
    model = FenceModel(
        id="basic", version=1, default_spec=LEGACY,
        variants=[Variant(condition=MISSING_FIELD, spec=TALLER),
                  Variant(condition=WIDTH_9999, spec=TALLER)],
    )
    assert select_variant(model, _ctx()) == (LEGACY, None)


def test_height_support_continuous_bounds_and_step():
    """A ladder expressed as a step, which is what a model with a 100 mm size
    range means: 1250 is inside the band and still not a height you can order."""
    from fenceai.fencemodel.model import Continuous
    from fenceai.fencemodel.resolve import height_supported

    band = Continuous(min_mm=1000, max_mm=2000, step_mm=100)
    assert height_supported(band, 1000)
    assert height_supported(band, 1500)
    assert height_supported(band, 2000)
    assert not height_supported(band, 999)
    assert not height_supported(band, 2001)
    assert not height_supported(band, 1250)


def test_height_support_continuous_with_no_step_accepts_every_height_in_band():
    from fenceai.fencemodel.model import Continuous
    from fenceai.fencemodel.resolve import height_supported

    band = Continuous(min_mm=0, max_mm=10_000)
    assert height_supported(band, 1723)
    # a step of 0 is not a division by zero waiting in a warning path: it means
    # the model stated no step at all
    assert height_supported(Continuous(min_mm=0, max_mm=10_000, step_mm=0), 1723)


def test_height_support_discrete_is_the_ladder_and_nothing_between_it():
    from fenceai.fencemodel.model import Discrete
    from fenceai.fencemodel.resolve import height_supported

    ladder = Discrete(heights_mm=[1000, 1200, 1800])
    assert height_supported(ladder, 1200)
    assert not height_supported(ladder, 1201)
    # an EMPTY ladder supports nothing, and says so rather than supporting
    # everything: a model that lists no heights has not been finished
    assert not height_supported(Discrete(heights_mm=[]), 1800)


def _optioned(sku_by_option: dict[str, str]) -> PanelSpec:
    """LEGACY's rail slot, bound to an axis and offering two members."""
    spec = LEGACY.model_copy(deep=True)
    req = spec.frame[0].requirement
    req.option_axis = "frame_finish"
    req.sku_by_option = dict(sku_by_option)
    req.eligibility = Eligibility(members=[
        EligibleItem(sku="RAIL-3000", priority=1),
        EligibleItem(sku="RAIL-ALT", priority=2),
    ])
    return spec


def test_an_option_value_narrows_eligibility_to_the_member_it_names():
    """It NARROWS: the named sku must already be a member (enforced at load), so
    a colour choice can never smuggle in a product the slot disallows."""
    spec = _optioned({"black": "RAIL-3000", "grey": "RAIL-ALT"})
    slot = resolve_panel(spec, _ctx(options={"frame_finish": "grey"})).slots[0]
    assert [m.sku for m in slot.eligibility.members] == ["RAIL-ALT"]
    assert slot.option_axis == "frame_finish" and slot.option_value == "grey"


def test_the_narrowed_member_keeps_its_authored_priority_and_approval():
    """Narrowing removes candidates; it does not rewrite the survivor. A member
    marked suggest_only must still need approval after a colour is chosen."""
    spec = _optioned({"grey": "RAIL-ALT"})
    spec.frame[0].requirement.eligibility.members[1].approval = "suggest_only"
    slot = resolve_panel(spec, _ctx(options={"frame_finish": "grey"})).slots[0]
    assert [(m.sku, m.priority, m.approval) for m in slot.eligibility.members] == [
        ("RAIL-ALT", 2, "suggest_only")]


def test_an_unanswered_axis_leaves_the_slot_with_its_whole_set():
    spec = _optioned({"black": "RAIL-3000", "grey": "RAIL-ALT"})
    slot = resolve_panel(spec, _ctx(options={})).slots[0]
    assert [m.sku for m in slot.eligibility.members] == ["RAIL-3000", "RAIL-ALT"]
    assert slot.option_axis is None


def test_an_option_value_the_slot_says_nothing_about_narrows_nothing():
    """`sku_by_option` is per SLOT: an axis may govern the rails and say nothing
    about the screws, and the value chosen for it must not empty the screw slot."""
    spec = _optioned({"black": "RAIL-3000"})
    slot = resolve_panel(spec, _ctx(options={"frame_finish": "grey"})).slots[0]
    assert [m.sku for m in slot.eligibility.members] == ["RAIL-3000", "RAIL-ALT"]
    assert slot.option_axis is None


def test_a_numeric_option_value_matches_its_string_key():
    """`FenceModelChoice.options` is `str | int` while `sku_by_option` is keyed by
    the axis value's key, which is a string. 20 and "20" are the same answer."""
    spec = _optioned({"20": "RAIL-ALT"})
    slot = resolve_panel(spec, _ctx(options={"frame_finish": 20})).slots[0]
    assert [m.sku for m in slot.eligibility.members] == ["RAIL-ALT"]
    assert slot.option_value == "20"


def test_narrowing_does_not_mutate_the_authored_model():
    """`resolve_panel` is pure: the model is reused by the next bay and by the
    next run, so a narrowed slot must be a new object."""
    spec = _optioned({"grey": "RAIL-ALT"})
    resolve_panel(spec, _ctx(options={"frame_finish": "grey"}))
    assert [m.sku for m in spec.frame[0].requirement.eligibility.members] == [
        "RAIL-3000", "RAIL-ALT"]


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


# --- rail positions: the fact a routed post is matched against ----------------

def test_rail_positions_are_the_resolved_count_placed_up_the_height():
    """The one derivation, and it is `placement_positions`' answer. The count is
    the knowledge-resolved one, because a company rule saying three rails moves
    where every rail sits — and a post routed for two would then not fit."""
    spec = PanelSpec(frame=[FrameSlot(
        key="rail", orientation="horizontal",
        placement=Distributed(count=2, count_param="rails_per_span",
                              bottom_inset_mm=150, top_inset_mm=150),
        requirement=RAIL)])
    assert rail_positions_mm(spec, 1800, {}) == [150, 1650]
    assert rail_positions_mm(spec, 1800, {"rails_per_span": 3}) == [150, 900, 1650]
    assert rail_positions_mm(spec, 2100, {}) == [150, 1950]


def test_only_horizontal_frame_slots_are_rails():
    """A vertical frame member is a stile, and it is placed across the clear
    WIDTH — a number a post may not read, because its own face helps define it.
    Including one here would put the cycle back."""
    spec = PanelSpec(frame=[
        FrameSlot(key="rail", orientation="horizontal",
                  placement=Distributed(count=2), requirement=RAIL),
        FrameSlot(key="stile", orientation="vertical",
                  placement=Distributed(count=2), requirement=RAIL),
    ])
    assert rail_positions_mm(spec, 1800, {}) == [0, 1800]


def test_rail_positions_agree_with_the_panel_that_gets_resolved():
    """The point of the whole exercise: the positions a post is matched against
    must be the positions the bay is built to. Asserted against `resolve_panel`'s
    own answer rather than against a literal, so a change to placement cannot
    move one without the other."""
    ctx = _ctx(params={"rails_per_span": 3})
    panel = resolve_panel(LEGACY, ctx)
    assert rail_positions_mm(LEGACY, ctx.height_mm, ctx.params) == sorted(
        p for slot in panel.slots for p in slot.positions_mm
        if slot.orientation == "horizontal")


def test_a_variant_condition_the_context_cannot_answer_is_not_applicable():
    """`choose_variant_by` takes the condition CONTEXT because a post is resolved
    at its own station, where the bay's width does not exist. A width-conditioned
    variant is therefore skipped there — which is why `validate_model` refuses
    that variant on a model whose post is matched on the rails."""
    model = FenceModel(
        id="basic", version=1, default_spec=TALLER,
        variants=[Variant(condition=WIDTH_1500, spec=LEGACY)],
    )
    assert choose_variant_by(model, {"panel": {"width_mm": 1500}}).spec is LEGACY
    assert choose_variant_by(model, {"panel": {"height_mm": 1800}}).spec is TALLER
