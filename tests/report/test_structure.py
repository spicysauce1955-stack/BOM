"""The structure report — layout and the items each element consists of.

The report is a READ MODEL: it must never become a second BOM. Its governing
property is that the per-element parts sum back to the BOM's engineering
quantities, with anything unpegged reported as unassigned rather than dropped.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, InventoryItem, fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.demo import demo_knowledge
from fenceai.report.structure import build_structure
from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    BasePayload, BaseTopPayload, BaseTopPoint, GatePayload, Node, Run, Topology,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology


def _report(topo, inventory: Inventory | None = None, run_id: str = "run-x", catalog=None):
    catalog = catalog or demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    requirements = resolve_supply(requirements, catalog, inventory).requirements
    bom = fulfill(requirements, catalog, inventory)
    report = build_structure(topo, result.strategy, requirements, bom, run_id=run_id,
                             catalog=catalog)
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
        assert bay.from_tag and bay.to_tag, bay.tag   # a missing link is a KeyError below
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
    assert rail.length_basis in ("width", "slope")
    # the basis decides which length: an `or` over both accepts a flipped basis
    assert rail.cut_length_mm == (bay.slope_len_mm if rail.length_basis == "slope"
                                  else bay.width_mm)
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


def test_each_element_gets_what_IT_asked_for():
    """A per-SKU grand total is invariant under permuting parts across elements:
    put every bag of concrete on P1 and the sum still balances, while the sheet
    tells the crew to pour six bags into one hole. Identity, not just totals."""
    report, result, _, _ = _report(_straight_with_gate())
    by_id = {s.element_id: s for s in report.sections[0].setting_out}
    for post in result.strategy.posts:
        assert {(p.sku, p.qty) for p in by_id[post.id].parts} == {
            (post.sku, 1), ("POST-CAP", 1), ("CONC-25", 1)}, post.id
    for bay in report.sections[0].bays:
        assert [(p.sku, p.qty) for p in bay.parts if p.role == "screw"] == \
            [("SCREW-S10", 8)], bay.tag
        assert [p.qty for p in bay.parts if p.role == "rail"] == [2], bay.tag


def test_parts_hang_off_the_kind_of_element_that_causes_them():
    """Roles drive the customer sheet (fixings are described, not counted), so a
    cap labelled as a post silently changes what a proposal itemises."""
    report, _, _, _ = _report(_straight_with_gate())
    section = report.sections[0]
    for st in section.setting_out:
        assert {p.role for p in st.parts} <= {"post", "cap", "concrete"}, st.tag
    for bay in section.bays:
        assert {p.role for p in bay.parts} <= {"rail", "screw"}, bay.tag
    for gate in section.gates:
        assert {p.role for p in gate.parts} <= {"gate_kit"}, gate.tag


def test_each_cut_piece_names_the_bar_it_actually_came_from():
    """`startswith(sku)` accepts any bar: with every piece claiming bar #1 the
    yard cuts eight rails out of one 3 m stick."""
    report, _, _, bom = _report(_straight_with_gate())
    labels = [b for s in report.sections for bay in s.bays
              for p in bay.parts for b in p.from_bars]
    plan = bom.cut_plans["RAIL-3000"]
    assert len(labels) == sum(len(bar.pieces) for bar in plan.bars)
    assert sorted(set(labels)) == [f"RAIL-3000 #{i}" for i in range(1, len(plan.bars) + 1)]
    # every bar carries exactly the pieces the plan put on it
    for i, bar in enumerate(plan.bars, start=1):
        assert labels.count(f"RAIL-3000 #{i}") == len(bar.pieces)


def _corner_topology():
    return Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=4000, y_mm=0),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")])


def test_the_parts_sum_back_to_the_bom_across_sections():
    """A shared corner post is SET OUT twice and BOUGHT once. Summing rendered
    rows without deduping bills it to both sections — so a repeat row must
    announce itself, and consumers that total must skip it."""
    report, _, _, bom = _report(_corner_topology())
    seen: set[str] = set()
    per_sku: dict[str, int] = {}
    for section in report.sections:
        for element in [*section.setting_out, *section.bays, *section.gates]:
            if element.element_id in seen:
                assert getattr(element, "shared_from", None), element.tag
                continue
            seen.add(element.element_id)
            for part in element.parts:
                per_sku[part.sku] = per_sku.get(part.sku, 0) + part.qty
    assert per_sku == {l.sku: l.engineering_qty for l in bom.lines}


def test_a_gate_names_the_posts_it_hangs_between():
    report, _, _, _ = _report(_straight_with_gate())
    section = report.sections[0]
    by_tag = {s.tag: s.station_mm for s in section.setting_out}
    gate = section.gates[0]
    assert gate.from_tag and gate.to_tag
    assert by_tag[gate.from_tag] == gate.start_station_mm
    assert by_tag[gate.to_tag] == gate.end_station_mm


def test_totals_agree_with_the_sections():
    report, result, _, _ = _report(_straight_with_gate())
    # pinned to the fixture, not to the strategy: a generator and a report that
    # drift together would satisfy a self-comparison
    assert (report.totals.posts, report.totals.bays, report.totals.gates,
            report.totals.fence_length_mm) == (6, 4, 1, 6000)
    assert report.totals.posts == len(result.strategy.posts)
    assert report.totals.bays == len(result.strategy.spans)
    assert report.totals.gates == len(result.strategy.gates)
    heights = {b.height_mm for s in report.sections for b in s.bays}
    assert report.totals.height_min_mm == min(heights)
    assert report.totals.height_max_mm == max(heights)


def test_the_sheet_says_what_is_fitted_and_the_bom_says_what_is_bought():
    """These are different numbers and both are right: 32 screws go into the fence,
    2 boxes of 50 get bought. The rounding lives in the BOM's purchase quantity,
    NOT in the engineering demand — so the sheet must equal the demand exactly."""
    report, _, _, bom = _report(_straight_with_gate())
    screws = next(l for l in bom.lines if l.sku == "SCREW-S10")
    per_box = demo_catalog().products["SCREW-S10"].consumption.qty_per_package
    assert (screws.engineering_qty, screws.purchase_qty, screws.overage_qty) == (32, 2, 8)
    counted = sum(p.qty for s in report.sections for e in [*s.setting_out, *s.bays, *s.gates]
                  for p in e.parts if p.sku == "SCREW-S10")
    assert counted == screws.engineering_qty == 32
    assert screws.purchase_qty * per_box - counted == screws.overage_qty
    # nothing to reconcile here: the demand is fully pegged
    assert not [u for u in report.totals.unassigned if u.sku == "SCREW-S10"]


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


# --- what the elevation needs to draw a post ----------------------------------

def test_a_station_carries_the_embedment_and_the_post_length():
    """The two numbers a macro elevation cannot see anywhere else. Both are read,
    never derived: the embedment is the strategy's own, the length is the
    catalog product's own."""
    topo = straight_topology(6000)
    report, result, _, _ = _report(topo)
    posts = {p.id: p for p in result.strategy.posts}
    stations = report.sections[0].setting_out
    assert stations
    for station in stations:
        assert station.embed_mm == posts[station.element_id].embed_mm
        assert station.post_length_mm == 2600  # POST-S declares its length


def test_a_masonry_station_reports_no_embedment():
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "base", 0, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "top", 0, 6000, BaseTopPayload(
        points=[BaseTopPoint(pos_permille=0, z_mm=600),
                BaseTopPoint(pos_permille=1000, z_mm=600)]))
    report, _, _, _ = _report(topo)
    stations = report.sections[0].setting_out
    assert stations
    assert all(s.mounting == "masonry" and s.embed_mm == 0 for s in stations)


def test_a_post_product_with_no_declared_length_yields_none():
    """POST-M declares no `length_mm`, and neither does this stripped POST-S: the
    sheet says None so the drawing omits the embed dimension. A guessed length on
    a setting-out drawing is worse than a missing one."""
    catalog = demo_catalog()
    catalog.products["POST-S"] = catalog.products["POST-S"].model_copy(
        update={"attrs": {}})
    report, _, _, _ = _report(straight_topology(6000), catalog=catalog)
    stations = report.sections[0].setting_out
    assert stations
    assert all(s.sku == "POST-S" for s in stations)
    assert all(s.post_length_mm is None for s in stations)
    # the embedment is unaffected: it is not a catalog fact
    assert all(s.embed_mm == 600 for s in stations)


def test_without_a_catalog_the_length_is_unknown_rather_than_invented():
    """`build_structure` still answers with four inputs — it simply cannot claim a
    post length it was never shown."""
    topo = straight_topology(6000)
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    requirements = resolve_supply(requirements, catalog).requirements
    bom = fulfill(requirements, catalog)
    report = build_structure(topo, result.strategy, requirements, bom, run_id="r")
    stations = report.sections[0].setting_out
    assert all(s.post_length_mm is None for s in stations)
    assert all(s.embed_mm == 600 for s in stations)


def test_a_section_with_one_height_reports_it():
    report, _, _, _ = _report(straight_topology(6000))
    assert report.sections[0].height_mm == 1800


# --- purity -------------------------------------------------------------------

def test_the_whole_pipeline_is_reproducible():
    """"Same run in, same report out" is about generate -> derive -> fulfil ->
    report, not just the last step."""
    first, _, _, _ = _report(_straight_with_gate())
    second, _, _, _ = _report(_straight_with_gate())
    assert first == second


def test_the_report_is_a_pure_function_of_its_inputs():
    topo = _straight_with_gate()
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    requirements = resolve_supply(requirements, catalog).requirements
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
    requirements = resolve_supply(requirements, catalog).requirements
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
    assert {"post", "cap", "concrete", "rail", "screw", "gate_kit"} <= set(roles)
    assert roles["post"] == {"POST-S", "POST-S-HD"} and roles["cap"] == {"POST-CAP"}
    assert roles["rail"] == {"RAIL-3000"} and roles["gate_kit"] == {"GATE-KIT-1000"}
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
    from fenceai.fulfillment.lines import ResolvedSupplyLine
    from fenceai.fulfillment.fulfill import Bom, BomLine
    from fenceai.report.structure import _parts_by_element

    ledger = _parts_by_element(
        [ResolvedSupplyLine(id="r1", sku="TUBE", engineering_qty=8, unit="cut",
                         pegs=["span@run1:0-1000"], role="rail"),
         ResolvedSupplyLine(id="r2", sku="TUBE", engineering_qty=5, unit="each",
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
    from fenceai.fulfillment.lines import ResolvedSupplyLine
    from fenceai.fulfillment.fulfill import Bom
    from fenceai.report.structure import _parts_by_element

    ledger = _parts_by_element(
        [ResolvedSupplyLine(id="r1", sku="MISC", engineering_qty=3, unit="each", pegs=[])],
        Bom())
    assert ledger.per_element == {}
    assert [(u.sku, u.qty) for u in ledger.unassigned] == [("MISC", 3)]


def test_a_section_with_two_base_surfaces_says_mixed():
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "b1", 0, 3000, BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "b2", 3000, 6000, BasePayload(surface="concrete"))
    report, _, _, _ = _report(topo)
    assert report.sections[0].base_surface == "mixed"


# --- the joint, on a stored bay ----------------------------------------------

def test_a_generated_bay_carries_the_joint_details_of_the_model_it_was_built_to():
    """The other half of the property `tests/fencemodel/test_preview.py` asserts
    from the preview side: the detail rides on `PanelElevation`, so a stored run
    and a panel preview get it from one code path and cannot disagree.

    The run is pinned to M-SLAT@v2, whose slats seat 15 mm into a 20 mm channel
    with 3 mm of insertion clearance. Every bay of it says the same thing,
    because the joint is the MODEL's and every bay is built to that model.
    """
    from fenceai.fencemodel.demo import M_LEGACY, M_SLAT, M_SLAT_V2
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.fencemodel.selection import FenceModelChoice

    library = FenceModelLibrary(models=[M_LEGACY, M_SLAT, M_SLAT_V2])
    catalog = demo_catalog()
    topo = straight_topology(6000)
    result = generate(topo, demo_knowledge(), catalog, models=library,
                      default_model=FenceModelChoice(model_id="M-SLAT", version_pin=2))
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    requirements = resolve_supply(requirements, catalog, None).requirements
    report = build_structure(topo, result.strategy, requirements,
                             fulfill(requirements, catalog, None),
                             run_id="run-joint", catalog=catalog)

    bays = [b for s in report.sections for b in s.bays]
    assert bays, "no bay to carry a detail"
    for bay in bays:
        assert bay.elevation is not None
        assert [d.key for d in bay.elevation.details] == ["slat@bottom_channel"]
        detail = bay.elevation.details[0]
        assert (detail.end, detail.kind) == ("base", "channel")
        assert (detail.channel_depth_mm, detail.engagement_mm, detail.margin_mm) == \
            (20, 15, 3)
        # and the members are hatched from the same extent the cut list bought
        slats = [m for m in bay.elevation.members if m.slot_key == "slat"]
        assert slats
        for slat in slats:
            assert slat.seat_start_mm == slat.y_mm
            assert slat.seat_end_mm - slat.seat_start_mm == detail.engagement_mm
