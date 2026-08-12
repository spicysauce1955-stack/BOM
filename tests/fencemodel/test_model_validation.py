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
    the slot does not allow."""
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
