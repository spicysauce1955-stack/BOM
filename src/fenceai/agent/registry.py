"""What an agent may propose — a code-registered table, not a config file.

`knowledge/ast.py`'s FnCall whitelist is the same instinct: a closed vocabulary
resolved in code, no eval of strings, ever. A task's permission list is
compiled into the model's output schema (spec §1), so an action absent from
this table has no word in any grammar an agent is ever handed. Narrow run stops
being a policy somebody must enforce and becomes a type.

**Growth is additive.** A run stamps only the inputs it actually had, so adding
an entry never invalidates a stored run. But a finding that fits no entry
becomes a COUNTER before it becomes a row here — T54 §2, where the Knowledge
team wanted a ninth Gap kind, found none of the eight fitted, and declined to
add one "for something we can measure on our own side". Without that restraint
the table accumulates one-off kinds and the grammar is only as good as the
judgement of whoever last extended it.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


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


@dataclass(frozen=True)
class ActionSpec:
    """One thing an agent may propose.

    A dataclass rather than a model: `payload_model` is a TYPE, and a registry
    row is code rather than data on the wire.
    """

    kind: str
    payload_model: type[BaseModel]
    rung: Literal["note", "selection", "directive", "rule"]
    i18n_key: str
    # Backend policy, and deliberately not the agent's business (spec §7): an
    # agent told which of its proposals get applied automatically will learn to
    # phrase things to get applied, and every check would still pass.
    disposition: Literal["show", "hold_pending", "auto"] = "show"


_REGISTRY: dict[str, ActionSpec] = {}


def register(spec: ActionSpec) -> ActionSpec:
    if spec.kind in _REGISTRY:
        raise ValueError(f"action kind already registered: {spec.kind}")
    _REGISTRY[spec.kind] = spec
    return spec


def spec_for(kind: str) -> ActionSpec:
    if kind not in _REGISTRY:
        raise KeyError(f"no registered action kind: {kind}")
    return _REGISTRY[kind]


def parse_payload(kind: str, payload: dict) -> BaseModel:
    """The typed model is authoritative; a stored `Proposal.payload` is its
    serialised form, and this is the only way to read one back."""
    return spec_for(kind).payload_model.model_validate(payload)


SELECT_CHOICE_POINT = register(ActionSpec(
    kind="select_choice_point",
    payload_model=SelectChoicePoint,
    rung="selection",
    i18n_key="agent.action.select_choice_point",
))

KINDS: tuple[str, ...] = tuple(_REGISTRY)
