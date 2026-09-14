import pytest

from fenceai.project.lifecycle import (
    FINISHED_STATES, OPEN_STATES, TRANSITIONS, is_open,
)
from fenceai.project.model import Project


def test_the_eight_states_partition_into_the_two_views():
    """The product owner asked for two lists. Eight states exist underneath
    because a job waiting to be picked up and one somebody is halfway through
    are not the same problem — but every one of them is in exactly one view."""
    assert OPEN_STATES | FINISHED_STATES == set(TRANSITIONS) | {"delivered", "cancelled"}
    assert not (OPEN_STATES & FINISHED_STATES)
    assert FINISHED_STATES == {"delivered", "cancelled"}


def test_there_is_no_won_or_lost():
    """The fence was sold at the kitchen table before the job existed, and
    `Quote.status` has no rejected either. Deals that never became jobs are lost
    before a job exists — the salesperson's screen, not this one."""
    every = OPEN_STATES | FINISHED_STATES
    assert "won" not in every and "lost" not in every


def test_a_new_project_is_drafting_and_belongs_to_nobody():
    p = Project(id="p1", name="x")
    assert p.status == "drafting"
    assert p.assignee is None
    assert p.submitted_at == ""


def test_the_four_new_fields_do_not_touch_the_topology_revision():
    """They are project state. A fact that changes no quantity must not 409
    every derived view — the rule `/job`, `/context` and `/stated` already set."""
    p = Project(id="p1", name="x")
    before = p.topology.revision
    p.status, p.assignee, p.created_by = "waiting", "u_yossi", "u_dana"
    assert p.topology.revision == before


def test_a_transition_nobody_allowed_is_not_in_the_table():
    assert "planning" in TRANSITIONS["waiting"]
    assert "delivered" not in TRANSITIONS["waiting"]
    assert TRANSITIONS["delivered"] == set()


def test_is_open_answers_for_every_state_and_guesses_for_none():
    for s in OPEN_STATES:
        assert is_open(s) is True
    for s in FINISHED_STATES:
        assert is_open(s) is False
    with pytest.raises(KeyError):
        is_open("nonsense")
