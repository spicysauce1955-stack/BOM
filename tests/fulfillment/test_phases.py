"""The declared phase list — inserting a step is a row, not a chain edit.

`docs/superpowers/specs/2026-08-25-engine-architecture.md` §4, the second seam:

> **A declared phase list** — instead of `derive → resolve → fulfil` hardcoded,
> declare an ordered list of named steps, each with its input and output type, so
> inserting *credit kits against assemblies* or *certify combinations* is a row.

The two named beneficiaries are real and pending: kit credit (build order item 10)
and `certify()` for `Combination` (contract obligation 17, the seam named and
inert). Both are steps in the MIDDLE of this chain, which is exactly where a
hardcoded call order is most expensive to change.

`PricedRun` is the shape `/bom`, `/structure` and `/quote` all return, so the
last test here pins that this refactor changed nothing a client can see.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.phases import PIPELINE, Phase, PipelineState, check_order
from fenceai.fulfillment.pipeline import PricedRun, price_strategy
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _priced():
    catalog = demo_catalog()
    result = generate(straight_topology(6000), demo_knowledge(), catalog)
    return result.strategy, catalog


# -- the list is declared, and it is the thing that runs -----------------------

def test_the_phases_are_named_and_ordered():
    assert [p.name for p in PIPELINE] == ["derive_demand", "resolve_supply", "fulfil"]


def test_every_phase_reads_only_what_an_earlier_one_wrote():
    """The check that makes inserting a row safe.

    A step declares what it reads and what it writes, so a row put in the wrong
    place is caught HERE — at import, by a check anyone can run — rather than at
    runtime as an empty list that quietly prices nothing.
    """
    check_order(PIPELINE)  # must not raise


def test_a_phase_inserted_before_its_input_exists_is_refused():
    late = Phase(name="credit_kits", fn=lambda s: None,
                 reads=("requirements",), writes=("requirements",))
    with pytest.raises(ValueError, match="credit_kits"):
        check_order((late, *PIPELINE))


def test_a_step_can_be_inserted_in_the_middle_without_touching_the_others():
    """The property the seam exists for: `certify combinations` and `credit kits
    against assemblies` are both middle steps."""
    seen = {}

    def certify(state: PipelineState) -> None:
        seen["requirements"] = len(state.requirements)
        state.warnings.append(_note("combination_uncertified"))

    strategy, catalog = _priced()
    extended = (*PIPELINE[:2],
                Phase(name="certify", fn=certify,
                      reads=("requirements",), writes=("warnings",)),
                PIPELINE[2])
    check_order(extended)

    out = price_strategy(strategy, catalog, phases=extended)
    assert seen["requirements"] > 0                    # it ran, and after resolve
    assert any(w.code == "combination_uncertified" for w in out.warnings)
    assert out.bom.lines                               # ...and fulfil still ran after it


def _note(code: str):
    from fenceai.strategy.model import StrategyWarning

    return StrategyWarning(code=code, severity="warning", message=code)


# -- nothing a caller can see moved --------------------------------------------

def test_the_pipeline_still_produces_exactly_what_the_hand_written_chain_did():
    """The refactor's whole claim. Run the three steps by hand and compare."""
    strategy, catalog = _priced()

    requirements = derive_requirements(strategy, catalog, None)
    resolution = resolve_supply(requirements, catalog, None, preset="least_cost")
    bom = fulfill(resolution.requirements, catalog, None)

    out = price_strategy(strategy, catalog)
    assert [r.model_dump() for r in out.requirements] == [
        r.model_dump() for r in resolution.requirements]
    assert [u.model_dump() for u in out.unresolved] == [
        u.model_dump() for u in resolution.unresolved]
    assert out.bom.lines == bom.lines
    assert out.bom.total_cents == bom.total_cents


def test_the_api_facing_shape_is_unchanged():
    """`PricedRun` is what /bom, /structure and /quote all return. A field added,
    renamed or dropped here is a client change, and this refactor is internal."""
    assert set(PricedRun.model_fields) == {
        "requirements", "unresolved", "warnings", "decisions", "bom",
    }


def test_pricing_is_deterministic_through_the_phase_list():
    strategy, catalog = _priced()
    assert price_strategy(strategy, catalog).model_dump() == \
        price_strategy(strategy, catalog).model_dump()
