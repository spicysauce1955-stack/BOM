"""Tasks are data, not code. Adding a capability is adding a row.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskSpec:
    """One goal, one output shape, one permission list.

    `goal` says what the task is FOR. It must never say what is TRUE: facts in
    prose go stale in the direction that keeps sounding right, and what is true
    comes from the view at run time.
    """

    id: str
    goal: str
    reads: list[str]
    may_emit: list[str]
    # A cap, not a target. "A guard that always fails is a guard everybody
    # learns to ignore" (conversation.md T55 §8) — an agent that comments on
    # everything is the same alarm.
    max_proposals: int = 1
    triggers: list[str] = field(default_factory=list)


RANK_CHOICE_SET = TaskSpec(
    id="rank_choice_set",
    goal=(
        "A question the data left open has more than one admissible answer and "
        "nothing prefers one. Propose the answer you would pick, and give the "
        "reason as claims a reader can check. Propose nothing if none is "
        "better than the one the engine already builds."
    ),
    reads=["choice_sets"],
    may_emit=["select_choice_point"],
    max_proposals=1,
    triggers=["choice_set_open"],
)

_TASKS = {RANK_CHOICE_SET.id: RANK_CHOICE_SET}


def task_for(task_id: str) -> TaskSpec:
    if task_id not in _TASKS:
        raise KeyError(f"no such task: {task_id}")
    return _TASKS[task_id]
