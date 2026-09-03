"""The alternatives a run offers, and what a probe can honestly measure.

Stage C of task 6. Two things this file pins that the design got wrong on paper.

**Where the second point comes from.** `layout_segment` already computes the
layout it did not choose and hands it back as `rejected_alternative` — so the
cheapest honest alternative is free, and regenerating a candidate list here
would risk offering something the built layout is not among.

**What an axis may be.** A `Strategy` holds posts, spans, gates, warnings and
member runs. It holds no cut plan, because what a fence COSTS belongs to a
`SupplyRun` against one yard (ADR-0011). So a probe can count posts and pieces
and cannot count boards — and a panel promising a board saving from here would
be promising a number this layer does not have.

Literals come from the demo knowledge: `max_span_mm = 1800`, so
`equal_layout(5000, 1800)` is `[1667, 1667, 1666]` and `nominal_layout(5000,
1800)` is `[1800, 1800, 1400]`.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _run(length_mm: int = 5000, **kw):
    return generate(straight_topology(length_mm), demo_knowledge(),
                    demo_catalog(), **kw)


def _bay_layout(result):
    return next((cs for cs in result.choice_sets if cs.id == "bay_layout"), None)


def test_the_default_and_the_layout_it_displaced_are_both_offered():
    """`layout_segment` chose equal widths and kept the nominal layout it
    displaced. Both are admissible and nothing in the data prefers one, so both
    are points — and the default is first, because a panel whose first row is
    not the fence on screen is a panel that has to be read twice."""
    question = _bay_layout(_run())
    assert question is not None
    assert question.scope == "gap:run1:0"
    assert [p.widths for p in question.points] == [[1667, 1667, 1666],
                                                    [1800, 1800, 1400]]
    assert question.points[0].is_default
    assert not question.points[1].is_default


def test_a_probe_offers_nothing_and_costs_nothing():
    """The bound that makes the cost linear. A probe must not probe, or two
    questions cost five generations and six sections cost 1957."""
    probed = _run(offer_alternatives=False)
    assert probed.choice_sets == []
    assert probed.run.probe_count == 0


def test_one_probe_per_offered_alternative_and_no_more():
    """`1 + n`, by construction rather than by a cap: the baseline, then one
    generation per alternative. The default is never probed — it is the run."""
    out = _run()
    alternatives = sum(len([p for p in cs.points if not p.is_default])
                       for cs in out.choice_sets)
    assert alternatives == 1
    assert out.run.probe_count == 1


def test_an_alternative_carries_only_axes_a_generation_can_count():
    """`posts` comes from the probe's own post list. `boards` does NOT appear,
    and its absence is the point: a cut plan is built in the supply layer against
    one yard's stock and inventory, so a board count promised from here would be
    a second, disagreeing answer (ADR-0011, and the spec's own rule that nothing
    is measured outside a real generation)."""
    alternative = _bay_layout(_run()).points[1]
    assert "posts" in alternative.axes
    assert "boards" not in alternative.axes
    assert "cuts" not in alternative.axes
    assert all(isinstance(v, int) for v in alternative.axes.values())


def test_two_layouts_with_the_same_post_count_both_survive_the_filter():
    """`1667·1667·1666` and `1800·1800·1400` are three bays and four posts
    either way, so no countable axis separates them and neither dominates. The
    difference is one odd bay — which is taste, is printed on the row, and does
    not eliminate."""
    question = _bay_layout(_run())
    default, other = question.points
    assert default.axes["posts"] == other.axes["posts"]
    assert other.delta == {}


def test_a_run_with_only_one_admissible_layout_asks_nothing():
    """3600 mm divides exactly at the maximum span, so the equal and nominal
    layouts agree, `rejected_alternative` is None, and there is no question. A
    set with one point is not a question."""
    out = _run(3600)
    assert [s.width_mm for s in out.strategy.spans] == [1800, 1800]
    assert _bay_layout(out) is None
    assert out.run.probe_count == 0


def test_the_probe_does_not_leak_into_the_baseline():
    """A probe generates with one answer swapped in. If its selection reached
    the baseline, the fence on screen would be the last thing probed."""
    out = _run()
    assert [s.width_mm for s in out.strategy.spans] == [1667, 1667, 1666]
    assert out.strategy.gaps == [] or all(
        g.because.code != "choice_unavailable" for g in out.strategy.gaps)
