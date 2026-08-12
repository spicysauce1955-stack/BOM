"""Choosing among eligible items. With one member there is nothing to choose and
the line simply gains its SKU; with more than one, the choice is cost-driven
(S15 in tests/scenarios covers the case that actually needs a cut plan to
resolve — stock lengths that cannot be ranked by nominal length alone)."""

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import Catalog, DivisibleLinear, Product
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


def test_an_unrecognised_preset_is_a_loud_error_not_a_silent_least_cost():
    """GenerationRun.objective_preset is stored as a plain str, so a stored run
    (or a typo) can carry a value outside Preset's Literal. `_choose` branches
    only on "honour_priority", so treating anything else as least-cost — the
    behaviour before this fix — would silently reinterpret garbage input as a
    real preset instead of refusing it."""
    with pytest.raises(ValueError, match="fewest_new_stock"):
        resolve_supply([_line()], demo_catalog(), preset="fewest_new_stock")


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


# --- fix round 1: infeasible candidates must lose gracefully, never crash ----

_FEASIBILITY_CATALOG = Catalog.of(
    Product(sku="GOOD", name="Good rail",
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3),
            price_cents=1000),
    Product(sku="SHORT", name="Too-short rail",
            consumption=DivisibleLinear(purchase_length_mm=1000, kerf_mm=3),
            price_cents=500),
)


def test_a_too_short_candidate_loses_without_crashing():
    """SHORT (1000 mm stock) cannot hold a 1500 mm piece at all: 1500+3=1503 >
    1000+3=1003. That candidate must rank last (infinite cost), not blow up
    plan_cuts/_waste with a piece it was never built to hold. GOOD (3000 mm)
    needs 1 bar for the single 1500 mm cut: 1 * 1000c = 1000c."""
    line = _line(engineering_qty=1, eligibility=Eligibility(members=[
        EligibleItem(sku="GOOD", priority=1),
        EligibleItem(sku="SHORT", priority=2),
    ]))
    out = resolve_supply([line], _FEASIBILITY_CATALOG, preset="least_cost")
    assert out.requirements[0].sku == "GOOD"
    assert out.decisions[0]["chosen"] == "GOOD"
    assert out.decisions[0]["rejected"] == ["SHORT"]


def test_a_candidate_missing_from_the_catalog_loses_without_crashing():
    """GHOST names a sku the catalog has never heard of — an authoring gap,
    not a code path that should ever raise KeyError out of resolve_supply."""
    line = _line(engineering_qty=1, eligibility=Eligibility(members=[
        EligibleItem(sku="GOOD", priority=1),
        EligibleItem(sku="GHOST", priority=2),
    ]))
    out = resolve_supply([line], _FEASIBILITY_CATALOG, preset="least_cost")
    assert out.requirements[0].sku == "GOOD"
    assert out.decisions[0]["chosen"] == "GOOD"
    assert out.decisions[0]["rejected"] == ["GHOST"]


# --- fix round 1: grouping must not drop a line's own priority -------------

_TWO_RAILS_CATALOG = Catalog.of(
    Product(sku="RAIL-3000", name="Rail stock 3000",
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3),
            price_cents=1800),
    Product(sku="RAIL-3050", name="Rail stock 3050",
            consumption=DivisibleLinear(purchase_length_mm=3050, kerf_mm=3),
            price_cents=1850),
)


def test_two_lines_with_opposite_priority_order_each_get_their_own_choice():
    """Both lines are eligible for the same two skus, but line1 prefers
    RAIL-3000 first and line2 prefers RAIL-3050 first — opposite priority
    orders, so they are different demands and must land in different groups.
    Grouping on the sku set alone would merge them and answer both with
    whichever line happened to be first, misreporting the other's decision
    in the graph that IS the explanation."""
    line1 = _line(id="req0001", eligibility=Eligibility(members=[
        EligibleItem(sku="RAIL-3000", priority=1),
        EligibleItem(sku="RAIL-3050", priority=2),
    ]))
    line2 = _line(id="req0002", eligibility=Eligibility(members=[
        EligibleItem(sku="RAIL-3000", priority=2),
        EligibleItem(sku="RAIL-3050", priority=1),
    ]))
    out = resolve_supply([line1, line2], _TWO_RAILS_CATALOG, preset="honour_priority")

    by_id = {r.id: r.sku for r in out.requirements}
    assert by_id == {"req0001": "RAIL-3000", "req0002": "RAIL-3050"}

    decisions = {d["requirement_id"]: d for d in out.decisions}
    assert decisions["req0001"]["chosen"] == "RAIL-3000"
    assert decisions["req0001"]["rejected"] == ["RAIL-3050"]
    assert decisions["req0002"]["chosen"] == "RAIL-3050"
    assert decisions["req0002"]["rejected"] == ["RAIL-3000"]


# ---- when nothing fits at all (fix wave, finding D) --------------------------

def _short_stock_catalog() -> Catalog:
    """Two divisible products, both with stock shorter than the piece asked for."""
    catalog = demo_catalog()
    catalog.products["SHORT-A"] = Product(
        sku="SHORT-A", name="Short stock A", price_cents=100,
        consumption=DivisibleLinear(purchase_length_mm=1000))
    catalog.products["SHORT-B"] = Product(
        sku="SHORT-B", name="Short stock B", price_cents=90,
        consumption=DivisibleLinear(purchase_length_mm=900))
    return catalog


def test_all_candidates_infeasible_is_reported_not_silently_picked():
    """Neither 1000 mm nor 900 mm stock can yield a 1500 mm piece.

    The old fallback (`feasible = usable`) picked one anyway: no warning, nothing
    in `unresolved`, a BOM line naming a product that cannot be cut — and then
    fulfill() raised ValueError from outside the routes' try/except, so a 500
    where the sibling no-eligible-item case gets a 400. Silence followed by a
    crash is not a fallback."""
    line = _line(engineering_qty=1, eligibility=Eligibility(members=[
        EligibleItem(sku="SHORT-A", priority=1),
        EligibleItem(sku="SHORT-B", priority=2),
    ]))
    out = resolve_supply([line], _short_stock_catalog())

    assert out.requirements == []                      # never a silent pick
    assert [r.id for r in out.unresolved] == ["req0001"]
    assert out.unresolved[0].sku == ""                 # and never a blank sku downstream
    # `no_feasible_item`, NOT `no_eligible_item`: there were candidates and they
    # were tried. One code for both cases sent the reader to the fence model when
    # the thing to go fix was the catalog's stock length.
    assert [w.code for w in out.warnings] == ["no_feasible_item"]
    assert out.warnings[0].severity == "error"
    assert out.warnings[0].params["role"] == "rail"
    assert out.warnings[0].params["skus"] == "SHORT-A, SHORT-B"


def test_all_candidates_infeasible_never_reaches_fulfill():
    """The point of routing it to `unresolved`: what fulfill() is handed is still
    only lines that can actually be built, so it cannot raise."""
    from fenceai.fulfillment.fulfill import fulfill

    catalog = _short_stock_catalog()
    line = _line(engineering_qty=1, eligibility=Eligibility(members=[
        EligibleItem(sku="SHORT-A"), EligibleItem(sku="SHORT-B")]))
    out = resolve_supply([line], catalog)
    assert fulfill(out.requirements, catalog).lines == []


def test_a_lone_infeasible_candidate_is_refused_exactly_like_a_field_of_them():
    """The gap-1 defect, at the unit that owns it.

    `_choose` used to return the single member without asking whether it could
    supply anything, on the reasoning that with one candidate there is no choice
    to make. The line then reached `fulfill()`, `plan_cuts` raised
    "piece 1500 mm exceeds stock length 1000 mm for SHORT-A", and /bom,
    /structure and /quote all answered 400 with that raw English sentence — no
    code, no params, no locale entry. Reachable through the catalog and
    knowledge editors alone (see tests/api/test_api.py::
    test_a_rail_default_pointing_at_short_stock_reads_as_unsupplied)."""
    line = _line(engineering_qty=1, eligibility=Eligibility(
        members=[EligibleItem(sku="SHORT-A")]))
    out = resolve_supply([line], _short_stock_catalog())

    assert out.requirements == []
    assert [r.id for r in out.unresolved] == ["req0001"]
    assert [w.code for w in out.warnings] == ["no_feasible_item"]
    assert out.warnings[0].params["skus"] == "SHORT-A"


def test_a_lone_infeasible_candidate_never_reaches_fulfill():
    """The invariant the fix exists for, asserted against the function that used
    to raise: fulfill() is handed nothing it cannot build."""
    from fenceai.fulfillment.fulfill import fulfill

    catalog = _short_stock_catalog()
    line = _line(engineering_qty=1, eligibility=Eligibility(
        members=[EligibleItem(sku="SHORT-A")]))
    out = resolve_supply([line], catalog)
    assert fulfill(out.requirements, catalog).lines == []   # no ValueError


def test_an_authored_sku_too_short_for_its_cut_is_refused_too():
    """A line arriving WITH a sku skips the choice — there is nothing to choose —
    but not the feasibility gate, or the same raw 400 comes back through a
    different door. No shipped demand line carries both a sku and a cut length,
    so this path is guarded rather than observed."""
    line = _line(sku="SHORT-A", engineering_qty=1, eligibility=Eligibility())
    out = resolve_supply([line], _short_stock_catalog())

    assert out.requirements == []
    assert [w.code for w in out.warnings] == ["no_feasible_item"]
    assert [r.id for r in out.unresolved] == ["req0001"]


def test_an_authored_sku_absent_from_the_catalog_is_still_the_flagged_bom_line():
    """The feasibility gate must not swallow the OTHER way a product falls short.
    An unknown sku is not a length problem: fulfill() prices it at zero and flags
    it, which is how a post pointing at a deleted product still shows up."""
    from fenceai.fulfillment.fulfill import fulfill

    catalog = _short_stock_catalog()
    line = _line(sku="GHOST-1", engineering_qty=1, cut_length_mm=None,
                 role="post", slot_key="", eligibility=Eligibility())
    out = resolve_supply([line], catalog)
    assert out.unresolved == [] and out.warnings == []
    assert fulfill(out.requirements, catalog).lines[0].notes == [
        "unknown product — not in catalog"]


def test_one_feasible_candidate_among_infeasible_ones_still_wins():
    """The guard must not turn a partially-infeasible field into a refusal —
    RAIL-3000 can be cut to 1500 mm and is the answer."""
    line = _line(engineering_qty=1, eligibility=Eligibility(members=[
        EligibleItem(sku="SHORT-A", priority=1),
        EligibleItem(sku="RAIL-3000", priority=2),
    ]))
    out = resolve_supply([line], _short_stock_catalog())
    assert out.unresolved == [] and out.warnings == []
    assert out.requirements[0].sku == "RAIL-3000"


# ---- the unit comes from the product, not from the length (finding B) --------

def test_the_resolved_unit_is_the_one_fulfill_will_stamp_on_the_bom_line():
    """asked and purchased are keyed on (sku, unit) in the parts ledger, and the
    two strings come from ONE function — so a product whose consumption kind
    disagrees with the line's shape (indivisible, but carrying a cut length)
    cannot split the ledger."""
    from fenceai.fulfillment.fulfill import engineering_unit_for

    catalog = demo_catalog()
    for sku, expected in [("RAIL-3000", "cut"), ("POST-S", "each"),
                          ("SCREW-S10", "each"), ("CONC-25", "application"),
                          ("GATE-KIT-1000", "each"), ("NOT-IN-CATALOG", "each")]:
        assert engineering_unit_for(catalog, sku) == expected, sku

    # POST-S is indivisible AND has attrs.length_mm, so it legitimately backs a
    # slot with a cut length — and is still counted in eaches.
    line = _line(cut_length_mm=1500,
                 eligibility=Eligibility(members=[EligibleItem(sku="POST-S")]))
    resolved = resolve_supply([line], catalog).requirements[0]
    assert resolved.sku == "POST-S" and resolved.unit == "each"


# ---- grouping is not bookkeeping: it decides the answer ----------------------

def test_grouping_changes_which_product_wins():
    """The measurement behind `validate_model` refusing `Eligibility.group`.

    Cut planning is not additive, so which lines are costed TOGETHER decides
    which product is cheapest. Two lines (1500 mm and 1000 mm) over BIG (3000 mm
    stock @ 1000c) and SMALL (1600 mm stock @ 600c): as one group BIG wins (both
    pieces share one bar for 1000c, against two SMALL bars for 1200c); split in
    two, SMALL wins each (600c against 1000c).

    `resolve_supply` groups by the members' (sku, priority, approval) signature
    and never reads `Eligibility.group`, so an authored group name would neither
    join nor separate the lines it names — and this is the difference it would
    have made."""
    catalog = Catalog.of(
        Product(sku="BIG", name="3 m bar", price_cents=1000,
                consumption=DivisibleLinear(purchase_length_mm=3000)),
        Product(sku="SMALL", name="1.6 m bar", price_cents=600,
                consumption=DivisibleLinear(purchase_length_mm=1600)),
    )
    members = [EligibleItem(sku="BIG", priority=1), EligibleItem(sku="SMALL", priority=2)]

    def line(n, cut):
        return _line(id=f"req000{n}", engineering_qty=1, cut_length_mm=cut,
                     slot_key=f"rail{n}",
                     eligibility=Eligibility(members=[m.model_copy() for m in members]))

    a, b = line(1, 1500), line(2, 1000)
    one_group = resolve_supply([a, b], catalog)
    assert [r.sku for r in one_group.requirements] == ["BIG", "BIG"]

    apart = [resolve_supply([a], catalog), resolve_supply([b], catalog)]
    assert [r.sku for out in apart for r in out.requirements] == ["SMALL", "SMALL"]
