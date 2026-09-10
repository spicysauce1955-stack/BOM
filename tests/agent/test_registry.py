"""The action registry. Spec §2.

A code-registered table, the same instinct as `knowledge/ast.py`'s FnCall
whitelist: a closed vocabulary resolved in code, never an eval of strings.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

import dataclasses

from fenceai.agent.registry import (
    KINDS, ActionSpec, SelectChoicePoint, parse_payload, spec_for)
from fenceai.strategy.choices import ChoiceSet, DesignPoint


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


def test_every_registered_kind_carries_its_own_referential_check():
    """Check 3 (spec §6) is a property of the ROW, not a branch in the
    dispatcher. A dispatcher that asked `if kind == "select_choice_point"`
    gave every kind registered after it checks 1 and 2 and no referential
    check at all — so a user could be offered something impossible and no
    test would fail. Iterating `KINDS` is what makes the next row obey."""
    for kind in KINDS:
        assert callable(spec_for(kind).referential), kind


def test_a_row_without_a_referential_check_cannot_be_constructed():
    """Not merely unwise — impossible. `referential` has no default, so the
    fail-open row is a TypeError at import time rather than a silent
    admission at run time."""
    with pytest.raises(TypeError):
        ActionSpec(kind="move_post", payload_model=SelectChoicePoint,
                   rung="directive", i18n_key="agent.action.move_post")


def test_the_referential_check_denies_a_point_no_open_set_offers():
    """The check itself, off the row and away from the dispatcher."""
    check = spec_for("select_choice_point").referential
    offered_point = DesignPoint(id="p1", label="a", widths=[2500],
                                axes={"posts": 3, "offcut_mm": 800}, is_default=True)
    other = DesignPoint(id="p2", label="b", widths=[1800, 1400],
                        axes={"posts": 4, "offcut_mm": 100})
    open_sets = [ChoiceSet(id="bay_layout", scope="gap:run1:0", question="q",
                           points=[offered_point, other])]
    payload = parse_payload("select_choice_point", {
        "choice_set": "bay_layout", "scope": "gap:run1:0", "point_id": "p2"})
    assert check(payload, open_sets) is True

    absent = parse_payload("select_choice_point", {
        "choice_set": "bay_layout", "scope": "gap:run1:0", "point_id": "p9"})
    assert check(absent, open_sets) is False
    # right point, a set this run does not consider open
    assert check(payload, []) is False


def test_a_row_is_frozen_so_a_check_cannot_be_swapped_at_run_time():
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec_for("select_choice_point").referential = lambda *_: True
