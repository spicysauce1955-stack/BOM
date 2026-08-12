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
    DivisibleLinear,
    IndivisibleDiscrete,
    KitComponent,
    PackagedDiscrete,
    Product,
)
from fenceai.decisions.explain import explain_node
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
    """A gate-focused catalog — plus the rail and screw the PANELS need.

    Those two were missing, and nothing noticed: these tests read the strategy
    and the decision graph, never the BOM, so a panel eligible for a product
    this catalog did not stock went unremarked. `generate()` now validates the
    resolved fence model against the catalog it was handed, which is exactly the
    kind of hole that gate exists to find — the fixture was incomplete, the
    behaviour under test was not."""
    return Catalog.of(
        Product(sku="POST-S", name="post", consumption=IndivisibleDiscrete(),
                price_cents=2500, attrs={"length_mm": 2600}),
        Product(sku="POST-S-HD", name="hd post", consumption=IndivisibleDiscrete(),
                price_cents=4200, attrs={"length_mm": 2600}),
        Product(sku="LEAF", name="leaf", consumption=IndivisibleDiscrete(), price_cents=1),
        Product(sku="RAIL-3000", name="rail", price_cents=1800,
                consumption=DivisibleLinear(purchase_length_mm=3000)),
        Product(sku="SCREW-S10", name="screws", price_cents=450,
                consumption=PackagedDiscrete(qty_per_package=20)),
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


# ---- provenance: the decision graph IS the explanation (foundation §15) ----

def _kit_node(result):
    return next(n for n in result.graph.nodes if n.action == "select_gate_kit")


def test_a_payload_kit_is_never_credited_to_a_knowledge_rule(knowledge, catalog):
    """`governed_by=reinf_refs` made the Hebrew explanation read "נבחרה ערכת שער
    GATE-KIT-1000. נקבע לפי K-GATE-REINF@v1" for a SKU typed by the user."""
    result = generate(_gated(1000, "GATE-KIT-1000"), knowledge, catalog)
    node = _kit_node(result)
    assert [e for e in result.graph.in_edges(node.id) if e.type == "governed_by"] == []
    assert node.payload["source"] == "payload"
    assert node.payload["event_id"] == "ev_gate"
    # the gate event the sku was copied from is a direct input of the decision
    gate_facts = {n.id for n in result.graph.nodes if n.action == "gate_event"}
    assert gate_facts & {e.from_id for e in result.graph.in_edges(node.id)}
    for lang in ("en", "he"):
        text = explain_node(result.graph, node, lang)
        assert "K-GATE-REINF" not in text
        assert "ev_gate" in text


def test_a_catalog_selected_kit_says_the_catalog_chose_it(knowledge):
    cat = _catalog_with(Product(
        sku="BAR-PORTAIL-A", name="portail", price_cents=9900,
        consumption=AssemblyKit(components=[KitComponent(sku="LEAF", qty=1)]),
        attrs={"opening_width_mm": 3500},
    ))
    node = _kit_node(generate(_gated(3500, None), knowledge, cat))
    assert node.payload["source"] == "catalog"
    assert node.payload["opening_width_mm"] == 3500


def test_a_gate_clamped_by_the_run_end_is_flagged_and_rechecks_its_kit(knowledge, catalog):
    """A gate authored past the end of its section is clamped to fit. Silently,
    that produced "opening 600 · GATE-KIT-1000" on the setting-out sheet: a gap
    no kit fits, handed to a crew. Both the clamp AND the kit are now reported."""
    topo = straight_topology(1200)
    add_point_event(topo, "run1", "ev_gate", 600,
                    GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    result = generate(topo, knowledge, catalog)

    gate = result.strategy.gates[0]
    assert gate.end_station_mm - gate.start_station_mm == 600
    codes = _codes(result)
    assert "gate_past_run_end" in codes, "the clamp itself must be reported"
    assert "gate_kit_width_mismatch" in codes, "and the kit no longer fits"
    clamp = next(w for w in result.strategy.warnings if w.code == "gate_past_run_end")
    assert clamp.params["asked_mm"] == 1000 and clamp.params["available_mm"] == 600


def test_a_gate_that_fits_says_nothing(knowledge, catalog):
    result = generate(_gated(1000, "GATE-KIT-1000"), knowledge, catalog)
    codes = _codes(result)
    assert "gate_past_run_end" not in codes and "gate_kit_width_mismatch" not in codes
