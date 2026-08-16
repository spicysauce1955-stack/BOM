"""One line, one lifecycle state — never several at once.

`RequirementLine` used to be both: demand emitted it with `sku=""` and `unit=""`,
and `resolve_supply` filled them in by MUTATING the same object. So the type said
"I have a product" through the whole half of its life where it did not, and the
invariant that a blank sku never reaches `fulfill()` rested on caller discipline —
which `fulfill()`'s own refusal records having been broken at all three routes by
a three-word edit that produced zero test failures.

Two types now, and the guarantee is structural: `fulfill()` accepts only the
resolved one, and the resolved one cannot be built without a product.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.demand.derive import DemandLine
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fulfillment.supply import ResolvedSupplyLine

ONE = Eligibility(members=[EligibleItem(sku="RAIL-3000")])


def test_a_demand_line_cannot_claim_a_product():
    """Demand says what the fence NEEDS. Which product satisfies it is
    `resolve_supply`'s answer, and the unit is a property of the product it
    chooses — which is why demand guessed the unit three different ways and was
    wrong each time."""
    line = DemandLine(id="d1", engineering_qty=2, role="rail", eligibility=ONE)
    assert not hasattr(line, "sku")
    assert not hasattr(line, "unit")


def test_a_resolved_line_cannot_lack_a_product():
    with pytest.raises(ValidationError):
        ResolvedSupplyLine(id="d1", engineering_qty=2, role="rail", unit="cut")


def test_a_resolved_line_cannot_carry_a_blank_product_either():
    """The failure this replaces: a blank sku makes every parts-ledger key
    `("", unit)`, so one demand reports as unassigned AND from stock at once and
    satisfies the both-directions property vacuously while being maximally
    wrong."""
    with pytest.raises(ValidationError):
        ResolvedSupplyLine(id="d1", engineering_qty=2, role="rail",
                           sku="", unit="cut")


def test_a_resolved_line_cannot_lack_a_unit():
    """`unit` is half the parts-ledger key, and it is a property of the CHOSEN
    product. A line missing it balances against nothing."""
    with pytest.raises(ValidationError):
        ResolvedSupplyLine(id="d1", engineering_qty=2, role="rail", sku="RAIL-3000")


def test_resolving_a_demand_line_produces_a_new_object():
    """Not a mutation of the demand line. One object carried across the boundary
    is how `unresolved` and `requirements` could ever come to disagree about the
    same line, and it is why the two states were indistinguishable at all."""
    demand = DemandLine(id="d1", engineering_qty=2, role="rail", eligibility=ONE)
    resolved = ResolvedSupplyLine.of(demand, sku="RAIL-3000", unit="cut")

    assert (resolved.id, resolved.engineering_qty, resolved.role) == ("d1", 2, "rail")
    assert not hasattr(demand, "sku"), "the demand line was mutated"


def test_every_demand_line_says_which_items_could_supply_it():
    """One path, after option A: a product knowledge already chose arrives as a
    one-member eligibility rather than as an authored `sku` on the line. That is
    what lets `resolve_supply` stop branching on whether a line already knows its
    answer."""
    from fenceai.catalog.demo import demo_catalog
    from fenceai.demand.derive import derive_requirements
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.knowledge.demo import demo_knowledge
    from fenceai.strategy.generator import generate
    from tests.conftest import straight_topology

    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    lines = derive_requirements(result.strategy, demo_catalog(),
                                policy=result.run.demand_skus)
    assert lines
    assert all(line.eligibility.members for line in lines), \
        "a demand line with no eligible member could never be supplied"
