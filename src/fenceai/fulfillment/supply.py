"""Choosing which eligible item supplies each requirement (fence-model spec §3).

Runs BEFORE fulfill() so every line names a product by the time the cut planner,
the BOM and the parts ledger see it — the ledger keys on (sku, unit) and a blank
SKU would make one demand read as both unassigned and from-stock.

The choice is an OBJECTIVE, not a lookup: with more than one member it is
coupled to the cut plan, because stock lengths cannot be ranked without planning
the cuts. Lexicographic tiers with named presets (ADR-0007), never raw weights.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.demand.derive import RequirementLine
from fenceai.fulfillment.fulfill import Inventory
from fenceai.strategy.model import StrategyWarning

Preset = Literal["least_cost", "honour_priority"]


class SupplyResolution(BaseModel):
    requirements: list[RequirementLine] = []
    warnings: list[StrategyWarning] = []
    decisions: list[dict] = []   # chosen + rejected, for the decision graph


def _usable(members, approvals: set[str]) -> list:
    return [m for m in members if m.approval == "auto" or m.sku in approvals]


def resolve_supply(
    requirements: list[RequirementLine],
    catalog: Catalog,
    inventory: Inventory | None = None,
    preset: Preset = "least_cost",
    approvals: set[str] | None = None,
) -> SupplyResolution:
    approvals = approvals or set()
    out = SupplyResolution()

    for req in requirements:
        line = req.model_copy(deep=True)   # never mutate the caller's lines
        if line.sku or not line.eligibility.members:
            if not line.sku:
                out.warnings.append(StrategyWarning(
                    code="no_eligible_item", severity="error",
                    message=f"No product is eligible to supply {line.role}.",
                    params={"role": line.role, "slot_key": line.slot_key},
                ))
            out.requirements.append(line)
            continue

        usable = _usable(line.eligibility.members, approvals)
        if not usable:
            out.warnings.append(StrategyWarning(
                code="substitute_needs_approval", severity="warning",
                message=f"Only a suggest-only product fits {line.role}; "
                        "it needs approval before it can be used.",
                params={"role": line.role, "slot_key": line.slot_key,
                        "sku": line.eligibility.members[0].sku},
            ))
            out.requirements.append(line)
            continue

        chosen = _choose(usable, line, catalog, inventory, preset)
        line.sku = chosen.sku
        out.requirements.append(line)
        if len(usable) > 1:
            out.decisions.append({
                "requirement_id": line.id, "slot_key": line.slot_key,
                "chosen": chosen.sku, "preset": preset,
                "rejected": [m.sku for m in usable if m.sku != chosen.sku],
            })
    return out


def _choose(usable, line, catalog, inventory, preset):
    """One member: no decision. More than one: Task 8 replaces this body with the
    cut-plan-coupled comparison. Ordering by priority here is correct for a
    single member and is the honour_priority answer for several."""
    return sorted(usable, key=lambda m: (m.priority, m.sku))[0]
