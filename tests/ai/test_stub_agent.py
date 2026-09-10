"""The deterministic stub for the agent port.

`test_every_ai_port_has_a_stub` requires one, and it must be capped: the stub
answers the demo vocabulary and must never become a second rule engine.
"""
from __future__ import annotations

from fenceai.agent.tasks import RANK_CHOICE_SET
from fenceai.agent.view import AgentView
from fenceai.ai.stub import StubAgent
from fenceai.project.model import Project
from fenceai.strategy.choices import ChoiceSet, DesignPoint
from fenceai.decisions.graph import DecisionGraph
from fenceai.strategy.model import GenerationResult, GenerationRun, Strategy


def _view(*points: DesignPoint) -> AgentView:
    result = GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=1,
                          snapshot_hash="kh"),
        strategy=Strategy(id="st_1"), graph=DecisionGraph(),
        choice_sets=[ChoiceSet(id="bay_layout", scope="gap:run1:0",
                               question="choices.question.bay_widths",
                               points=list(points))])
    return AgentView(Project(id="pr_1", name="t"), result)


DEFAULT = DesignPoint(id="p1", label="2 x 2500", widths=[2500, 2500],
                      axes={"posts": 3}, is_default=True)
ALT = DesignPoint(id="p2", label="1800 + 1400 + 1800", widths=[1800, 1400, 1800],
                  axes={"posts": 4})


def test_the_stub_actually_produces_a_proposal():
    """A framework test whose stub returns nothing passes and proves nothing —
    the same family as vacuous green. `conversation.md` T49 §9: an entire suite
    "reports green by not running"."""
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    assert result.evaluated is True
    assert len(result.proposals) == 1
    assert result.proposals[0].kind == "select_choice_point"
    assert result.proposals[0].payload["point_id"] == "p2"


def test_every_claim_the_stub_makes_cites_a_point_it_was_handed():
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    for claim in result.proposals[0].claims:
        if claim.marker != "inferred":
            assert claim.evidence.startswith("point:")


def test_the_stub_argues_nothing_and_only_states_what_it_was_shown():
    """It has no judgement, so it makes no claim about WHY — not even one
    admitting it has none.

    The earlier version of this test required an `inferred` claim saying the
    stub was only picking the first alternative. That sentence was true and it
    was still wrong to print: it taught the reader to discount the panel weeks
    before a real model arrived, and the panel would still be discounted when
    the advice became good (checkpoint, 2026-09-09). Silence about reasoning
    the stub does not have is the honest form."""
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    claims = result.proposals[0].claims
    assert claims, "the proposal must still be evidenced"
    assert all(c.marker == "read" for c in claims), [c.marker for c in claims]
    assert all(c.evidence for c in claims), "a read claim without evidence is not grounded"


def test_one_admissible_answer_is_not_a_question():
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT), project_id="pr_1")
    assert result.evaluated is True
    assert result.proposals == []


def test_the_stub_is_deterministic():
    a = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    b = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    assert a.proposals[0].id == b.proposals[0].id
    assert a.model_dump() == b.model_dump()


def test_the_stub_stamps_its_identity():
    result = StubAgent().run(RANK_CHOICE_SET, _view(DEFAULT, ALT), project_id="pr_1")
    assert result.proposals[0].agent_id == "stub"
