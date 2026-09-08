"""Dispatch and the three checks. Spec §6 and §8.

Nothing a person sees has skipped a check, and a proposal that fails one is
DROPPED and counted as an agent defect — never shown. A user must never be
offered something impossible.
"""
from __future__ import annotations

from fenceai.agent.proposal import Claim, Proposal, TaskResult, proposal_id
from fenceai.agent.run import run_task
from fenceai.agent.tasks import RANK_CHOICE_SET
from fenceai.agent.view import AgentView
from fenceai.decisions.graph import DecisionGraph
from fenceai.project.model import Project
from fenceai.strategy.choices import ChoiceSet, DesignPoint
from fenceai.strategy.model import GenerationResult, GenerationRun, Strategy

DEFAULT = DesignPoint(id="p1", label="2 x 2500", widths=[2500, 2500],
                      axes={"posts": 3}, is_default=True)
ALT = DesignPoint(id="p2", label="1800 + 1400 + 1800", widths=[1800, 1400, 1800],
                  axes={"posts": 4})


def _view(*points: DesignPoint) -> AgentView:
    sets = [ChoiceSet(id="bay_layout", scope="gap:run1:0",
                      question="q", points=list(points))] if points else []
    return AgentView(Project(id="pr_1", name="t"), GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=1,
                          snapshot_hash="kh"),
        strategy=Strategy(id="st_1"), graph=DecisionGraph(), choice_sets=sets))


class _Runner:
    """A runner under test control — the point is what the CHECKS do with it."""

    interpreter_id = "fake"

    def __init__(self, *proposals: Proposal):
        self._proposals = list(proposals)

    def run(self, task, view, project_id) -> TaskResult:
        return TaskResult(task_id=task.id, evaluated=True,
                          proposals=self._proposals, produced=len(self._proposals))


def _proposal(point_id="p2", kind="select_choice_point", claims=None,
              scope="gap:run1:0") -> Proposal:
    payload = {"choice_set": "bay_layout", "scope": scope, "point_id": point_id}
    return Proposal(id=proposal_id("rank_choice_set", kind, payload, scope),
                    task_id="rank_choice_set", project_id="pr_1", kind=kind,
                    payload=payload, scope=scope,
                    claims=claims if claims is not None
                    else [Claim(marker="read", text="x", evidence=f"point:{point_id}")])


def test_a_good_proposal_survives_every_check():
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _Runner(_proposal()),
                   project_id="pr_1")
    assert out.evaluated is True
    assert len(out.proposals) == 1
    assert out.produced == 1 and out.dropped == 0


def test_an_action_the_task_may_not_emit_is_dropped():
    """Check 1. The permission list is the grammar, and this is the belt to its
    braces — a runner that emitted an unpermitted kind is broken, not creative."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(kind="pin_post")), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_claim_citing_something_the_view_never_handed_over_is_dropped():
    """Check 2, and it is the one that stops fabrication. A `ref_id` the view
    did not return is refused whether or not it would have resolved —
    conversation.md T58 §2 and T59 §2."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[
                       Claim(marker="read", text="page 17",
                             evidence="ref:sha256-nobody-handed-this-over")])),
                   project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_an_inferred_claim_needs_no_evidence_and_is_not_dropped():
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[
                       Claim(marker="inferred", text="it looks better")])),
                   project_id="pr_1")
    assert len(out.proposals) == 1


def test_a_point_that_is_not_in_the_offered_set_is_dropped():
    """Check 3. A user must never be offered something impossible."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(point_id="p9")), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_task_with_an_empty_slice_reports_that_it_did_not_look():
    """Vacuous green. "I did not look" is never "nothing to report"."""
    out = run_task(RANK_CHOICE_SET, _view(), _Runner(_proposal()), project_id="pr_1")
    assert out.evaluated is False
    assert out.proposals == []


def test_the_runner_is_not_called_when_there_is_nothing_to_look_at():
    class _Exploding:
        interpreter_id = "boom"

        def run(self, task, view, project_id):
            raise AssertionError("must not be called on an empty slice")

    assert run_task(RANK_CHOICE_SET, _view(), _Exploding(),
                    project_id="pr_1").evaluated is False


def test_more_proposals_than_the_cap_are_trimmed_not_dropped():
    """A cap is a cap. Trimming is not a defect, so it does not count as one."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(), _proposal(point_id="p1")), project_id="pr_1")
    assert len(out.proposals) == RANK_CHOICE_SET.max_proposals
    assert out.dropped == 0


def test_a_runner_that_raises_reports_not_evaluated_rather_than_nothing_found():
    class _Broken:
        interpreter_id = "broken"

        def run(self, task, view, project_id):
            raise RuntimeError("adapter exploded")

    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _Broken(), project_id="pr_1")
    assert out.evaluated is False
    assert out.proposals == []
