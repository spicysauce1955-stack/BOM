"""The action registry. Spec §2.

A code-registered table, the same instinct as `knowledge/ast.py`'s FnCall
whitelist: a closed vocabulary resolved in code, never an eval of strings.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.agent.registry import KINDS, SelectChoicePoint, parse_payload, spec_for


def test_the_one_action_this_slice_ships_is_registered():
    spec = spec_for("select_choice_point")
    assert spec.rung == "selection"
    assert spec.payload_model is SelectChoicePoint
    assert spec.i18n_key == "agent.action.select_choice_point"


def test_an_unregistered_kind_is_refused_by_name():
    with pytest.raises(KeyError, match="move_post"):
        spec_for("move_post")


def test_a_payload_is_parsed_into_its_typed_model():
    payload = parse_payload("select_choice_point", {
        "choice_set": "bay_layout", "scope": "gap:run1:0", "point_id": "p2"})
    assert isinstance(payload, SelectChoicePoint)
    assert payload.point_id == "p2"


def test_a_payload_missing_a_field_is_refused():
    with pytest.raises(ValidationError):
        parse_payload("select_choice_point", {"choice_set": "bay_layout"})


def test_a_payload_with_an_unknown_field_is_refused():
    """Structured outputs require additionalProperties:false, so a free-form
    dict is inexpressible in the schema and silently stays empty
    (`ai/claude.py`). The payload models are explicit and closed for the same
    reason, in the other direction."""
    with pytest.raises(ValidationError):
        parse_payload("select_choice_point", {
            "choice_set": "bay_layout", "scope": "s", "point_id": "p2",
            "and_also": "move a post"})


def test_kinds_is_the_whole_vocabulary():
    assert KINDS == ("select_choice_point",)
