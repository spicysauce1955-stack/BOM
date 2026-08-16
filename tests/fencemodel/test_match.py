"""Matching items to a part's SPEC, instead of a human typing SKUs into a slot.

`Eligibility.predicate` has been on the schema since phase 1 and refused at load
ever since, for two stated reasons: nothing evaluated it, and nothing froze it
into the run's snapshot. This module closes both — it EVALUATES the predicate and
returns the concrete members, which is the shape a run already records.

What is pinned here is the matcher in isolation. Its wiring into generation lives
in `tests/strategy/`.
"""

from __future__ import annotations

from fenceai.catalog.model import Catalog, DivisibleLinear, IndivisibleDiscrete, Product
from fenceai.fencemodel.match import match_eligibility
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit

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
