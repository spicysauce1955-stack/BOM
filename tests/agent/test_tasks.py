"""Task declarations. Spec §3."""
from __future__ import annotations

import pytest

from fenceai.agent.registry import KINDS
from fenceai.agent.tasks import RANK_CHOICE_SET, task_for


def test_the_task_may_only_emit_registered_kinds():
    """The permission list becomes the output schema, so a kind that is not in
    the registry has no word in the grammar the agent is handed."""
    assert set(RANK_CHOICE_SET.may_emit) <= set(KINDS)


def test_the_task_declares_what_it_reads():
    assert RANK_CHOICE_SET.reads == ["choice_sets"]


def test_the_goal_says_what_the_task_is_for_and_never_what_is_true():
    """`conversation.md` T49 §6c found three stale claims in one day: "every one
    of them was true when written, load-bearing for a real decision, and left
    behind by the boundary moving." Domain facts come from the view at run
    time, never from prose that ages."""
    goal = RANK_CHOICE_SET.goal.lower()
    for stale in ("1800", "2500", "mm", "certainteed", "m-vinyl", "window"):
        assert stale not in goal, f"the goal states a domain fact: {stale!r}"


def test_a_cap_exists_and_is_not_a_target():
    assert RANK_CHOICE_SET.max_proposals >= 1


def test_an_unknown_task_is_refused_by_name():
    with pytest.raises(KeyError, match="place_posts"):
        task_for("place_posts")
