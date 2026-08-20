"""What a BOM was priced AGAINST, named.

A run id answers "what fence is this" — topology, knowledge, overrides, models,
parts, policy, engine version — and is reproducible for ever (ADR-0004). It does
NOT answer "what does it cost to build, from the stock we have, under this
objective", because inventory, prices and the objective preset are statements
about a moment and are legitimately different tomorrow.

Before this module the second question had no name at all: /bom read LIVE
inventory, computed an `inventory_hash` on every read, wrote it to the audit log,
and put it in no identity and no stored document. One run id could therefore
print two different BOMs with `GET /api/runs/{id}` byte-identical between them
(the spec reproduces it: 40 700 then 27 200 agorot after three posts arrive).

WHERE THIS SITS. `derive_requirements` is the last pure stage: a `DemandLine`
says what the fence NEEDS — pegs, role, slot_key, a frozen eligibility — and
deliberately carries no sku and no unit. `resolve_supply(requirements, catalog,
inventory, preset)` is the first stage that depends on a MOMENT, and
`ResolvedSupplyLine(DemandLine)` adds exactly `sku` + `unit`. A `SupplyRun` is
the persisted, identified form of the in-memory `PricedRun` that
`fulfillment/pipeline.py` already returns: the same requirements/unresolved/bom
bundle, plus the provenance saying which yard, which prices and which objective
produced it.

NOT "material". `material` is a catalog product attribute from a closed
vocabulary (`attrs={"material": "vinyl"}`), which a part's spec declares as a
CONSTRAINT on an item rather than a fact about itself, and which the UI renders
in a surface called the material drawer. This entity is about none of that.

`SUPPLY_BEHAVIOR_VERSION` is the other half of PLANNING_BEHAVIOR_VERSION. That
constant covers generation's output; nothing covered cut planning, supply
resolution or allocation. Bump this one when what a strategy COSTS changes for
unchanged inputs — a different packer, a different remnant policy, a different
allocation order — or a stored quote silently comes to mean something else.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from fenceai.demand.derive import DemandLine
from fenceai.fulfillment.fulfill import Bom, Inventory
from fenceai.fulfillment.lines import ResolvedSupplyLine

SUPPLY_BEHAVIOR_VERSION = "supply-v1"


def inventory_hash(inventory: Inventory) -> str:
    """What was in the yard, as sixteen characters.

    Three sites in `api/app.py` each computed this inline with the same
    expression; three copies of a hash are three chances for one of them to
    quietly hash something else.
    """
    return hashlib.sha256(inventory.model_dump_json().encode()).hexdigest()[:16]


def supply_id(
    design_id: str,
    inventory_hash: str,
    catalog_hash: str,
    objective_preset: str,
) -> str:
    """The content address of one supply run.

    `SUPPLY_BEHAVIOR_VERSION` is read through the module global rather than a
    default argument, so `monkeypatch.setattr` on the constant moves the id — a
    default argument would bind the version at import time and make the guard
    untestable.
    """
    return "sup_" + hashlib.sha256(
        json.dumps(
            [design_id, inventory_hash, catalog_hash, objective_preset,
             SUPPLY_BEHAVIOR_VERSION],
            sort_keys=True, default=str,
        ).encode()
    ).hexdigest()[:12]


class SupplyRun(BaseModel):
    """One design, priced against one yard, under one objective.

    `Quote` already froze this thing's numbers without being able to name what
    produced them; a quote now carries `supply_id` and can.
    """

    id: str
    design_id: str            # the GenerationRun this prices
    inventory_hash: str = ""  # what was in the yard
    catalog_hash: str = ""    # narrowed to the skus the run named, as the design does
    objective_preset: str = "least_cost"
    supply_version: str = ""
    created_at: str = ""
    requirements: list[ResolvedSupplyLine] = []
    # kept, never dropped, for the same reason PricedRun keeps them: a working
    # view reports the gap, and /quote refuses to freeze a document that
    # under-prices the job. Still DemandLines, which is the point — an unresolved
    # line is one that never got a product, and the TYPE is what stops it
    # reaching fulfill().
    unresolved: list[DemandLine] = []
    bom: Bom
