"""Choosing among eligible items. With one member there is nothing to choose and
the line simply gains its SKU; the two-member case arrives in the next task."""

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import RequirementLine
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fulfillment.supply import resolve_supply


def _line(**kw) -> RequirementLine:
    base = dict(id="req0001", sku="", engineering_qty=2, unit="cut",
                cut_length_mm=1500, role="rail", slot_key="rail",
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]))
    return RequirementLine(**{**base, **kw})


def test_a_single_member_resolves_to_itself():
    out = resolve_supply([_line()], demo_catalog())
    assert out.requirements[0].sku == "RAIL-3000"
    assert out.warnings == []


def test_a_line_that_already_names_a_sku_is_left_alone():
    """Posts, caps and concrete never go through eligibility."""
    line = _line(sku="POST-S", eligibility=Eligibility(), role="post", slot_key="")
    assert resolve_supply([line], demo_catalog()).requirements[0].sku == "POST-S"


def test_an_empty_eligibility_warns_rather_than_guessing():
    out = resolve_supply([_line(eligibility=Eligibility())], demo_catalog())
    assert out.requirements[0].sku == ""
    assert [w.code for w in out.warnings] == ["no_eligible_item"]
    assert out.warnings[0].params["role"] == "rail"


def test_a_suggest_only_member_is_not_used_without_approval():
    line = _line(eligibility=Eligibility(
        members=[EligibleItem(sku="RAIL-3000", approval="suggest_only")]))
    out = resolve_supply([line], demo_catalog())
    assert out.requirements[0].sku == ""
    assert [w.code for w in out.warnings] == ["substitute_needs_approval"]


def test_resolution_does_not_mutate_the_caller_s_lines():
    """generate() is pure and the report is a pure function of its inputs; a
    resolver that mutated in place would make a stored run's requirements depend
    on whether anyone had looked at the BOM."""
    line = _line()
    resolve_supply([line], demo_catalog())
    assert line.sku == ""


def test_resolved_line_keeps_its_engineering_fields():
    """resolve_supply only WRITES the sku — it must not lose pegs, quantities or
    cut-length data on the way, or the ledger and cut planner both go blind."""
    line = _line(pegs=["span1"])
    out = resolve_supply([line], demo_catalog())
    resolved = out.requirements[0]
    assert resolved.id == "req0001"
    assert resolved.pegs == ["span1"]
    assert resolved.engineering_qty == 2
    assert resolved.unit == "cut"
    assert resolved.cut_length_mm == 1500
    assert resolved.role == "rail"
    assert resolved.slot_key == "rail"


def test_two_members_chosen_by_priority_records_a_decision():
    """With more than one usable member, the lowest-priority (then sku-ordered)
    member wins today, and the choice is recorded for the decision graph — Task 8
    replaces the comparison itself, not this bookkeeping."""
    line = _line(eligibility=Eligibility(members=[
        EligibleItem(sku="RAIL-3000", priority=2),
        EligibleItem(sku="POST-S", priority=1),
    ]))
    out = resolve_supply([line], demo_catalog())
    assert out.requirements[0].sku == "POST-S"
    assert out.warnings == []
    assert len(out.decisions) == 1
    decision = out.decisions[0]
    assert decision["requirement_id"] == "req0001"
    assert decision["slot_key"] == "rail"
    assert decision["chosen"] == "POST-S"
    assert decision["preset"] == "least_cost"
    assert decision["rejected"] == ["RAIL-3000"]


def test_an_approved_suggest_only_member_is_used():
    """The rejection in test_a_suggest_only_member_is_not_used_without_approval is
    only half the contract — once the sku is in `approvals`, it must actually be
    used, not just tolerated."""
    line = _line(eligibility=Eligibility(
        members=[EligibleItem(sku="RAIL-3000", approval="suggest_only")]))
    out = resolve_supply([line], demo_catalog(), approvals={"RAIL-3000"})
    assert out.requirements[0].sku == "RAIL-3000"
    assert out.warnings == []
