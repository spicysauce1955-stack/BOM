"""The thousandths a publisher sent, and what happens when we spend them early.

`contract.md:112-117` is BINDING twice over. It says conversion from thousandths
happens at one named point and ROUNDS there — `to_mm`, covered by
`tests/knowledge/test_parameters.py` — and then it says something the first half
does not imply:

> Any arithmetic that MULTIPLIES a published value — a count, a pitch, a span
> limit — consumes the thousandths and rounds only its output.

This file is about the second half, which was breached in production. The ACTIVE
snapshot publishes `max_span_mm` as a named member of a `paired(...)` value type,
five of its six span magnitudes are not whole millimetres, and the span layout
divides by the limit to get a bay count. Rounding first — correctly, at the one
named point — moved the count on 2318 of the first hundred thousand run lengths:
mostly DOWN, buying the extra post, footing and pour the clause names, and once
UP, laying a bay 0.2 mm wider than a sealed maximum.

**Why it stayed invisible, and what this file does about it.** Nobody's scan
descended into `value_type`. A scan enumerating `ParameterTable.parameter`
returns `footing_schedule` and never `max_span_mm`, because amendment 006 — which
we accept-modified so pairs name their members — moved the parameter name inside
the type string. The threshold was found by hand, by the other team. So the first
section here is a LEDGER: it enumerates every parameter published as a paired
member across the vendored real snapshots and pins the inventory, so the next
such threshold fails a test rather than waiting to be noticed. The second section
is the invariant that does not need updating when it does: no published
thousandth is dropped on its way into knowledge.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.evaluator import resolve_param
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.knowledge.parameters import (
    ParameterRow, ParameterTable, Provenance, Quantity, expand, paired_columns, to_mm,
)
from fenceai.core.errors import GenerationFailure
from fenceai.core.gaps import SourceRef
from fenceai.core.units import round_milli_to_mm
from fenceai.knowledge.snapshot import load
from fenceai.knowledge.source_policy import SHIPPED_DEFAULT
from fenceai.project.model import Selection, SiteConditions
from fenceai.strategy.layout import (
    LayoutResult, admits_widths, alternative_widths, equal_layout,
    equal_layout_milli, layout_segment, min_bay_count, remainder_ceiling_mm,
)
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import LockBay, Override
from fenceai.topology.station import make_anchor
from tests.conftest import demo_catalog, straight_topology

FIXTURES = Path(__file__).parent / "fixtures" / "real_snapshots"


def _tables() -> list[ParameterTable]:
    """Every parameter table in every vendored real snapshot.

    All three fixtures, not the one this file cares about: the point of a ledger
    is that it looks everywhere the data actually is, and the reason this breach
    survived is that something looked in one place.
    """
    out: list[ParameterTable] = []
    for path in sorted(FIXTURES.glob("*.json")):
        snapshot, _ = load(json.loads(path.read_text()))
        out.extend(snapshot.parameters)
    return out


def _published_quantities() -> list[tuple[str, str, Quantity]]:
    """`(table parameter, the parameter actually BOUND, the quantity)` for every
    published length in the vendored snapshots — descending into `value_type`.

    The two names differ exactly where the breach hid: a `paired(...)` table's
    `parameter` is `footing_schedule` and the parameters it binds are
    `footing_depth_mm` and `max_span_mm`. Any scan that reports only the first is
    blind to every threshold published as a member, which is where the span limit
    this engine divides by has been living since amendment 006.
    """
    out: list[tuple[str, str, Quantity]] = []
    for table in _tables():
        columns = paired_columns(table.value_type)
        if columns:
            for row in table.rows:
                for pair in row.value:
                    for name, q in zip(columns, pair):
                        out.append((table.parameter, name, q))
        elif table.quantity_unit() == "mm":
            for row in table.rows:
                if isinstance(row.value, Quantity):
                    out.append((table.parameter, table.parameter, row.value))
    return out


# -- the ledger: what is published as a paired MEMBER ---------------------------

def test_every_parameter_published_as_a_paired_member_is_enumerated():
    """The scan neither team had, pinned as an inventory.

    This asserts an exact set on purpose, and it is meant to FAIL when the
    Knowledge Platform re-cuts with a new paired member or a new magnitude. That
    failure is the whole feature: somebody then has to look at the new number and
    decide whether anything multiplies it, which is the review this breach
    escaped. Updating the expectation is the correct fix — silently widening the
    assertion into `>= 1` is not.

    Named members, never positions. `paired(footing_depth_mm:mm, max_span_mm:mm)`
    is amendment 006's form precisely so a publisher who lists the span first is
    not misread as sinking a 1676 mm hole under a 610 mm span.
    """
    members: dict[str, set[str]] = {}
    for table in _tables():
        for name in paired_columns(table.value_type):
            members.setdefault(table.parameter, set()).add(name)

    assert members == {"footing_schedule": {"footing_depth_mm", "max_span_mm"}}
    # ...and the parameter this engine DIVIDES by is one of them, which is the
    # fact a scan on `ParameterTable.parameter` cannot see.
    assert "max_span_mm" not in {t.parameter for t in _tables()}
    assert "max_span_mm" in members["footing_schedule"]


def test_the_published_span_magnitudes_and_which_are_not_whole_millimetres():
    """The six magnitudes, and the five that cost money.

    A span limit stated in inches is a span limit with thousandths: `56"` is
    1422.4 mm and nothing rounds it away at the source. The lexemes are asserted
    beside the numbers because they are what a curator checks against the page —
    if this test ever has to change, the inches say which page.
    """
    spans = {(q.amount_milli, q.value_raw[0])
             for table_param, bound, q in _published_quantities()
             if bound == "max_span_mm"}
    assert spans == {
        (1422400, '56"'), (1676400, '66"'), (1727200, '68"'),
        (1905000, '75"'), (2235200, '88"'), (2463800, '97"'),
    }
    not_whole = sorted(m for m, _ in spans if m % 1000)
    assert not_whole == [1422400, 1676400, 1727200, 2235200, 2463800]


# -- the invariant: nothing is dropped on the way in ---------------------------

def test_no_published_thousandth_is_dropped_on_the_way_into_knowledge():
    """Every published length reaches a `SetParam` with its thousandths intact.

    Unlike the ledger above this needs no maintenance: a new table, a new member
    or a new magnitude satisfies it or fails it on its own terms. It is the
    property that makes the ledger's failure recoverable — once someone has
    looked at the new number, the number is already carried.

    Both expansion paths, deliberately. The plain `quantity(mm)` path was not the
    one that broke, and it carries `value_milli` anyway: `footing_depth_mm` is
    published as 609.6 mm and `footing_diameter_mm` as 304.8, so a future consumer
    that computes a pour volume — `depth x diameter^2`, multiplication of two
    published values — finds the thousandths waiting rather than re-learning this
    lesson at a concrete supplier's expense.
    """
    seen = 0
    for table in _tables():
        versions, _, _ = expand(table, policy=SHIPPED_DEFAULT)
        published = {
            name: q.amount_milli
            for table_param, name, q in _published_quantities()
            if table_param == table.parameter
        }
        for version in versions:
            for action in version.actions:
                if action.kind != "set_param" or action.param not in published:
                    continue
                assert action.value_milli is not None, (
                    f"{table.parameter} -> {action.param} landed at rest with no "
                    "published precision beside it"
                )
                assert to_mm(Quantity(amount_milli=action.value_milli, unit="mm")) \
                    == action.value
                assert action.effective_milli() == action.value_milli
                seen += 1
    assert seen, "the fixtures published no lengths at all — the scan is broken"


def test_a_set_param_refuses_thousandths_that_disagree_with_its_value():
    """The field is only worth having if the two agree.

    A value at rest and a milli that round to different millimetres are two
    different numbers wearing one name, and the fence would then depend on which
    field the reader happened to pick. `2463800` is the clause's own example and
    `2464` is its correct rounding; `2463` is the floor the clause forbids.
    """
    ok = SetParam(param="max_span_mm", value=2464, value_milli=2463800)
    assert ok.effective_milli() == 2463800

    with pytest.raises(ValueError, match="thousandths"):
        SetParam(param="max_span_mm", value=2463, value_milli=2463800)


def test_an_authored_rule_carries_no_precision_and_scaling_it_is_exact():
    """Every rule in `demo.py` is ours and int mm all the way down, so
    `effective_milli()` is `value * 1000` — the exact no-op that makes wiring a
    divider through it safe for the whole existing suite."""
    for version in demo_knowledge().versions:
        for action in version.actions:
            if action.kind == "set_param":
                assert action.value_milli is None
                assert action.effective_milli() == action.value * 1000


# -- the arithmetic: only the count consumes them ------------------------------

REAL_SPANS = [1422400, 1676400, 1727200, 1905000, 2235200, 2463800]


@pytest.mark.parametrize("max_span_milli", REAL_SPANS)
def test_the_bay_count_never_diverges_from_the_published_limit(max_span_milli):
    """The measurement, over the first hundred metres at one-millimetre steps.

    `ceil(L / max_span)` computed on the true limit is the definition of the
    right answer, so this compares the layout against it directly rather than
    against a table of expected counts. Before the fix these six magnitudes
    diverged on 966, 684, 308, 0, 180 and 180 lengths respectively; the whole
    point is that the only acceptable number is zero.
    """
    for length_mm in range(1, 100_001):
        exact = -(-length_mm * 1000 // max_span_milli)
        assert len(equal_layout_milli(length_mm * 1000, max_span_milli)) == exact


@pytest.mark.parametrize("max_span_milli", REAL_SPANS)
def test_the_true_bay_width_fits_and_the_stored_one_is_over_by_under_a_millimetre(
    max_span_milli,
):
    """The harm rounding UP causes, and the residue ADR-0002 leaves behind.

    `2463800` rounds to `2464 mm` — correctly — and a 2464 mm run was then laid
    out as ONE bay of 2464.000 mm against a maximum of 2463.8 that a stamped
    engineering table set. Cheaper by a post, and over the limit. Dividing by
    the published thousandths fixes that: the run becomes two bays.

    What it does NOT do is put every stored bay inside the limit, and pretending
    otherwise would be the more dangerous claim. Three bays of a 4267 mm run
    under a 1422.4 mm maximum are 1422.333 mm each and all fit; stored as
    integer millimetres they must sum to 4267, and `1422 x 3` is 4266 — so the
    remainder spread puts ONE bay at 1423, six tenths of a millimetre over. The
    alternative is a fourth post, which is the whole harm the clause names. So
    the property is stated as it actually holds, on both sides of the rounding:
    the TRUE bay width always fits, and the STORED one is never a whole
    millimetre over. `_SegmentModel.admits()` is the same bound at the
    generator's guard.
    """
    for length_mm in range(1, 20_001):
        widths = equal_layout_milli(length_mm * 1000, max_span_milli)
        assert sum(widths) == length_mm, "widths still tile the run exactly"
        # the true width — what the layout actually decided — is inside the limit
        assert length_mm * 1000 <= len(widths) * max_span_milli
        # ...and rounding it to whole millimetres costs less than one millimetre
        assert max(widths) <= -(-max_span_milli // 1000)


def test_the_clauses_own_worked_examples():
    """Two lengths, named in the brief and in the clause, spelled out.

    A parametrized sweep proves the property; these two say what it BUYS, so a
    reader who breaks it sees the cost rather than a count mismatch.
    """
    # DOWN: 1422.4 floored to the nearest mm at 1422 turns three bays into four
    assert len(equal_layout_milli(4267 * 1000, 1422400)) == 3
    assert len(equal_layout(4267, 1422)) == 4, "the pre-fix count, for contrast"
    # UP: 2463.8 rounded to 2464 lets one bay stand at exactly the rounded limit
    assert equal_layout_milli(2464 * 1000, 2463800) == [1232, 1232]
    assert equal_layout(2464, 2464) == [2464], "the pre-fix layout, for contrast"


@pytest.mark.parametrize("max_span_mm", [1200, 1500, 1676, 1800, 2400])
def test_whole_millimetre_data_is_an_exact_no_op(max_span_mm):
    """The property the golden scenarios depend on.

    Every rule this repo authored is int mm, so `value * 1000` is exact and the
    milli divider must agree with the mm one on every length. If this ever fails,
    the scenarios have moved and the fix is wrong rather than merely incomplete.
    """
    for length_mm in range(1, 20_001):
        assert equal_layout_milli(length_mm * 1000, max_span_mm * 1000) \
            == equal_layout(length_mm, max_span_mm)


def test_layout_segment_defaults_to_the_millimetre_limit():
    """A caller that knows nothing about published precision keeps its behaviour.

    `max_span_milli` is optional for this reason: `strategy/overrides.py`,
    `alternative_widths` and every existing test pass a millimetre limit and no
    thousandths, and omitting it must mean `* 1000` rather than zero.
    """
    assert layout_segment(4267, 1422).widths == layout_segment(
        4267, 1422, max_span_milli=1422000).widths
    assert layout_segment(4267, 1422, max_span_milli=1422400).widths == [1423, 1422, 1422]


# -- end to end: the published row lays out the fence --------------------------

def _real_span_table(milli: int, lexeme: str) -> ParameterTable:
    """One `paired` row in the shape and provenance the real snapshot uses, so
    §1.4 admits it and it lands as knowledge rather than as a gap."""
    return ParameterTable(
        parameter="footing_schedule", task="structural_parameter",
        value_type="paired(footing_depth_mm:mm, max_span_mm:mm)",
        rows=[ParameterRow(
            provenance=Provenance(
                cites=[SourceRef(id="doc-1", belongs_to="doc-1")],
                source_class="sealed_approval", curation_level=2),
            value=[[Quantity(amount_milli=609600, unit="mm", value_raw=['24"']),
                    Quantity(amount_milli=milli, unit="mm", value_raw=[lexeme])]])],
    )


def test_a_published_span_limit_reaches_the_layout_with_its_thousandths():
    """The whole chain, on the number the clause names.

    A 4267 mm run under a published 56" (1422.4 mm) maximum is three bays. The
    engine used to build four — an extra post, an extra footing, an extra pour —
    because the thousandths were spent at expansion, four calls before the
    division that needed them. Asserted through `generate()` rather than through
    the layout function, because every link in between is where it went wrong:
    expansion, the action at rest, `resolve_param`, the segment model, the
    divider.
    """
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    versions, gaps, _ = expand(_real_span_table(1422400, '56"'), policy=SHIPPED_DEFAULT)
    assert gaps == []
    kb.versions.extend(versions)

    res = resolve_param(kb, {"scope": {}, "site": {}, "run": {}}, "max_span_mm")
    winner = next(a for a in res.winner.actions if a.kind == "set_param")
    assert (winner.value, winner.value_milli) == (1422, 1422400)

    result = generate(straight_topology(4267), kb, demo_catalog(),
                      site=SiteConditions(exposure_category="B"))
    widths = [s.width_mm for s in result.strategy.spans]
    assert widths == [1423, 1422, 1422], "three bays, not four"
    assert sum(widths) == 4267
    # ...and the decision node still explains the fence in millimetres, because
    # that is the unit the fence is built in. `value_milli` reaches the divider
    # and nothing else.
    firings = [n for n in result.graph.nodes
               if n.action == "resolve_max_span"]
    assert firings and all(n.payload["value"] == 1422 for n in firings)


def test_a_published_limit_at_a_whole_millimetre_builds_what_it_always_did():
    """The control. 75" is 1905.000 mm exactly — the one magnitude of the six with
    nothing below the millimetre — and it must lay out identically either way."""
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    versions, _, _ = expand(_real_span_table(1905000, '75"'), policy=SHIPPED_DEFAULT)
    kb.versions.extend(versions)
    result = generate(straight_topology(9000), kb, demo_catalog(),
                      site=SiteConditions(exposure_category="B"))
    assert [s.width_mm for s in result.strategy.spans] == equal_layout(9000, 1905)


# -- agreement is measured where the consumer reads ----------------------------

def _row(object_id: str, value: int, milli: int | None) -> KnowledgeVersion:
    """Two published rows at the same authority and the same specificity, so
    neither `_beats` the other and the only question left is whether they AGREE."""
    return KnowledgeVersion.from_published(
        object_id=object_id, version=1, type="hard_constraint",
        actions=[SetParam(param="max_span_mm", value=value, value_milli=milli)],
    )


def test_two_rows_that_differ_below_the_millimetre_do_not_corroborate():
    """The `same_value` decision, and why it went this way.

    `2463.8` and `2464.2` both round to `2464`, so at `value` these two tie and
    were judged to AGREE: DMN ANY, no conflict raised, no `defeated` edge, and one
    of them recorded as corroborating the other. But `equal_layout_milli` now
    divides by the winner's thousandths, and the last tie-break in `resolve` is
    `object_id` — so the fence depended on the alphabet, which is exactly what the
    generator's hard-tie handling exists to refuse. Two sources that sent
    different numbers did not corroborate each other, and a graph edge saying they
    did is a false claim about the sources.

    So it is a Conflict: a warned line and a review task, never a raise. Both
    rows are `published`, and §3.2.4 forbids failing a run over a disagreement
    nobody in this repo can fix.
    """
    kb = KnowledgeBase(versions=[_row("A-ROW", 2464, 2463800),
                                 _row("B-ROW", 2464, 2464200)])
    res = resolve_param(kb, {"scope": {}}, "max_span_mm")
    assert [c.param_or_action for c in res.conflicts] == ["max_span_mm"]
    assert all(c.hard for c in res.conflicts)
    assert any(f.defeated_by for f in res.firings)
    assert not any(f.corroborated_by for f in res.firings)


def test_two_rows_that_agree_to_the_thousandth_still_corroborate():
    """The other half, unchanged. Real corroboration — two documents stating the
    same limit — must still read as agreement and draw the `corroborated_by` edge
    commit `e291d4b` added, or tightening the predicate would have turned every
    duplicate publication into a conflict."""
    kb = KnowledgeBase(versions=[_row("A-ROW", 2464, 2463800),
                                 _row("B-ROW", 2464, 2463800)])
    res = resolve_param(kb, {"scope": {}}, "max_span_mm")
    assert res.conflicts == []
    assert any(f.corroborated_by for f in res.firings)
    assert not any(f.defeated_by for f in res.firings)


def test_an_authored_row_and_a_published_row_stating_the_same_mm_agree():
    """The mixed case, and the reason `effective_milli()` normalises rather than
    comparing `value_milli` raw. An authored `1800` carries `None`; a published
    `1800000` carries thousandths. Comparing the fields would call those a
    disagreement and manufacture a conflict out of two rules that say the same
    thing."""
    kb = KnowledgeBase(versions=[
        KnowledgeVersion(object_id="A-AUTHORED", version=1, type="hard_constraint",
                         actions=[SetParam(param="max_span_mm", value=1800)]),
        _row("B-ROW", 1800, 1800000),
    ])
    res = resolve_param(kb, {"scope": {}}, "max_span_mm")
    assert res.conflicts == []
    assert any(f.corroborated_by for f in res.firings)


# -- the residue is reported, not merely tolerated ----------------------------
#
# `_SegmentModel.admits()` decided the three-bay layout is right and it is:
# a fourth bay is the extra post, footing and pour the clause exists to prevent,
# bought to recover six tenths of a millimetre. What was missing is that the
# trade was SILENT — no code, no locale entry, no decision node — so a fence
# built a fraction outside a tested configuration said nothing about it, and an
# installer with a tape could not tell a deliberate rounding from a wrong rule.

ROUNDED = "span_rounded_over_published_limit"


def _kb_with_limit(milli: int, lexeme: str) -> KnowledgeBase:
    """The demo knowledge with its authored span rule replaced by a published
    row at this magnitude — the only way to get a sub-millimetre limit into a
    run, since every rule this repo authored is whole millimetres."""
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    versions, gaps, _ = expand(_real_span_table(milli, lexeme), policy=SHIPPED_DEFAULT)
    assert gaps == []
    kb.versions.extend(versions)
    return kb


def _generated_with_limit(milli: int, lexeme: str, length_mm: int, **kw):
    return generate(straight_topology(length_mm), _kb_with_limit(milli, lexeme),
                    demo_catalog(), site=SiteConditions(exposure_category="B"),
                    **kw)


def test_the_rounded_bay_is_reported_by_its_real_numbers():
    """4267 mm under a published 56" maximum: three bays, one of them 0.6 mm over.

    The layout is the one the clause requires and is NOT under test here — the
    assertions on the widths are context, so a reader who breaks the reporting
    can see what it is reporting about. What is under test is that the choice
    leaves an artefact: a coded warning carrying the published limit at its own
    precision, and a decision node a reader lands on from the bay.
    """
    result = _generated_with_limit(1422400, '56"', 4267)
    assert [s.width_mm for s in result.strategy.spans] == [1423, 1422, 1422]

    warning = next(w for w in result.strategy.warnings if w.code == ROUNDED)
    # `info`, not `warning`: nothing here is wrong and nothing can be fixed. A
    # gap names a row a curator could author, and no row anybody could write
    # makes 4267 divide into three whole millimetres — so there is none.
    assert warning.severity == "info"
    assert not [g for g in result.strategy.gaps
                if g.because and g.because.code == ROUNDED]
    assert warning.params["n"] == 3
    assert warning.params["widest_mm"] == 1423
    # the published limit at published precision AND the millimetre it rests at.
    # Both, because they are two different facts: `limit_milli` is what the
    # sentence has to show, `max_mm` is what every clamp in the generator is
    # made against — and printing 1422 in the sentence would report a whole
    # millimetre over a number nobody published.
    assert warning.params["limit_milli"] == 1422400
    assert warning.params["max_mm"] == 1422
    assert warning.params["over_milli"] == 600

    # ONE per segment. A 60-bay fence with this limit is one fact about the
    # layout, not sixty lines on the drawing.
    assert [w.code for w in result.strategy.warnings].count(ROUNDED) == 1
    nodes = [n for n in result.graph.nodes if n.action == ROUNDED]
    assert len(nodes) == 1
    assert warning.decision_ref == nodes[0].id


def test_the_node_cites_the_published_limit_as_governing_not_as_defeated():
    """The rule was not beaten: it is the number that CHOSE the bay count.

    A `defeated` edge is reserved for the version that actually lost (CLAUDE.md),
    and one here would tell a reader the manufacturer's maximum was overridden —
    when in fact it was honoured everywhere a whole millimetre can honour it.
    """
    result = _generated_with_limit(1422400, '56"', 4267)
    node = next(n for n in result.graph.nodes if n.action == ROUNDED)
    edges = result.graph.in_edges(node.id)
    governed = [e for e in edges if e.type == "governed_by"]
    assert governed and all("footing_schedule" in (e.knowledge_ref or "")
                            for e in governed)
    assert not [e for e in edges if e.type == "defeated"]
    # and it hangs off the layout it is about, so `ancestors` walks from the bay
    # to the rule through it
    assert any(result.graph.node(e.from_id).action == "layout_spans"
               for e in edges if e.type == "input_from")


def test_the_sentence_renders_in_both_languages_at_published_precision():
    """en/he, mm and cm, with no placeholder left over — and the fraction intact.

    The regression this pins is not a missing key: it is `{limit_milli}` being
    renamed `{limit_mm}` by somebody tidying suffixes, which would round the
    limit onto the millimetre grid and print "1422". The bay is 1423, so the
    sentence would then read as a whole millimetre over a limit nobody sealed —
    our unit problem reported as the customer's, which is the one thing this
    warning exists not to do.
    """
    from fenceai.decisions.explain import explain_node

    result = _generated_with_limit(1422400, '56"', 4267)
    node = next(n for n in result.graph.nodes if n.action == ROUNDED)
    for lang in ("en", "he"):
        for units, limit, over in (("mm", "1422.4", "0.6"), ("cm", "142.24", "0.06")):
            line = explain_node(result.graph, node, lang=lang, units=units)
            assert "{" not in line, (lang, units, line)
            assert limit in line and over in line, (lang, units, line)


def test_a_whole_millimetre_limit_says_nothing_ever():
    """75" is 1905.000 mm and there is no fraction to carry.

    Every rule this repo authored is int millimetres, so `max_span_milli` is
    `max_span * 1000` and the remainder ceiling is exactly `max_span` — which is the
    arithmetic reason this warning cannot reach a golden scenario. Asserted on
    the one published magnitude of the six that is whole, so the claim is made
    against real data rather than against an authored rule alone.
    """
    result = _generated_with_limit(1905000, '75"', 9000)
    assert [s.width_mm for s in result.strategy.spans] == equal_layout(9000, 1905)
    assert ROUNDED not in [w.code for w in result.strategy.warnings]
    assert ROUNDED not in [n.action for n in result.graph.nodes]


def test_a_spread_that_lands_inside_the_limit_says_nothing():
    """4266 mm under the same 56" maximum: three bays of 1422, and nothing to say.

    One millimetre shorter than the case above and the remainder vanishes — the
    run divides exactly, every stored bay sits on the largest whole millimetre
    the limit admits, and a warning here would be crying over a fence that is
    inside its published maximum. The pair is deliberate: the difference between
    a report and a silence must be the residue, not the fractional limit.
    """
    result = _generated_with_limit(1422400, '56"', 4266)
    assert [s.width_mm for s in result.strategy.spans] == [1422, 1422, 1422]
    assert ROUNDED not in [w.code for w in result.strategy.warnings]
    assert ROUNDED not in [n.action for n in result.graph.nodes]


@pytest.mark.parametrize("max_span_milli,runs,worst_milli", [
    (1422400, 966, 600),
    (1676400, 684, 600),
    (1727200, 308, 800),
    (1905000, 0, 0),      # whole millimetre: nothing to report, ever
    (2235200, 180, 800),
    (2463800, 640, 200),
])
def test_how_much_residue_there_is_to_report(max_span_milli, runs, worst_milli):
    """The measurement, pinned: over the first hundred metres at one-millimetre
    steps, how many run lengths end with a bay wider than the published limit,
    and by how much at worst.

    Not a property — a census. It says the reporting surface is neither empty
    nor constant noise (about one length in a hundred), and it says the worst
    case is eight tenths of a millimetre rather than something a person should
    act on. Measured on the layout function rather than through `generate()`
    because a hundred thousand generations is not a test; the end-to-end cases
    above are what tie the predicate to the warning.

    If a re-cut moves these numbers, that is worth a look and not a rubber
    stamp: the counts are a function of the published magnitudes alone.
    """
    over = [max(equal_layout_milli(L * 1000, max_span_milli)) * 1000 - max_span_milli
            for L in range(1, 100_001)]
    assert sum(1 for o in over if o > 0) == runs
    assert max(over) == worst_milli
    # ...and never a whole millimetre over, which is what makes it reportable
    # rather than a refusal: above the ceiling the generator still stops.
    assert max(over) < 1000


# -- the bound is a predicate over a LAYOUT, never a ceiling on a bay ----------
#
# `ceil(published limit)` was a free-standing per-bay maximum for one release and
# it was unsound. The argument that made it safe — with `n = ceil(L/max)` the
# widest bay is `floor(L/n)+1` at most, so nothing can land above the ceiling —
# is an argument about layouts THIS ENGINE computes, and three of the four sites
# comparing against it were not given layouts this engine computed: a person's
# stored answer, a hand-placed bay, and the offer side, which was meanwhile
# filtering against the ROUNDED millimetre and so refused to propose the very
# widths the accept side would take.
#
# `layout.admits_widths` carries the premise as a condition, and this section is
# what makes the bound falsifiable in the loosening direction — the direction
# that had no test at all. Widening the ceiling by a single millimetre, or the
# guard by one, left the whole suite green.

_MAGNITUDES = [1422400, 1676400, 1727200, 1905000, 2235200, 2463800]


@pytest.mark.parametrize("max_span_milli", _MAGNITUDES)
def test_every_layout_this_engine_computes_is_admitted(max_span_milli):
    """The premise the old ceiling assumed, now asserted rather than assumed.

    A predicate that refused one of these would not be conservative, it would be
    a `GenerationFailure` on a fence the clause requires — so this is the guard
    against tightening, and the sweep below is the guard against loosening. Both
    directions, on the real published magnitudes, because a bound with a test on
    only one side is the bound that drifted.
    """
    max_span_mm = round_milli_to_mm(max_span_milli)
    for length_mm in range(1, 20_001):
        widths = equal_layout_milli(length_mm * 1000, max_span_milli)
        assert admits_widths(widths, length_mm, max_span_mm,
                             max_span_milli=max_span_milli), (length_mm, widths)


def test_the_ceiling_belongs_to_the_layout_that_could_not_be_split_again():
    """The whole fix in one place: the same 1423 mm bay, admitted and refused.

    Under a published 1422.4 mm maximum a 4267 mm run is three bays that all fit
    at 1422.333 mm; stored as whole millimetres they must sum to 4267, so one of
    them carries the odd millimetre and stands 0.6 mm over. That bay is
    admissible because the alternative is a fourth post to recover six tenths of
    a millimetre.

    On a 4269 mm run the same limit allows FOUR bays, and three bays of 1423
    are not a rounding artefact — they are a post and a footing removed from a
    stamped schedule. A per-bay ceiling cannot tell those apart, because the
    difference is not in the bay.
    """
    assert admits_widths([1423, 1422, 1422], 4267, 1422, max_span_milli=1422400)
    assert not admits_widths([1423, 1423, 1423], 4269, 1422, max_span_milli=1422400)
    # a spare bay: the fraction was never forced, so nothing excuses it
    assert not admits_widths([1423, 1422, 1421, 1], 4267, 1422,
                             max_span_milli=1422400)
    # one millimetre above the ceiling, at the right count: a layout bug or a
    # rule carrying a wrong number, and still refused
    assert not admits_widths([1424, 1421, 1422], 4267, 1422, max_span_milli=1422400)
    # ...and the widths must still tile the gap
    assert not admits_widths([1422, 1422], 4267, 1422, max_span_milli=1422400)

    # a whole-millimetre limit — every rule this repo authored — reduces to
    # `max(widths) <= max_span` exactly, which is why nothing here can move a
    # golden scenario
    assert remainder_ceiling_mm(1905000) == 1905
    assert min_bay_count(5715, 1905000) == 3
    assert admits_widths([1905, 1905, 1905], 5715, 1905, max_span_milli=1905000)
    assert not admits_widths([1906, 1905, 1904], 5715, 1905, max_span_milli=1905000)
    # and with no thousandths at all, which is what `overrides.py` and every
    # pre-existing caller pass
    assert admits_widths([1800, 1800, 1800], 5400, 1800)
    assert not admits_widths([1801, 1800, 1799], 5400, 1800)


@pytest.mark.parametrize("milli,lexeme,length_mm,at_maximum,one_over", [
    # whole millimetre: the ceiling IS the maximum
    (1905000, '75"', 5715, [1905, 1905, 1905], [1906, 1905, 1904]),
    # fractional: the ceiling is one millimetre above the maximum at rest, and
    # the bay one millimetre above THAT is still fatal
    (1422400, '56"', 4267, [1423, 1422, 1422], [1424, 1421, 1422]),
])
def test_a_bay_at_the_maximum_builds_and_one_millimetre_over_stops_the_run(
    monkeypatch, milli, lexeme, length_mm, at_maximum, one_over,
):
    """The top invariant in `docs/scenarios/golden-scenarios.md`, "Invariants
    checked across all scenarios" — *no span
    exceeds the resolved maximum* — pinned at its boundary, in the direction that
    had no test.

    Widening the bound by one millimetre used to leave 2682 tests green: only a
    five-metre loosening tripped anything, because every existing assertion is
    about a layout comfortably inside the limit. So this asserts the two adjacent
    cases and nothing in between: the widest admissible layout is BUILT, and the
    same layout with one more millimetre in the widest bay stops the run.

    The over-wide layout is injected, because there is no data that produces one
    — which is the point. Every route in is now guarded by the same predicate, so
    the guard at the span loop is defending against a layout bug or a rule
    carrying a wrong number, and that is exactly what is simulated: the accident
    itself, the way `tests/strategy/test_lock_bay.py` simulates it.
    """
    from fenceai.strategy import generator as gen

    result = _generated_with_limit(milli, lexeme, length_mm)
    assert [s.width_mm for s in result.strategy.spans] == at_maximum

    monkeypatch.setattr(
        gen, "layout_segment",
        lambda length_mm, max_span_mm, **kw: LayoutResult(
            widths=list(one_over), rejected_alternative=None),
    )
    with pytest.raises(GenerationFailure) as exc:
        _generated_with_limit(milli, lexeme, length_mm, offer_alternatives=False)
    assert "exceeds hard max" in str(exc.value)


def test_the_offer_bound_and_the_accept_bound_are_the_same_bound():
    """One choice set, one admissibility rule — and it used to be two, pointing
    opposite ways.

    `alternative_widths` filtered offers against the rounded millimetre limit
    while the accept side compared a returning answer against `ceil(published)`,
    so the engine would never OFFER a 1423 mm bay and would happily ACCEPT one.
    Neither half is what the other assumed, and a person could only reach the
    lax half by holding an answer from before.
    """
    limit_mm, milli = 1422, 1422400
    for length_mm in range(1, 3_001):
        default = equal_layout_milli(length_mm * 1000, milli)
        for name, widths in alternative_widths(
            length_mm, limit_mm, default=default, max_span_milli=milli,
            piece_stock_mm=2000,
        ):
            assert admits_widths(widths, length_mm, limit_mm,
                                 max_span_milli=milli), (length_mm, name, widths)

    # the concrete pair: a tiling at the ceiling on a run the limit allows four
    # bays for. Not offered, and not accepted either — the two bounds now agree
    # about the case that showed they disagreed.
    assert alternative_widths(4269, limit_mm, default=[1068, 1067, 1067, 1067],
                              exact_mm=1423, max_span_milli=milli) == []
    assert not admits_widths([1423, 1423, 1423], 4269, limit_mm,
                             max_span_milli=milli)


def test_a_stored_answer_of_over_limit_bays_is_refused_and_says_whose_it_was():
    """The regression the per-bay ceiling introduced, end to end.

    `Selection(bay_layout, gap:run1:0, [1423, 1423, 1423])` on a 4269 mm run
    under a published 1422.4 mm maximum: three bays over a sealed limit, one post
    and one footing short of the stamped schedule, and before the ceiling existed
    this input was REFUSED. It came back honoured, with no warning, no gap and no
    node — a stale answer building an over-maximum fence because somebody once
    chose it under a laxer rule, which is the exact sentence
    `_choice_unavailable_gap` was written for.
    """
    result = _generated_with_limit(
        1422400, '56"', 4269, offer_alternatives=False,
        choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                           widths=[1423, 1423, 1423], author="bob")])
    assert [s.width_mm for s in result.strategy.spans] \
        == equal_layout_milli(4269 * 1000, 1422400)
    assert max(s.width_mm for s in result.strategy.spans) <= 1422

    gap = next(g for g in result.strategy.gaps
               if g.because and g.because.code == "choice_unavailable")
    # the artefact a person gets: their widths, their name, and the gap they no
    # longer fit — a work item, not "an answer was lost"
    assert gap.because.params["widths"] == [1423, 1423, 1423]
    assert gap.because.params["author"] == "bob"
    assert gap.because.params["gap_mm"] == 4269
    assert gap.closes_by == "planning"
    assert ROUNDED not in [w.code for w in result.strategy.warnings]


def test_a_stored_answer_carrying_the_forced_rounding_is_still_honoured():
    """The other half, and the reason the accept side cannot simply compare
    against `max_span`.

    `[1423, 1422, 1422]` on 4267 IS the layout the clause requires — the engine
    computes it unprompted — so refusing it as a person's stored answer would
    mean the engine building a fence it will not accept back, and a
    `choice_unavailable` gap accusing them of an answer nobody could give.
    """
    result = _generated_with_limit(
        1422400, '56"', 4267, offer_alternatives=False,
        choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                           widths=[1423, 1422, 1422], author="bob")])
    assert [s.width_mm for s in result.strategy.spans] == [1423, 1422, 1422]
    assert not [g for g in result.strategy.gaps
                if g.because and g.because.code == "choice_unavailable"]
    node = next(n for n in result.graph.nodes if n.action == "resolve_choice_set")
    assert node.payload["widths"] == [1423, 1422, 1422]
    assert node.payload["chosen_by"] == "bob"


def test_a_hand_placed_bay_at_the_ceiling_is_attributed_not_narrated_as_ours():
    """A `lock_bay` of exactly `ceil(published limit)` — the width where the two
    reports could be confused, and each one must do its own job.

    1423 mm placed by hand in a 1423 mm gap under a 1422.4 mm maximum. Compared
    against a per-bay ceiling this bay was inside the bound, so the placement
    lost BOTH its artefacts at once: no `defeated` edge, so a deliberate
    departure read as the engine's own choice, and no `span_placed_over_maximum`,
    so it was unwarned as well as unattributed.

    And the rounding disclosure must stay silent. `span_rounded_over_published_limit`
    names OUR unit problem; firing it here would tell a reader that an engineer's
    placement was an arithmetic artefact of ours. What keeps it out is the bay
    COUNT clause — a lock builds ONE bay of the whole gap, and this limit allows
    two — so this is the test that pins that clause: drop it and the lock is
    re-narrated as our rounding.
    """
    topo = straight_topology(1423)
    at = make_anchor(topo, topo.run("run1"), 0).model_copy(
        update={"reanchor": "rigid"})
    result = generate(
        topo, _kb_with_limit(1422400, '56"'), demo_catalog(),
        site=SiteConditions(exposure_category="B"),
        overrides=[Override(id="o1", run_id="run1", author="dana",
                            directive=LockBay(at=at, width_mm=1423))])

    assert [s.width_mm for s in result.strategy.spans] == [1423]
    placed = next(w for w in result.strategy.warnings
                  if w.code == "span_placed_over_maximum")
    assert placed.params == {"run_id": "run1", "placed_mm": 1423, "max_mm": 1422,
                             "over_mm": 1, "author": "dana"}
    # our rounding is NOT their placement
    assert ROUNDED not in [w.code for w in result.strategy.warnings]
    assert ROUNDED not in [n.action for n in result.graph.nodes]
    # the span limit is cited as the version the placement beat
    lock = next(n for n in result.graph.nodes if n.action == "lock_bay")
    assert [e.knowledge_ref for e in result.graph.in_edges(lock.id)
            if e.type == "defeated"] == ["footing_schedule#0@v1"]
    # the control: unlocked, this run is two bays and nothing is over anything
    free = _generated_with_limit(1422400, '56"', 1423)
    assert [s.width_mm for s in free.strategy.spans] == [712, 711]
    assert [w.code for w in free.strategy.warnings] == []


def test_the_node_is_reachable_from_the_bay_that_carries_the_fraction():
    """*"The decision graph is the explanation"* — of the bay, by the bay's id.

    `scope_refs` read `span@run1:0-4267`: the SEGMENT's bounds in a span id's
    format. `n >= 2` whenever this node fires, so that id can never name a bay
    that exists, and `nodes_for_element` returned nothing for every bay in the
    segment. A reader clicking the 1423 mm bay to ask why it is 1423 landed on
    nothing — for the one decision this disclosure exists to make.

    Scoped to the bays actually over the published limit and not to the whole
    segment: a 1422 mm bay beside them is inside the maximum, and hanging the
    sentence on it would tell a reader it was over a limit it is not.
    """
    result = _generated_with_limit(1422400, '56"', 4267)
    spans = result.strategy.spans
    node = next(n for n in result.graph.nodes if n.action == ROUNDED)

    widest = max(spans, key=lambda s: s.width_mm)
    assert widest.width_mm == 1423
    assert node.id in [n.id for n in result.graph.nodes_for_element(widest.id)]
    # every scope_ref names a bay that exists — the property the old id broke
    assert set(node.scope_refs) <= {s.id for s in spans}
    assert node.scope_refs == [widest.id]
    assert f"span@run1:0-4267" not in {s.id for s in spans}
    for span in spans:
        if span.width_mm * 1000 <= 1422400:
            assert node.id not in [
                n.id for n in result.graph.nodes_for_element(span.id)]
