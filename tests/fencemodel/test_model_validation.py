"""Load-time validation. A model is authored data, so it is checked once when it
loads rather than trusted at every resolution."""

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, validate_model,
)


def _slot(**kw) -> FrameSlot:
    req = kw.pop("requirement", PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    ))
    return FrameSlot(key="rail", orientation="horizontal",
                     placement=Distributed(count=2), requirement=req, **kw)


def _model(spec: PanelSpec) -> FenceModel:
    return FenceModel(id="M-TEST", version=1, name_i18n={"en": "Test"},
                      default_spec=spec)


def test_a_wellformed_model_validates_clean():
    assert validate_model(_model(PanelSpec(frame=[_slot()])), demo_catalog()) == []


def test_an_eligible_sku_missing_from_the_catalog_is_rejected():
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="NOPE", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("NOPE" in e for e in errs)


def test_a_length_requirement_needs_a_member_that_can_supply_a_length():
    """POST-CAP is indivisible with no length_mm attribute, so it cannot be cut
    to a rail length. Consumption semantics live on the product (foundation §5)
    and the model is checked against them rather than restating them."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="POST-CAP", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("POST-CAP" in e and "length" in e for e in errs)


def test_sku_by_option_must_name_an_eligible_member():
    """An option value can NARROW eligibility; it can never smuggle in a product
    the slot does not allow. Still refused now that options RESOLVE: this is the
    check that makes "narrows, never bypasses" true rather than aspirational."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        option_axis="frame_finish", sku_by_option={"black": "POST-S"},
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("frame_finish" in e and "POST-S" in e for e in errs)


def test_sku_by_option_key_must_be_a_declared_axis_value():
    """The flip side of the eligible-member check: an option VALUE that no
    `OptionValue` declares can never be selected, so it narrows nothing — the
    same dangling-reference error the eligible-sku and option_axis checks
    already catch."""
    from fenceai.fencemodel.model import Axis, OptionValue

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        option_axis="frame_finish", sku_by_option={"TYPO_VALUE": "RAIL-3000"},
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    model = FenceModel(
        id="M-TEST", version=1, name_i18n={"en": "Test"},
        default_spec=PanelSpec(frame=[_slot(requirement=req)]),
        option_axes=[Axis(key="frame_finish", kind="enum", values=[
            OptionValue(key="black", label_i18n={"en": "Black"}),
        ])],
    )
    errs = validate_model(model, demo_catalog())
    assert any("frame_finish" in e and "TYPO_VALUE" in e for e in errs)


def test_duplicate_slot_keys_are_rejected():
    """slot_key is an override anchor dimension; two slots sharing one key would
    make an override ambiguous."""
    errs = validate_model(_model(PanelSpec(frame=[_slot(), _slot()])), demo_catalog())
    assert any("duplicate" in e.lower() for e in errs)


def test_a_swatch_must_be_a_plain_hex_colour():
    """The swatch reaches an SVG fill, which is a style context where esc() is not
    sufficient — so it is constrained at load, not escaped at render."""
    from fenceai.fencemodel.model import Axis, OptionValue

    model = FenceModel(
        id="M-TEST", version=1, name_i18n={"en": "T"},
        default_spec=PanelSpec(frame=[_slot()]),
        option_axes=[Axis(key="finish", kind="enum", values=[
            OptionValue(key="x", label_i18n={"en": "X"}, swatch="url(javascript:0)"),
        ])],
    )
    assert any("swatch" in e for e in validate_model(model, demo_catalog()))


# ---- a pattern that never advances (fix wave, finding A) ---------------------

def _infill_model(**member_kw) -> FenceModel:
    """A model whose single infill member is authored by the caller."""
    from fenceai.fencemodel.model import InfillSpec, Member

    base = dict(key="slat", width_mm=90, gap_after_mm=20)
    return _model(PanelSpec(infill=InfillSpec(
        orientation="vertical",
        pattern=[Member(**{**base, **member_kw}, requirement=PartRequirement(
            role="infill", qty=1, length_rule="centre_to_centre",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),
        ))],
    )))


def test_a_zero_width_member_is_rejected():
    """`fit_pattern` places members while the next one still fits; a member with
    no width fits for ever. Nothing bounded width_mm before."""
    errs = validate_model(_infill_model(width_mm=0), demo_catalog())
    assert any("width_mm must be positive" in e for e in errs)


def test_a_member_whose_overlap_swallows_it_whole_is_rejected():
    """A negative gap is a documented feature (board-on-board). A negative gap
    at least as big as the member is a pattern that never advances — infinitely
    many slats in one bay, which used to hang generate()."""
    errs = validate_model(_infill_model(width_mm=100, gap_after_mm=-100),
                          demo_catalog())
    assert any("never advance" in e for e in errs)


def test_an_ordinary_overlap_is_still_accepted():
    """The bound is on the member's NET advance, not on the sign of the gap —
    board-on-board must keep working."""
    assert validate_model(_infill_model(width_mm=100, gap_after_mm=-25),
                          demo_catalog()) == []


# ---- validated-then-ignored features (fix wave, finding G) -------------------

def test_a_model_with_variants_validates_clean_now_that_they_resolve():
    """Turned on in W3: `choose_variant` is called per bay by the generator, so a
    variant condition is evaluated rather than ignored. The entry that refused
    this left `_unsupported_features` in the same change."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    from fenceai.fencemodel.model import Variant

    model = _model(PanelSpec(frame=[_slot()]))
    model.variants = [Variant(
        condition=Cmp(cmp="<", left=FieldRef(path="panel.height_mm"), right=Lit(value=1200)),
        spec=PanelSpec(frame=[_slot()]),
    )]
    assert validate_model(model, demo_catalog()) == []


def test_a_variants_own_spec_is_validated_like_the_default_one():
    """A variant spec reaches `resolve_panel` exactly as `default_spec` does, so
    an unstocked sku inside one is the same wrong BOM."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    from fenceai.fencemodel.model import Variant

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="NOPE", priority=1)]),
    )
    model = _model(PanelSpec(frame=[_slot()]))
    model.variants = [Variant(
        condition=Cmp(cmp="<", left=FieldRef(path="panel.height_mm"), right=Lit(value=1200)),
        spec=PanelSpec(frame=[_slot(requirement=req)]),
    )]
    assert any("NOPE" in e for e in validate_model(model, demo_catalog()))


def test_option_axes_validate_clean_now_that_a_chosen_value_is_read():
    from fenceai.fencemodel.model import Axis, OptionValue

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        option_axis="finish", sku_by_option={"black": "RAIL-3000"},
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    model = _model(PanelSpec(frame=[_slot(requirement=req)]))
    model.option_axes = [Axis(key="finish", kind="enum",
                              values=[OptionValue(key="black", swatch="#101010")])]
    assert validate_model(model, demo_catalog()) == []


def test_an_axis_with_available_when_is_still_refused():
    """The one part of the axis feature W3 did NOT build: nothing evaluates
    `available_when`, so an axis that is supposed to disappear would still be
    answerable and the answer would still narrow a slot."""
    from fenceai.fencemodel.model import Axis, OptionValue
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit

    model = _model(PanelSpec(frame=[_slot()]))
    model.option_axes = [Axis(
        key="finish", kind="enum", values=[OptionValue(key="black")],
        available_when=Cmp(cmp=">", left=FieldRef(path="panel.height_mm"),
                           right=Lit(value=1200)),
    )]
    errs = validate_model(model, demo_catalog())
    assert any("available_when" in e and "not yet supported" in e for e in errs)


def test_a_restricted_height_support_validates_clean_now_that_it_is_checked():
    """Generation compares each bay's height against the ladder and reports the
    ones it cannot build, per section — so declaring a ladder is no longer an
    ask that goes nowhere."""
    from fenceai.fencemodel.model import Discrete

    model = _model(PanelSpec(frame=[_slot()]))
    model.height_support = Discrete(heights_mm=[1000, 1200])
    assert validate_model(model, demo_catalog()) == []


def test_the_permissive_default_height_support_is_not_flagged():
    """Only a model that ASKS for something unbuilt is refused; the default asks
    for nothing, so M-LEGACY and every phase-1 model stay clean."""
    assert validate_model(_model(PanelSpec(frame=[_slot()])), demo_catalog()) == []


def test_a_layout_policy_over_series_scoped_params_validates_clean():
    """Each contribution becomes a knowledge version scoped to `series=<model>`,
    resolved by the same evaluator as everything else."""
    from fenceai.fencemodel.model import PolicyContribution

    model = _model(PanelSpec(frame=[_slot()]))
    model.layout_policy = [
        PolicyContribution(param="max_span_mm", value=1500,
                           knowledge_type="hard_constraint"),
        PolicyContribution(param="rails_per_span", value=3,
                           knowledge_type="preference"),
    ]
    assert validate_model(model, demo_catalog()) == []


def test_a_contribution_to_a_param_no_model_scope_reaches_is_refused():
    """`post_embed_mm` is resolved once for the whole topology, from a scope with
    no `series` bound. A contribution naming it would enter the evaluator and
    match nothing — accepted, emitted, and silently without effect, which is the
    exact shape this table exists to refuse."""
    from fenceai.fencemodel.model import PolicyContribution

    model = _model(PanelSpec(frame=[_slot()]))
    model.layout_policy = [PolicyContribution(
        param="post_embed_mm", value=900, knowledge_type="hard_constraint")]
    errs = validate_model(model, demo_catalog())
    assert any("post_embed_mm" in e and "not yet supported" in e for e in errs)


def test_an_eligibility_predicate_is_refused_because_it_is_never_evaluated():
    """Its docstring said "resolved and FROZEN into the run's snapshot". Nothing
    resolves it and nothing freezes it."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(
            members=[EligibleItem(sku="RAIL-3000", priority=1)],
            predicate=Cmp(cmp="==", left=FieldRef(path="product.attrs.finish"),
                          right=Lit(value="black")),
        ),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("predicate" in e and "not yet supported" in e for e in errs)


def test_trim_last_and_extension_clip_are_refused_because_they_behave_as_truncate():
    """`space` and `trim_last` produce DIFFERENT BOMs from the same model — that
    is the point of the field. fit_pattern treats them identically today."""
    from fenceai.fencemodel.model import InfillSpec, Member

    for excess in ("trim_last", "extension_clip"):
        model = _model(PanelSpec(infill=InfillSpec(
            orientation="vertical", excess=excess,
            pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                            requirement=PartRequirement(
                                role="infill", qty=1, length_rule="centre_to_centre",
                                eligibility=Eligibility(members=[
                                    EligibleItem(sku="RAIL-3000")])))],
        )))
        errs = validate_model(model, demo_catalog())
        assert any(excess in e and "not yet supported" in e for e in errs), excess


def test_an_assembly_infill_is_refused_because_resolve_panel_buys_the_parts():
    """`supply="assembly"` means the infill is BOUGHT as one pre-made unit rather
    than as N members. `resolve_panel` unconditionally emits a component slot per
    member and nothing reads the field, so authoring it passed validation and
    silently produced a different set of purchased SKUs. It was classified as
    geometry-only in the first pass; it is not geometry, it is the BOM."""
    from fenceai.fencemodel.model import InfillSpec, Member

    model = _model(PanelSpec(infill=InfillSpec(
        orientation="vertical", supply="assembly",
        pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                        requirement=PartRequirement(
                            role="infill", qty=1, length_rule="centre_to_centre",
                            eligibility=Eligibility(members=[
                                EligibleItem(sku="RAIL-3000")])))],
    )))
    errs = validate_model(model, demo_catalog())
    assert any("supply=" in e and "not yet supported" in e for e in errs), errs


def test_the_default_components_infill_supply_is_not_flagged():
    """The rejection must be of the UNBUILT value, not of the field existing —
    or every infill model in phase 2 starts life invalid."""
    from fenceai.fencemodel.model import InfillSpec, Member

    model = _model(PanelSpec(infill=InfillSpec(
        orientation="vertical",
        pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                        requirement=PartRequirement(
                            role="infill", qty=1, length_rule="centre_to_centre",
                            eligibility=Eligibility(members=[
                                EligibleItem(sku="RAIL-3000")])))],
    )))
    assert validate_model(model, demo_catalog()) == []


def test_a_named_eligibility_group_is_refused_because_it_could_change_the_answer():
    """`resolve_supply` groups by the members' (sku, priority, approval)
    signature and never reads `Eligibility.group`. That is not cosmetic:
    grouping decides which lines are costed TOGETHER, and cut planning is not
    additive, so it decides which product wins. See
    test_grouping_changes_which_product_wins in tests/fulfillment/test_supply.py
    for the measurement."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(
            group="rails", members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("Eligibility.group" in e and "not yet supported" in e for e in errs)
