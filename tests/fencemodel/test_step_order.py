"""The step order as a PARTIAL order (contract obligation 11).

*"Prerequisites are edges with a kind, not list order. Publish `requires` where a
document asserts a dependency, and leave it empty where the document merely
prints one step after another. Two guides here explicitly deny their own print
order."*

The claim under test is not "the steps come out sorted". It is that the read
model can tell the difference between an order the document ASSERTED and an
order it merely PRINTED, and can say when the sequence it returns is one of
several — because a fitter planning a crew around a sequence the model never
claimed is the failure the obligation exists to prevent.
"""

from __future__ import annotations

from fenceai.fencemodel.model import AssemblyStep, Prerequisite
from fenceai.fencemodel.step_order import step_order


def _steps(*spec: tuple[str, list[tuple[str, str]]]) -> list[AssemblyStep]:
    """`("boards", [("rails", "after")])` -> one authored step list."""
    return [
        AssemblyStep(key=key, slots=[key],
                     requires=[Prerequisite(step=s, kind=k) for s, k in reqs])
        for key, reqs in spec
    ]


def test_print_order_alone_asserts_nothing():
    """The whole of obligation 11 in one case. Three steps printed one after
    another, no `requires` anywhere: the document has not said which comes first,
    and a read model that reported a unique order would be inventing the
    dependency the contract forbids inventing."""
    order = step_order(_steps(("a", []), ("b", []), ("c", [])))
    assert order.basis == "authored"
    assert order.stages == [["a", "b", "c"]]
    assert order.unique is False


def test_an_asserted_edge_beats_the_print_order_it_contradicts():
    """`b` is printed first and requires `a`, so the returned sequence is a, b.
    If list position were still doing the work this would come back b, a — which
    is precisely what the two guides that deny their own print order would get."""
    order = step_order(_steps(("b", [("a", "after")]), ("a", [])))
    assert order.stages == [["a"], ["b"]]
    assert order.basis == "requires"
    assert order.unique is True


def test_a_chain_is_the_only_case_that_is_unique():
    order = step_order(_steps(
        ("a", []), ("b", [("a", "after")]), ("c", [("b", "after")])))
    assert order.stages == [["a"], ["b"], ["c"]]
    assert order.unique is True


def test_two_steps_waiting_on_the_same_one_share_a_stage_and_are_not_unique():
    """The case a numbered list silently destroys: `b` and `c` both follow `a`
    and neither follows the other, so b-then-c and c-then-b are equally right.
    The sequence returned has to pick one; `stages` is how the reader finds out
    that it was a pick."""
    order = step_order(_steps(
        ("a", []), ("b", [("a", "after")]), ("c", [("a", "after")])))
    assert order.stages == [["a"], ["b", "c"]]
    assert order.unique is False


def test_before_is_the_same_edge_stated_from_the_other_end():
    """A maximum edge. The document says "bolt the brackets on before you stand
    the post", and rewriting that as the post step's `after` would put words in a
    step that never spoke."""
    order = step_order(_steps(("brackets", [("stand", "before")]), ("stand", [])))
    assert order.stages == [["brackets"], ["stand"]]
    assert order.unique is True


def test_a_strict_circle_is_a_conflict():
    """`after` asserts a step is finished first, so a loop of them asserts a step
    precedes itself. There is no sequence; there is a mistake."""
    order = step_order(_steps(
        ("a", [("b", "after")]), ("b", [("a", "after")])))
    assert order.conflicts == [["a", "b"]]
    assert order.concurrent == []
    assert order.unique is False


def test_a_not_before_circle_is_CONCURRENCY_and_not_a_conflict():
    """The distinction a single edge kind cannot make, and the reason
    `not_before` exists. "Neither of these starts before the other" is a document
    saying they happen together — pour both footings, then move on — and refusing
    it would make a true statement unauthorable. Only a loop carrying a STRICT
    edge is a contradiction."""
    order = step_order(_steps(
        ("a", [("b", "not_before")]), ("b", [("a", "not_before")])))
    assert order.conflicts == []
    assert order.concurrent == [["a", "b"]]
    assert order.stages == [["a", "b"]]


def test_one_strict_edge_makes_an_otherwise_loose_circle_a_conflict():
    """Mixed loop. a ≤ b ≤ c < a still says a precedes itself, and reading the
    kinds one at a time — "no `after` pair is reversed" — would have missed it."""
    order = step_order(_steps(
        ("a", [("c", "after")]),
        ("b", [("a", "not_before")]),
        ("c", [("b", "not_before")])))
    assert order.conflicts == [["a", "b", "c"]]


def test_exclusive_with_constrains_no_order_at_all():
    """The negative edge. Two ways of setting a post are alternatives, not a
    sequence — the fact a prerequisite LIST has nowhere to put, which is the
    contract's own argument for kinds."""
    order = step_order(_steps(
        ("dig", [("drive", "exclusive_with")]), ("drive", [])))
    assert order.exclusive == [["dig", "drive"]]
    assert order.stages == [["dig", "drive"]]
    assert order.basis == "requires"


def test_an_edge_to_a_step_that_does_not_exist_constrains_nothing():
    """`validate_model` refuses it; this function must not invent a node for it,
    because a phantom predecessor would make the rendered order disagree with the
    document it was read from."""
    order = step_order(_steps(("a", [("ghost", "after")]), ("b", [])))
    assert order.stages == [["a", "b"]]
    assert order.conflicts == []


def test_a_step_is_never_its_own_predecessor_here():
    """Also refused at authoring. Here it must simply not deadlock the layering:
    a self-edge would leave the node with an in-degree nothing can clear."""
    order = step_order(_steps(("a", [("a", "after")]), ("b", [("a", "after")])))
    assert order.stages == [["a"], ["b"]]


def test_ties_inside_a_stage_break_by_authored_position():
    """Deterministic, and deliberately the document's own order rather than
    alphabetical: the tie-break decides what a list LOOKS like, and picking any
    other key would be a second opinion about build order competing with the
    author's."""
    order = step_order(_steps(
        ("root", []),
        ("zulu", [("root", "after")]),
        ("alpha", [("root", "after")])))
    assert order.stages == [["root"], ["zulu", "alpha"]]


def test_no_steps_is_a_unique_order_of_nothing():
    order = step_order([])
    assert order.stages == [] and order.unique is True
