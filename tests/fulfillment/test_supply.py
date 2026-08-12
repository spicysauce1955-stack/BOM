"""Choosing among eligible items. With one member there is nothing to choose and
the line simply gains its SKU; with more than one, the choice is cost-driven
(S15 in tests/scenarios covers the case that actually needs a cut plan to
resolve — stock lengths that cannot be ranked by nominal length alone)."""

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
    assert out.requirements == []            # never a blank-sku line in `requirements`
    assert out.unresolved[0].sku == ""
    assert [w.code for w in out.warnings] == ["no_eligible_item"]
    assert out.warnings[0].params["role"] == "rail"


def test_a_suggest_only_member_is_not_used_without_approval():
    line = _line(eligibility=Eligibility(
        members=[EligibleItem(sku="RAIL-3000", approval="suggest_only")]))
    out = resolve_supply([line], demo_catalog())
    assert out.requirements == []
    assert out.unresolved[0].sku == ""
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


def test_two_members_chosen_by_cost_records_a_decision():
    """With more than one usable member, least_cost plans the cuts for each
    candidate and picks the cheaper one — priority only breaks a cost tie.
    The line asks for 2 cuts of 1500 mm: RAIL-3000 (divisible_linear, 3000 mm
    stock, 3 mm kerf) needs 2 new bars since two 1500 mm pieces cost 1503 mm
    each against a 3003 mm capacity (3006 > 3003) — 2 * 1800c = 3600c. POST-S
    (indivisible_discrete) is bought 1-for-1 at 2500c each for 2 = 5000c.
    3600c < 5000c, so RAIL-3000 wins despite its lower (worse) priority."""
    line = _line(eligibility=Eligibility(members=[
        EligibleItem(sku="RAIL-3000", priority=2),
        EligibleItem(sku="POST-S", priority=1),
    ]))
    out = resolve_supply([line], demo_catalog())
    assert out.requirements[0].sku == "RAIL-3000"
    assert out.warnings == []
    assert len(out.decisions) == 1
    decision = out.decisions[0]
    assert decision["requirement_id"] == "req0001"
    assert decision["slot_key"] == "rail"
    assert decision["chosen"] == "RAIL-3000"
    assert decision["preset"] == "least_cost"
    assert decision["rejected"] == ["POST-S"]


def test_an_approved_suggest_only_member_is_used():
    """The rejection in test_a_suggest_only_member_is_not_used_without_approval is
    only half the contract — once the sku is in `approvals`, it must actually be
    used, not just tolerated."""
    line = _line(eligibility=Eligibility(
        members=[EligibleItem(sku="RAIL-3000", approval="suggest_only")]))
    out = resolve_supply([line], demo_catalog(), approvals={"RAIL-3000"})
    assert out.requirements[0].sku == "RAIL-3000"
    assert out.warnings == []


def test_a_blank_sku_can_never_reach_requirements_even_in_a_mixed_batch():
    """The invariant fulfill() and the parts ledger depend on: no caller can hand a
    blank-sku line to fulfill() by forgetting to filter, because resolve_supply
    never puts one in `requirements` to begin with — resolvable and unresolvable
    lines are sorted into two different lists, structurally, not by convention."""
    resolvable = _line(id="req0001")
    no_item = _line(id="req0002", eligibility=Eligibility())
    needs_approval = _line(id="req0003", eligibility=Eligibility(
        members=[EligibleItem(sku="RAIL-3000", approval="suggest_only")]))
    already_named = _line(id="req0004", sku="POST-S", eligibility=Eligibility(),
                          role="post", slot_key="")

    out = resolve_supply([resolvable, no_item, needs_approval, already_named], demo_catalog())

    assert {r.sku for r in out.requirements} == {"RAIL-3000", "POST-S"}
    assert all(r.sku for r in out.requirements)   # the invariant: never blank here
    assert {r.id for r in out.requirements} == {"req0001", "req0004"}

    assert {r.id for r in out.unresolved} == {"req0002", "req0003"}
    assert all(r.sku == "" for r in out.unresolved)

    # one warning per unresolved line, in the same order the loop visited them
    assert [w.code for w in out.warnings] == [
        "no_eligible_item", "substitute_needs_approval",
    ]
