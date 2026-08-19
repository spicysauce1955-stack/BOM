"""Matching items to a part's SPEC, instead of a human typing SKUs into a slot.

`Eligibility.predicate` has been on the schema since phase 1 and refused at load
ever since, for two stated reasons: nothing evaluated it, and nothing froze it
into the run's snapshot. This module closes both — it EVALUATES the predicate and
returns the concrete members, which is the shape a run already records.

What is pinned here is the matcher in isolation. Its wiring into generation lives
in `tests/strategy/`.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.model import (
    Capabilities, Catalog, DivisibleLinear, IndivisibleDiscrete,
    PackagedDiscrete, Product,
)
from fenceai.fencemodel.match import _item_ctx, match_eligibility, stock_length_mm
from fenceai.fencemodel.model import Eligibility, EligibleItem, _can_supply_length
from fenceai.knowledge.ast import (
    FUNCTIONS, And, Cmp, FieldRef, FnCall, Lit, MissingField, evaluate_expr,
)

VINYL = Cmp(cmp="==", left=FieldRef(path="item.material"), right=Lit(value="vinyl"))


def _catalog() -> Catalog:
    # Deliberately NOT in sku order. A catalog whose insertion order happened to
    # be sorted would let an unsorted matcher pass the ordering tests below.
    return Catalog.of(
        Product(sku="RAIL-V2", name="Wide vinyl rail", price_cents=100,
                consumption=DivisibleLinear(purchase_length_mm=3000),
                attrs={"material": "vinyl", "width_mm": 50}),
        Product(sku="RAIL-A", name="Aluminium rail", price_cents=100,
                consumption=DivisibleLinear(purchase_length_mm=3000),
                attrs={"material": "aluminium", "width_mm": 38}),
        Product(sku="RAIL-V", name="Vinyl rail", price_cents=100,
                consumption=DivisibleLinear(purchase_length_mm=3000),
                attrs={"material": "vinyl", "width_mm": 38}),
        # declares no material at all — ordinary, and it must not match a
        # predicate that asks about one
        Product(sku="CAP-X", name="Unlabelled cap", price_cents=10,
                consumption=IndivisibleDiscrete()),
    )


def _match(predicate, facts=None) -> list[str]:
    resolved = match_eligibility(
        Eligibility(predicate=predicate), _catalog(), facts or {},
    )
    return [m.sku for m in resolved.members]


def test_a_predicate_selects_every_item_whose_specs_cover_it():
    assert _match(VINYL) == ["RAIL-V", "RAIL-V2"]


def test_members_come_back_in_a_deterministic_order():
    """`resolve_supply` groups by the members' (sku, priority, approval)
    signature, and grouping decides which product is chosen — so an order that
    varied between runs would change the answer, not just the JSON."""
    assert _match(VINYL) == sorted(_match(VINYL))


def test_an_item_that_does_not_declare_the_attribute_is_excluded():
    """`MissingField` means "not applicable" in the knowledge evaluator, where the
    question is whether a rule fires. Here the question is whether an item COVERS
    a requirement, and an item that cannot answer has not covered it. CAP-X
    declares no material; a predicate about material must not sweep it in."""
    assert "CAP-X" not in _match(VINYL)


def test_several_terms_all_have_to_hold():
    narrow = And(items=[VINYL, Cmp(cmp=">=", left=FieldRef(path="item.width_mm"),
                                   right=Lit(value=50))])
    assert _match(narrow) == ["RAIL-V2"]


def test_a_predicate_may_read_the_panel_it_is_being_fitted_to():
    """The panel is the mediator: every relation this design needs is
    item-against-panel rather than item-against-item, which is what removes the
    need for any resolution order."""
    fits = Cmp(cmp="<=", left=FieldRef(path="item.width_mm"),
               right=FieldRef(path="panel.clear_width_mm"))
    assert _match(fits, {"panel": {"clear_width_mm": 40}}) == ["RAIL-A", "RAIL-V"]


def test_the_resolved_eligibility_carries_no_predicate():
    """Frozen, not re-evaluated. A stored run records its members; a predicate
    riding along would let a later reader re-run it against a moved catalog and
    get a different candidate set for the same run."""
    resolved = match_eligibility(Eligibility(predicate=VINYL), _catalog(), {})
    assert resolved.predicate is None


def test_authored_members_are_passed_through_untouched():
    """The two modes are exclusive, and the authored one is what every shipped
    model still uses."""
    authored = Eligibility(members=[EligibleItem(sku="RAIL-A", priority=3,
                                                 approval="suggest_only")])
    resolved = match_eligibility(authored, _catalog(), {})
    assert resolved == authored


def test_an_item_may_declare_a_list_spec_and_a_predicate_may_match_it():
    """A routed post's hole heights are a LIST — `[150, 1650]` — and no scalar
    can hold one. The comparison that matters is against a panel fact rather than
    a literal, because what a routed post must agree with is where the panel puts
    its rails."""
    catalog = Catalog.of(
        Product(sku="POST-R", name="Routed post", price_cents=100,
                consumption=IndivisibleDiscrete(),
                attrs={"routed_heights_mm": [150, 1650]}),
        Product(sku="POST-R9", name="Wrongly routed post", price_cents=100,
                consumption=IndivisibleDiscrete(),
                attrs={"routed_heights_mm": [200, 1700]}),
    )
    agrees = Cmp(cmp="==", left=FieldRef(path="item.routed_heights_mm"),
                 right=FieldRef(path="panel.rail_positions_mm"))
    resolved = match_eligibility(
        Eligibility(predicate=agrees), catalog,
        {"panel": {"rail_positions_mm": [150, 1650]}},
    )
    assert [m.sku for m in resolved.members] == ["POST-R"]


def _bar(sku="BAR", length=3000):
    return Product(sku=sku, name=sku,
                   consumption=DivisibleLinear(purchase_length_mm=length))


def _fixed(sku="POST", length=2400):
    return Product(sku=sku, name=sku, consumption=IndivisibleDiscrete(),
                   capabilities=Capabilities(length_mm=length))


def _box(sku="SCREW"):
    return Product(sku=sku, name=sku,
                   consumption=PackagedDiscrete(qty_per_package=100))


def test_stock_length_reads_bar_stock_from_its_consumption():
    assert stock_length_mm(_bar(length=3000)) == 3000


def test_stock_length_reads_a_fixed_piece_from_its_capability():
    assert stock_length_mm(_fixed(length=2400)) == 2400


def test_an_item_with_no_length_anywhere_has_none():
    assert stock_length_mm(_box()) is None


def test_stock_length_and_can_supply_length_cannot_drift():
    """Two definitions of 'how long a piece can you get' would disagree the moment
    either moved. `_can_supply_length` is now expressed in terms of this one."""
    catalog = Catalog.of(_bar(), _fixed(), _box())
    for sku in catalog.products:
        assert _can_supply_length(catalog, sku) == (
            stock_length_mm(catalog.products[sku]) is not None)


def test_stock_length_reaches_a_predicate():
    assert _item_ctx(_bar(length=3000))["stock_length_mm"] == 3000


def test_an_item_without_one_omits_the_key_rather_than_passing_none():
    """A None would compare as a value and quietly satisfy `>= 0`. Absence raises
    MissingField, which `_covers` reads as 'has not covered the requirement'."""
    assert "stock_length_mm" not in _item_ctx(_box())


def test_a_stale_attrs_value_does_not_leak_when_the_product_has_no_real_length():
    """`_RESERVED` names `stock_length_mm`, and the filter that enforces it must
    run BEFORE attrs merges in, not overwrite after — a product with no real
    length must not surface a `stock_length_mm` an author happened to leave in
    attrs, or a `supplies` predicate (`item.stock_length_mm >= 0`) would admit it."""
    item = Product(sku="SCREW", name="SCREW", consumption=PackagedDiscrete(qty_per_package=100),
                   attrs={"stock_length_mm": 9999})
    assert "stock_length_mm" not in _item_ctx(item)


def test_a_stale_attrs_value_does_not_override_the_real_length():
    """A product WITH a real length reports the real one, never an attrs value
    that happens to disagree with it."""
    item = Product(sku="BAR", name="BAR", consumption=DivisibleLinear(purchase_length_mm=3000),
                   attrs={"stock_length_mm": 9999})
    assert _item_ctx(item)["stock_length_mm"] == 3000


def test_supplies_admits_bar_stock_and_fixed_pieces_and_refuses_a_box():
    from fenceai.parts.compile import compile_field
    from fenceai.parts.model import SpecField
    term = compile_field(SpecField(key="length_mm", agree="supplies", unit="mm"))
    assert evaluate_expr(term, {"item": _item_ctx(_bar())}) is True
    assert evaluate_expr(term, {"item": _item_ctx(_fixed())}) is True
    with pytest.raises(MissingField):
        evaluate_expr(term, {"item": _item_ctx(_box())})


def test_covers_is_registered():
    assert "covers" in FUNCTIONS


def test_covers_accepts_a_scalar_inside_the_items_list():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"interface": ["vinyl-routed-5x5", "vinyl-routed-4x4"]})
    term = FnCall(name="covers", args=[FieldRef(path="item.interface"),
                                       Lit(value="vinyl-routed-5x5")])
    assert evaluate_expr(term, {"item": _item_ctx(item)}) is True


def test_covers_refuses_a_token_the_item_does_not_declare():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"interface": ["vinyl-routed-4x4"]})
    term = FnCall(name="covers", args=[FieldRef(path="item.interface"),
                                       Lit(value="vinyl-routed-5x5")])
    assert evaluate_expr(term, {"item": _item_ctx(item)}) is False


def test_covers_needs_every_one_of_the_parts_values():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"routed_at": [150, 900, 1650]})
    ok = FnCall(name="covers", args=[FieldRef(path="item.routed_at"),
                                     Lit(value=[150, 1650])])
    no = FnCall(name="covers", args=[FieldRef(path="item.routed_at"),
                                     Lit(value=[150, 1700])])
    assert evaluate_expr(ok, {"item": _item_ctx(item)}) is True
    assert evaluate_expr(no, {"item": _item_ctx(item)}) is False


def test_covers_treats_a_scalar_item_value_as_a_one_element_set():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"material": "vinyl"})
    term = FnCall(name="covers", args=[FieldRef(path="item.material"),
                                       Lit(value="vinyl")])
    assert evaluate_expr(term, {"item": _item_ctx(item)}) is True


def test_field_paths_sees_through_a_function_call():
    """`validate_model` refuses a post predicate that reads outside its allowed set,
    and it asks `field_paths`. A read hidden inside an args list would slip past."""
    from fenceai.knowledge.ast import field_paths
    term = FnCall(name="covers", args=[FieldRef(path="item.interface"), Lit(value="x")])
    assert field_paths(term) == {"item.interface"}


def test_an_unregistered_function_raises_rather_than_passing():
    with pytest.raises(MissingField):
        evaluate_expr(FnCall(name="nope", args=[]), {})


# --- the item context is memoised, per PRODUCT (fix wave, F6) -----------------

def test_the_item_context_is_computed_once_per_product():
    """Predicates turned matching into a full-catalog scan per slot per bay —
    957 000 `_item_ctx` calls on one 120 m run against a realistic catalog, almost
    all of them a `model_dump()` of three optional integers already computed."""
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"material": "vinyl"})
    assert _item_ctx(item) is _item_ctx(item)


def test_replacing_a_product_under_the_same_sku_is_not_served_the_old_context():
    """The one failure a memo must not have. A catalog is edited by REPLACING a
    product — `catalog.products[sku] = ...`, which is what the /api/catalog route
    and half the strategy tests do — so a memo keyed by sku would answer the new
    product's question with the old product's facts, and the run would buy against
    a spec nobody wrote."""
    old = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                  attrs={"material": "vinyl"})
    new = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                  attrs={"material": "aluminium"})
    catalog = Catalog.of(old)
    wants_vinyl = Eligibility(predicate=Cmp(
        cmp="==", left=FieldRef(path="item.material"), right=Lit(value="vinyl")))

    assert [m.sku for m in match_eligibility(wants_vinyl, catalog, {}).members] == ["P"]
    catalog.products["P"] = new
    assert match_eligibility(wants_vinyl, catalog, {}).members == []
