"""A published part is refused for the same reasons a slot with no eligible product
is refused: at authoring time, when the author can still say what belongs there."""

from fenceai.catalog.model import Capabilities, Catalog, DivisibleLinear, IndivisibleDiscrete, Product
from fenceai.parts.model import Part, SpecField
from fenceai.parts.validate import matching_skus, validate_part


def catalog() -> Catalog:
    return Catalog.of(
        Product(sku="RAIL-3000", name="Rail 3000",
                consumption=DivisibleLinear(purchase_length_mm=3000),
                attrs={"width_mm": 38, "material": "vinyl", "type": "rail"}),
        Product(sku="RAIL-2400", name="Rail 2400",
                consumption=DivisibleLinear(purchase_length_mm=2400),
                attrs={"width_mm": 38, "material": "steel", "type": "rail"}),
        Product(sku="POST-V", name="Post vinyl", consumption=IndivisibleDiscrete(),
                capabilities=Capabilities(length_mm=2400, face_width_mm=127),
                attrs={"material": "vinyl", "type": "post"}),
    )


def part(*spec, status="active") -> Part:
    return Part(id="p", version=1, type="rail", status=status, spec=list(spec))


def test_a_part_whose_spec_matches_a_product_is_accepted():
    p = part(SpecField(key="width_mm", value=38, agree="==", unit="mm"),
             SpecField(key="material", value="vinyl", agree="=="))
    assert validate_part(p, catalog()) == []


def test_a_published_part_matching_nothing_is_refused():
    p = part(SpecField(key="width_mm", value=99, agree="==", unit="mm"))
    errors = validate_part(p, catalog())
    assert any("no product" in e for e in errors)


def test_a_draft_may_match_nothing():
    """The draft bargain: an author writes the spec before the item exists."""
    p = part(SpecField(key="width_mm", value=99, agree="==", unit="mm"), status="draft")
    assert validate_part(p, catalog()) == []


def test_a_duplicate_key_is_refused():
    """Two authorities over one field: it would draw one number and buy another."""
    p = part(SpecField(key="width_mm", value=38, agree="==", unit="mm"),
             SpecField(key="width_mm", value=40, agree=">=", unit="mm"))
    assert any("width_mm" in e and "twice" in e for e in validate_part(p, catalog()))


def test_a_published_part_with_an_empty_spec_is_refused():
    """An empty conjunction is `all([])` — true for every product in the catalog.
    A part that matches everything is not a specification."""
    assert any("empty" in e for e in validate_part(part(), catalog()))


def test_matching_skus_is_sorted_and_narrows_as_terms_are_added():
    c = catalog()
    wide = part(SpecField(key="type", value="rail", agree="=="))
    assert matching_skus(wide, c) == ["RAIL-2400", "RAIL-3000"]
    narrow = part(SpecField(key="type", value="rail", agree="=="),
                  SpecField(key="material", value="vinyl", agree="=="))
    assert matching_skus(narrow, c) == ["RAIL-3000"]


def test_a_missing_field_is_a_no_not_a_pass():
    """POST-V declares no width_mm. It must not be swept into a slot that asked."""
    p = part(SpecField(key="width_mm", value=38, agree="==", unit="mm"))
    assert "POST-V" not in matching_skus(p, catalog())
