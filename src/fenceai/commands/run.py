"""The door. Three questions, then the effect.

Every change that moves a job — whose desk it is on, or what it commits to — comes
through here (design §10). Field edits do not: typing an address is not a command,
and forcing it to be one turns the design into ceremony.

One door rather than a check per handler, because the alternative is a permission
scattered across handlers half of which will be added later by somebody who did
not know. It also makes a proposal and a button the same call: accepting an
agent's suggestion is performing the row it named, with a different actor.
"""

from __future__ import annotations

from fenceai.commands.model import CommandRefused, CommandSpec
from fenceai.commands.registry import parse_payload, spec_for


def perform(kind: str, data: dict, project, *, actor: str, capacity: str, now: str,
            precondition=None):
    """Run one command against one job, or refuse it.

    **The order is the design.** Capacity is asked FIRST so a refusal never leaks
    whether the job was in a state that would have allowed it — a salesperson
    who tries to take a job gets the same sentence whether or not there was a job
    there to take. Then whether this row is something a hand performs at all,
    which is a fact about the table and tells the asker nothing about the job.
    Then the state, then the payload.

    `precondition` is how a row states something only the CALLER can check — a
    run belonging to this job, a drawing that has not moved since it was
    generated. It is asked LAST, after capacity, performability, state and
    payload, for the same reason capacity is asked first: answered earlier, it
    would tell a salesperson which runs exist and how far a job has got, through
    a door that should only ever say "not your account". It takes the PARSED
    payload, so a precondition never re-reads a raw dict.

    Nothing is persisted here and nothing is logged: the caller owns the store,
    and a pure `perform` is what lets the desk tests drive all six rows through
    every state they declare without a database.

    Raises `KeyError` for a kind nobody registered — a word in no grammar we hand
    out — and `ValidationError` for a payload that does not type-check.
    """
    spec: CommandSpec = spec_for(kind)
    if capacity not in spec.capacities:
        raise CommandRefused(code="command_not_permitted", kind=kind, capacity=capacity)
    if spec.materialize is None:
        # A real row, not a broken one: `materialize=None` is something an agent
        # may PROPOSE that nothing performs by hand yet. Refused rather than
        # called, because calling `None` reaches a person as a 500 and tells them
        # the app is broken when the honest answer is "not through this door".
        raise CommandRefused(code="command_not_performable", kind=kind)
    if spec.from_states and project.status not in spec.from_states:
        raise CommandRefused(code="command_wrong_state", kind=kind,
                             status=project.status)
    payload = parse_payload(kind, data)
    if precondition is not None:
        precondition(kind, payload, project)
    return spec.materialize(payload, project, actor=actor, now=now)
