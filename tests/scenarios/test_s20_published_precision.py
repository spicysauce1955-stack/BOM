"""S20 — a published span limit that falls between whole millimetres.

`contract.md`:112-117, second half: *"any arithmetic that MULTIPLIES a published
value — a count, a pitch, a span limit — consumes the thousandths and rounds only
its output."* The span layout DIVIDES by the maximum to get a bay count, and five
of the ACTIVE snapshot's six span magnitudes are not whole millimetres, so a limit
rounded on arrival buys an extra post on about one run length in fifty.

It is a scenario rather than a unit test for two reasons. The arithmetic is only
half the behaviour — the other half is that the fence is built a fraction outside
a tested configuration and the plan SAYS SO, which is a claim about the strategy,
the decision graph and the BOM together. And it is the only run in this suite
where a bay is legitimately wider than its own resolved maximum with no override
behind it: the second authorized exception to the hard-max invariant, which lived
in the code for twelve commits with nothing in the release gate observing it.

See docs/scenarios/golden-scenarios.md §S20 for the numbers, and the section "The
hard maximum's second authorized exception" for the invariant it amends.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.model import KnowledgeVersion, SetParam
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology
from tests.scenarios.published_limit_fixture import (
    EXACT_RUN_MM,
    PUBLISHED_CEIL_MM,
    PUBLISHED_LIMIT_MILLI,
    PUBLISHED_MAX_MM,
    ROUNDED,
    RUN_MM,
    WHOLE_LIMIT_MILLI,
    WHOLE_RUN_MM,
    published_knowledge,
)

SITE = SiteConditions(exposure_category="B")


def _spine(knowledge, length_mm: int):
    """Topology -> strategy -> decisions -> requirements -> fulfillment -> BOM."""
    catalog = demo_catalog()
    result = generate(straight_topology(length_mm), knowledge, catalog, site=SITE)
    reqs = resolve_supply(
        derive_requirements(result.strategy, catalog), catalog).requirements
    return result, reqs, fulfill(reqs, catalog)


def _published(length_mm: int = RUN_MM, milli: int = PUBLISHED_LIMIT_MILLI,
               lexeme: str = '56"'):
    return _spine(published_knowledge(milli, lexeme), length_mm)


def _rounded_limit_knowledge():
    """The counterfactual: the SAME limit, stated as the whole millimetre the
    conversion rounds it to. Not the old code — an authored rule saying 1422 —
    because what is being priced here is the number, not a diff."""
    kb = published_knowledge()
    kb.versions = [v for v in kb.versions
                   if "max_span_mm" not in {a.param for a in v.actions
                                            if a.kind == "set_param"}]
    kb.versions.append(KnowledgeVersion(
        object_id="K-ROUNDED", version=1, type="hard_constraint",
        title="max span 1422 (the published limit, rounded on arrival)",
        actions=[SetParam(param="max_span_mm", value=PUBLISHED_MAX_MM)]))
    return kb


def test_s20_three_bays_not_four():
    """`ceil(4267000 / 1422400)` is 3; `ceil(4267 / 1422)` is 4.

    The thousandths reach the divider, so the run is three bays on four posts.
    Spend them on arrival and the same fence is four bays on five posts — the
    extra post, footing and pour the clause exists to prevent, bought back for
    six tenths of a millimetre.
    """
    result, _, _ = _published()
    assert [sp.width_mm for sp in result.strategy.spans] == [1423, 1422, 1422]
    assert sum(sp.width_mm for sp in result.strategy.spans) == RUN_MM
    assert len(result.strategy.posts) == 4

    rounded, _, _ = _spine(_rounded_limit_knowledge(), RUN_MM)
    assert [sp.width_mm for sp in rounded.strategy.spans] == [1067, 1067, 1067, 1066]
    assert len(rounded.strategy.posts) == 5

    # ...and the decision node still explains the fence in whole millimetres,
    # because that is the unit the fence is built in: `value_milli` reaches the
    # divider and nothing else.
    firings = [n for n in result.graph.nodes if n.action == "resolve_max_span"]
    assert firings and all(n.payload["value"] == PUBLISHED_MAX_MM for n in firings)


def test_s20_the_residue_is_forced_and_bounded():
    """Three integer bays summing to 4267 cannot all be <= 1422 (3 x 1422 = 4266).

    So one bay carries the leftover 0.6 mm. The bound it may reach is
    `ceil(limit)` and not a tolerance: with `n = ceil(L / max)` the widest bay is
    at most `floor(L / n) + 1` while `L / n <= max`, so no admissible layout ever
    lands above it. That is what keeps the guard against an ACCIDENTAL over-wide
    bay exactly where it was.
    """
    result, _, _ = _published()
    widths = [sp.width_mm for sp in result.strategy.spans]
    assert max(widths) == PUBLISHED_CEIL_MM
    assert max(widths) * 1000 - PUBLISHED_LIMIT_MILLI == 600
    assert max(widths) * 1000 - PUBLISHED_LIMIT_MILLI < 1000, "never a whole mm over"
    assert len(widths) * PUBLISHED_MAX_MM < RUN_MM, "3 x 1422 cannot reach 4267"


def test_s20_the_rounding_is_reported_once_per_segment():
    """One `info` warning carrying the published limit at published precision.

    `info`, because nothing is wrong and nothing can be fixed — which is also why
    it is a decision and not a `Gap`: a gap names a row a curator could author,
    and no row anybody could write makes 4267 divide into three whole
    millimetres. The two sub-millimetre figures ride as `_milli` params; a
    `*_mm` param would be rounded to the grid by the display layer and print
    `1422`, reporting our unit problem as the customer's.
    """
    result, _, _ = _published()
    codes = [w.code for w in result.strategy.warnings]
    assert codes.count(ROUNDED) == 1, "once per segment, not once per bay"

    warning = next(w for w in result.strategy.warnings if w.code == ROUNDED)
    assert warning.severity == "info"
    assert warning.params["n"] == 3
    assert warning.params["widest_mm"] == PUBLISHED_CEIL_MM
    assert warning.params["max_mm"] == PUBLISHED_MAX_MM
    assert warning.params["limit_milli"] == PUBLISHED_LIMIT_MILLI
    assert warning.params["over_milli"] == 600
    assert warning.params["run_id"] == "run1"

    assert not [g for g in result.strategy.gaps
                if g.because and g.because.code == ROUNDED]
    nodes = [n for n in result.graph.nodes if n.action == ROUNDED]
    assert len(nodes) == 1 and warning.decision_ref == nodes[0].id


def test_s20_the_published_row_governed_and_was_not_defeated():
    """The rule was not beaten: it is the number that CHOSE the bay count.

    CLAUDE.md reserves a `defeated` edge for the version that actually lost, and
    one here would tell a reader the manufacturer's maximum was overridden — when
    it was honoured everywhere a whole millimetre can honour it.
    """
    result, _, _ = _published()
    node = next(n for n in result.graph.nodes if n.action == ROUNDED)
    edges = result.graph.in_edges(node.id)
    governed = [e for e in edges if e.type == "governed_by"]
    assert governed and all("footing_schedule" in (e.knowledge_ref or "")
                            for e in governed)
    assert not [e for e in edges if e.type == "defeated"]
    # it hangs off the layout it is about, so `ancestors` walks from the bay to
    # the published row through it
    assert any(result.graph.node(e.from_id).action == "layout_spans"
               for e in edges if e.type == "input_from")


def test_s20_the_bill_is_the_three_bay_bill_and_every_line_traces():
    """A warning is a note on an answer, not an input to one."""
    result, reqs, bom = _published()
    assert {l.sku: l.purchase_qty for l in bom.lines} == {
        "POST-S": 4, "POST-CAP": 4, "CONC-25": 2, "RAIL-3000": 3, "SCREW-S10": 2}
    assert {l.sku: l.engineering_qty for l in bom.lines} == {
        "POST-S": 4, "POST-CAP": 4, "CONC-25": 4, "RAIL-3000": 6, "SCREW-S10": 24}
    assert sum(l.total_cents for l in bom.lines) == 19100

    # the fourth bay's price, which is what the thousandths bought back
    _, _, rounded_bom = _spine(_rounded_limit_knowledge(), RUN_MM)
    assert sum(l.total_cents for l in rounded_bom.lines) == 24500

    # BOM line -> requirement -> element -> decision, over a run carrying the
    # rounding node: no line, requirement or peg moved because of it.
    req_ids = {r.id for r in reqs}
    element_ids = set(result.strategy.element_ids())
    for r in reqs:
        assert r.pegs and all(e in element_ids for e in r.pegs)
        assert all(result.graph.nodes_for_element(e) for e in r.pegs)
    covered = ({p for l in bom.lines for p in l.pegs}
               | {p for a in bom.allocations for p in a.pegs})
    assert covered == req_ids


def test_s20_one_millimetre_shorter_and_there_is_nothing_to_say():
    """4266 mm under the SAME published limit: three bays of 1422, and silence.

    The pair is the point. The difference between a report and a silence must be
    the leftover residue, not the presence of a fractional limit — a warning on
    this run would be crying over a fence that is inside its published maximum.
    Every purchased quantity and every price is the same on both runs, so what
    the millimetre changes is the cut list and whether the plan says anything.
    """
    result, _, bom = _published(EXACT_RUN_MM)
    assert [sp.width_mm for sp in result.strategy.spans] == [1422, 1422, 1422]
    assert len(result.strategy.posts) == 4
    assert ROUNDED not in [w.code for w in result.strategy.warnings]
    assert ROUNDED not in [n.action for n in result.graph.nodes]

    _, _, over_bom = _published(RUN_MM)
    assert [l.model_dump() for l in bom.lines] == [
        l.model_dump() for l in over_bom.lines]
    # ...and the one thing that does differ is the millimetre itself: two of the
    # six rail cuts on the reported run are 1 mm longer, out of the same 3 bars.
    def _cuts(plan):
        return sorted(p.length_mm for bar in plan.bars for p in bar.pieces)
    assert (sum(_cuts(over_bom.cut_plans["RAIL-3000"]))
            - sum(_cuts(bom.cut_plans["RAIL-3000"]))) == 2


def test_s20_a_whole_millimetre_limit_says_nothing_ever():
    """75 in is 1905.000 mm — the one magnitude of the six with nothing below the
    millimetre — and it must lay out exactly as an authored rule would.

    This is the arithmetic reason no other scenario in the file can produce the
    warning: where the limit is whole, `max_span_milli` is `max_span * 1000` and
    the remainder ceiling is exactly `max_span`.
    """
    result, _, _ = _published(WHOLE_RUN_MM, WHOLE_LIMIT_MILLI, '75"')
    assert [sp.width_mm for sp in result.strategy.spans] == [1800] * 5
    assert ROUNDED not in [w.code for w in result.strategy.warnings]
    assert ROUNDED not in [n.action for n in result.graph.nodes]
