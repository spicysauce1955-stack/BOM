"""A gate that stands BESIDE the runs, and is its own element.

    o------------o  [====gate====]  o------------o
        run rA      the GateSpan        run rB
                    n2          n3

The other kind — `GatePayload`, a point event inside a run — is untouched and
still works; every stored project and every golden scenario uses it. This file
is about the second kind, and about the two properties that make it safe to add:

  * a topology with no `gates` key still loads and round-trips, so nothing
    stored before this existed becomes unreadable; and
  * the geometry is asked, never stored — there is no `width_mm` on a
    `GateSpan`, because a stored width would disagree with the drawing the
    moment somebody drags a node, and from then on the picture and the price
    would be about different gates.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.topology.model import GatePayload, GateSpan, Node, Run, Topology
from fenceai.topology.station import gate_opening_mm


def _nodes(*coords: tuple[str, int, int]) -> list[Node]:
    return [Node(id=i, x_mm=x, y_mm=y) for i, x, y in coords]


def _two_runs_and_a_gate() -> Topology:
    """The picture in the docstring: two runs drawn unconnected, joined by a
    gate that lies on neither."""
    return Topology(
        nodes=_nodes(("n1", 0, 0), ("n2", 5000, 0),
                     ("n3", 6000, 0), ("n4", 11000, 0)),
        runs=[
            Run(id="rA", start_node_id="n1", end_node_id="n2"),
            Run(id="rB", start_node_id="n3", end_node_id="n4"),
        ],
        gates=[GateSpan(id="g1", start_node_id="n2", end_node_id="n3")],
    )


# --- compatibility ----------------------------------------------------------

def test_a_topology_authored_before_gate_spans_still_loads():
    """The compatibility claim, made explicitly, and from the WIRE form: every
    project stored before this field existed has no `gates` key at all."""
    old = {
        "revision": 3,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 5000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    }
    topo = Topology.model_validate(old)
    assert topo.gates == [], "no gates key means no gates, not a failure to load"

    # and it round-trips: re-reading what we serialise gives back the same thing
    assert Topology.model_validate(topo.model_dump()) == topo


def test_a_topology_with_gate_spans_round_trips():
    topo = _two_runs_and_a_gate()
    assert Topology.model_validate(topo.model_dump()) == topo


# --- the opening is the geometry, and is stored nowhere ----------------------

def test_a_gate_span_stores_no_width():
    """The one fact, in the one place. A `width_mm` field here would be a second
    copy of something the nodes already say."""
    assert "width_mm" not in GateSpan.model_fields


def test_the_opening_is_the_distance_between_the_two_nodes():
    topo = _two_runs_and_a_gate()
    assert gate_opening_mm(topo, topo.gate("g1")) == 1000


def test_dragging_a_node_moves_the_opening_with_it():
    """The failure the missing field prevents: a stored width would still read
    1000 here, and the drawing and the price would part company."""
    topo = _two_runs_and_a_gate()
    topo.node("n3").x_mm = 9000
    assert gate_opening_mm(topo, topo.gate("g1")) == 4000


# --- integrity --------------------------------------------------------------

def test_duplicate_gate_ids_are_refused():
    with pytest.raises(ValidationError) as exc:
        Topology(
            nodes=_nodes(("n1", 0, 0), ("n2", 1000, 0), ("n3", 2000, 0)),
            gates=[GateSpan(id="g1", start_node_id="n1", end_node_id="n2"),
                   GateSpan(id="g1", start_node_id="n2", end_node_id="n3")],
        )
    assert "duplicate gate ids in topology" in str(exc.value)


def test_a_gate_id_that_collides_with_a_run_id_is_refused():
    """Both are ELEMENT ids downstream — the strategy pegs to them, the graph
    scopes to them, the reports group by them — so a collision would silently
    merge two different things rather than merely look odd."""
    with pytest.raises(ValidationError) as exc:
        Topology(
            nodes=_nodes(("n1", 0, 0), ("n2", 5000, 0), ("n3", 6000, 0)),
            runs=[Run(id="x", start_node_id="n1", end_node_id="n2")],
            gates=[GateSpan(id="x", start_node_id="n2", end_node_id="n3")],
        )
    assert "gate id x collides with a run id in topology" in str(exc.value)


def test_a_gate_at_a_node_that_does_not_exist_is_refused():
    with pytest.raises(ValidationError) as exc:
        Topology(
            nodes=_nodes(("n1", 0, 0)),
            gates=[GateSpan(id="g1", start_node_id="n1", end_node_id="nope")],
        )
    assert "gate g1 references a missing node" in str(exc.value)


def test_a_gate_between_one_node_and_itself_is_refused():
    """It has no opening: there is nothing for a leaf to close."""
    with pytest.raises(ValidationError) as exc:
        Topology(
            nodes=_nodes(("n1", 0, 0)),
            gates=[GateSpan(id="g1", start_node_id="n1", end_node_id="n1")],
        )
    assert "gate g1 starts and ends at the same node" in str(exc.value)


# --- the swing, refused by the SAME implementation --------------------------
#
# Parametrised over both models on purpose. These are the same four facts about
# the same physical object, and the assertion that matters is that the two
# authoring routes answer in the same words — a second copy of the check is how
# one of them would quietly start accepting the nonsense the other refuses.

def _make(model, **swing):
    if model is GatePayload:
        return GatePayload(width_mm=1000, **swing)
    return GateSpan(id="g1", start_node_id="n1", end_node_id="n2", **swing)


MODELS = [GatePayload, GateSpan]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("field", ["opens_to", "hinge"])
def test_a_sliding_gate_that_swings_is_refused(model, field):
    value = "left" if field == "opens_to" else "start"
    with pytest.raises(ValidationError) as exc:
        _make(model, leaf="sliding", **{field: value})
    assert "a sliding gate swings toward no side and hangs from no edge" in str(exc.value)
    assert f"{field}={value!r}" in str(exc.value), "the refusal must name what it saw"


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("leaf", ["single", "double"])
def test_a_swing_gate_that_slides_is_refused(model, leaf):
    with pytest.raises(ValidationError) as exc:
        _make(model, leaf=leaf, slides_to="end")
    assert "a swing gate slides nowhere" in str(exc.value)
    assert f"leaf={leaf!r} with slides_to='end'" in str(exc.value)


@pytest.mark.parametrize("model", MODELS)
def test_a_double_gate_with_one_hinge_edge_is_refused(model):
    with pytest.raises(ValidationError) as exc:
        _make(model, leaf="double", hinge="start", opens_to="left")
    assert "a double gate hangs from both edges of the opening" in str(exc.value)
    assert "hinge='start'" in str(exc.value)


@pytest.mark.parametrize("model", MODELS)
def test_a_gate_span_says_nothing_it_was_not_told(model):
    gate = _make(model)
    assert gate.leaf == "single", "a gate is a single swing leaf unless said otherwise"
    assert gate.opens_to is None and gate.hinge is None and gate.slides_to is None


def test_a_stated_swing_round_trips_on_a_gate_span():
    """`opens_to` is relative to the gate's OWN direction (start -> end), the
    same convention `GatePayload` documents against its run."""
    gate = GateSpan(id="g1", start_node_id="n1", end_node_id="n2",
                    leaf="single", opens_to="left", hinge="start")
    assert GateSpan.model_validate(gate.model_dump()) == gate
