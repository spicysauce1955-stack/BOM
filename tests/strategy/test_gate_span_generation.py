"""Generating a gate that stands BESIDE the runs.

    o------------o  [====gate====]  o------------o
        run rA      the GateSpan        run rB
                    n2          n3

The load-bearing property of this whole feature is negative, and it is the
user's own sentence: *"it doesn't change the layout of already placed runs"*.
Placing a gate next to a run must leave that run's posts, bays, warnings, BOM
and explanation byte-identical to what they were before the gate existed — so
that property is asserted by GENERATING THE SAME TOPOLOGY TWICE, once with its
gate spans and once with `gates=[]`, and comparing the two results. Nothing is
hard-coded: the fence is its own expected value.

What the gate DOES add is its own — one `Gate` element, its kit, and a post at
each of its two nodes, because a gate with a post on one side only is
unbuildable.
"""

from __future__ import annotations

from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.strategy.generator import generate
from fenceai.topology.model import GateSpan, Node, Run, Topology

GATE_ID = "g1"
GATE_ELEMENT = "gate@g1"


def _two_runs(with_gate: bool, **swing) -> Topology:
    """Two runs drawn unconnected, optionally joined by a 1000 mm gate. Every
    node position is identical in both, so the ONLY difference between the two
    generations is the gate itself."""
    return Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=5000, y_mm=0),
               Node(id="n3", x_mm=6000, y_mm=0), Node(id="n4", x_mm=11000, y_mm=0)],
        runs=[Run(id="rA", start_node_id="n1", end_node_id="n2"),
              Run(id="rB", start_node_id="n3", end_node_id="n4")],
        gates=([GateSpan(id=GATE_ID, start_node_id="n2", end_node_id="n3", **swing)]
               if with_gate else []),
    )


def _one_run_and_a_gate() -> Topology:
    """`o-----o [gate]` — the gate hangs off one run's end and there is nothing
    beyond it. Its far node is the case with nothing to inherit a post from."""
    return Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=5000, y_mm=0),
               Node(id="n3", x_mm=6000, y_mm=0)],
        runs=[Run(id="rA", start_node_id="n1", end_node_id="n2")],
        gates=[GateSpan(id=GATE_ID, start_node_id="n2", end_node_id="n3")],
    )


def _bom_lines(result, catalog):
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    requirements = resolve_supply(requirements, catalog, None).requirements
    bom = fulfill(requirements, catalog, None)
    return [line.model_dump() for line in bom.lines]


def _gate_nodes(graph) -> set[str]:
    """The decision nodes the gate itself caused — the ones that must be the
    ONLY difference between the two graphs."""
    return {n.id for n in graph.nodes
            if GATE_ELEMENT in n.scope_refs or n.payload.get("gate_id") == GATE_ID}


# --- the invariant ----------------------------------------------------------

def test_a_gate_span_changes_nothing_about_the_runs_it_stands_between(
        knowledge, catalog):
    """*"it doesn't change the layout of already placed runs"* — as an executable
    statement, not a comment.

    Take everything the gate itself caused out of the with-gate generation, and
    what is left must be indistinguishable from the fence generated without it:
    the same posts, the same bays, the same warnings, the same purchase, and the
    same explanation.
    """
    with_gate = generate(_two_runs(True), knowledge, catalog)
    without = generate(_two_runs(False), knowledge, catalog)

    assert [p.model_dump() for p in with_gate.strategy.posts] == \
        [p.model_dump() for p in without.strategy.posts], \
        "every post, including the node posts the gate hangs from, is untouched"
    assert [s.model_dump() for s in with_gate.strategy.spans] == \
        [s.model_dump() for s in without.strategy.spans]
    assert [w.model_dump() for w in with_gate.strategy.warnings] == \
        [w.model_dump() for w in without.strategy.warnings]
    assert [m.model_dump() for m in with_gate.strategy.member_runs] == \
        [m.model_dump() for m in without.strategy.member_runs]

    # the BOM differs by the gate kit and by nothing else
    gate_kit = with_gate.strategy.gates[0].kit_sku
    assert gate_kit, "the demo catalog fits a 1000 mm opening; the test needs that"
    assert [l for l in _bom_lines(with_gate, catalog) if l["sku"] != gate_kit] == \
        _bom_lines(without, catalog)

    # ...and so does the explanation. Node ids are sequence numbers, so they are
    # excluded and the ORDER carries the identity: with the gate's own nodes
    # removed, the two graphs are the same graph.
    gate_nodes = _gate_nodes(with_gate.graph)
    rest = [n for n in with_gate.graph.nodes if n.id not in gate_nodes]
    assert [n.model_dump(exclude={"id", "ordinal"}) for n in rest] == \
        [n.model_dump(exclude={"id", "ordinal"}) for n in without.graph.nodes]
    # every edge of the ungated fence is still there, joining the same two nodes
    remap = dict(zip([n.id for n in without.graph.nodes], [n.id for n in rest]))
    with_edges = {(e.from_id, e.to_id, e.type, e.knowledge_ref)
                  for e in with_gate.graph.edges}
    without_edges = {(remap[e.from_id], remap[e.to_id], e.type, e.knowledge_ref)
                     for e in without.graph.edges}
    assert without_edges <= with_edges
    assert all(to_id in gate_nodes for _, to_id, _, _ in with_edges - without_edges), \
        "every new edge points INTO a node the gate itself caused"


def test_the_gate_span_is_the_one_thing_that_was_added(knowledge, catalog):
    """The positive half of the invariant above: exactly one more `Gate`, and
    the posts at the gate's own two nodes are there (the runs' own node posts,
    which is why nothing had to be added for them)."""
    with_gate = generate(_two_runs(True), knowledge, catalog)
    without = generate(_two_runs(False), knowledge, catalog)

    assert len(with_gate.strategy.gates) == len(without.strategy.gates) + 1
    gate = with_gate.strategy.gates[-1]
    assert gate.id == GATE_ELEMENT
    assert gate.run_ref is None, "a standalone gate lies on no run"
    assert (gate.start_node_id, gate.end_node_id) == ("n2", "n3")
    assert gate.width_mm == 1000, "the opening is the distance between its nodes"
    assert (gate.start_station_mm, gate.end_station_mm) == (0, 0), \
        "it has no station, and 0/0 says so rather than claiming a place on a run"

    by_ref = {p.run_ref for p in with_gate.strategy.posts}
    assert {"node:n2", "node:n3"} <= by_ref, "a gate needs a post at each end"


def test_a_gate_hanging_off_one_end_gets_a_post_at_its_far_node(knowledge, catalog):
    """`o-----o [gate]` — n3 is touched by no run, so nothing else would ever
    put a post there, and a gate with a post on one side only is unbuildable."""
    result = generate(_one_run_and_a_gate(), knowledge, catalog)
    far = next(p for p in result.strategy.posts if p.run_ref == "node:n3")
    assert far.kind == "end"
    assert far.sku, "it is a real post, resolved through the same path as any other"
    assert far.reinforced, \
        "it stands for the gate alone, so the gate's context governs it outright"
    assert far.embed_mm > 0, "it is set into the ground like any other post"
    assert far.exposed_mm is None, \
        "no bay meets it, so the length check measured no top to carry"
    # ...and it is on the graph, traceable to the gate that caused it
    placed = result.graph.nodes_for_element(far.id)
    assert any(n.action == "place_post" for n in placed)
    causes = {n.action for n in result.graph.ancestors(
        next(n.id for n in placed if n.action == "place_post"))}
    assert "gate_span" in causes, "the post must name the gate it exists for"


def test_a_gate_beside_a_run_does_not_disturb_that_run(knowledge, catalog):
    """The same invariant in the asymmetric case: adding the hanging gate to a
    single run leaves that run's own posts and bays exactly as they were."""
    with_gate = generate(_one_run_and_a_gate(), knowledge, catalog)
    bare = _one_run_and_a_gate()
    bare.gates = []
    without = generate(bare, knowledge, catalog)

    run_posts = lambda r: [p.model_dump() for p in r.strategy.posts
                           if p.run_ref in ("rA", "node:n1", "node:n2")]
    assert run_posts(with_gate) == run_posts(without)
    assert [s.model_dump() for s in with_gate.strategy.spans] == \
        [s.model_dump() for s in without.strategy.spans]


# --- the gate itself --------------------------------------------------------

def test_the_swing_is_carried_through_untouched(knowledge, catalog):
    result = generate(_two_runs(True, leaf="double", opens_to="right"),
                      knowledge, catalog)
    gate = result.strategy.gates[0]
    assert (gate.leaf, gate.opens_to, gate.hinge, gate.slides_to) == \
        ("double", "right", None, None)


def test_the_kit_is_resolved_through_the_same_path_as_an_in_run_gate(
        knowledge, catalog):
    """Not by parsing a SKU: the catalog is asked BY DECLARED WIDTH, exactly as
    it is for a gate inside a run."""
    result = generate(_two_runs(True), knowledge, catalog)
    assert result.strategy.gates[0].kit_sku == "GATE-KIT-1000"
    chosen = next(n for n in result.graph.nodes
                  if n.action == "select_gate_kit" and GATE_ELEMENT in n.scope_refs)
    assert chosen.payload["source"] == "catalog"
    assert chosen.payload["opening_width_mm"] == 1000


def test_an_opening_nothing_fits_is_reported_in_the_same_words(knowledge, catalog):
    topo = _two_runs(True)
    topo.node("n3").x_mm = 8500  # a 3500 mm opening; the demo catalog fits 1000
    result = generate(topo, knowledge, catalog)
    warning = next(w for w in result.strategy.warnings if w.code == "no_gate_kit")
    assert warning.severity == "error"
    assert warning.params == {"element": GATE_ELEMENT, "opening_width_mm": 3500}
    assert warning.element_refs == [GATE_ELEMENT]


def test_a_kit_that_does_not_fit_the_opening_is_an_error(knowledge, catalog):
    """The same check, the same message and the same params an in-run gate gets
    (`tests/strategy/test_gate_kit.py`) — one implementation, two callers."""
    topo = _two_runs(True, kit_sku="GATE-KIT-1000")
    topo.node("n3").x_mm = 8500
    result = generate(topo, knowledge, catalog)
    warning = next(w for w in result.strategy.warnings
                   if w.code == "gate_kit_width_mismatch")
    assert warning.severity == "error"
    assert warning.params == {
        "element": GATE_ELEMENT, "sku": "GATE-KIT-1000",
        "kit_width_mm": 1000, "opening_width_mm": 3500,
    }
    assert warning.decision_ref


def test_the_gate_kit_reaches_the_bom(knowledge, catalog):
    result = generate(_two_runs(True), knowledge, catalog)
    lines = _bom_lines(result, catalog)
    kit = next(l for l in lines if l["sku"] == "GATE-KIT-1000")
    assert kit["engineering_qty"] == 1


def test_generation_is_deterministic_whatever_order_the_gates_arrive_in(
        knowledge, catalog):
    """`generate()` is deterministic (ADR-0004), and a frontend appends gates in
    whatever order the user drew them."""
    forward = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=5000, y_mm=0),
               Node(id="n3", x_mm=6000, y_mm=0), Node(id="n4", x_mm=11000, y_mm=0),
               Node(id="n5", x_mm=12000, y_mm=0)],
        runs=[Run(id="rA", start_node_id="n1", end_node_id="n2"),
              Run(id="rB", start_node_id="n3", end_node_id="n4")],
        gates=[GateSpan(id="gA", start_node_id="n2", end_node_id="n3"),
               GateSpan(id="gB", start_node_id="n4", end_node_id="n5")],
    )
    reversed_ = forward.model_copy(deep=True)
    reversed_.gates = list(reversed(reversed_.gates))
    a, b = generate(forward, knowledge, catalog), generate(reversed_, knowledge, catalog)
    assert a.strategy.model_dump() == b.strategy.model_dump()
    assert a.graph.model_dump() == b.graph.model_dump()
