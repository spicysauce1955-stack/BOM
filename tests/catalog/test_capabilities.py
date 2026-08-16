"""What deterministic code reads about a product is TYPED; what a predicate or
the UI reads may stay in the open bag.

The backend audit's §4.2, drawn precisely. `attrs.get("length_mm")` compiles
whether or not anything ever sets it, a typo is a silent `None`, and by the time
it matters the number is on a cut list. Three keys were read that way — the post
length the length check measures against, the post face the clear opening is
measured to, and the opening a gate kit fits.

`attrs` keeps everything else, deliberately: material, finish and colour are the
catalog's answer, not the code's, and a company that stocks bamboo should add a
product and a locale word rather than ship a release.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import (
    Capabilities, Catalog, IndivisibleDiscrete, Product,
)
from fenceai.fencemodel.match import match_eligibility
from fenceai.fencemodel.model import Eligibility
from fenceai.knowledge.ast import Cmp, FieldRef, Lit

# every key a deterministic reader used to fetch out of the open bag
CODE_READ_KEYS = ("length_mm", "face_width_mm", "opening_width_mm")


def test_a_product_declares_what_code_reads_as_a_typed_field():
    product = Product(sku="P", name="Post", consumption=IndivisibleDiscrete(),
                      capabilities=Capabilities(length_mm=2600, face_width_mm=80))
    assert product.capabilities.length_mm == 2600
    assert product.capabilities.face_width_mm == 80
    # a fact this product simply does not have, said as None rather than absent
    assert product.capabilities.opening_width_mm is None


def test_a_product_that_declares_nothing_still_loads():
    """Every capability is optional because every one is a fact only SOME
    products have: a rail declares no opening width, a gate kit no face width."""
    product = Product(sku="L", name="Latch", consumption=IndivisibleDiscrete())
    assert product.capabilities.length_mm is None


def test_the_demo_catalog_reads_none_of_them_out_of_attrs_any_more():
    """The migration itself. A key left behind in `attrs` is the failure mode
    this closes — code would read the typed field, find nothing, and quietly
    behave as though the product never declared it."""
    for sku, product in demo_catalog().products.items():
        for key in CODE_READ_KEYS:
            assert key not in product.attrs, f"{sku}.attrs still carries {key}"


def test_the_demo_catalog_still_declares_the_facts_it_used_to():
    """...and the migration MOVED them rather than dropping them."""
    products = demo_catalog().products
    assert products["POST-S"].capabilities.length_mm == 2600
    assert products["POST-S"].capabilities.face_width_mm == 80
    assert products["GATE-KIT-1000"].capabilities.opening_width_mm == 1000


def test_a_predicate_can_still_read_a_capability():
    """Typing them for code must not put them out of reach of the matcher: an
    eligibility predicate asking "is this post wide enough" is data reading data,
    and it reads the same fact by the same name."""
    catalog = Catalog.of(
        Product(sku="WIDE", name="Wide post", consumption=IndivisibleDiscrete(),
                capabilities=Capabilities(face_width_mm=100)),
        Product(sku="NARROW", name="Narrow post", consumption=IndivisibleDiscrete(),
                capabilities=Capabilities(face_width_mm=60)),
    )
    wide = Cmp(cmp=">=", left=FieldRef(path="item.face_width_mm"), right=Lit(value=80))
    resolved = match_eligibility(Eligibility(predicate=wide), catalog, {})
    assert [m.sku for m in resolved.members] == ["WIDE"]
