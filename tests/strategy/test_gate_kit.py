"""A gate kit must actually fit the opening it is priced against (persona-lab B3).

`kit = ev.payload.kit_sku or f"GATE-KIT-{width_mm}"` was pure passthrough: a 3500 mm
opening was priced as a 1000 mm kit, silently, and the quote went to a customer.

The fit is decided by a **declared catalog attribute** (`opening_width_mm`), never by
parsing a SKU string — a SKU is an opaque id and "GATE-KIT-1000" is a naming accident
of the demo catalog, not data. A product that declares nothing is not second-guessed.
"""

from __future__ import annotations

from fenceai.catalog.model import (
    AssemblyKit,
    Catalog,
    IndivisibleDiscrete,
    KitComponent,
    Product,
)
from fenceai.strategy.generator import generate
from fenceai.topology.model import GatePayload
from tests.conftest import add_point_event, straight_topology


def _gated(width_mm: int, kit_sku: str | None):
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "ev_gate", 2000,
                    GatePayload(width_mm=width_mm, kit_sku=kit_sku))
    return topo


def _codes(result) -> set[str]:
    return {w.code for w in result.strategy.warnings}


def test_kit_narrower_than_the_opening_is_an_error(knowledge, catalog):
    result = generate(_gated(3500, "GATE-KIT-1000"), knowledge, catalog)
    w = next(w for w in result.strategy.warnings if w.code == "gate_kit_width_mismatch")
    assert w.severity == "error"
    assert w.params == {
        "element": "gate@run1:2000-5500",
        "sku": "GATE-KIT-1000",
        "kit_width_mm": 1000,
        "opening_width_mm": 3500,
    }
    assert w.element_refs == ["gate@run1:2000-5500"]
    assert w.decision_ref  # the graph carries the conflict, not just the warning list


def test_kit_that_fits_raises_nothing(knowledge, catalog):
    result = generate(_gated(1000, "GATE-KIT-1000"), knowledge, catalog)
    assert "gate_kit_width_mismatch" not in _codes(result)


def _catalog_with(kit: Product) -> Catalog:
    return Catalog.of(
        Product(sku="POST-S", name="post", consumption=IndivisibleDiscrete(),
                price_cents=2500, attrs={"length_mm": 2600}),
        Product(sku="POST-S-HD", name="hd post", consumption=IndivisibleDiscrete(),
                price_cents=4200, attrs={"length_mm": 2600}),
        Product(sku="LEAF", name="leaf", consumption=IndivisibleDiscrete(), price_cents=1),
        kit,
    )


def test_kit_without_a_declared_width_is_not_second_guessed(knowledge):
    """Datasets that do not carry the attribute keep working — the check is data
    driven, and silence here is a catalog-data gap, not a false accusation."""
    cat = _catalog_with(Product(
        sku="ANY-GATE", name="gate", price_cents=1,
        consumption=AssemblyKit(components=[KitComponent(sku="LEAF", qty=1)]),
    ))
    result = generate(_gated(3500, "ANY-GATE"), knowledge, cat)
    assert "gate_kit_width_mismatch" not in _codes(result)


def test_kit_is_chosen_from_the_catalog_by_its_declared_width(knowledge):
    """No `kit_sku` on the payload: the kit comes from the catalog by attribute, so
    a catalog whose gates are named nothing like "GATE-KIT-<n>" still works."""
    cat = _catalog_with(Product(
        sku="BAR-PORTAIL-A", name="portail", price_cents=9900,
        consumption=AssemblyKit(components=[KitComponent(sku="LEAF", qty=1)]),
        attrs={"opening_width_mm": 3500},
    ))
    result = generate(_gated(3500, None), knowledge, cat)
    assert [g.kit_sku for g in result.strategy.gates] == ["BAR-PORTAIL-A"]
    assert "gate_kit_width_mismatch" not in _codes(result)
    assert "no_gate_kit" not in _codes(result)


def test_no_kit_in_the_catalog_fits_the_opening(knowledge, catalog):
    """The demo catalog holds one 1000 mm kit: a 3500 mm opening cannot be priced
    at all, and saying so is the whole point — a synthesized SKU hid it."""
    result = generate(_gated(3500, None), knowledge, catalog)
    w = next(w for w in result.strategy.warnings if w.code == "no_gate_kit")
    assert w.severity == "error"
    assert w.params == {"element": "gate@run1:2000-5500", "opening_width_mm": 3500}
    assert [g.kit_sku for g in result.strategy.gates] == [""]
