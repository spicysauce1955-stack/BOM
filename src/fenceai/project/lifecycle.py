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


#: The five words a SALESPERSON reads for where her job is. Eight states is the
#: office's vocabulary — "planning" and "planned" are two problems to the person
#: choosing what to work on next and one fact to the person who sold the fence:
#: the office took it. So her list folds them.
#:
#:   draft       still hers; nobody in the office has seen it
#:   pending     sent, waiting for somebody to take it
#:   needs_info  the office handed it back with a question
#:   accepted    the office is working on it, or has finished it
#:   rejected    it is not happening
SalesStatus = Literal["draft", "pending", "needs_info", "accepted", "rejected"]

SALES_STATUS: dict[str, str] = {
    "drafting": "draft",
    "waiting": "pending",
    "returned": "needs_info",
    "planning": "accepted",
    "planned": "accepted",
    "quoted": "accepted",
    "delivered": "accepted",
    "cancelled": "rejected",
}


def sales_status(state: str) -> str:
    """The salesperson's word for a job state. Raises on an unknown state, for
    `is_open`'s reason: a state nobody declared must not quietly read as one of
    hers."""
    if state not in SALES_STATUS:
        raise KeyError(f"unknown job state: {state!r}")
    return SALES_STATUS[state]
