"""The structure report — layout and the items each element consists of.

The report is a READ MODEL: it must never become a second BOM. Its governing
property is that the per-element parts sum back to the BOM's engineering
quantities, with anything unpegged reported as unassigned rather than dropped.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, InventoryItem, fulfill
from fenceai.knowledge.demo import demo_knowledge
from fenceai.report.structure import build_structure
from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    BasePayload, BaseTopPayload, BaseTopPoint, GatePayload, Node, Run, Topology,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology


def _report(topo, inventory: Inventory | None = None, run_id: str = "run-x"):
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    bom = fulfill(requirements, catalog, inventory)
    report = build_structure(topo, result.strategy, requirements, bom, run_id=run_id)
    return report, result, requirements, bom


def _straight_with_gate(length_mm: int = 6000):
    topo = straight_topology(length_mm)
    add_point_event(topo, "run1", "ev_gate", 2000,
                    GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    return topo


# --- setting out ------------------------------------------------------------

def test_sections_posts_bays_and_gates_are_tagged_in_order():
    report, _, _, _ = _report(_straight_with_gate())
    section = report.sections[0]
    assert section.tag == "A" and section.run_id == "run1"
    assert [s.tag for s in section.setting_out] == \
        [f"A/P{i}" for i in range(1, len(section.setting_out) + 1)]
    assert [b.tag for b in section.bays] == \
        [f"A/B{i}" for i in range(1, len(section.bays) + 1)]
    assert [g.tag for g in section.gates] == ["A/G1"]
    stations = [s.station_mm for s in section.setting_out]
    assert stations == sorted(stations), "setting out must read along the run"


def test_stations_are_cumulative_and_spacings_are_their_differences():
    """The crew measures from one end: the running station and the spacing between
    consecutive posts must agree, or the tape and the table disagree on site."""
    report, _, _, _ = _report(_straight_with_gate())
    section = report.sections[0]
    assert section.setting_out[0].station_mm == 0
    assert section.setting_out[0].spacing_mm is None
    assert section.setting_out[-1].station_mm == section.length_mm
    for previous, current in zip(section.setting_out, section.setting_out[1:]):
        assert current.spacing_mm == current.station_mm - previous.station_mm


def test_bays_name_the_posts_they_run_between():
    report, _, _, _ = _report(_straight_with_gate())
    section = report.sections[0]
    by_tag = {s.tag: s.station_mm for s in section.setting_out}
    for bay in section.bays:
        assert by_tag[bay.from_tag] == bay.start_station_mm
        assert by_tag[bay.to_tag] == bay.end_station_mm
        assert bay.width_mm == bay.end_station_mm - bay.start_station_mm


def test_a_node_post_appears_in_both_sections_that_share_it():
    """A corner post is one post; both sections must set it out, or one crew is
    missing a hole."""
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=4000, y_mm=0),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")])
    report, _, _, _ = _report(topo)
    assert [s.tag for s in report.sections] == ["A", "B"]
    shared = "post@node:n2"
    a = [s for s in report.sections[0].setting_out if s.element_id == shared]
    b = [s for s in report.sections[1].setting_out if s.element_id == shared]
    assert len(a) == 1 and len(b) == 1
    assert a[0].station_mm == report.sections[0].length_mm  # the end of A
    assert b[0].station_mm == 0                             # the start of B


# --- the items each element consists of --------------------------------------

def test_every_post_lists_what_it_consists_of():
    report, _, _, _ = _report(_straight_with_gate())
    post = report.sections[0].setting_out[0]
    skus = {p.sku for p in post.parts}
    assert post.sku in skus, "a post consists of, at least, itself"
    assert "POST-CAP" in skus


def test_a_bay_lists_its_rails_with_their_cut_length_and_bar():
    report, _, _, _ = _report(_straight_with_gate())
    bay = report.sections[0].bays[0]
    rails = [p for p in bay.parts if p.unit == "cut"]
    assert rails, "a bay is rails and screws"
    rail = rails[0]
    assert rail.cut_length_mm == bay.width_mm or rail.cut_length_mm == bay.slope_len_mm
    assert rail.length_basis in ("width", "slope")
    assert rail.from_bars, "a cut piece knows which bar it comes from"
    assert all(b.startswith(rail.sku) for b in rail.from_bars)


def test_parts_of_one_element_merge_per_sku_and_cut_length():
    """Two rails of the same cut read as one line of 2, not two lines of 1."""
    report, _, _, _ = _report(_straight_with_gate())
    for bay in report.sections[0].bays:
        keys = [(p.sku, p.unit, p.cut_length_mm) for p in bay.parts]
        assert len(keys) == len(set(keys))


def test_the_parts_sum_back_to_the_bom():
    """THE property: the report groups the BOM by element, it never recomputes it."""
    report, _, requirements, bom = _report(_straight_with_gate())
    from collections import defaultdict

    per_sku: dict[str, int] = defaultdict(int)
    for section in report.sections:
        for element in [*section.setting_out, *section.bays, *section.gates]:
            for part in element.parts:
                per_sku[part.sku] += part.qty
    for line in bom.lines:
        counted = per_sku.get(line.sku, 0)
        extra = sum(u.qty for u in report.totals.unassigned if u.sku == line.sku)
        assert counted + extra == line.engineering_qty, line.sku


def test_totals_agree_with_the_sections():
    report, result, _, _ = _report(_straight_with_gate())
    assert report.totals.posts == len(result.strategy.posts)
    assert report.totals.bays == len(result.strategy.spans)
    assert report.totals.gates == len(result.strategy.gates)
    assert report.totals.fence_length_mm == sum(s.length_mm for s in report.sections)
    heights = {b.height_mm for s in report.sections for b in s.bays}
    assert report.totals.height_min_mm == min(heights)
    assert report.totals.height_max_mm == max(heights)


def test_unassigned_demand_is_reported_not_hidden():
    """A packaged SKU rounds up to whole boxes: the extra belongs to no element and
    must still appear, or the report and the invoice disagree."""
    report, _, _, bom = _report(_straight_with_gate())
    screws = next((l for l in bom.lines if l.sku == "SCREW-S10"), None)
    assert screws is not None
    counted = sum(p.qty for s in report.sections for e in [*s.setting_out, *s.bays, *s.gates]
                  for p in e.parts if p.sku == "SCREW-S10")
    extra = sum(u.qty for u in report.totals.unassigned if u.sku == "SCREW-S10")
    assert counted + extra == screws.engineering_qty


# --- the built base and the section header ------------------------------------

def test_a_section_reports_its_base_and_what_its_posts_stand_on():
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "base", 0, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "top", 0, 6000, BaseTopPayload(
        points=[BaseTopPoint(pos_permille=0, z_mm=600),
                BaseTopPoint(pos_permille=1000, z_mm=600)]))
    report, _, _, _ = _report(topo)
    section = report.sections[0]
    assert section.base_surface == "masonry_wall"
    assert all(s.base_z_mm == 600 for s in section.setting_out)
    assert all(s.ground_z_mm == 0 for s in section.setting_out)


def test_a_section_with_one_height_reports_it():
    report, _, _, _ = _report(straight_topology(6000))
    assert report.sections[0].height_mm is not None


# --- purity -------------------------------------------------------------------

def test_the_report_is_a_pure_function_of_its_inputs():
    topo = _straight_with_gate()
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    bom = fulfill(requirements, catalog)
    first = build_structure(topo, result.strategy, requirements, bom, run_id="r")
    second = build_structure(topo, result.strategy, requirements, bom, run_id="r")
    assert first == second


def test_the_report_does_not_alias_the_strategy():
    """A report handed to a caller must not change under them when the strategy
    object is edited afterwards."""
    topo = _straight_with_gate()
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    bom = fulfill(requirements, catalog)
    report = build_structure(topo, result.strategy, requirements, bom)
    before = report.model_dump_json()
    result.strategy.spans[0].height_mm = 12345
    result.strategy.posts[0].sku = "MUTATED"
    assert report.model_dump_json() == before


def test_remnants_are_named_as_their_own_source():
    """A rail cut from stock reads differently from one cut from a remnant, so the
    yard knows which bar to pick up."""
    topo = straight_topology(6000)
    inventory = Inventory(items=[
        InventoryItem(id="inv1", sku="RAIL-3000", kind="remnant", qty=1, length_mm=2000)])
    report, _, _, _ = _report(topo, inventory)
    bars = [b for s in report.sections for bay in s.bays for p in bay.parts for b in p.from_bars]
    assert any("⟲inv1" in b for b in bars), bars


def test_every_part_says_what_it_structurally_is():
    """A customer proposal names posts and panels but describes fixings — that
    filter must read a role, never guess from a SKU string."""
    report, _, _, _ = _report(_straight_with_gate())
    roles: dict[str, set[str]] = {}
    for section in report.sections:
        for element in [*section.setting_out, *section.bays, *section.gates]:
            for part in element.parts:
                assert part.role, part.sku
                roles.setdefault(part.role, set()).add(part.sku)
    assert set(roles) == {"post", "cap", "concrete", "rail", "screw", "gate_kit"}
    assert roles["concrete"] == {"CONC-25"} and roles["screw"] == {"SCREW-S10"}


# --- the findings the architecture review turned up ---------------------------

def test_a_shared_corner_post_has_exactly_one_tag():
    """It is one post: both sections set it out, and both must call it the same
    thing, or the drawing (which can only print one label) contradicts a table."""
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=4000, y_mm=0),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")])
    report, result, _, _ = _report(topo)
    tags: dict[str, set[str]] = {}
    for section in report.sections:
        for row in [*section.setting_out, *section.bays, *section.gates]:
            tags.setdefault(row.element_id, set()).add(row.tag)
    assert all(len(v) == 1 for v in tags.values()), tags
    assert len(set().union(*tags.values())) == len(tags), "tags are unique per element"
    # the borrowing section says whose post it is
    borrowed = [s for s in report.sections[1].setting_out if s.shared_from]
    assert [b.shared_from for b in borrowed] == ["A"]
    assert borrowed[0].tag.startswith("A/")
    # and it is counted ONCE
    assert report.totals.posts == len(result.strategy.posts)


def test_demand_met_from_stock_is_reported_not_lost():
    """Fulfilment emits no BOM line at all when inventory covers the demand. The
    parts still exist and still have to be picked, so the report says so."""
    topo = straight_topology(6000)
    inventory = Inventory(items=[
        InventoryItem(id="posts", sku="POST-S", kind="full_stock", qty=10)])
    report, _, _, bom = _report(topo, inventory)
    assert not any(l.sku == "POST-S" for l in bom.lines), "fixture must cover the demand"
    from_stock = {u.sku: u.qty for u in report.totals.from_stock}
    counted = sum(p.qty for s in report.sections for st in s.setting_out
                  for p in st.parts if p.sku == "POST-S")
    assert from_stock.get("POST-S") == counted > 0


def test_every_sku_balances_in_both_directions():
    """asked ≡ purchased + from_stock − unassigned, per (sku, unit). One equation,
    checked over the union of what the elements want and what the BOM buys."""
    topo = straight_topology(6000)
    inventory = Inventory(items=[
        InventoryItem(id="posts", sku="POST-S", kind="full_stock", qty=2),
        InventoryItem(id="rail", sku="RAIL-3000", kind="remnant", qty=1, length_mm=2500)])
    report, _, requirements, bom = _report(topo, inventory)
    asked: dict[tuple[str, str], int] = {}
    for req in requirements:
        asked[(req.sku, req.unit)] = asked.get((req.sku, req.unit), 0) + req.engineering_qty
    purchased = {(l.sku, l.engineering_unit): l.engineering_qty for l in bom.lines}
    stock = {(u.sku, u.unit): u.qty for u in report.totals.from_stock}
    extra = {(u.sku, u.unit): u.qty for u in report.totals.unassigned}
    for key in set(asked) | set(purchased):
        assert asked.get(key, 0) == (purchased.get(key, 0) + stock.get(key, 0)
                                     - extra.get(key, 0)), key


def test_unassigned_never_reports_a_negative_quantity():
    """A negative count is a defect, not a quantity — it used to appear when one
    SKU was demanded in two units (a tube bought as a post, cut as a rail)."""
    from fenceai.demand.derive import RequirementLine
    from fenceai.fulfillment.fulfill import Bom, BomLine
    from fenceai.report.structure import _parts_by_element

    ledger = _parts_by_element(
        [RequirementLine(id="r1", sku="TUBE", engineering_qty=8, unit="cut",
                         pegs=["span@run1:0-1000"], role="rail"),
         RequirementLine(id="r2", sku="TUBE", engineering_qty=5, unit="each",
                         pegs=["post@run1:0"], role="post")],
        Bom(lines=[BomLine(sku="TUBE", name="tube", purchase_qty=4, purchase_unit="bar",
                           engineering_qty=8, engineering_unit="cut",
                           unit_price_cents=100, total_cents=400)]))
    assert all(u.qty > 0 for u in ledger.unassigned), ledger.unassigned
    assert all(u.qty > 0 for u in ledger.from_stock), ledger.from_stock
    # the "each" demand is unpurchased, and says so in ITS unit
    assert ("TUBE", 5, "each") in [(u.sku, u.qty, u.unit) for u in ledger.from_stock]


def test_a_requirement_pegged_to_nothing_lands_in_unassigned():
    """The spec says nothing is hidden; it used to land under a phantom element
    that no table renders."""
    from fenceai.demand.derive import RequirementLine
    from fenceai.fulfillment.fulfill import Bom
    from fenceai.report.structure import _parts_by_element

    ledger = _parts_by_element(
        [RequirementLine(id="r1", sku="MISC", engineering_qty=3, unit="each", pegs=[])],
        Bom())
    assert ledger.per_element == {}
    assert [(u.sku, u.qty) for u in ledger.unassigned] == [("MISC", 3)]


def test_a_section_with_two_base_surfaces_says_mixed():
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "b1", 0, 3000, BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "b2", 3000, 6000, BasePayload(surface="concrete"))
    report, _, _, _ = _report(topo)
    assert report.sections[0].base_surface == "mixed"
