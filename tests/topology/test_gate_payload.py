"""A gate's swing is topology, and a contradiction in it is refused.

"Gate at station 2000, opening 1000" tells an installer there is a hole and not
which way the leaf goes. The four facts that answer that live here — on the
drawing the salesperson authored — because contract obligation 18 has the
knowledge platform's `PanelSpec` model no gate at all.

Two properties are load-bearing. `None` means NOBODY HAS SAID and must stay
valid, or every gate authored before these fields existed becomes unloadable.
And a contradiction (a sliding gate with a hinge) is somebody's UI writing
nonsense: clearing it quietly would hide that bug and hand a crew a confident
wrong drawing.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.topology.model import GatePayload
from tests.conftest import add_point_event


def test_a_gate_authored_before_any_of_this_is_still_valid():
    """The compatibility claim, made explicitly: the old two-field payload
    loads, and says nothing it was not told."""
    gate = GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000")
    assert gate.leaf == "single", "a gate is a single swing leaf unless said otherwise"
    assert gate.opens_to is None
    assert gate.hinge is None
    assert gate.slides_to is None

    # and it round-trips through the wire form unchanged
    assert GatePayload.model_validate(gate.model_dump()) == gate

    # including a payload serialised before the fields existed
    old = {"kind": "gate", "width_mm": 1000, "kit_sku": "GATE-KIT-1000"}
    assert GatePayload.model_validate(old) == gate


def test_a_stated_swing_round_trips():
    gate = GatePayload(width_mm=1000, leaf="single", opens_to="left", hinge="start")
    assert GatePayload.model_validate(gate.model_dump()) == gate


@pytest.mark.parametrize("field", ["opens_to", "hinge"])
def test_a_sliding_gate_that_swings_is_refused(field):
    value = "left" if field == "opens_to" else "start"
    with pytest.raises(ValidationError) as exc:
        GatePayload(width_mm=3000, leaf="sliding", **{field: value})
    assert "a sliding gate swings toward no side and hangs from no edge" in str(exc.value)
    assert f"{field}={value!r}" in str(exc.value), "the refusal must name what it saw"


@pytest.mark.parametrize("leaf", ["single", "double"])
def test_a_swing_gate_that_slides_is_refused(leaf):
    with pytest.raises(ValidationError) as exc:
        GatePayload(width_mm=1000, leaf=leaf, slides_to="end")
    assert "a swing gate slides nowhere" in str(exc.value)
    assert f"leaf={leaf!r} with slides_to='end'" in str(exc.value)


def test_a_double_gate_with_one_hinge_edge_is_refused():
    with pytest.raises(ValidationError) as exc:
        GatePayload(width_mm=2000, leaf="double", hinge="start", opens_to="left")
    assert "a double gate hangs from both edges of the opening" in str(exc.value)
    assert "hinge='start'" in str(exc.value)


def test_a_double_gate_still_states_the_side_it_opens_toward():
    """The refusal above is about the HINGE only — which way both leaves swing
    is exactly the fact the installer is missing."""
    gate = GatePayload(width_mm=2000, leaf="double", opens_to="right")
    assert gate.opens_to == "right" and gate.hinge is None


