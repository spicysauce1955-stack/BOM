"""S15 — two eligible stock lengths for one requirement.

A 1500 mm rail from 3000 mm stock yields ONE piece per bar, not two: with a 3 mm
kerf, two pieces need 3003 mm (cutplan.py:98 fits n pieces iff
n*(piece+kerf) <= stock+kerf). A 3050 mm bar fits two. The choice cannot be made
by comparing stock lengths — only by planning the cuts.
"""

from fenceai.catalog.model import Catalog, DivisibleLinear, Product
from fenceai.demand.derive import RequirementLine
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.supply import resolve_supply

CATALOG = Catalog.of(
    Product(sku="RAIL-3000", name="Rail stock 3000",
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3),
            price_cents=1800),
    Product(sku="RAIL-3050", name="Rail stock 3050",
            consumption=DivisibleLinear(purchase_length_mm=3050, kerf_mm=3),
            price_cents=1850),
)

BOTH = Eligibility(members=[
    EligibleItem(sku="RAIL-3000", priority=1),
    EligibleItem(sku="RAIL-3050", priority=2),
])


def _rails(n: int) -> list[RequirementLine]:
    return [RequirementLine(id=f"req{i:04d}", sku="", engineering_qty=1, unit="cut",
                            cut_length_mm=1500, role="rail", slot_key="rail",
                            eligibility=BOTH) for i in range(1, n + 1)]


def test_least_cost_picks_the_longer_bar_because_two_pieces_fit_it():
    """4 rails: RAIL-3000 needs 4 bars (7200c), RAIL-3050 needs 2 (3700c)."""
    out = resolve_supply(_rails(4), CATALOG, preset="least_cost")
    assert {r.sku for r in out.requirements} == {"RAIL-3050"}
    bom = fulfill(out.requirements, CATALOG)
    assert bom.lines[0].purchase_qty == 2
    assert bom.lines[0].total_cents == 3700


def test_honour_priority_keeps_the_companys_first_choice_and_costs_more():
    out = resolve_supply(_rails(4), CATALOG, preset="honour_priority")
    assert {r.sku for r in out.requirements} == {"RAIL-3000"}
    assert fulfill(out.requirements, CATALOG).lines[0].purchase_qty == 4


def test_the_rejected_candidate_is_recorded_for_the_explanation():
    out = resolve_supply(_rails(4), CATALOG, preset="least_cost")
    assert out.decisions and out.decisions[0]["chosen"] == "RAIL-3050"
    assert out.decisions[0]["rejected"] == ["RAIL-3000"]


def test_the_choice_is_the_same_for_every_line_of_one_group():
    """Splitting one demand across two stock lengths is SAP's usage probability,
    which we deliberately rejected: it is a forecasting device, not an answer for
    one exact job."""
    out = resolve_supply(_rails(4), CATALOG, preset="least_cost")
    assert len({r.sku for r in out.requirements}) == 1
