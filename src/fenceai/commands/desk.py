"""The six things a desk does to a job — who hands it over, who takes it, who
hands it back.

**Where the rows for a WORKING day live, as opposed to the table they sit in.**
`model.py` and `registry.py` know nothing about fences, jobs or people, and must
not; these rows change a `Project`, so they name one. That is the line this
package draws: the table is a leaf, the rows reach the domain they act on, and
neither reaches `fenceai.api` or `fenceai.agent` — the two ends whose ownership
of this table was the whole reason it was moved out of `agent/` (design §10).

Each row answers the three questions in `run.py` before anything happens, and
then does exactly one thing. What is NOT here is as deliberate as what is:

* **Nothing here is gated on completeness.** `submit_job` sends a job with
  nothing drawn on it. `HandoverGap.blocking` withholds the ESTIMATE, not the
  handover, and a sheet that refused an incomplete handover "would be worked
  around within a week" (spec §4). The office's answer to an incomplete job is
  to see how incomplete it is, not to reject it.
* **Nothing here is a lock.** Two people opening one job is rare; `claim_job`
  simply does not run from `planning`, so the second person is told to ask. If
  it stops being rare the honest fix is optimistic concurrency on the revision,
  not a lock somebody forgets to release before going on holiday (spec §5).
* **No reason is ever a code.** `return_to_sales` keeps the sentence somebody
  wrote, verbatim, as an `Annotation` — whoever reads it has to see the question
  in the words it was asked in.

`admin` appears in every row beside the capacity that owns it. Three personas,
and the third is the super user; an admin locked out of the queue would need a
second account to unstick anything, which is how a permission table stops being
the place permissions live.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from fenceai.commands.model import CommandSpec
from fenceai.commands.registry import register
from fenceai.core.ids import new_id
from fenceai.project.lifecycle import OPEN_STATES, TRANSITIONS
from fenceai.project.model import (
    SALE_READ, WARNINGS_REVIEWED, Acknowledgement, Annotation, Project,
    sale_anchor,
)

#: The capacities that run the back office. A name rather than the set spelled
#: out five times, so widening the queue is one edit and not a search.
DESK = frozenset({"backoffice", "admin"})


class NoPayload(BaseModel):
    """A command that carries nothing but its own name.

    Still a model, and still `extra="forbid"`: a caller who sends
    `{"status": "delivered"}` alongside `claim_job` is told so, rather than
    having it silently ignored and believing it worked.
    """

    model_config = {"extra": "forbid"}


class AssignJob(BaseModel):
    """Put the job on a named person's desk."""

    model_config = {"extra": "forbid"}

    # Not checked against the people list here, and that is a SEAM rather than an
    # omission: this package may not reach the store, and an id that resolves to
    # nobody would make the job vanish off every desk at once. The check belongs
    # where users are known — a `referential` column like the agent's, or the
    # route — and `ActionSpec.referential` is the shape it should take when §9
    # gives commands a second caller.
    user_id: str


class ReturnToSales(BaseModel):
    """Hand it back, with the question that has to be answered first."""

    model_config = {"extra": "forbid"}

    reason: str

    @field_validator("reason")
    @classmethod
    def _said_something(cls, v: str) -> str:
        """Required, non-blank, and stripped — here rather than in `materialize`,
        so that an agent proposing this command meets the same floor a button
        does. The whole point of `returned` is the question: a job handed back
        with nothing said gives the salesperson no way to know what to answer.

        Stripping the edges is the only change ever made to this text. It is a
        promise a person made, and it is immutable from here on.
        """
        text = v.strip()
        if not text:
            raise ValueError("a job handed back to sales must say why")
        return text


def _move(project: Project, to: str) -> None:
    """Change the status, and refuse a move the lifecycle table does not have.

    `from_states` and `TRANSITIONS` are two descriptions of one lifecycle, and
    they are edited by different people on different days. This is the place they
    are made to agree: a row that grows a `from_state` whose target is not a real
    transition fails loudly here instead of writing a status the queue then has
    to interpret. Not a `CommandRefused` — nobody asking can cause it, and
    dressing a table disagreement as a user refusal would hide it.
    """
    if to != project.status and to not in TRANSITIONS[project.status]:
        raise ValueError(
            f"no transition {project.status!r} -> {to!r} in the lifecycle table")
    project.status = to


def _submit(payload: BaseModel, project: Project, *, actor: str, now: str) -> Project:
    """Sales hands the job over. Never gated on completeness — see the header."""
    _move(project, "waiting")
    # Stamped every time, including on a job coming back round after `returned`:
    # the queue's service-promise sort asks how long this has been WAITING, and
    # the first submission stopped being the answer the moment it came back.
    project.submitted_at = now
    return project


def _claim(payload: BaseModel, project: Project, *, actor: str, now: str) -> Project:
    """Take it. TWO things in one act, because in the office they are one
    gesture: it becomes yours AND it moves `waiting -> planning` (spec §5)."""
    project.assignee = _user_id(actor)
    _move(project, "planning")
    return project


def _assign(payload: AssignJob, project: Project, *, actor: str, now: str) -> Project:
    """Put it on somebody else's desk.

    The status moves only out of `waiting`: passing a folder somebody is already
    planning changes the name on it and nothing else, and `planning -> planning`
    is not a transition the table has.
    """
    project.assignee = payload.user_id
    if project.status == "waiting":
        _move(project, "planning")
    return project


def _return_to_sales(payload: ReturnToSales, project: Project, *,
                     actor: str, now: str) -> Project:
    """Hand it back with a question.

    The assignee is CLEARED. If only the salesperson can answer something, the
    job has to leave the backoffice desk or the queue stops meaning "work I can
    do" (spec §4). The reason travels as verbatim human text — a note on the
    job, never a code — because a code would need a sentence written in advance
    for a question nobody has asked yet.
    """
    _move(project, "returned")
    project.assignee = None
    project.annotations.append(Annotation(
        id=new_id("ann"), target_ref="job", text=payload.reason,
        author=actor, created_at=now,
    ))
    return project


def _cancel(payload: BaseModel, project: Project, *, actor: str, now: str) -> Project:
    """It is not happening.

    The assignee is KEPT, unlike `return_to_sales`. A cancelled job is off the
    open list entirely, so the name can no longer mislead anyone about work that
    is waiting — and it is the only remaining record of whose desk it was on when
    it stopped.
    """
    _move(project, "cancelled")
    return project


def _reopen(payload: BaseModel, project: Project, *, actor: str, now: str) -> Project:
    """It is happening after all.

    Back to `waiting` with nobody's name on it, rather than to whoever held it
    when it was cancelled: that may have been months ago and they may have left
    the company. A reopened job is work somebody has to choose again.
    """
    _move(project, "waiting")
    project.assignee = None
    return project


def _user_id(actor: str) -> str:
    """`user:u_yossi` -> `u_yossi`.

    Two spellings for one person, and each is right where it is used: the log
    carries `actor_ref` because one column holds three KINDS of actor and a
    reader must tell a person from an agent without a lookup, while `assignee` is
    joined against the people list and holds the bare id. Converted in one place
    so the queue never has to guess which spelling it was handed.
    """
    return actor.split(":", 1)[1] if actor.startswith("user:") else actor


SUBMIT_JOB = register(CommandSpec(
    kind="submit_job",
    payload_model=NoPayload,
    rung="directive",
    i18n_key="command.submit_job",
    capacities=frozenset({"sales", "admin"}),
    from_states=frozenset({"drafting", "returned"}),
    materialize=_submit,
))

CLAIM_JOB = register(CommandSpec(
    kind="claim_job",
    payload_model=NoPayload,
    rung="directive",
    i18n_key="command.claim_job",
    capacities=DESK,
    from_states=frozenset({"waiting"}),
    materialize=_claim,
))

ASSIGN_JOB = register(CommandSpec(
    kind="assign_job",
    payload_model=AssignJob,
    rung="directive",
    i18n_key="command.assign_job",
    capacities=DESK,
    from_states=frozenset({"waiting", "planning"}),
    materialize=_assign,
))

RETURN_TO_SALES = register(CommandSpec(
    kind="return_to_sales",
    payload_model=ReturnToSales,
    rung="directive",
    i18n_key="command.return_to_sales",
    capacities=DESK,
    from_states=frozenset({"waiting", "planning"}),
    materialize=_return_to_sales,
))

CANCEL_JOB = register(CommandSpec(
    kind="cancel_job",
    payload_model=NoPayload,
    rung="directive",
    i18n_key="command.cancel_job",
    # Every OPEN state, written as the set rather than listed: a ninth state
    # added to the lifecycle is cancellable the day it exists, and a job that
    # cannot be cancelled from the state it is stuck in is the one case where
    # somebody edits the database by hand.
    capacities=DESK,
    from_states=frozenset(OPEN_STATES),
    materialize=_cancel,
))

REOPEN_JOB = register(CommandSpec(
    kind="reopen_job",
    payload_model=NoPayload,
    rung="directive",
    i18n_key="command.reopen_job",
    capacities=DESK,
    # `delivered` is deliberately absent. `TRANSITIONS` gives it no way out at
    # all: a job whose plan has been priced and handed on is finished, and
    # un-finishing one would make "delivered" a state the office could not trust.
    from_states=frozenset({"cancelled"}),
    materialize=_reopen,
))


# -- the two acknowledgements -------------------------------------------------
#
# The only rows here that record something the system cannot work out for
# itself. Everything else moves a job between desks; these two say a person read
# something — which is the one fact the office road's steps 1 and 4 turn on, and
# the one nothing can derive.
#
# `from_states` is empty on both: reading her promise is not a stage of the work,
# it is a thing you do while doing the work, and a job in `returned` is exactly
# when somebody most wants to re-read what she wrote.


class AcknowledgeWarnings(BaseModel):
    """Which run's warnings were read.

    Explicit rather than "the latest run": by the time this arrives the latest
    run may already be a newer one than the person was looking at, and an
    acknowledgement that quietly covered a run nobody read is worse than none.
    """

    model_config = {"extra": "forbid"}

    run_id: str


def _remember(project: Project, kind: str, anchor: str, *, actor: str,
              now: str) -> Project:
    """Write one acknowledgement, replacing any earlier answer to the SAME
    question.

    Same question means same `(kind, anchor)`. Two runs are two questions and
    keep two rows; pressing the button twice on one run is one answer given
    twice, and a list that grew each time would be a list nothing could read.
    """
    kept = [a for a in project.acknowledgements
            if not (a.kind == kind and a.anchor == anchor)]
    kept.append(Acknowledgement(kind=kind, anchor=anchor, by=actor, at=now))
    return project.model_copy(update={"acknowledgements": kept})


def _acknowledge_sale(payload, project: Project, *, actor: str, now: str) -> Project:
    # The anchor comes from `readiness.sale_anchor`, never rebuilt here. Two
    # spellings of "what was this read against" is precisely how an
    # acknowledgement stops matching without anybody touching it.
    return _remember(project, SALE_READ, sale_anchor(project), actor=actor, now=now)


def _acknowledge_warnings(payload: AcknowledgeWarnings, project: Project, *,
                          actor: str, now: str) -> Project:
    return _remember(project, WARNINGS_REVIEWED, payload.run_id, actor=actor, now=now)


ACKNOWLEDGE_SALE = register(CommandSpec(
    kind="acknowledge_sale",
    payload_model=NoPayload,
    rung="note",
    i18n_key="command.acknowledge_sale",
    # The office's record of having read HER work. A salesperson pressing it
    # would make the one fact nobody can derive also the one nobody can trust.
    capacities=DESK,
    from_states=frozenset(),
    materialize=_acknowledge_sale,
))

ACKNOWLEDGE_WARNINGS = register(CommandSpec(
    kind="acknowledge_warnings",
    payload_model=AcknowledgeWarnings,
    rung="note",
    i18n_key="command.acknowledge_warnings",
    capacities=DESK,
    from_states=frozenset(),
    materialize=_acknowledge_warnings,
))
