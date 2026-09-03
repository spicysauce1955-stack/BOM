"""A recorded choice changes the fence, deterministically, and says so.

Inputs are built explicitly — the style of `tests/strategy/test_boundary_posts.py`
— because an earlier draft of this plan rested seventeen test functions on an
eight-method env fixture that appeared in no task and was never written.

Every literal below is derived from the demo knowledge: `max_span_mm = 1800`
(`knowledge/demo.py`), so `equal_layout(5000, 1800)` is `[1667, 1667, 1666]` and
`equal_layout(3000, 1800)` is `[1500, 1500]`.

`docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md` §5–§7.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.project.model import Selection
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import Override, PinPost
from tests.conftest import straight_topology


def _run(*, length_mm: int = 5000, **kw):
    return generate(straight_topology(length_mm), demo_knowledge(),
                    demo_catalog(), **kw)


def _widths(result) -> list[int]:
    return [s.width_mm for s in result.strategy.spans]


# -- stage A: the new inputs exist and change nothing -------------------------

def test_with_no_selection_the_default_is_todays_answer():
    """The property that keeps the golden gate still, asserted against a literal
    derived from the demo knowledge rather than against a second call to the
    thing under test."""
    assert _widths(_run()) == [1667, 1667, 1666]


def test_passing_the_new_inputs_explicitly_changes_nothing():
    """`choices` and `offer_alternatives` are threaded the way `site` and `parts`
    were. An empty list must be indistinguishable from the default."""
    assert _widths(_run(choices=[])) == [1667, 1667, 1666]
    assert _widths(_run(offer_alternatives=False)) == [1667, 1667, 1666]


def test_a_probe_does_not_offer_its_own_alternatives():
    """The bound that makes the cost linear rather than factorial. Without it a
    probe re-enters generation and probes again: two questions cost five
    generations, six sections 1957."""
    assert _run(offer_alternatives=False).choice_sets == []


# -- stage B: a selection is honoured, or reported ----------------------------

def test_a_recorded_selection_changes_the_layout():
    """`[1800, 1800, 1400]` sums to the gap and its widest bay is exactly the
    resolved maximum, so it is buildable and it is what the person asked for."""
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[1800, 1800, 1400])])
    assert _widths(out) == [1800, 1800, 1400]


def test_a_selection_that_does_not_fit_the_gap_reports_and_falls_back():
    """Never a silent fallback. And the WIDTHS are what goes stale, not the name
    of the generator that proposed them — `fewest_posts` is defined relative to
    `max_span`, so a name would silently mean something else."""
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[9999], author="bob")])
    assert _widths(out) == [1667, 1667, 1666]
    gap = next(g for g in out.strategy.gaps
               if g.because.code == "choice_unavailable")
    assert gap.because.params["author"] == "bob"
    assert gap.because.params["widths"] == [9999]
    assert gap.closes_by == "planning"


def test_a_selection_wider_than_the_resolved_maximum_is_refused():
    """It sums to the gap, so only the span check catches it — and this is the
    case that matters: a stale selection must not build an over-maximum fence
    just because a person once chose it under a laxer rule."""
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[2500, 2500])])
    assert _widths(out) == [1667, 1667, 1666]
    assert any(g.because.code == "choice_unavailable" for g in out.strategy.gaps)


def test_a_selection_is_scoped_to_a_gap_not_to_the_run():
    """One pinned post makes a 5 m run two gaps. A run-scoped key applied one
    answer to a gap it was never measured for — and the moment a person pins a
    post, every run has more than one gap."""
    pinned = [Override(id="o1", run_id="run1",
                        directive=PinPost(station_mm=2000))]
    assert _widths(_run(overrides=pinned)) == [1000, 1000, 1500, 1500]

    out = _run(overrides=pinned,
               choices=[Selection(choice_set="bay_layout",
                                   scope="gap:run1:2000",
                                   widths=[1800, 1200])])
    assert _widths(out) == [1000, 1000, 1800, 1200]


def test_a_selection_scoped_to_another_gap_is_not_applied_here():
    """The other half of the same property: a scope that matches no gap on this
    run changes nothing and is not silently applied to the first gap."""
    out = _run(choices=[Selection(choice_set="bay_layout",
                                   scope="gap:run1:4321",
                                   widths=[1800, 1800, 1400])])
    assert _widths(out) == [1667, 1667, 1666]


# -- the graph, the digest, and purity ---------------------------------------

def test_a_choice_node_records_who_chose_and_what_it_displaced():
    """A choice node with no loser is an assertion. The displaced default rides
    in the payload — not on a `defeated` edge, which materialises a knowledge
    node per ref and would invent a fact for a layout point that has none."""
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[1800, 1800, 1400], author="bob")])
    node = next(n for n in out.graph.nodes if n.action == "resolve_choice_set")
    assert node.kind == "choice"
    assert node.payload["chosen_by"] == "bob"
    assert node.payload["widths"] == [1800, 1800, 1400]
    assert node.payload["displaced"] == [1667, 1667, 1666]


def test_the_run_id_moves_when_a_choice_is_recorded_and_not_before():
    """`objective_preset` was REMOVED from the digest because a design is what it
    is regardless of how it is bought. A choice is the opposite: it changes the
    design. Hashed only when non-empty, so no existing run id moves and
    `RUN_DIGEST_VERSION` does not need to change."""
    plain = _run().run.id
    assert _run().run.id == plain
    assert _run(choices=[]).run.id == plain

    chosen = _run(choices=[Selection(choice_set="bay_layout",
                                      scope="gap:run1:0",
                                      widths=[1800, 1800, 1400])]).run.id
    assert chosen != plain


def test_generation_never_mutates_the_choices_it_was_given():
    """Purity. A probe will deep-copy and add a selection of its own; if the
    caller's list were mutated the baseline would grow one selection per probe."""
    choices = [Selection(choice_set="bay_layout", scope="gap:run1:0",
                          widths=[1800, 1800, 1400])]
    before = [c.model_dump() for c in choices]
    _run(choices=choices)
    assert [c.model_dump() for c in choices] == before


def test_two_runs_agree_on_the_fence_and_on_the_questions():
    """`test_determinism` covers strategy and graph. The new surface needs the
    same guarantee, because probing is exactly the kind of thing that leaks dict
    iteration order into output."""
    picked = [Selection(choice_set="bay_layout", scope="gap:run1:0",
                         widths=[1800, 1800, 1400])]
    a, b = _run(choices=picked), _run(choices=picked)
    assert b.strategy.model_dump() == a.strategy.model_dump()
    assert b.graph.model_dump() == a.graph.model_dump()
    assert [cs.model_dump() for cs in b.choice_sets] \
        == [cs.model_dump() for cs in a.choice_sets]
