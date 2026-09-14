"""The closed table of what may be DONE to a job. Backoffice design §10.

This table is not new — it is `agent/registry.py`'s, moved. So these tests assert
two things at once: that it behaves like a closed vocabulary, and that the one row
which already existed reads from out here exactly as it read from inside `agent/`.
The second half matters more than it looks: a refactor that quietly changed what
`select_choice_point` resolves to would change what an agent may propose, and
nothing downstream would say so.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from fenceai.commands.model import CommandSpec
from fenceai.commands.registry import all_kinds, parse_payload, register, spec_for

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"


def _bundles():
    en = json.loads((STATIC / "i18n" / "en.json").read_text())
    he = json.loads((STATIC / "i18n" / "he.json").read_text())
    return en, he


class _Payload(BaseModel):
    model_config = {"extra": "forbid"}

    user_id: str


@pytest.fixture
def desk_row():
    """A row shaped like the desk commands Task 4 registers, put in and taken out.

    Registered rather than merely constructed, because the property under test is
    that the TABLE hands back the permission untouched — a `register` that
    normalised or dropped a column would still leave a constructed spec correct.
    Popped in teardown: a row the locale test below would then demand a sentence
    for is not something one test may leave behind for another to trip over.
    """
    from fenceai.commands.registry import _TABLE

    spec = register(CommandSpec(
        kind="_test_only_claim",
        payload_model=_Payload,
        rung="directive",
        capacities=frozenset({"backoffice", "admin"}),
        from_states=frozenset({"waiting"}),
        disposition="ask",
        i18n_key="command._test_only_claim",
        materialize=lambda payload, project, **_: project,
    ))
    try:
        yield spec
    finally:
        _TABLE.pop("_test_only_claim", None)


def test_the_table_is_closed_and_a_kind_nobody_registered_has_no_word():
    """`knowledge/ast.py`'s FnCall whitelist is the same instinct: a closed
    vocabulary resolved in code, no eval of strings, ever."""
    with pytest.raises(KeyError):
        spec_for("drop_all_tables")


def test_the_row_that_was_never_the_agents_is_here_and_unchanged():
    """`select_choice_point` lived in `agent/registry.py` because it was the only
    row and the agent was its only caller. It reads identically from here."""
    from fenceai.agent.registry import SelectChoicePoint

    spec = spec_for("select_choice_point")
    assert spec.rung == "selection"
    assert spec.payload_model is SelectChoicePoint
    assert spec.i18n_key == "agent.action.select_choice_point"


def test_a_spec_names_which_capacities_may_perform_it(desk_row):
    """The permission lives on the command, not in the handler. One table rather
    than a check scattered across handlers, half of which get added later by
    somebody who did not know."""
    spec = spec_for("_test_only_claim")
    assert "backoffice" in spec.capacities
    assert "sales" not in spec.capacities


def test_a_spec_names_which_states_it_may_run_from(desk_row):
    spec = spec_for("_test_only_claim")
    assert "waiting" in spec.from_states
    assert "delivered" not in spec.from_states


def test_a_row_that_names_no_capacity_is_nobody_s_to_perform():
    """The default is the empty set, and `perform` asks `capacity in capacities` —
    so a row whose author forgot the column refuses everybody rather than
    admitting everybody. The agent's own row is that case today: nothing performs
    `select_choice_point` by hand yet, and until something does, no capacity may."""
    assert spec_for("select_choice_point").capacities == frozenset()


def test_registering_a_kind_twice_is_refused():
    """Two rows for one word is a table with no answer. It fails where the
    second one is written."""
    with pytest.raises(ValueError):
        register(spec_for("select_choice_point"))


def test_a_payload_is_parsed_against_its_own_kinds_model():
    """A free-form dict is inexpressible under `additionalProperties:false` and
    silently arrives empty — the lesson `ai/claude.py` already carries."""
    payload = parse_payload("select_choice_point", {
        "choice_set": "bay_layout", "scope": "gap:run1:0", "point_id": "p2"})
    assert payload.point_id == "p2"
    with pytest.raises(ValidationError):
        parse_payload("select_choice_point", {
            "choice_set": "bay_layout", "scope": "s", "point_id": "p2",
            "and_also": "move a post"})


def test_every_registered_kind_has_a_locale_key_in_both_bundles():
    """The activity log renders per language from what happened, never from a
    stored sentence — the rule the warning registry already lives by."""
    en, he = _bundles()
    assert all_kinds(), "the table read empty — every assertion below would pass vacuously"
    for kind in all_kinds():
        assert f"command.{kind}" in en, kind
        assert f"command.{kind}" in he, kind


def test_the_table_imports_nothing_of_ours():
    """A pure leaf, and pinned rather than intended.

    Both ends of the system reach this package — a route performs a row, an agent
    proposes one — so the moment it can import either, one of them owns it again
    and we are back to a table living wherever its first caller happened to be.
    `fenceai.commands.model` is the one exception the scan allows: the package
    naming its own row type is not a dependency on anything.
    """
    import ast

    src = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "commands"
    modules = sorted(src.rglob("*.py"))
    assert modules, "no command modules found — this test is looking at nothing"
    offenders = []
    for path in modules:
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            offenders += [f"{path.name} imports {n}" for n in names
                          if n.startswith("fenceai.") and not n.startswith("fenceai.commands.")]
    assert not offenders, offenders
