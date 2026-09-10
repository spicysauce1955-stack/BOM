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
from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import ForceMounting, ForcePostSku, Override
from fenceai.topology.model import (
    GatePayload,
    GateSpan,
    Node,
    PointEvent,
    Run,
    Topology,
)
from fenceai.topology.station import make_anchor

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
    # The FENCE is order-independent; the run id deliberately is not. The id is a
    # digest of the input document, and two orderings are two documents — which
    # is the safe direction the digest comment names: "over-splitting is safe;
    # under-splitting serves the wrong fence under a reused id". Asserted rather
    # than left implied, because the test's name says "deterministic" and a
    # reader is entitled to know which of the two it means.
    assert a.run.id != b.run.id


def test_adding_a_gate_changes_the_run_id(knowledge, catalog):
    """A fence with a gate and the same fence without one are different runs.

    The user-facing half of the digest property: `save_run` is `INSERT OR
    IGNORE`, so two fences sharing an id means the second is dropped and every
    later read — structure sheet, BOM, the handover the office works from —
    serves the first. Nothing asserted it for gates at all.

    Honest about what it does NOT prove: this pair does not isolate
    `topology.gates` as the digest input responsible. Excluding `gates` from the
    dump leaves these two ids different anyway, through some other input a gate
    moves. The assertion that `gates` genuinely reaches the digest is the run-id
    line in `test_generation_is_deterministic_whatever_order_the_gates_arrive_in`
    above, which that exclusion does turn red — verified by making the mutation.
    """
    with_gate = _two_runs(True)
    without = _two_runs(False)
    a = generate(with_gate, knowledge, catalog)
    b = generate(without, knowledge, catalog)
    assert a.run.id != b.run.id, "a gate is part of the fence the id identifies"
    # ...and the same topology twice is the same id, so the assertion above is
    # about the gate and not about digest noise
    assert generate(_two_runs(True), knowledge, catalog).run.id == a.run.id


# --- the ground under the gate ----------------------------------------------
#
# `gate_on_slope` was checked for an in-run gate and skipped for a standalone
# one — so the gate MOST likely to be on falling ground, the one bridging two
# stretches at different levels, was the one nothing warned about. Both kinds
# now ask `_resolve_gate_max_slope` for the limit and `_check_gate_slope` for
# the verdict; only the measurement differs, because only the caller knows
# where its ground is (a run's profile at two stations, or a span's two nodes).

def _hanging_gate_at(z_far_mm: int | None, z_near_mm: int | None = None) -> Topology:
    """`o-----o [gate]` with elevations SAID out loud (or, for None, not said)."""
    topo = _one_run_and_a_gate()
    if z_near_mm is not None:
        topo.node("n1").z_mm = z_near_mm
        topo.node("n2").z_mm = z_near_mm
    if z_far_mm is not None:
        topo.node("n3").z_mm = z_far_mm
    return topo


def _slope_warning(result):
    return next((w for w in result.strategy.warnings if w.code == "gate_on_slope"), None)


def test_a_gate_span_between_two_levels_is_flagged(knowledge, catalog):
    """A 1000 mm opening with a 100 mm drop is 100‰ — twice K-GATE-SLOPE's 50‰."""
    result = generate(_hanging_gate_at(100), knowledge, catalog)
    warning = _slope_warning(result)
    assert warning is not None, "the gate bridging two levels is the whole point"
    assert warning.severity == "warning"
    assert warning.params == {
        "element": GATE_ELEMENT, "slope_permille": 100, "max_permille": 50,
    }, "the same params shape an in-run gate files, naming the gate as gate@<id>"
    assert warning.element_refs == [GATE_ELEMENT]
    # ...and the graph says WHICH version of WHICH rule decided the limit, which
    # is what sharing the resolution with the run path buys.
    node = result.graph.node(warning.decision_ref)
    assert node.action == "gate_on_slope"
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id)
            if e.type == "governed_by"}
    assert "K-GATE-SLOPE@v1" in refs


def test_a_gate_span_on_level_ground_is_not_flagged(knowledge, catalog):
    """Level ground SAID out loud — a site sitting 1500 mm up is not a slope."""
    result = generate(_hanging_gate_at(1500, 1500), knowledge, catalog)
    assert _slope_warning(result) is None


def test_a_gate_span_whose_nodes_state_no_elevation_is_not_flagged(
        knowledge, catalog):
    """An UNSTATED elevation is not a slope.

    `Node.z_mm` defaults to 0 and the run path reads the very same defaulted
    field through `ground_samples`, where it anchors the ends of a run whose
    ground nobody described. Unstated means LEVEL there, so it means level here:
    a gate whose nodes were never given a height warns about nothing, exactly as
    the run beside it does.
    """
    topo = _hanging_gate_at(None)
    assert topo.node("n2").z_mm == 0 and topo.node("n3").z_mm == 0, \
        "nobody stated an elevation; the default is what the run path reads too"
    assert _slope_warning(generate(topo, knowledge, catalog)) is None


def test_the_slope_of_an_in_run_gate_is_unchanged_by_the_sharing(
        knowledge, catalog):
    """The in-run check now runs through the same two helpers, and says the same
    thing it said before (`tests/scenarios/test_vertical_ground.py` is the gate
    on this; this is the half that lives beside the code it shares)."""
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0, z_mm=0),
               Node(id="n2", x_mm=6000, y_mm=0, z_mm=600)],
        runs=[Run(id="rA", start_node_id="n1", end_node_id="n2")],
    )
    run = topo.run("rA")
    run.point_events.append(PointEvent(
        id="g", anchor=make_anchor(topo, run, 2000),
        payload=GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000")))
    warning = _slope_warning(generate(topo, knowledge, catalog))
    assert warning.params == {
        "element": "gate@rA:2000-3000", "slope_permille": 100, "max_permille": 50,
    }


# --- overrides on a post only this pass creates -------------------------------
#
# A gate-only node post is real, it is bought and it is on the setting-out
# sheet, and until now no override could reach it: this pass never consulted
# them, so a forced sku did nothing and was then reported back as
# `orphaned_override`. The address needed no invention — `node:<id>` at station
# 0 is what the post already carries and what `_matched_force_overrides`
# already compares.

def _force_sku(run_id: str, sku: str) -> Override:
    return Override(id="ov1", run_id=run_id,
                    directive=ForcePostSku(station_mm=0, sku=sku))


def _orphaned(result) -> list[str]:
    return [w.params["override_id"] for w in result.strategy.warnings
            if w.code == "orphaned_override"]


def test_a_forced_sku_reaches_a_gate_only_post(knowledge, catalog):
    topo = _one_run_and_a_gate()
    plain = generate(topo, knowledge, catalog)
    far_before = next(p for p in plain.strategy.posts if p.run_ref == "node:n3")
    assert far_before.sku == "POST-S-HD", \
        "left alone it is the gate-reinforced post, which is what the force must beat"

    result = generate(topo, knowledge, catalog,
                      overrides=[_force_sku("node:n3", "POST-S")])
    far = next(p for p in result.strategy.posts if p.run_ref == "node:n3")
    assert far.sku == "POST-S", "a forced sku outranks the gate reinforcement"
    assert far.reinforced, "it is still the gate's post; only its product was chosen"
    assert "ov1" not in _orphaned(result), \
        "a directive that was honoured must not then blame the user's drawing"
    assert "ov1" in result.run.overrides_applied
    # the graph records WHY this post is this product
    assert any(n.action == "force_post_sku" and n.payload["override_id"] == "ov1"
               for n in result.graph.nodes)


def test_a_forced_mounting_reaches_a_gate_only_post(knowledge, catalog):
    result = generate(
        _one_run_and_a_gate(), knowledge, catalog,
        overrides=[Override(id="ov1", run_id="node:n3",
                            directive=ForceMounting(station_mm=0, mounting="masonry"))])
    far = next(p for p in result.strategy.posts if p.run_ref == "node:n3")
    assert far.mounting == "masonry"
    assert "ov1" not in _orphaned(result)


def test_an_override_may_not_reach_a_post_a_run_already_stands_at(
        knowledge, catalog):
    """The invariance, as an assertion about the one door that could have got
    around it: consulting overrides for the posts this pass CREATES must not
    become a way to re-specify a post the runs decided.

    n2 is the shared node — run rA ends there and the gate hangs off it — and
    the override is addressed at `node:n2`, exactly as the honoured one above is
    addressed at `node:n3`. It changes nothing, and it says so: the post is
    byte-identical to the one the same fence generates with no override at all,
    and the directive is reported orphaned rather than silently swallowed.
    """
    topo = _one_run_and_a_gate()
    without = generate(topo, knowledge, catalog)
    assert next(p for p in without.strategy.posts
                if p.run_ref == "node:n2").sku == "POST-S", \
        "the run decided POST-S here; the override below asks for something else"
    result = generate(topo, knowledge, catalog,
                      overrides=[_force_sku("node:n2", "POST-S-HD")])

    shared = next(p for p in result.strategy.posts if p.run_ref == "node:n2")
    assert shared.model_dump() == \
        next(p for p in without.strategy.posts if p.run_ref == "node:n2").model_dump()
    assert _orphaned(result) == ["ov1"], \
        "unreachable is reported, not silently applied somewhere else"
    # and the run beside it is untouched in every other respect too
    assert [p.model_dump() for p in result.strategy.posts] == \
        [p.model_dump() for p in without.strategy.posts]
    assert [s.model_dump() for s in result.strategy.spans] == \
        [s.model_dump() for s in without.strategy.spans]


def test_a_gate_exactly_on_the_permille_boundary_warns(knowledge, catalog):
    """The slope permille is rounded half-AWAY-from-zero, not by `round()`.

    A 105 mm drop across a 1000 mm opening is 105 permille exactly, and a 52.5
    case is the one that separates the two rules: `round()` is banker's and
    returns the EVEN neighbour, so 52.5 became 52 and a gate sitting exactly on
    the boundary of a 52 permille limit passed the check. That is the wrong
    direction to round a safety comparison, and it is the same trap
    `core/units.round_milli_to_mm` was written for.

    Asserted through the reported permille rather than by reaching into the
    helper: the number in `params` is the number the installer reads.
    """
    from fenceai.strategy.generator import _check_gate_slope
    from fenceai.decisions.graph import GraphBuilder
    from fenceai.strategy.model import Strategy

    def permille(drop_mm, opening_mm, limit):
        strategy = Strategy(id="s1")
        _check_gate_slope(GraphBuilder(), strategy, "g1", drop_mm, opening_mm,
                          limit, [])
        return [w.params["slope_permille"] for w in strategy.warnings]

    # 52.5 permille: half-away-from-zero says 53, which is over a limit of 52
    assert permille(105, 2000, 52) == [53]
    # 51.5 -> 52 under BOTH rules (banker's rounds to the even 52 here), so this
    # one is not discriminating and is kept only to pin the reported number
    assert permille(103, 2000, 51) == [52]
    # a drop genuinely at the limit still does not warn
    assert permille(104, 2000, 52) == []


# --- what the standalone gate's rule context is BOUND to ---------------------

def test_a_site_conditioned_gate_slope_rule_governs_a_standalone_gate(catalog):
    """`site` must reach `_resolve_gate_max_slope`, and nothing said so.

    The resolution context for a gate span is `{"scope": ..., "site": site}`.
    Dropping `"site": site` from it left the entire suite green — so a
    site-conditioned `gate_max_slope_permille` silently ceasing to apply to
    standalone gates was invisible, and the fence would be built to a limit the
    site's own rule does not set. `_assert_namespaces_bound` cannot catch it:
    that raises when a rule conditions on an UNBOUND namespace, and an unbound
    `site` is indistinguishable from a project that answered nothing.

    So: one rule that applies only in exposure C, tightening the limit to 20‰,
    and a gate at 100‰ that is inside 50‰-land but well outside 20‰.
    """
    tight = KnowledgeBase(versions=[
        *demo_knowledge().versions,
        KnowledgeVersion(
            object_id="K-GATE-SLOPE-EXPOSED", version=1, type="company_rule",
            title="Exposed sites need flatter gate ground",
            condition=Cmp(cmp="==", left=FieldRef(path="site.exposure_category"),
                          right=Lit(value="C")),
            actions=[SetParam(param="gate_max_slope_permille", value=20)],
        ),
    ])
    topo = _hanging_gate_at(30)   # 30 mm over 1000 mm = 30 permille

    # in exposure C the tighter rule governs, and 30 > 20 warns...
    exposed = generate(topo, tight, catalog,
                       site=SiteConditions(exposure_category="C"))
    warning = _slope_warning(exposed)
    assert warning is not None, "the site rule never reached the standalone gate"
    assert warning.params["max_permille"] == 20, \
        "the limit came from the unconditioned rule, so `site` was not bound"

    # ...and with no site stated the rule is NOT APPLICABLE, so 30 is inside 50
    assert _slope_warning(generate(topo, tight, catalog)) is None
