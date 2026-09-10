"""The read interface. Spec §4.

Breadth is in what may be looked at; narrowness is in what is asked and what
may be emitted. `ai/ports.py` refuses an ambient context object because "an
adapter that wanted more would be reaching for state the deterministic side
owns" — this class is the read half of that, with no mutators to reach with.
"""
from __future__ import annotations

from fenceai.agent.view import AgentView, point_ref
from fenceai.project.model import Project, Selection
from fenceai.strategy.choices import ChoiceSet, DesignPoint
from fenceai.strategy.model import GenerationResult


def _result(*sets: ChoiceSet) -> GenerationResult:
    from fenceai.strategy.model import GenerationRun, Strategy
    from fenceai.decisions.graph import DecisionGraph
    return GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=4,
                          snapshot_hash="kh_abc"),
        strategy=Strategy(id="st_1"), graph=DecisionGraph(), choice_sets=list(sets))


def _set(scope: str = "gap:run1:0") -> ChoiceSet:
    return ChoiceSet(
        id="bay_layout", scope=scope, question="choices.question.bay_widths",
        points=[DesignPoint(id="p1", label="2 x 2500", widths=[2500, 2500],
                            axes={"posts": 3}, is_default=True),
                DesignPoint(id="p2", label="1800 + 1400 + 1800",
                            widths=[1800, 1400, 1800], axes={"posts": 4})])


def test_an_unanswered_choice_set_is_open():
    view = AgentView(Project(id="pr_1", name="t"), _result(_set()))
    assert [c.scope for c in view.open_choice_sets()] == ["gap:run1:0"]


def test_a_choice_set_the_person_already_answered_is_not_open():
    """The agent advises on questions that are still questions. Re-advising on
    a settled one is the alarm that always rings."""
    project = Project(id="pr_1", name="t", choices=[
        Selection(choice_set="bay_layout", scope="gap:run1:0", widths=[1800, 1400, 1800])])
    view = AgentView(project, _result(_set()))
    assert view.open_choice_sets() == []


def test_the_view_reports_whether_a_slice_has_anything_in_it():
    """`has()` is what separates "I looked and found nothing" from "I never
    looked" one layer up."""
    assert AgentView(Project(id="pr_1", name="t"), _result(_set())).has("choice_sets")
    assert not AgentView(Project(id="pr_1", name="t"), _result()).has("choice_sets")


def test_the_view_records_which_point_ids_it_handed_over():
    """The grounding check compares a claim's evidence against this. An agent
    can echo a citation and never invent one."""
    view = AgentView(Project(id="pr_1", name="t"), _result(_set()))
    view.open_choice_sets()
    assert view.point_ids("bay_layout", "gap:run1:0") == {"p1", "p2"}
    assert point_ref("bay_layout", "gap:run1:0", "p2") in view.refs_handed_over()
    # ...and the ref is QUALIFIED: a bare point id is not an identity,
    # because every open gap on a job carries points with the same ids.
    assert "point:p2" not in view.refs_handed_over()


def test_nothing_is_handed_over_until_it_is_read():
    view = AgentView(Project(id="pr_1", name="t"), _result(_set()))
    assert view.refs_handed_over() == set()


def test_the_digest_is_identity_not_payload():
    view = AgentView(Project(id="pr_1", name="t"), _result(_set()))
    digest = view.digest(["choice_sets"])
    assert digest.run_id == "run_1"
    assert digest.topology_revision == 4
    assert digest.knowledge_hash == "kh_abc"
    assert digest.slices == ["choice_sets"]


def test_the_ref_separator_cannot_be_spelled_by_another_triple():
    """`point_ref` joins on NUL, and the tests that use it build their expected
    value by calling it — so any separator satisfies them, including one that
    reintroduces the collision the qualification was added to remove.

    A real scope contains colons (`gap:run1:0`). Joining on ":" lets
    ("a", "gap:1", "b") and ("a", "gap", "1:b") spell the same reference, which
    is the same "one ref, two things" defect one level down.
    """
    assert point_ref("a", "gap:1", "b") != point_ref("a", "gap", "1:b")
    assert point_ref("bay_layout", "gap:run1:0", "p") != \
        point_ref("bay_layout", "gap:run1", "0:p")
