"""Every agreement pins its emitted Expr. A new agreement without a row here is a
missing test, visibly."""

import pytest

from fenceai.knowledge.ast import And, Between, Cmp, FieldRef, FnCall, In, Lit
from fenceai.parts.compile import compile_field, compile_spec
from fenceai.parts.model import Part, SpecField


def f(**kw) -> SpecField:
    return SpecField(**kw)


CASES = [
    (f(key="width_mm", value=38, agree="==", unit="mm"),
     Cmp(cmp="==", left=FieldRef(path="item.width_mm"), right=Lit(value=38))),
    (f(key="material", value="vinyl", agree="!="),
     Cmp(cmp="!=", left=FieldRef(path="item.material"), right=Lit(value="vinyl"))),
    (f(key="face_width_mm", value=90, agree=">=", unit="mm"),
     Cmp(cmp=">=", left=FieldRef(path="item.face_width_mm"), right=Lit(value=90))),
    (f(key="face_width_mm", value=90, agree="<=", unit="mm"),
     Cmp(cmp="<=", left=FieldRef(path="item.face_width_mm"), right=Lit(value=90))),
    (f(key="length_mm", agree="supplies", unit="mm"),
     Cmp(cmp=">=", left=FieldRef(path="item.stock_length_mm"), right=Lit(value=0))),
    (f(key="interface", value="vinyl-routed-5x5", agree="covers"),
     FnCall(name="covers", args=[FieldRef(path="item.interface"),
                                 Lit(value="vinyl-routed-5x5")])),
    (f(key="sku", value=["RAIL-3000", "RAIL-2400"], agree="among"),
     In(item=FieldRef(path="item.sku"), options=["RAIL-3000", "RAIL-2400"])),
    (f(key="width_mm", value=[36, 40], agree="between", unit="mm"),
     Between(item=FieldRef(path="item.width_mm"), low=36, high=40)),
]


@pytest.mark.parametrize("field,expected", CASES, ids=[c[0].agree for c in CASES])
def test_each_agreement_compiles_to_its_term(field, expected):
    assert compile_field(field) == expected


def test_every_agreement_value_has_a_case():
    """The table above must cover the whole vocabulary, or a new operator ships
    compiled by nothing and silently matching everything."""
    from typing import get_args
    from fenceai.parts.model import Agree
    assert {c[0].agree for c in CASES} == set(get_args(Agree))


def test_supplies_is_the_missing_field_check_not_a_disjunction():
    """`stock_length_mm` is defined for BOTH consumption kinds, so one term does it:
    an item declaring neither a purchase length nor a capability length has no such
    key, `lookup` raises MissingField, and `_covers` reads that as not covered."""
    term = compile_field(f(key="length_mm", agree="supplies", unit="mm"))
    assert isinstance(term, Cmp) and term.left.path == "item.stock_length_mm"


def test_a_whole_spec_is_a_conjunction_in_authored_order():
    part = Part(id="p", version=1, type="rail", spec=[
        f(key="type", value="rail", agree="=="),
        f(key="width_mm", value=38, agree="==", unit="mm"),
    ])
    expr = compile_spec(part)
    assert isinstance(expr, And)
    assert [t.left.path for t in expr.items] == ["item.type", "item.width_mm"]


def test_sole_excluding_term_can_still_name_the_one_term_that_excluded_everybody():
    """The conjunction is not incidental. `sole_excluding_term` only diagnoses an And
    of two or more terms, and losing that shape would turn 'your posts are punched
    300mm from where this bay wants its rails' back into a bare 'no match'."""
    from fenceai.catalog.model import Catalog, DivisibleLinear, Product
    from fenceai.fencemodel.match import sole_excluding_term

    catalog = Catalog.of(Product(
        sku="RAIL-3000", name="Rail",
        consumption=DivisibleLinear(purchase_length_mm=3000),
        attrs={"type": "rail", "width_mm": 45}))
    part = Part(id="p", version=1, type="rail", spec=[
        f(key="type", value="rail", agree="=="),
        f(key="width_mm", value=38, agree="==", unit="mm"),
    ])
    found = sole_excluding_term(compile_spec(part), catalog, {})
    assert found is not None
    term, near_misses = found
    assert term.left.path == "item.width_mm"
    assert near_misses == ["RAIL-3000"]
