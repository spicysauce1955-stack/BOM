"""The one way a stored strategy becomes a priced BOM.

`derive_requirements -> resolve_supply -> fulfill` was copy-pasted at four sites
(`/bom`, `/structure`, `/quote` and the impact preview). Four copies of a
sequence are four chances to diverge, and they already had: `create_quote` — the
one endpoint that freezes an immutable commercial document — loaded the catalog
directly instead of through the staleness check, so it was the only caller
exempt from it. Verified end to end before the fix: BOM 409, structure 409,
quote 200.

So the sequence lives here, once, and every caller runs the same one. The API
adds the two things only it can do — resolving the fresh catalog against the
run's stamped hash, and converting the domain error into an HTTP status — around
this function rather than beside a fourth copy of it.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.demand.derive import RequirementLine, derive_requirements
from fenceai.fulfillment.fulfill import Bom, Inventory, fulfill
from fenceai.fulfillment.supply import SupplyDecision, resolve_supply
from fenceai.strategy.model import Strategy, StrategyWarning


class PricedRun(BaseModel):
    """What a strategy costs, and what could not be supplied for it."""

    # every line here names a product — `fulfill()` refuses a blank sku, so this
    # is structural rather than a convention
    requirements: list[RequirementLine] = []
    # lines no eligible product could supply. Kept, never dropped: /bom and
    # /structure are working views and report the gap, /quote refuses to freeze
    # a document that under-prices the job.
    unresolved: list[RequirementLine] = []
    warnings: list[StrategyWarning] = []
    # why each multi-candidate group resolved the way it did. Carried out of the
    # pipeline because the decision-graph nodes for it are DERIVED at read time:
    # selection is coupled to the cut plan and runs here, where there is no graph
    # builder (`decisions/supply.py`).
    decisions: list[SupplyDecision] = []
    bom: Bom


def price_strategy(
    strategy: Strategy,
    catalog: Catalog,
    inventory: Inventory | None = None,
    demand_skus: dict | None = None,
    preset: str = "least_cost",
) -> PricedRun:
    """Engineering demand, supply resolution and fulfilment, in that order.

    Raises `ValueError` (including `core.errors.ReadRefused`, which carries a
    code + params) when the run cannot be read or the preset is unknown.
    """
    requirements = derive_requirements(strategy, catalog, demand_skus)
    resolution = resolve_supply(requirements, catalog, inventory, preset=preset)
    bom = fulfill(resolution.requirements, catalog, inventory)
    bom.warnings = resolution.warnings
    return PricedRun(
        requirements=resolution.requirements,
        unresolved=resolution.unresolved,
        warnings=resolution.warnings,
        decisions=resolution.decisions,
        bom=bom,
    )
