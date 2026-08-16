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

from pydantic import BaseModel, Field

from fenceai.catalog.model import Catalog, purchase_price_cents
from fenceai.core.units import Cents, Mm
from fenceai.demand.derive import DemandLine
from fenceai.fulfillment.lines import ResolvedSupplyLine
from fenceai.fulfillment.cutplan import CutPiece, RemnantStock, plan_cuts
from fenceai.fulfillment.fulfill import Inventory, engineering_unit_for
from fenceai.strategy.model import StrategyWarning

Preset = Literal["least_cost", "honour_priority"]
# introspected from the Literal itself so the runtime check and the type can
# never drift apart (task 10 fix round 1, finding 3)
_PRESETS: frozenset[str] = frozenset(get_args(Preset))

_INFEASIBLE = 2**62


class Candidate(BaseModel):
    """One product that was in the running, and how it ranked.

    `cost_cents` and `waste_mm` are None for an INFEASIBLE candidate rather than
    zero or a sentinel: nothing was planned for it, and a zero there reads as
    "free", which is the opposite of what happened."""

    sku: str
    priority: int
    feasible: bool = True
    cost_cents: Cents | None = None
    waste_mm: Mm | None = None


class SupplyDecision(BaseModel):
    """Why one product was bought and the others were not.

    One per eligibility GROUP, not per requirement line: a 40-slat panel answers
    one demand once, and forty identical nodes would bury the explanation they
    exist to give (the same rule `fit_pattern` follows — one node per span, never
    one per member)."""

    requirement_ids: list[str] = []
    pegs: list[str] = []          # strategy element ids the group's lines peg to
    slot_key: str = ""
    role: str = ""
    chosen: str = ""
    preset: str = ""
    candidates: list[Candidate] = []

    @property
    def rejected(self) -> list[str]:
        return [c.sku for c in self.candidates if c.sku != self.chosen]


class SupplyResolution(BaseModel):
    # every line here has a real sku — enforced by the TYPE now, so it cannot be
    # bypassed by a caller, a refactor, or a three-word edit
    requirements: list[ResolvedSupplyLine] = []
    # lines that could not be resolved (no eligible item, nothing feasible, or
    # only suggest-only members without approval). Still DemandLines, which is
    # the point: an unresolved line is one that never got a product, and it
    # cannot reach `fulfill()` because `fulfill()` does not accept its type.
    # Each has a matching entry in `warnings`, so nothing goes silent.
    unresolved: list[DemandLine] = []
    warnings: list[StrategyWarning] = []
    decisions: list[SupplyDecision] = []


def _usable(members, approvals: set[str]) -> list:
    return [m for m in members if m.approval == "auto" or m.sku in approvals]


def _element_params(line: DemandLine) -> dict[str, str | int]:
    """The part of a warning that says WHICH element it is about.

    `role` + `slot_key` alone name a KIND of part, not an instance: every bay of
    a 60-bay fence resolves the same rail slot, so sixty identical sentences
    named no bay between them. The requirement's pegs are the strategy element
    ids that asked for it, which is the same handle `report/structure.py` inverts
    to put a part on a bay row — so a reader (and the structure tab, which can
    map an element id to its bay tag) can tell one from another."""
    return {"pegs": ", ".join(line.pegs)}


def _piece_too_long(sku: str, lines: list[DemandLine], catalog: Catalog) -> bool:
    """This product exists, and one of these pieces is longer than its stock.

    The same comparison `plan_cuts` makes before it raises — kerf cancels on both
    sides (`piece + kerf > stock + kerf`), so it is simply `piece > stock`. An
    unknown sku is NOT a length problem and is not reported as one: `fulfill()`
    has its own defined answer for it (a flagged, zero-priced line)."""
    product = catalog.products.get(sku)
    if product is None:
        return False
    sem = product.consumption
    if sem.kind != "divisible_linear":
        return False
    return any(
        line.cut_length_mm > sem.purchase_length_mm
        for line in lines
        if line.cut_length_mm is not None
    )


def _can_supply(sku: str, lines: list[DemandLine], catalog: Catalog) -> bool:
    """Can this candidate supply these lines AT ALL — the gate every candidate
    passes before it can be chosen, whatever the preset and however many rivals
    it has. Pure catalog + geometry: no cut plan is built, so it is cheap enough
    to apply to a one-member group."""
    return sku in catalog.products and not _piece_too_long(sku, lines, catalog)


def _resolved(line: DemandLine, sku: str, catalog: Catalog) -> ResolvedSupplyLine:
    """Give a line its product — and, in the SAME statement, the unit that
    product is counted in.

    This is the only place a demand acquires a sku, which makes it the only place
    that can decide the unit; setting the two together is what stops the asked
    and purchased sides of the parts ledger from ever disagreeing. The value
    comes from `fulfillment.fulfill.engineering_unit_for`, which is literally the
    function `fulfill()` uses to stamp `BomLine.engineering_unit`.
    """
    return ResolvedSupplyLine.of(line, sku, engineering_unit_for(catalog, sku))


def _infeasible_warning(line: DemandLine, skus: list[str]) -> StrategyWarning:
    """"There are candidates, and not one of them fits" — distinct from
    `no_eligible_item` ("there are no candidates at all"), because the two send
    the reader to different places: one to the model's eligibility, the other to
    the catalog's stock lengths."""
    joined = ", ".join(skus)
    return StrategyWarning(
        code="no_feasible_item", severity="error",
        message=f"No product can supply {line.role} ({line.slot_key}) for "
                f"{', '.join(line.pegs) or 'this fence'}: none of {joined} fits "
                "the required piece.",
        params={"role": line.role, "slot_key": line.slot_key, "skus": joined,
                **_element_params(line)},
        element_refs=list(line.pegs),
    )


def resolve_supply(
    requirements: list[DemandLine],
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
    pending: list[DemandLine] = []
    for req in requirements:
        line = req.model_copy(deep=True)   # never mutate the caller's lines
        # There is no longer a branch for "this line already knows its product".
        # A sku knowledge chose arrives as a ONE-MEMBER eligibility, so it takes
        # the same path as every other line and passes the same feasibility gate
        # — which is what the old authored-sku branch had to re-implement, and
        # what it was missing until a saved run could be made permanently
        # unreadable through the UI alone.
        if not line.eligibility.members:
            out.warnings.append(StrategyWarning(
                code="no_eligible_item", severity="error",
                message=f"No product is eligible to supply {line.role}.",
                params={"role": line.role, "slot_key": line.slot_key,
                        **_element_params(line)},
                element_refs=list(line.pegs),
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
                        "sku": line.eligibility.members[0].sku,
                        **_element_params(line)},
                element_refs=list(line.pegs),
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
    groups: dict[tuple, list[DemandLine]] = {}
    for line in pending:
        usable_members = _usable(line.eligibility.members, approvals)
        key = tuple(sorted((m.sku, m.priority, m.approval) for m in usable_members))
        groups.setdefault(key, []).append(line)

    for key, lines in sorted(groups.items()):
        usable = [m for m in lines[0].eligibility.members
                  if (m.sku, m.priority, m.approval) in key]
        chosen, candidates = _choose(usable, lines, catalog, inventory, preset)
        if chosen is None and len(usable) == 1 and usable[0].sku not in catalog.products:
            # ONE candidate, and it names a product the catalog does not have.
            # That is not a length problem, and `_piece_too_long`'s docstring says
            # so: `fulfill()` has its own defined answer — a zero-priced, flagged
            # line — which is how a post pointing at a DELETED product still shows
            # up on the BOM instead of vanishing into a warnings panel.
            #
            # Narrow on purpose. With rivals, an unknown sku must stay filtered
            # out so a real product can win; `_candidate_cost` cannot price a
            # product that does not exist, and a candidate costing nothing would
            # beat every one that does. With exactly one there is no rival to
            # protect, and losing the line loses the information.
            for line in lines:
                out.requirements.append(_resolved(line, usable[0].sku, catalog))
            continue
        if chosen is None:
            # Every candidate is infeasible. This used to fall back to the full
            # field and pick one anyway: no warning, nothing in `unresolved`, and
            # a BOM line naming a product that cannot physically be cut to the
            # piece — after which fulfill() raised ValueError from OUTSIDE the
            # routes' try/except, i.e. a 500 where the sibling "no eligible item"
            # case gets a 400. A silent wrong answer followed by a crash is two
            # bugs, not a fallback. Nothing here can supply this part, which is
            # NEARLY the same fact as an empty eligibility set — near enough to
            # take the same path, far enough to deserve its own code: "nothing is
            # eligible" and "the eligible items are all too short" are different
            # things to go fix, and one code for both left the reader guessing.
            for line in lines:
                out.warnings.append(
                    _infeasible_warning(line, [m.sku for m in usable]))
                out.unresolved.append(line)
            continue
        for line in lines:
            out.requirements.append(_resolved(line, chosen.sku, catalog))
        if candidates:
            # only when there was a real choice: `_choose` returns no candidates
            # for a lone feasible member, because there is nothing to account for
            out.decisions.append(SupplyDecision(
                requirement_ids=[line.id for line in lines],
                pegs=sorted({peg for line in lines for peg in line.pegs}),
                slot_key=lines[0].slot_key, role=lines[0].role,
                chosen=chosen.sku, preset=preset, candidates=candidates,
            ))

    # Grouping is an internal optimisation — one demand answered once — and it
    # must not reorder the ANSWER. Posts, caps and concrete used to be emitted
    # immediately, in demand order, because they skipped the choice; now that
    # every line is grouped, the natural output order is group order, which
    # reads as an unrelated change on every /bom response and in every gate
    # file. Restored to the order demand asked in, which is the order the fence
    # is built in.
    position = {req.id: i for i, req in enumerate(requirements)}
    out.requirements.sort(key=lambda line: position[line.id])
    out.unresolved.sort(key=lambda line: position[line.id])
    return out


def _candidate_cost(sku: str, lines: list[DemandLine], catalog, inventory) -> int:
    """Cents to buy this candidate for these lines, by actually planning the cuts.
    A candidate the planner cannot use at all costs infinitely."""
    if not _can_supply(sku, lines, catalog):
        return _INFEASIBLE
    product = catalog.products[sku]
    sem = product.consumption
    if sem.kind != "divisible_linear":
        return purchase_price_cents(product) * sum(l.engineering_qty for l in lines)
    pieces = [
        CutPiece(length_mm=l.cut_length_mm, requirement_id=l.id)
        for l in lines for _ in range(l.engineering_qty)
        if l.cut_length_mm is not None
    ]
    remnants = [
        RemnantStock(inventory_item_id=i.id, length_mm=i.length_mm)
        for i in (inventory or Inventory()).for_sku(sku)
        if i.kind == "remnant" and i.length_mm
    ]
    plan = plan_cuts(sku, sem, pieces, remnants)
    return plan.new_bar_count * purchase_price_cents(product)


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
    """One FEASIBLE member: no decision. More than one: the choice is coupled to
    the cut plan — stock lengths cannot be ranked without planning the cuts
    (Task 8). `None` means every candidate was infeasible and there is no answer.

    Feasibility is resolved FIRST and filters the field before any other tier
    runs, AND BEFORE the count of candidates is looked at. It used to be skipped
    for a one-member group, on the reasoning that with one candidate there is no
    choice to make and `fulfill()` has a defined answer for each way one product
    can fall short. It does not: a piece longer than the stock reached
    `plan_cuts`, which raises a raw English sentence, and that sentence became a
    400 on /bom, /structure and /quote at once — a saved run made permanently
    unreadable through the catalog and knowledge editors alone, with the
    structure tab then rendering "generate a strategy to see how it is laid out",
    which is false. "Nothing can supply this" is the same fact whether one
    candidate failed or five did, so it takes the same path either way.

    An unusable candidate (piece longer than its stock, or a sku absent from the
    catalog) must lose gracefully under every preset, never win on priority, and
    never reach a later tier's helper (`_waste`) with a sku it can't plan for.
    Filtering here — rather than folding `_INFEASIBLE` into the rank tuple —
    makes it structurally impossible for a third tier added later to forget this
    guard: whatever it does, it only ever sees skus already proven buildable.
    """
    feasible = [m for m in usable if _can_supply(m.sku, lines, catalog)]
    infeasible = [Candidate(sku=m.sku, priority=m.priority, feasible=False)
                  for m in usable if m not in feasible]
    if not feasible:
        # No candidate can supply this part. Answering anyway would be a wrong
        # answer with nobody told, so there is no answer — the caller reports it
        # as `no_feasible_item` + an `unresolved` line, alongside the way it
        # reports an empty eligibility set.
        return None, infeasible
    if len(feasible) == 1:
        # No RANKING to do, but if other candidates were considered and could not
        # supply the part, that is still the answer to "why this one" — so they
        # are recorded. No cost is planned for any of them: a cost here would
        # imply a comparison that never happened.
        lone = Candidate(sku=feasible[0].sku, priority=feasible[0].priority)
        return feasible[0], ([lone, *infeasible] if infeasible else [])

    # only now, with a real choice to make, is it worth planning cuts per candidate
    costs = {m.sku: _candidate_cost(m.sku, lines, catalog, inventory) for m in feasible}

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

    winner = min(feasible, key=rank)
    ranked = [
        Candidate(sku=m.sku, priority=m.priority, feasible=True,
                  cost_cents=costs[m.sku],
                  waste_mm=_waste(m.sku, lines, catalog, inventory))
        for m in sorted(feasible, key=rank)
    ]
    return winner, ranked + infeasible
