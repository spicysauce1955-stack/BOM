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
from fenceai.fulfillment.cutplan import CutPiece, RemnantStock, plan_cuts
from fenceai.fulfillment.fulfill import Inventory
from fenceai.strategy.model import StrategyWarning

Preset = Literal["least_cost", "honour_priority"]

_INFEASIBLE = 2**62


class SupplyResolution(BaseModel):
    # every line here has a real sku — the invariant fulfill() and the parts
    # ledger both depend on is enforced HERE, structurally, not by caller
    # discipline: a blank sku can never leave this module inside `requirements`.
    requirements: list[RequirementLine] = []
    # lines that could not be resolved (no eligible item, or only suggest-only
    # members without approval). Not discarded — each one has a matching entry
    # in `warnings`, so nothing goes silent; a future caller is free to surface
    # them (e.g. on the structure sheet) without risking them reaching fulfill().
    unresolved: list[RequirementLine] = []
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

    # lines still needing a choice, deep-copied so the caller's lines are never
    # touched — grouped below so one demand is answered by one product, never
    # split across skus the way SAP's usage-probability model would.
    pending: list[RequirementLine] = []
    for req in requirements:
        line = req.model_copy(deep=True)   # never mutate the caller's lines
        if line.sku:
            out.requirements.append(line)
            continue

        if not line.eligibility.members:
            out.warnings.append(StrategyWarning(
                code="no_eligible_item", severity="error",
                message=f"No product is eligible to supply {line.role}.",
                params={"role": line.role, "slot_key": line.slot_key},
            ))
            out.unresolved.append(line)
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
            out.unresolved.append(line)
            continue

        pending.append(line)

    # Group by the full eligibility SIGNATURE — sku, priority and approval —
    # not just the set of usable skus. Two lines can be eligible for the same
    # skus but disagree about which one they prefer (opposite priority
    # order); grouping on sku alone would merge them and answer both with
    # whichever line happened to be lines[0], silently misreporting the
    # other's decision. Same sku set + same priorities + same approvals is
    # still "one demand", so it is still answered once.
    groups: dict[tuple, list[RequirementLine]] = {}
    for line in pending:
        usable_members = _usable(line.eligibility.members, approvals)
        key = tuple(sorted((m.sku, m.priority, m.approval) for m in usable_members))
        groups.setdefault(key, []).append(line)

    for key, lines in sorted(groups.items()):
        usable = [m for m in lines[0].eligibility.members
                  if (m.sku, m.priority, m.approval) in key]
        chosen = _choose(usable, lines, catalog, inventory, preset)
        for line in lines:
            line.sku = chosen.sku
            out.requirements.append(line)
            if len(usable) > 1:
                out.decisions.append({
                    "requirement_id": line.id, "slot_key": line.slot_key,
                    "chosen": chosen.sku, "preset": preset,
                    "rejected": [m.sku for m in usable if m.sku != chosen.sku],
                })
    return out


def _candidate_cost(sku: str, lines: list[RequirementLine], catalog, inventory) -> int:
    """Cents to buy this candidate for these lines, by actually planning the cuts.
    A candidate the planner cannot use at all costs infinitely."""
    product = catalog.products.get(sku)
    if product is None:
        return _INFEASIBLE
    sem = product.consumption
    if sem.kind != "divisible_linear":
        return product.price_cents * sum(l.engineering_qty for l in lines)
    pieces = [
        CutPiece(length_mm=l.cut_length_mm, requirement_id=l.id)
        for l in lines for _ in range(l.engineering_qty)
        if l.cut_length_mm is not None
    ]
    if any(p.length_mm + sem.kerf_mm > sem.purchase_length_mm + sem.kerf_mm
           for p in pieces):
        return _INFEASIBLE
    remnants = [
        RemnantStock(inventory_item_id=i.id, length_mm=i.length_mm)
        for i in (inventory or Inventory()).for_sku(sku)
        if i.kind == "remnant" and i.length_mm
    ]
    plan = plan_cuts(sku, sem, pieces, remnants)
    return plan.new_bar_count * product.price_cents


def _waste(sku: str, lines, catalog, inventory) -> int:
    """Only ever called for a candidate `_choose` already proved feasible
    (see `_choose`'s `feasible` filter) — a sku that costs `_INFEASIBLE` (a
    piece too long for the stock, or missing from the catalog entirely) never
    reaches here, so `plan_cuts` never sees a piece it would raise on."""
    product = catalog.products[sku]
    sem = product.consumption
    if sem.kind != "divisible_linear":
        return 0
    pieces = [CutPiece(length_mm=l.cut_length_mm, requirement_id=l.id)
              for l in lines for _ in range(l.engineering_qty)
              if l.cut_length_mm is not None]
    return plan_cuts(sku, sem, pieces, []).waste_mm   # CutPlan.waste_mm, cutplan.py:45


def _choose(usable, lines, catalog, inventory, preset):
    """One member: no decision. More than one: the choice is coupled to the cut
    plan — stock lengths cannot be ranked without planning the cuts (Task 8).

    Feasibility is resolved FIRST and filters the field before any other tier
    runs: an unusable candidate (piece longer than its stock, or a sku absent
    from the catalog) must lose gracefully under every preset, never win on
    priority, and never reach a later tier's helper (`_waste`) with a sku it
    can't plan for. Filtering here — rather than folding `_INFEASIBLE` into
    the rank tuple — makes it structurally impossible for a third tier added
    later to forget this guard: whatever it does, it only ever sees skus
    already proven buildable.
    """
    if len(usable) == 1:
        return usable[0]

    costs = {m.sku: _candidate_cost(m.sku, lines, catalog, inventory) for m in usable}
    feasible = [m for m in usable if costs[m.sku] < _INFEASIBLE]
    if not feasible:
        # every candidate is unusable — no good answer exists; fall back to
        # the full field so the ordinary tie-break still yields a stable,
        # deterministic pick rather than an exception. `rank` below still
        # never calls `_waste` on one of these, since none has a cost under
        # `_INFEASIBLE`.
        feasible = usable

    def rank(m):
        cost = costs[m.sku]
        # `_waste` plans real cuts for `sku` — only safe once `_candidate_cost`
        # has already proved the sku buildable; an infeasible candidate (only
        # reachable via the all-infeasible fallback above) gets no waste tier.
        waste = _waste(m.sku, lines, catalog, inventory) if cost < _INFEASIBLE else 0
        if preset == "honour_priority":
            return (m.priority, cost, waste, m.sku)
        return (cost, waste, m.priority, m.sku)

    return min(feasible, key=rank)
