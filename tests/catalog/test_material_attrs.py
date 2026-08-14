"""What a product is MADE OF is catalog data (two-tier visualizer spec §4).

The material drawer shows a material, a finish and a colour swatch for the
product in a slot. None of the three is a Python enum: a company that stocks
bamboo adds a product and a locale word, not a release. What code does own is
the one of them that is not text — a colour is paint, and paint reaches a CSS
`fill`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import IndivisibleDiscrete, Product


def plain(**attrs) -> Product:
    return Product(sku="X", name="Plain", consumption=IndivisibleDiscrete(),
                   attrs=attrs)


# --- the colour is validated, because esc() cannot help it --------------------

def test_a_good_swatch_is_accepted():
    assert plain(colour="#a16207").attrs["colour"] == "#a16207"
    assert plain(colour="#FFFFFF").attrs["colour"] == "#FFFFFF"


@pytest.mark.parametrize("bad", [
    "red",                       # a CSS keyword is not a swatch
    "#abc",                      # the three-digit shorthand this app does not use
    "#a16207;background:url(x)",  # the reason the check exists at all
    "  #a16207",
    "#gggggg",
    12345,                       # attrs are `str | int | bool`; an int is not a colour
])
def test_a_malformed_colour_is_refused_at_load(bad):
    """Escaping makes a string safe to put INSIDE an element; it does nothing
    for a value handed to the painter. `#rrggbb` is the whole vocabulary."""
    with pytest.raises(ValidationError, match="colour must be"):
        plain(colour=bad)


def test_no_colour_at_all_is_ordinary():
    """A product with no swatch is not a broken product — the drawer shows no
    swatch, the same way it shows no material row for a product with no
    material."""
    assert plain().attrs == {}
    assert plain(material="cedar").attrs["material"] == "cedar"


# --- the demo catalog says what its products are ------------------------------

def test_every_demo_colour_is_a_swatch_the_client_can_paint_with():
    for sku, product in demo_catalog().products.items():
        colour = product.attrs.get("colour")
        if colour is not None:
            assert isinstance(colour, str) and colour.startswith("#") \
                and len(colour) == 7, sku


def test_a_material_declares_a_finish_beside_it():
    """The pair is what a stock profile IS — "aluminium" alone does not tell a
    fabricator whether it arrives coated. Not enforced by the schema (a catalog
    may know one and not the other); asserted of the DEMO, which is the data
    every screenshot and every smoke run is taken against."""
    for sku, product in demo_catalog().products.items():
        if "material" in product.attrs:
            assert "finish" in product.attrs, sku


def test_a_product_with_no_material_is_still_a_product():
    """LATCH declares none of the three on purpose: the drawer must leave the
    row out rather than guess, and a demo catalog where every product had a
    material would leave that path untested by the thing people click."""
    bare = [sku for sku, p in demo_catalog().products.items()
            if "material" not in p.attrs]
    assert bare, "no demo product exercises the no-material path"


def test_the_posts_declare_the_width_they_are_seen_at():
    """The macro elevation draws a post at its real width or says it is drawing
    a nominal band — `length_mm` cannot answer that question, because a post's
    length runs into the ground and its face width runs across the drawing."""
    catalog = demo_catalog()
    for sku in ("POST-S", "POST-S-HD", "POST-M"):
        width = catalog.product(sku).attrs.get("face_width_mm")
        assert isinstance(width, int) and width > 0, sku
    assert catalog.product("POST-S-HD").attrs["face_width_mm"] > \
        catalog.product("POST-S").attrs["face_width_mm"], \
        "the heavy-duty post is the heavier section, and the drawing shows it"
