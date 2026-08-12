"""Choosing which eligible item supplies each requirement (fence-model spec §3).

Runs BEFORE fulfill() so every line names a product by the time the cut planner,
the BOM and the parts ledger see it — the ledger keys on (sku, unit) and a blank
SKU would make one demand read as both unassigned and from-stock.

The choice is an OBJECTIVE, not a lookup: with more than one member it is
coupled to the cut plan, because stock lengths cannot be ranked without planning
the cuts. Lexicographic tiers with named presets (ADR-0007), never raw weights.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.demand.derive import RequirementLine
from fenceai.fulfillment.cutplan import CutPiece, RemnantStock, plan_cuts
from fenceai.fulfillment.fulfill import Inventory, engineering_unit_for
from fenceai.strategy.model import StrategyWarning

Preset = Literal["least_cost", "honour_priority"]
# introspected from the Literal itself so the runtime check and the type can
# never drift apart (task 10 fix round 1, finding 3)
_PRESETS: frozenset[str] = frozenset(get_args(Preset))

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


def _name_product(line: RequirementLine, sku: str, catalog: Catalog) -> None:
    """Give a line its product — and, in the SAME statement, the unit that
    product is counted in.

    This is the only place a requirement acquires a sku, which makes it the only
    place that can decide the unit; setting the two together is what stops the
    asked and purchased sides of the parts ledger from ever disagreeing. The
    value comes from `fulfillment.fulfill.engineering_unit_for`, which is
    literally the function `fulfill()` uses to stamp `BomLine.engineering_unit`.
    """
    line.sku = sku
    line.unit = engineering_unit_for(catalog, sku)


def resolve_supply(
    requirements: list[RequirementLine],
    catalog: Catalog,
    inventory: Inventory | None = None,
    preset: Preset = "least_cost",
    approvals: set[str] | None = None,
) -> SupplyResolution:
    # `preset` arrives here as a plain str (GenerationRun.objective_preset is
    # unvalidated at rest — a stored run can carry any string), and `_choose`
    # below branches only on "honour_priority" — every OTHER value used to fall
    # through as least-cost with nobody told. That silent fallback is exactly
    # the failure mode this checks for: an unrecognised preset is a loud error
    # at the one boundary every caller (get_bom, get_structure, create_quote,
    # impact preview) funnels through, not a quiet reinterpretation.
    if preset not in _PRESETS:
        raise ValueError(
            f"unknown objective preset {preset!r}; expected one of {sorted(_PRESETS)}"
        )
    approvals = approvals or set()
    out = SupplyResolution()

    # lines still needing a choice, deep-copied so the caller's lines are never
    # touched — grouped below so one demand is answered by one product, never
    # split across skus the way SAP's usage-probability model would.
    pending: list[RequirementLine] = []
    for req in requirements:
        line = req.model_copy(deep=True)   # never mutate the caller's lines
        if line.sku:
            _name_product(line, line.sku, catalog)
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
        if chosen is None:
            # Every candidate is infeasible. This used to fall back to the full
            # field and pick one anyway: no warning, nothing in `unresolved`, and
            # a BOM line naming a product that cannot physically be cut to the
            # piece — after which fulfill() raised ValueError from OUTSIDE the
            # routes' try/except, i.e. a 500 where the sibling "no eligible item"
            # case gets a 400. A silent wrong answer followed by a crash is two
            # bugs, not a fallback. It is the same fact as an empty eligibility
            # set — nothing here can supply this part — so it is reported the
            # same way, with the candidates that were tried in `params`.
            for line in lines:
                out.warnings.append(StrategyWarning(
                    code="no_eligible_item", severity="error",
                    message=f"No eligible product can supply {line.role}: none of "
                            f"{', '.join(m.sku for m in usable)} can be cut to the "
                            "required piece.",
                    params={"role": line.role, "slot_key": line.slot_key,
                            "skus": ", ".join(m.sku for m in usable)},
                ))
                out.unresolved.append(line)
            continue
        for line in lines:
            _name_product(line, chosen.sku, catalog)
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


def _choose(usable, lines, catalog, inventory, preset) -> "EligibleItem | None":
    """One member: no decision. More than one: the choice is coupled to the cut
    plan — stock lengths cannot be ranked without planning the cuts (Task 8).
    `None` means every candidate was infeasible and there is no answer to give.

    The single-member path deliberately does NOT check feasibility: with one
    candidate there is no choice to make, and fulfill() already has a defined
    answer for each way that one product can fall short — an unknown sku becomes
    a flagged zero-priced line, and a piece longer than its stock becomes a
    ValueError the routes now convert to a 400. Adding a feasibility gate here
    would reroute the unknown-product case away from that flagged line.

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
        # No candidate can supply this part. Answering anyway would be a wrong
        # answer with nobody told, so there is no answer — the caller reports it
        # as `no_eligible_item` + an `unresolved` line, exactly as it reports an
        # empty eligibility set.
        return None

    def rank(m):
        cost = costs[m.sku]
        # `_waste` plans real cuts for `sku` — only safe once `_candidate_cost`
        # has already proved the sku buildable. Every member of `feasible` has,
        # by the filter above, so this tier can never reach a sku plan_cuts
        # would raise on.
        waste = _waste(m.sku, lines, catalog, inventory)
        if preset == "honour_priority":
            return (m.priority, cost, waste, m.sku)
        return (cost, waste, m.priority, m.sku)

    return min(feasible, key=rank)
