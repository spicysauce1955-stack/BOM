"""One row of the table, and nothing about who is asking.

**Extracted from `fenceai/agent/registry.py`, which was never the agent's table.**
It held one row and the agent was its only caller, so it lived there; but the list
of things that may be done to a job belongs to the job. An agent keeps the SUBSET
of it that it may propose, which is `TaskSpec.may_emit` and stays in `agent/`.

That direction matters: a human pressing a button and an agent proposing one must
reach the same row, or the second implementation drifts from the first — and the
drift is where an untraceable change comes from (design §10, §11).

Keyword-only, because two things construct these — the desk rows and the agent's
`ActionSpec`, which extends this row with a check only an agent needs. Positional
fields would make that extension an ordering puzzle, and the field a subclass adds
is exactly the field nobody may forget.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

#: How far up the ladder a command reaches: a remark, an answer to a question
#: somebody was already asked, an instruction, or a change to the rules themselves.
Rung = Literal["note", "selection", "directive", "rule"]

#: How much a command may do on its own. The dial an agent is turned up on (§11),
#: and the reason `commit_plan` can be pinned at `ask` for ever.
Disposition = Literal["ask", "suggest", "auto"]


class CommandRefused(Exception):
    """A command that may not run, as `code + params` like every other refusal
    here — the English message is a fallback and the sentence lives in both
    bundles."""

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass(frozen=True, kw_only=True)
class CommandSpec:
    """One thing that may be done to a job.

    A dataclass rather than a model: `payload_model` is a TYPE, and a registry row
    is code rather than data on the wire.
    """

    kind: str
    payload_model: type[BaseModel]
    rung: Rung
    #: What the activity log calls this, per language. The log renders from what
    #: happened, never from a stored sentence.
    i18n_key: str
    #: Which capacities may perform it. On the COMMAND rather than in a handler,
    #: and EMPTY by default — a row whose author forgot this column refuses
    #: everybody. The other default would hand the whole table to anyone who
    #: added a row in a hurry, and nothing would fail while it happened.
    capacities: frozenset[str] = frozenset()
    #: Which job states it may run from. Empty means "any state" — which is safe
    #: in a way the capacity default is not: a status is where the work is, not
    #: who is allowed near it.
    from_states: frozenset[str] = frozenset()
    disposition: Disposition = "ask"
    #: payload + project -> the changed project. Pure; the caller persists.
    #: `None` is a real row: something an agent may PROPOSE that nothing performs
    #: by hand yet. Splitting propose-able from perform-able into two tables is
    #: how the two would drift.
    materialize: Callable | None = field(default=None, repr=False)
