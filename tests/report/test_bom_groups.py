"""The BOM, seen from the fence rather than from the warehouse.

`Bom.lines` are flat and sorted by sku, which is the right shape for ordering and
the wrong one for every question an estimator actually asks: what does THIS
section cost me, what is in THIS panel, and which choice put that product on the
list.

The one thing this view must not do is invent a number. A BOM line is a
PURCHASE, pooled per sku across the whole run — one 3000 mm bar is cut for two
different bays — so a section cannot own a fraction of a bar without an
apportionment nothing measured. What IS exact per element is the engineering
DEMAND, and that is what is grouped here. The purchase stays where it is true.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import DivisibleLinear, Product
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fencemodel.demo import M_SLAT
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.demand.derive import DemandLine
from fenceai.fulfillment.fulfill import Inventory, InventoryItem
from fenceai.fulfillment.lines import ResolvedSupplyLine
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.knowledge.demo import demo_knowledge
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.report.bom_groups import group_bom
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

PARTS = PartLibrary(parts=demo_parts())


def _priced(length_mm: int = 6000):
    catalog = demo_catalog()
    result = generate(
        straight_topology(length_mm), demo_knowledge(), catalog, parts=PARTS,
        models=FenceModelLibrary(models=[M_SLAT]),
        default_model=FenceModelChoice(model_id="M-SLAT"),
    )
    return result, price_strategy(result.strategy, catalog,
                                  demand_skus=result.run.demand_skus)


def test_every_bay_of_the_fence_is_a_group():
    """The question "what is in this panel" answered without the reader counting
    rows: one group per bay, named by the element the rest of the app already
    tags."""
    result, priced = _priced()
    grouped = group_bom(result.strategy, priced.requirements, priced.bom,
                        priced.decisions)
    bays = [g for g in grouped.groups if g.kind == "bay"]
    assert len(bays) == len(result.strategy.spans)
    assert {g.element_id for g in bays} == {s.id for s in result.strategy.spans}
    assert all(g.lines for g in bays)


def test_a_section_is_the_unit_the_estimator_asks_about():
    """A run is a section, and its group is every element that stands on it —
    posts and bays alike, which no single existing view rolls up together."""
    result, priced = _priced()
    grouped = group_bom(result.strategy, priced.requirements, priced.bom,
                        priced.decisions)
    sections = [g for g in grouped.groups if g.kind == "section"]
    assert [g.element_id for g in sections] == ["run1"]
    roles = {line.role for line in sections[0].lines}
    assert {"post", "rail", "infill"} <= roles, \
        "a section rolls up its posts AND its bays, not one or the other"


def test_a_post_shared_at_a_node_is_named_rather_than_given_to_a_side():
    """`Post.run_ref` for a terminus is `node:n1`: it belongs to no single run,
    which is exactly why the setting-out sheet gives it ONE tag and
    cross-references it from the other section. Grouping it under a run would
    have to pick a side, and the two sections would disagree about who bought
    the post."""
    result, priced = _priced()
    grouped = group_bom(result.strategy, priced.requirements, priced.bom,
                        priced.decisions)
    nodes = [g for g in grouped.groups if g.kind == "node"]
    assert [g.element_id for g in nodes] == ["node:n1", "node:n2"]
    assert all({line.role for line in g.lines} <= {"post", "cap", "concrete"}
               for g in nodes), "a node carries its post, never a bay's infill"


def _with_a_real_choice():
    """A run whose rail slot has two eligible stocks, so `select_supply` actually
    DECIDES. Every demo model names one product per slot, which is why the plain
    fixture above records no decision at all — a decision group tested on it
    would be testing an empty list."""
    catalog = demo_catalog()
    catalog.products["RAIL-3050"] = Product(
        sku="RAIL-3050", name="Rail stock 3050 mm",
        consumption=DivisibleLinear(purchase_length_mm=3050, kerf_mm=3,
                                    min_reusable_remnant_mm=300),
        price_cents=1850,
    )
    model = M_SLAT.model_copy(deep=True)
    rail = model.default_spec.frame[0].requirement
    rail.part_id = ""
    rail.role = "rail"
    rail.eligibility = Eligibility(members=[
        EligibleItem(sku="RAIL-3000", priority=1),
        EligibleItem(sku="RAIL-3050", priority=2),
    ])
    result = generate(
        straight_topology(6000), demo_knowledge(), catalog, parts=PARTS,
        models=FenceModelLibrary(models=[model]),
        default_model=FenceModelChoice(model_id=model.id),
    )
    return result, price_strategy(result.strategy, catalog,
                                  demand_skus=result.run.demand_skus)


def test_a_decision_group_says_which_choice_bought_it():
    """The new grouping, and the one `Bom.lines` cannot express at all: the rows
    a single supply decision is responsible for, beside the runner-up it beat.
    "Why is this product on my list" is answerable in the view that raised it."""
    result, priced = _with_a_real_choice()
    assert priced.decisions, "the fixture must actually decide something"
    grouped = group_bom(result.strategy, priced.requirements, priced.bom,
                        priced.decisions)
    decisions = [g for g in grouped.groups if g.kind == "decision"]
    assert decisions
    rail = next(g for g in decisions if any(x.role == "rail" for x in g.lines))
    assert rail.chosen in ("RAIL-3000", "RAIL-3050")
    assert rail.rejected and rail.chosen not in rail.rejected
    assert rail.preset
    assert all(line.sku == rail.chosen for line in rail.lines), \
        "a decision group holds the lines that decision bought, not its rivals"


def _assert_balances(grouped, bom):
    """Per (sku, unit): what the sections and nodes asked for, plus what nothing
    asked for, less what stock covered, is exactly what the BOM accounts for."""
    asked: dict[tuple[str, str], int] = {}
    for group in grouped.groups:
        if group.kind not in ("section", "node"):
            continue   # sections and nodes partition it; bays are a subset of
                       # sections and decisions cut across both
        for line in group.lines:
            asked[(line.sku, line.unit)] = asked.get((line.sku, line.unit), 0) + line.qty
    for total in grouped.unassigned:
        asked[(total.sku, total.unit)] = asked.get((total.sku, total.unit), 0) + total.qty
    for total in grouped.from_stock:
        asked[(total.sku, total.unit)] = asked.get((total.sku, total.unit), 0) - total.qty
    purchased = {(line.sku, line.engineering_unit): line.engineering_qty
                 for line in bom.lines}
    assert {k: v for k, v in asked.items() if v} == purchased


def test_the_grouped_demand_adds_up_to_the_bom():
    """THE governing property, and the same one `Σ(parts) ≡ BOM` states for the
    structure sheet: grouping may not lose or invent a quantity. Per (sku, unit),
    what the sections asked for plus what nothing asked for, less what stock
    covered, is exactly what the BOM accounts for."""
    result, priced = _priced()
    grouped = group_bom(result.strategy, priced.requirements, priced.bom,
                        priced.decisions)
    _assert_balances(grouped, priced.bom)


def test_what_stock_covered_is_reported_rather_than_balanced_away():
    """`from_stock` is demand that appears on NO purchase line because inventory
    met it — the yard still picks it. A grouping that quietly balanced by
    dropping it would read as a fence with fewer parts than it has."""
    catalog = demo_catalog()
    result = generate(
        straight_topology(1500), demo_knowledge(), catalog, parts=PARTS,
        models=FenceModelLibrary(models=[M_SLAT]),
        default_model=FenceModelChoice(model_id="M-SLAT"),
    )
    inventory = Inventory(items=[
        InventoryItem(id="c1", sku="POST-CAP", kind="full_stock", qty=2)])
    priced = price_strategy(result.strategy, catalog, inventory,
                            demand_skus=result.run.demand_skus)
    grouped = group_bom(result.strategy, priced.requirements, priced.bom,
                        priced.decisions)
    assert [(t.sku, t.qty) for t in grouped.from_stock] == [("POST-CAP", 2)]
    _assert_balances(grouped, priced.bom)


def test_a_line_pegged_to_nothing_lands_in_unassigned():
    """The bucket no demo run fills, and the one a grouping loses most easily: a
    line that pegs to no element belongs to no section, and putting it in a
    phantom one would show a section nobody built. It is reported instead —
    which is what keeps the sum honest rather than merely equal."""
    result, priced = _priced()
    orphan = ResolvedSupplyLine.of(
        DemandLine(id="req-orphan", engineering_qty=3, role="screw",
                   slot_key="screw", pegs=[]),
        sku="SCREW-S10", unit="each")
    grouped = group_bom(result.strategy, [*priced.requirements, orphan],
                        priced.bom, priced.decisions)
    assert ("SCREW-S10", 3) in [(t.sku, t.qty) for t in grouped.unassigned]
    assert not any(line.sku == "SCREW-S10" and line.qty == 3
                   for g in grouped.groups for line in g.lines), \
        "an orphan must not be invented into a section"


def test_no_group_carries_money():
    """Deliberate, and the reason this view is honest. A purchase is pooled per
    sku across the whole run — one bar is cut for two bays — so a per-section
    price is an apportionment nothing measured. `open-work.md` scoped this as a
    read-model addition rather than new arithmetic, and a cost field would be
    exactly that arithmetic, wearing the authority of a BOM."""
    result, priced = _priced()
    grouped = group_bom(result.strategy, priced.requirements, priced.bom,
                        priced.decisions)
    for group in grouped.groups:
        assert not any("cent" in f or "price" in f
                       for f in group.model_dump())
        for line in group.lines:
            assert not any("cent" in f or "price" in f for f in line.model_dump())


def test_grouping_is_pure_and_deterministic():
    result, priced = _priced()
    once = group_bom(result.strategy, priced.requirements, priced.bom,
                     priced.decisions)
    twice = group_bom(result.strategy, priced.requirements, priced.bom,
                      priced.decisions)
    assert once == twice
