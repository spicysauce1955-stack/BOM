"""A part declares what it is; a dimension is what falls out when three fields line up."""

import pytest
from pydantic import ValidationError

from fenceai.parts.model import Part, PartType, SpecField, is_dimension


def rail() -> Part:
    return Part(
        id="rail-38-vinyl", version=1, type="rail",
        name_i18n={"en": "38mm vinyl rail", "he": "שלב ויניל 38 מ\"מ"},
        spec=[
            SpecField(key="width_mm", value=38, agree="==", unit="mm"),
            SpecField(key="thickness_mm", value=20, agree="==", unit="mm"),
            SpecField(key="face_width_mm", value=90, agree=">=", unit="mm"),
            SpecField(key="length_mm", agree="supplies", unit="mm"),
            SpecField(key="material", value="vinyl", agree="=="),
        ],
    )


def test_a_dimension_is_mm_plus_equality_plus_a_scalar():
    fields = {f.key: f for f in rail().spec}
    assert is_dimension(fields["width_mm"])
    # a floor on the item is not a dimension of the part — the part has no face width
    assert not is_dimension(fields["face_width_mm"])
    # no value at all; the bay resolves the length
    assert not is_dimension(fields["length_mm"])
    # not a measurement
    assert not is_dimension(fields["material"])


def test_dimensions_is_derived_and_carries_only_the_equalities():
    assert rail().dimensions == {"width_mm": 38, "thickness_mm": 20}


def test_the_two_keys_code_knows_by_name_have_typed_doors():
    assert rail().width_mm == 38
    assert rail().thickness_mm == 20


def test_an_undeclared_dimension_is_none_not_zero():
    """Zero is a measurement; None is 'nobody recorded it'. The elevation draws
    declared=False for the second and a real band for the first."""
    bare = Part(id="p", version=1, type="rail", spec=[])
    assert bare.width_mm is None
    assert bare.thickness_mm is None


def test_supplies_may_not_carry_a_value():
    """A part cannot declare its length: the same rail serves a 2400 bay and an
    1800 one, so the number is the slot's, not the part's."""
    with pytest.raises(ValidationError, match="supplies"):
        SpecField(key="length_mm", value=1800, agree="supplies", unit="mm")


def test_supplies_requires_a_millimetre_field():
    with pytest.raises(ValidationError, match="unit"):
        SpecField(key="material", agree="supplies")


def test_every_agreement_except_supplies_requires_a_value():
    with pytest.raises(ValidationError, match="value"):
        SpecField(key="width_mm", agree="==", unit="mm")


def test_between_takes_two_ints():
    ok = SpecField(key="width_mm", value=[36, 40], agree="between", unit="mm")
    assert ok.value == [36, 40]
    with pytest.raises(ValidationError, match="between"):
        SpecField(key="width_mm", value=[36], agree="between", unit="mm")


def test_ref_and_display_name():
    assert rail().ref == "rail-38-vinyl@v1"
    assert rail().display_name("he").startswith("שלב")
    assert rail().display_name("fr") == rail().name_i18n["en"]


def test_part_type_carries_a_localised_label():
    t = PartType(key="rail", label_i18n={"en": "Rails", "he": "שלבים"})
    assert t.label("he") == "שלבים"


def test_a_set_valued_agreement_refuses_a_scalar():
    """`_LIST_VALUED` named this invariant and nothing enforced it. `among` with a
    string compiles to `In(options=['w','h','i','t','e'])` — a part that publishes
    clean and matches nothing, on every bay of every job; with an int it raises
    TypeError out of compilation, which reaches the author as a 500."""
    for value in ("white", 38):
        with pytest.raises(ValueError, match="takes a LIST"):
            SpecField(key="colour", value=value, agree="among")
    with pytest.raises(ValueError, match="takes a LIST"):
        SpecField(key="width_mm", value=38, agree="between", unit="mm")
    # the list forms are untouched
    assert SpecField(key="colour", value=["white"], agree="among").value == ["white"]
    assert SpecField(key="width_mm", value=[30, 40], agree="between",
                     unit="mm").value == [30, 40]


def test_covers_still_takes_a_scalar():
    """`covers` is deliberately NOT list-valued: a scalar on either side is a
    one-element set, which is what lets one operator serve "my token is among
    yours" and "your holes include mine"."""
    assert SpecField(key="finishes", value="black", agree="covers").value == "black"
