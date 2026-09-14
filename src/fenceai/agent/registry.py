"""What an AGENT may propose — the subset, and the row shape a proposal needs.

`knowledge/ast.py`'s FnCall whitelist is the same instinct: a closed vocabulary
resolved in code, no eval of strings, ever. Spec §1 asks that a task's
permission list BE the model's output schema, so an action absent from the table
has no word in any grammar an agent is ever handed — narrow run stops being a
policy somebody must enforce and becomes a type.

**That schema half is not built yet.** It arrives with the Claude adapter in
slice 2, which will compile the schema FROM `may_emit`. Until then the property
is enforced at run time instead, by a single membership test in
`run.py::_admissible` ("belt to the grammar's braces") — one belt, no grammar.
Said here rather than only in the plan because a reader of this package would
otherwise be told the grammar already exists: `view.py` carries the reason we
are careful about that ("Ours was worse than a stale comment — we asserted the
stale state as a current reason").

**The table itself left this module.** It is `fenceai/commands/` now, and it was
never the agent's: it held one row, the agent was its only caller, so it lived
here. The list of things that may be done to a job belongs to the job (backoffice
design §10). What stays is the agent's half — the payload it may send, the
referential check a proposal has to survive, and `KINDS`, the SUBSET it may
propose. `register` / `spec_for` / `parse_payload` are re-exported rather than
re-implemented, because a human pressing a button and an agent proposing one must
reach the same row; two tables would drift, and the drift is where an untraceable
change comes from.

**Growth is additive.** A run stamps only the inputs it actually had, so adding
an entry never invalidates a stored run. But a finding that fits no entry
becomes a COUNTER before it becomes a row there — T54 §2, where the Knowledge
team wanted a ninth Gap kind, found none of the eight fitted, and declined to
add one "for something we can measure on our own side". Without that restraint
the table accumulates one-off kinds and the grammar is only as good as the
judgement of whoever last extended it.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §2;
docs/superpowers/specs/2026-09-15-backoffice-design.md §10.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from fenceai.commands.model import CommandSpec
from fenceai.commands.registry import _TABLE as _REGISTRY  # noqa: F401
from fenceai.commands.registry import parse_payload, register, spec_for  # noqa: F401
from fenceai.strategy.choices import ChoiceSet, offered


class SelectChoicePoint(BaseModel):
    """Answer an open choice set by naming one of the points it offered.

    Explicit fields, never a dict: a free-form params dict is inexpressible
    under `additionalProperties:false` and silently arrives empty — the lesson
    `ai/claude.py` already carries in a comment.
    """

    model_config = {"extra": "forbid"}

    choice_set: str
    scope: str
    point_id: str


@dataclass(frozen=True, kw_only=True)
class ActionSpec(CommandSpec):
    """A command row an agent may propose: the shared row, plus check 3.

    A subclass rather than a parallel class, so `spec_for` hands back one kind of
    thing and the desk and the agent cannot end up describing the same command
    twice. `referential` is the only column an agent needs and a button does not:
    a person pressing `Take it` names nothing that has to still exist, while a
    proposal names a point that may have stopped being offered.
    """

    # Check 3 (spec §6), and it lives HERE rather than in the dispatcher on
    # purpose: a `kind` whose payload parses is not a `kind` whose payload
    # RESOLVES, and a dispatcher that asked "is this the one kind I know how to
    # check?" would silently admit every kind added after it. Required, with no
    # default, so registering an action without a referential check is a
    # TypeError at import rather than a fail-open row nobody notices. Returning
    # False is the deny; a check that cannot answer must deny.
    referential: Callable[[BaseModel, list[ChoiceSet]], bool]
    # Backend policy, and deliberately not the agent's business (spec §7): an
    # agent told which of its proposals get applied automatically will learn to
    # phrase things to get applied, and every check would still pass.
    #
    # Redeclared with the agent framework's own words rather than inheriting
    # `CommandSpec.disposition`. They are one dial — `show` is `suggest` and
    # `hold_pending` is `ask` — and reconciling them to one vocabulary is §11's
    # job, when the agent actually starts proposing desk commands. Doing it in a
    # commit that only moves a table would leave the agent spec's §7 table
    # describing words the code no longer has, which is the drift this package
    # keeps warning about.
    disposition: Literal["show", "hold_pending", "auto"] = "show"


def _select_choice_point_resolves(payload: BaseModel, open_sets: list[ChoiceSet]) -> bool:
    """Does the thing this payload names actually exist, right now?

    The set it answers must be one THIS run still considers open (`open_sets`,
    not every set the result ever carried), and the point must be in
    `offered()` of that set — exactly as spec §6 asks: "is that `DesignPoint`
    actually in `offered()`?", not merely present somewhere in the result.
    """
    if not isinstance(payload, SelectChoicePoint):
        return False  # a check that cannot answer denies
    matching = next((c for c in open_sets
                     if c.id == payload.choice_set and c.scope == payload.scope), None)
    if matching is None:
        return False
    return payload.point_id in {p.id for p in offered(matching.points)}


SELECT_CHOICE_POINT = register(ActionSpec(
    kind="select_choice_point",
    payload_model=SelectChoicePoint,
    rung="selection",
    i18n_key="agent.action.select_choice_point",
    referential=_select_choice_point_resolves,
))

#: What an agent may propose — the agent's SUBSET of the table, not the table.
#: Written from the rows this module registers rather than read off `_REGISTRY`,
#: which is now shared: `tuple(_REGISTRY)` would grow a desk command the day one
#: happened to be imported first, and `may_emit` would silently widen.
KINDS: tuple[str, ...] = (SELECT_CHOICE_POINT.kind,)
