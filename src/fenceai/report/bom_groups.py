"""The BOM, seen from the fence rather than from the warehouse.

`Bom.lines` are flat and sorted by sku. That is the right shape for placing an
order and the wrong one for every question asked before the order is placed:
what does this SECTION need, what is in this PANEL, and which CHOICE put that
product on the list.

Derived, never stored, and — like `report/structure.py` — it recomputes no
quantity: every number here is a `ResolvedSupplyLine.engineering_qty` that
`resolve_supply` already settled, re-grouped by the pegs the line already
carries.

**The one thing this view refuses to do.** A BOM line is a PURCHASE, pooled per
sku across the whole run: one 3000 mm bar is cut into pieces for two different
bays, and a package of 20 screws is bought once for a fence. A section therefore
cannot own a fraction of a bar without an apportionment nothing measured, so
nothing here carries money, and a group states DEMAND. The purchase stays where
it is true — on the BOM — and the difference between the two is already reported,
line by line, as `unassigned` and `from_stock`.

Sections are keyed by `run_ref` rather than by the tag a sheet prints, because
`js/structure-data.js` is the single tag source for the tab and both drawings
(structure review round, 2026-08-11). A second tag derivation here is how the
schedule and the money view would eventually disagree about which section is "B".
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.demand.derive import DemandLine
from fenceai.fulfillment.fulfill import Bom
from fenceai.fulfillment.lines import ResolvedSupplyLine
from fenceai.decisions.supply import decision_id
from fenceai.fulfillment.supply import SupplyDecision
from fenceai.strategy.model import Strategy


class GroupedLine(BaseModel):
    """One material line of one group — the same numbers as the BOM's demand
    side, seen from whatever caused them.

    `length_basis` is here because dropping it made this a subtly POORER copy of
    `structure.Part`: a raked bay's rails are cut on the slope, so two lines of
    the same nominal length are different pieces, and merging them would report
    one cut length for two cuts. The comment below claimed the same merge key as
    the schedule while quietly using a shorter one.
    """

    sku: str
    qty: int
    unit: str
    role: str = ""
    slot_key: str = ""
    cut_length_mm: Mm | None = None
    length_basis: str | None = None


class SkuTotal(BaseModel):
    sku: str
    qty: int
    unit: str


class BomGroup(BaseModel):
    """`kind` is what the group IS, and the three do not partition the same way:
    `section` partitions the run, `bay` is a strict subset of it (a post belongs
    to no bay), and `decision` cuts across both. A reader that summed all three
    would count the fence three times, so the kinds are never mixed in one total.
    """

    kind: str                 # section | bay | decision
    element_id: str           # run_ref, span id, or the decision's own key
    lines: list[GroupedLine] = []
    # decision groups only: what was chosen and what it beat, so "why is this
    # product on my list" is answerable in the view that raised the question
    chosen: str = ""
    rejected: list[str] = []
    preset: str = ""


class GroupedBom(BaseModel):
    groups: list[BomGroup] = []
    # the same two buckets `report/structure.py` reports, and for the same
    # reason: a grouping that silently dropped either would balance by hiding
    unassigned: list[SkuTotal] = []
    from_stock: list[SkuTotal] = []
    unresolved: list[DemandLine] = []


def _decision_order(decision: SupplyDecision) -> tuple:
    """Ordered by what the decision is ABOUT — never by what it chose, for the
    reason its id is not: `chosen` moves with the inventory, and a total order
    needs the requirement ids anyway (two groups can share role and slot)."""
    return (decision.role, decision.slot_key, tuple(sorted(decision.requirement_ids)))


def _line(req: ResolvedSupplyLine) -> GroupedLine:
    return GroupedLine(
        sku=req.sku, qty=req.engineering_qty, unit=req.unit, role=req.role,
        slot_key=req.slot_key, cut_length_mm=req.cut_length_mm,
        length_basis=req.length_basis,
    )


def _merged(lines: list[GroupedLine]) -> list[GroupedLine]:
    """One row per (sku, unit, role, slot, cut length): two rails of one cut read
    as 2, not as 1 + 1. Same key `report/structure.py::_merge_parts` uses, so a
    bay reads the same here as it does on the schedule."""
    out: dict[tuple, GroupedLine] = {}
    for line in lines:
        key = (line.sku, line.unit, line.role, line.slot_key, line.cut_length_mm,
               line.length_basis)
        if key in out:
            out[key].qty += line.qty
        else:
            out[key] = line.model_copy(deep=True)
    return sorted(out.values(), key=lambda x: (x.sku, x.unit, x.slot_key,
                                               x.cut_length_mm or 0))


def group_bom(
    strategy: Strategy,
    requirements: list[ResolvedSupplyLine],
    bom: Bom,
    decisions: list[SupplyDecision] | None = None,
    unresolved: list[DemandLine] | None = None,
) -> GroupedBom:
    """`(strategy, requirements, bom, decisions)` -> the same demand, three ways.

    Pure. The strategy is read only to learn which element stands on which run —
    a section is a run, and `run_ref` is the element's own answer rather than a
    second layout derivation.
    """
    section_of = {**{p.id: p.run_ref for p in strategy.posts},
                  **{s.id: s.run_ref for s in strategy.spans},
                  **{g.id: g.run_ref for g in strategy.gates}}

    by_section: dict[str, list[GroupedLine]] = {}
    by_bay: dict[str, list[GroupedLine]] = {}
    spans = {s.id for s in strategy.spans}
    asked: dict[tuple[str, str], int] = {}
    unpegged: dict[tuple[str, str], int] = {}

    for req in requirements:
        line = _line(req)
        key = (req.sku, req.unit)
        asked[key] = asked.get(key, 0) + req.engineering_qty
        if not req.pegs:
            # nobody's part — it belongs in the unassigned bucket rather than in
            # a phantom section no table would ever show (`structure.py` draws
            # the same line for the same reason)
            unpegged[key] = unpegged.get(key, 0) + req.engineering_qty
            continue
        # ONCE per group, however many of its elements a line pegs to. Every
        # demand line pegs to exactly one element today, so this changes nothing
        # — and the day a line pegs to a span AND the posts it fixes to (an
        # obvious next step for panel-to-post fixings) the section total would
        # have counted it twice while `asked` counted it once, and the balance
        # test would fail with no hint why.
        for run_ref in {section_of[e] for e in req.pegs if e in section_of}:
            by_section.setdefault(run_ref, []).append(line)
        for span_id in {e for e in req.pegs if e in spans}:
            by_bay.setdefault(span_id, []).append(line)

    # A post shared at a node belongs to no single run — `Post.run_ref` says
    # `node:n1`, which is the strategy's own answer and the reason the
    # setting-out sheet gives such a post ONE tag and cross-references it from
    # the other section (`Station.shared_from`). Grouping it under a run would
    # have to pick a side; naming what it is costs nothing and stays true.
    # Sections and nodes together partition the run's demand exactly once.
    groups = [BomGroup(kind="node" if run_ref.startswith("node:") else "section",
                       element_id=run_ref, lines=_merged(lines))
              for run_ref, lines in sorted(by_section.items())]
    groups += [BomGroup(kind="bay", element_id=span_id, lines=_merged(lines))
               for span_id, lines in sorted(by_bay.items())]

    by_id = {req.id: req for req in requirements}
    for decision in sorted(decisions or [], key=_decision_order):
        lines = [_line(by_id[rid]) for rid in decision.requirement_ids if rid in by_id]
        if not lines:
            continue
        groups.append(BomGroup(
            kind="decision",
            # THE decision's id, the same one `/explain` and a comment's
            # `decision_ref` use. It was `role:slot:chosen` here, which is the
            # outcome-derived name `decisions/supply.py` refuses at length: two
            # names for one decision, and the one here changed when the yard
            # restocked, so this view could not be joined to the graph or to the
            # conversation about the same decision.
            element_id=f"s{decision_id(decision)}",
            lines=_merged(lines), chosen=decision.chosen,
            rejected=decision.rejected, preset=decision.preset,
        ))

    purchased: dict[tuple[str, str], int] = {}
    for line in bom.lines:
        key = (line.sku, line.engineering_unit)
        purchased[key] = purchased.get(key, 0) + line.engineering_qty
    unassigned: list[SkuTotal] = []
    from_stock: list[SkuTotal] = []
    for key in sorted(set(asked) | set(purchased)):
        sku, unit = key
        extra = purchased.get(key, 0) - asked.get(key, 0)
        if extra > 0:
            unassigned.append(SkuTotal(sku=sku, qty=extra, unit=unit))
        elif extra < 0:
            from_stock.append(SkuTotal(sku=sku, qty=-extra, unit=unit))
    for key, qty in sorted(unpegged.items()):
        unassigned.append(SkuTotal(sku=key[0], qty=qty, unit=key[1]))

    return GroupedBom(groups=groups, unassigned=unassigned, from_stock=from_stock,
                      unresolved=list(unresolved or []))
