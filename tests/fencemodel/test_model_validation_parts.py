"""`validate_model` against a model whose slots NAME parts.

Three of its rules ask about numbers a slot stopped carrying when the part became
the entity that declares them — a member's width, a frame member's thickness, and
which products a slot admits. All three now arrive at resolution time, so the
question this file settles is which document gets validated: the one an author
typed, or the one a bay is built from.

Deliberately free of `fencemodel.demo` and of `Store`: the models here are built in
the test, so a change to the demo library cannot make these pass or fail.
"""

import pytest

from fenceai.catalog.model import Catalog, DivisibleLinear, IndivisibleDiscrete, Product
from fenceai.fencemodel.model import (
    Axis, Distributed, FenceModel, FrameSlot, InfillSpec, Member, OptionValue,
    PanelSpec, PartRequirement, validate_model,
)
from fenceai.parts.model import Part, PartLibrary, SpecField


def catalog() -> Catalog:
    return Catalog.of(
        Product(sku="RAIL-3000", name="Rail",
                consumption=DivisibleLinear(purchase_length_mm=3000),
                price_cents=1800, attrs={"thickness_mm": 40, "material": "aluminium"}),
        Product(sku="SLAT-100", name="Slat",
                consumption=DivisibleLinear(purchase_length_mm=2400),
                price_cents=900, attrs={"width_mm": 100, "material": "aluminium"}),
        Product(sku="SCREW-S10", name="Screw", consumption=IndivisibleDiscrete(),
                price_cents=12, attrs={"material": "steel"}),
    )


def library(**overrides) -> PartLibrary:
    parts = [
        Part(id="rail-40", version=1, type="rail",
             spec=[SpecField(key="thickness_mm", value=40, agree="==", unit="mm"),
                   SpecField(key="material", value="aluminium", agree="==")]),
        Part(id="slat-100", version=1, type="infill",
             spec=[SpecField(key="width_mm", value=100, agree="==", unit="mm"),
                   SpecField(key="material", value="aluminium", agree="==")]),
    ]
    parts += overrides.get("extra", [])
    return PartLibrary(parts=[p for p in parts if p.id not in overrides.get("drop", ())])


def model(rail_part="rail-40", slat_part="slat-100") -> FenceModel:
    """A channelled frame and a slat infill — the two shapes whose numbers moved.

    The frame slot is housed (`channel_depth_mm`), which is only checkable once the
    member's thickness is known, and the infill member has a width only the part
    declares. Authored, both are 0.
    """
    return FenceModel(
        id="M-TEST", version=1, name_i18n={"en": "Test"},
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal",
                placement=Distributed(count=2),
                joint="channel", channel_depth_mm=10, insertion_margin_mm=3,
                requirement=PartRequirement(part_id=rail_part,
                                            length_rule="centre_to_centre"),
            )],
            infill=InfillSpec(orientation="vertical", pattern=[Member(
                key="slat", gap_after_mm=20,
                requirement=PartRequirement(part_id=slat_part,
                                            length_rule="panel_height"),
            )]),
        ),
    )


# --- with a library: the resolved document is the one that is checked ---------

def test_a_model_whose_parts_resolve_validates_clean():
    assert validate_model(model(), catalog(), library()) == []


def test_the_authored_document_would_have_been_refused_on_every_rule():
    """The reason the parameter exists. Validating what the author typed refuses a
    member 0 wide, a channel in a member of undeclared thickness, and a slot with
    no eligible product — three refusals for facts that are simply not looked up
    yet, on a model that is perfectly buildable."""
    unresolved = validate_model(model(), catalog())
    assert unresolved == [], (
        "the part-derived rules must be SKIPPED without a library, not fired: "
        f"{unresolved}"
    )


def test_a_part_with_no_active_version_is_refused_by_name():
    errors = validate_model(model(rail_part="rail-nope"), catalog(), library())
    assert len(errors) == 1
    assert "rail-nope" in errors[0] and "no active version" in errors[0]


def test_a_retired_part_is_no_more_resolvable_than_a_missing_one():
    lib = library()
    lib.parts[0].status = "retired"
    errors = validate_model(model(), catalog(), lib)
    assert any("rail-40" in e for e in errors)


def test_an_unresolvable_part_ends_the_check_rather_than_cascading():
    """A page of consequential errors under the one real cause is how an author is
    sent to the wrong file. Nothing further is answerable about a document that
    cannot be resolved."""
    broken = model(rail_part="rail-nope")
    broken.option_axes = [Axis(key="colour", kind="enum", values=[
        OptionValue(key="white", swatch="not-a-colour")])]
    errors = validate_model(broken, catalog(), library())
    assert len(errors) == 1
    assert "swatch" not in errors[0]


def test_a_part_no_product_covers_is_refused():
    """The guardrail did not disappear when the member list did — it moved one
    level down, onto the object that says what may supply the slot."""
    lib = library(extra=[Part(id="rail-99", version=1, type="rail", spec=[
        SpecField(key="width_mm", value=999, agree="==", unit="mm")])])
    errors = validate_model(model(rail_part="rail-99"), catalog(), lib)
    assert any("rail-99@v1" in e and "no product in the catalog covers" in e
               for e in errors)


def test_one_part_backing_two_slots_is_refused_once():
    """An author cannot fix the same part twice, and a repeated refusal reads as
    two problems."""
    lib = library(extra=[Part(id="rail-99", version=1, type="rail", spec=[
        SpecField(key="width_mm", value=999, agree="==", unit="mm")])])
    errors = validate_model(model(rail_part="rail-99", slat_part="rail-99"),
                            catalog(), lib)
    assert len([e for e in errors if "rail-99@v1" in e]) == 1


def test_the_resolved_thickness_is_what_the_channel_is_measured_against():
    """A channel deeper than the member it is cut into comes out the far side. The
    number it is checked against is the PART's, so this rule only became answerable
    when the library arrived — and it must still bite."""
    lib = library()
    deep = model()
    deep.default_spec.frame[0].channel_depth_mm = 60      # part declares 40
    errors = validate_model(deep, catalog(), lib)
    assert any("deeper than the member it is cut into" in e for e in errors)
    assert validate_model(deep, catalog()) == [], "unanswerable without a library"


def test_the_resolved_width_is_what_the_pattern_advance_is_measured_against():
    lib = library()
    swallowed = model()
    swallowed.default_spec.infill.pattern[0].gap_after_mm = -100   # part declares 100
    errors = validate_model(swallowed, catalog(), lib)
    assert any("never advance" in e for e in errors)


# --- without a library: everything that is still answerable still runs --------

@pytest.mark.parametrize("with_library", [True, False])
def test_an_authored_rule_fires_either_way(with_library):
    """`library=None` skips the three part-derived rules and nothing else. A
    caller without a library is not a caller without validation."""
    bad = model()
    bad.option_axes = [Axis(key="colour", kind="enum", values=[
        OptionValue(key="white", swatch="not-a-colour")])]
    bad.default_spec.infill.pattern[0].base_ref = "nosuchslot"
    errors = validate_model(bad, catalog(), library() if with_library else None)
    assert any("swatch" in e for e in errors)
    assert any("nosuchslot" in e for e in errors)


def test_a_slot_with_no_predicate_and_no_members_is_not_an_authoring_error():
    """It is an UNRESOLVED slot. Refusing it was refusing every model in the
    portfolio for the shape resolution is supposed to fill."""
    assert not any("no eligible product" in e for e in validate_model(model(), catalog()))


# --- the authoring gate a part-named slot used to walk past (fix wave M1/M2/M8) --

def test_a_part_named_slot_still_answers_for_its_option_axis():
    """After resolution EVERY part slot carries a predicate, so the loop's
    `continue` past the option checks was the normal path and not the rare one.
    `resolve._chosen_option` cites both of these BY NAME as load-time guarantees,
    and without them it fell through to `unnarrowed` — the user's option choice
    silently ignored rather than refused."""
    m = model()
    req = m.default_spec.frame[0].requirement
    req.option_axis = "colour_that_does_not_exist"
    req.sku_by_option = {"white": "NOT-A-SKU"}
    errors = validate_model(m, catalog(), library())
    assert any("option_axis colour_that_does_not_exist is not declared" in e
               for e in errors), errors
    assert any("NOT-A-SKU" in e and "not an eligible member" in e
               for e in errors), errors


def test_a_part_named_slot_still_answers_for_its_length_rule():
    """The same `continue` dropped `_can_supply_length`. A rail part that admits
    the screw asks a `centre_to_centre` cut of a product that cannot be cut."""
    screw_rail = Part(id="rail-steel", version=1, type="rail",
                      spec=[SpecField(key="material", value="steel", agree="==")])
    errors = validate_model(model(rail_part="rail-steel"), catalog(),
                            library(extra=[screw_rail]))
    assert any("SCREW-S10" in e and "cannot supply a length" in e
               for e in errors), errors


def test_a_slot_cannot_name_a_part_and_also_author_what_it_is():
    """Accepted, validated clean, and then silently destroyed: resolution
    overwrites `eligibility` and `role` for every part slot, so a `suggest_only`
    approval a human insisted on went out with the rest of the members list."""
    from fenceai.fencemodel.model import Eligibility, EligibleItem

    with pytest.raises(ValueError, match="eligibility.members"):
        PartRequirement(part_id="rail-40", eligibility=Eligibility(
            members=[EligibleItem(sku="RAIL-3000", approval="suggest_only")]))
    with pytest.raises(ValueError, match="role"):
        PartRequirement(part_id="rail-40", role="screw")
    # a slot that names NO part authors all of it, which is what M-LEGACY's rail
    # and M-VINYL's post do
    assert PartRequirement(role="rail").role == "rail"


def test_a_holder_cannot_name_a_part_and_also_author_the_dimension_it_fills():
    """`_apply_dimensions` writes `part.thickness_mm or 0` unconditionally, so a
    part declaring no thickness ZEROED an authored one — and 0 is not neutral
    here, it is what the elevation renders as `declared=False`."""
    with pytest.raises(ValueError, match="thickness_mm"):
        FrameSlot(key="rail", orientation="horizontal",
                  placement=Distributed(count=2), thickness_mm=40,
                  requirement=PartRequirement(part_id="rail-40"))
    with pytest.raises(ValueError, match="width_mm"):
        Member(key="slat", width_mm=100,
               requirement=PartRequirement(part_id="slat-100"))
    # naming no part leaves the authored number alone — `_apply_dimensions` skips
    # it for the same reason
    assert Member(key="slat", width_mm=100,
                  requirement=PartRequirement(role="infill")).width_mm == 100
