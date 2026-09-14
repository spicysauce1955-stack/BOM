"""The table itself.

**Growth is additive**, and that is a property rather than a convenience: a run
stamps only the inputs it actually had, so adding a row never invalidates a stored
one. The restraint that goes with it came from the Knowledge team at T54 §2 — a
finding that fits no entry becomes a COUNTER before it becomes a row, or the table
accumulates one-off kinds and is only as good as the judgement of whoever last
extended it.

Registration is at import time, from the modules that own the rows. Nothing here
imports those modules back: the table must not know what is in it, or the leaf
stops being a leaf.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.commands.model import CommandSpec

_TABLE: dict[str, CommandSpec] = {}


def register(spec: CommandSpec) -> CommandSpec:
    """Put a row in, and refuse a second row for a word that already has one.

    Two rows for one kind is a table with no answer, and the last import to run
    would silently win. It fails where the second one is written.
    """
    if spec.kind in _TABLE:
        raise ValueError(f"command kind already registered: {spec.kind}")
    _TABLE[spec.kind] = spec
    return spec


def spec_for(kind: str) -> CommandSpec:
    """The row for a kind, or `KeyError`.

    Raises rather than returning `None`: a kind nobody registered has no word in
    any grammar we hand out, and a caller that got `None` back would have to
    remember to check.
    """
    if kind not in _TABLE:
        raise KeyError(f"no registered command kind: {kind}")
    return _TABLE[kind]


def all_kinds() -> tuple[str, ...]:
    """Every registered kind, sorted. Sorted because callers iterate it to assert
    things — a locale key per kind, a doc row per kind — and an assertion that
    depends on import order fails for a reason nobody can read."""
    return tuple(sorted(_TABLE))


def parse_payload(kind: str, payload: dict) -> BaseModel:
    """Validate against the kind's own model.

    The typed model is authoritative; a stored payload is its serialised form, and
    this is the only way to read one back. A free-form dict is inexpressible under
    `additionalProperties:false` and silently arrives empty — the lesson
    `ai/claude.py` already carries in a comment.
    """
    return spec_for(kind).payload_model.model_validate(payload)
