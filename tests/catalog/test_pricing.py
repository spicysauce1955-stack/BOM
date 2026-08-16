"""Pricing by the running metre.

`Product.price_cents` is flat per purchase unit; the Israeli market quotes bar
stock at ₪/מטר רץ. A rate is a way of AUTHORING the purchase price of a whole
bar, not a second basis for the BOM to carry — which is exactly why per-m² and
per-band pricing are not here (see the LinearPrice docstring).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import (
    Catalog,
    DivisibleLinear,
    IndivisibleDiscrete,
    LinearPrice,
    Product,
    purchase_price_cents,
)
from fenceai.demand.derive import DemandLine
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.supply import resolve_supply


def rate_product(cents_per_m: int, length_mm: int = 3000) -> Product:
    return Product(
        sku="RATE-RAIL", name="Rail by the metre",
        consumption=DivisibleLinear(purchase_length_mm=length_mm, kerf_mm=3),
        pricing=LinearPrice(cents_per_m=cents_per_m),
    )


# --- the price of one bar -----------------------------------------------------

def test_a_flat_product_keeps_its_price():
    """The default basis is unchanged, which is the whole point of a default."""
    assert purchase_price_cents(demo_catalog().products["RAIL-3000"]) == 1800


def test_a_rate_prices_a_whole_bar():
    assert purchase_price_cents(rate_product(600)) == 1800          # 6.00/m x 3 m
    assert purchase_price_cents(rate_product(600, 2000)) == 1200


def test_the_rate_rounds_half_up_exactly_once():
    """ADR-0002: one documented rounding point. Two call sites rounding
    differently would total the same BOM two ways."""
    assert purchase_price_cents(rate_product(1, 1500)) == 2        # 1.5c -> 2c
    assert purchase_price_cents(rate_product(1, 1499)) == 1        # 1.499c -> 1c
    assert purchase_price_cents(rate_product(1, 500)) == 1         # 0.5c -> 1c
    assert purchase_price_cents(rate_product(1, 499)) == 0


# --- one price, never two -----------------------------------------------------

def test_a_rate_priced_product_may_not_also_carry_a_flat_price():
    """Two fields that can each claim to be the price is a lie waiting to happen
    — the same reason an eligibility member declares no consumption semantics of
    its own."""
    with pytest.raises(ValidationError, match="two prices cannot both be the price"):
        Product(sku="X", name="X", price_cents=100,
                consumption=DivisibleLinear(purchase_length_mm=3000),
                pricing=LinearPrice(cents_per_m=600))


def test_a_rate_needs_something_with_a_length_to_be_a_rate_of():
    with pytest.raises(ValidationError, match="not bought by the length"):
        Product(sku="X", name="X", consumption=IndivisibleDiscrete(),
                pricing=LinearPrice(cents_per_m=600))


# --- through the pipeline -----------------------------------------------------

def _line(**kw) -> DemandLine:
    base = dict(id="req0001", engineering_qty=2, cut_length_mm=1500, role="rail", slot_key="rail",
                eligibility=Eligibility(members=[EligibleItem(sku="RATE-RAIL")]))
    return DemandLine(**{**base, **kw})


def test_the_bom_prices_a_rate_product_per_bar():
    catalog = Catalog.of(rate_product(600))
    out = resolve_supply([_line()], catalog)
    bom = fulfill(out.requirements, catalog)
    line = bom.lines[0]
    # two 1500 mm pieces need 1503 mm each against a 3003 mm capacity, so 2 bars
    assert line.purchase_qty == 2
    assert line.unit_price_cents == 1800
    assert line.total_cents == 3600


def test_a_rate_product_competes_on_its_real_cost():
    """Selection ranks candidates by planned cost, so a rate-priced candidate has
    to be costed the same way a flat one is — otherwise it would win or lose on
    the accident of how its price was written down."""
    catalog = Catalog.of(
        rate_product(600),                                   # 1800c per 3 m bar
        Product(sku="FLAT-RAIL", name="Flat rail", price_cents=2500,
                consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3)),
    )
    line = _line(eligibility=Eligibility(members=[
        EligibleItem(sku="FLAT-RAIL", priority=1),
        EligibleItem(sku="RATE-RAIL", priority=2),
    ]))
    out = resolve_supply([line], catalog)
    assert out.requirements[0].sku == "RATE-RAIL"
    costs = {c.sku: c.cost_cents for c in out.decisions[0].candidates}
    assert costs["RATE-RAIL"] == 3600 and costs["FLAT-RAIL"] == 5000


def test_the_same_bar_priced_either_way_totals_the_same():
    """The basis is authoring, not arithmetic: a bar at 6.00/m and a bar at 1800c
    are the same bar at the same price, and no view may say otherwise."""
    rate = Catalog.of(rate_product(600))
    flat = Catalog.of(Product(
        sku="RATE-RAIL", name="Rail", price_cents=1800,
        consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3)))
    a = fulfill(resolve_supply([_line()], rate).requirements, rate)
    b = fulfill(resolve_supply([_line()], flat).requirements, flat)
    assert a.total_cents == b.total_cents
