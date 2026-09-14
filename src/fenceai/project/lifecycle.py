"""Whose desk a job is on.

Eight states, and the product owner asked for two LISTS — open and finished. Both
are true: the views are two, and eight states live underneath them because a job
waiting to be picked up and a job somebody is halfway through planning are not the
same problem to whoever is choosing what to work on next.

There is deliberately no `won` / `lost`. The fence was sold at the customer's
kitchen table before this job existed — the sales MVP's own sentence is that the
app's number "is never what wins the deal" — and `Quote.status` carries no
"rejected" either. A deal that never became a job is lost before a job exists.
"""

from __future__ import annotations

from typing import Literal

JobState = Literal[
    "drafting", "waiting", "planning", "planned", "quoted", "returned",
    "delivered", "cancelled",
]

#: What each state may become. A closed table rather than scattered `if`s, so
#: "can this job be taken?" has one answer in one place.
TRANSITIONS: dict[str, set[str]] = {
    "drafting":  {"waiting", "cancelled"},
    "waiting":   {"planning", "returned", "cancelled"},
    "planning":  {"planned", "returned", "cancelled"},
    "planned":   {"quoted", "planning", "cancelled"},
    "quoted":    {"delivered", "planning", "cancelled"},
    "returned":  {"waiting", "cancelled"},
    "delivered": set(),
    "cancelled": {"waiting"},
}

FINISHED_STATES: frozenset[str] = frozenset({"delivered", "cancelled"})
OPEN_STATES: frozenset[str] = frozenset(set(TRANSITIONS) - FINISHED_STATES)


def is_open(state: str) -> bool:
    """Which of the two lists this job is on.

    Raises on an unknown state rather than answering. A state nobody declared is
    a bug, and defaulting it into `open` would hide the job in the list somebody
    is actually reading.
    """
    if state not in TRANSITIONS:
        raise KeyError(f"unknown job state: {state!r}")
    return state not in FINISHED_STATES
