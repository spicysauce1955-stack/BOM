"""The decisions of one SECTION, rather than of one element.

`/explain/{element}` answers "why is this post here". The question the roadmap
asks is a different one — *"focus on specific sections of the fence and get only
the decisions related to the selected section"* — and nothing answered it: a
section is a topology object, and the graph indexes by strategy element.

This view is a SUMMARY in causal order, not a deeper trail: every node that
decided something about this section, once, in the order the generator settled
them. The per-element trail with its `←` ancestors is still the place to go for
one element, and duplicating it per section would bury the summary it exists to
be.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.report.section_decisions import decisions_for_section
from fenceai.strategy.generator import generate
from fenceai.topology.model import Node, Run, Topology
from tests.conftest import straight_topology

PARTS = PartLibrary(parts=demo_parts())


def _straight():
    topo = straight_topology(6000)
    return topo, generate(topo, demo_knowledge(), demo_catalog(), parts=PARTS)


def _corner():
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0),
               Node(id="n2", x_mm=4000, y_mm=0),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")],
    )
    return topo, generate(topo, demo_knowledge(), demo_catalog(), parts=PARTS)


def test_a_section_gets_the_decisions_about_its_own_elements():
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "run1")
    assert got.section_id == "run1"
    assert got.decisions
    scoped = {e for d in got.decisions for e in d.elements}
    assert any(e.startswith("span@run1") for e in scoped)
    assert any(e.startswith("post@") for e in scoped)


def test_every_decision_carries_the_sentence_the_reader_sees():
    """Rendered here, from the graph, in the reader's language — the same
    `explain_node` the element trail uses. A view that returned node kinds and
    left the client to phrase them would be a second explanation."""
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "run1",
                                lang="he")
    assert all(d.sentence for d in got.decisions)
    assert any(any("א" <= ch <= "ת" for ch in d.sentence)
               for d in got.decisions), "Hebrew was asked for and not rendered"


def test_the_decisions_arrive_in_the_order_they_were_made():
    """The graph's ordinal IS the causal order — every edge points from a lower
    ordinal to a higher one, by construction. A section view sorted any other way
    would tell the story out of sequence."""
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "run1")
    ordinals = [d.ordinal for d in got.decisions]
    assert ordinals == sorted(ordinals)
    assert len(set(ordinals)) == len(ordinals), "a node is reported once"


def test_a_run_level_decision_belongs_to_its_section():
    """Not every decision names an element. The vertical mode and the run's own
    geometry are decided for the SECTION and carry `run_id` in their payload
    instead of a scope ref — and they are exactly the decisions a person asking
    about a section wants first."""
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "run1")
    actions = {d.action for d in got.decisions}
    assert "choose_vertical_mode" in actions
    assert "run_geometry" in actions


def test_the_other_section_does_not_leak_in():
    """The whole point of the view. Two runs, and asking about one must not
    return the other's bays."""
    topo, result = _corner()
    a = decisions_for_section(result.graph, result.strategy, topo, "runA")
    b = decisions_for_section(result.graph, result.strategy, topo, "runB")
    a_elements = {e for d in a.decisions for e in d.elements}
    b_elements = {e for d in b.decisions for e in d.elements}
    assert any("runA" in e for e in a_elements)
    assert not any("@runB" in e for e in a_elements)
    assert not any("@runA" in e for e in b_elements)


def test_a_shared_corner_post_is_reported_to_BOTH_sections():
    """A corner post stands on both runs and is decided once. Reporting it to
    one section would leave the other's story with a post that appeared from
    nowhere — the same fact the setting-out sheet states by tagging it once and
    cross-referencing it from the other section."""
    topo, result = _corner()
    a = decisions_for_section(result.graph, result.strategy, topo, "runA")
    b = decisions_for_section(result.graph, result.strategy, topo, "runB")
    shared = "post@node:n2"
    assert any(shared in d.elements for d in a.decisions)
    assert any(shared in d.elements for d in b.decisions)


def test_a_run_level_decision_of_another_section_does_not_leak_in():
    """Element leakage is the visible half; this is the invisible one. A
    run-level node carries NO elements, so the other section's vertical mode or
    geometry slipping in would show up in no `elements` list at all — and it is
    exactly what the broadest attribution rule in the file could get wrong."""
    topo, result = _corner()
    a = decisions_for_section(result.graph, result.strategy, topo, "runA")
    assert not any(result.graph.node(d.node_id).payload.get("run_id") == "runB"
                   for d in a.decisions)
    b = decisions_for_section(result.graph, result.strategy, topo, "runB")
    shared = {d.node_id for d in a.decisions} & {d.node_id for d in b.decisions}
    # exactly the corner they meet at: the topology fact for node n2, the post
    # standing on it, and the check that measured that post. Anything else
    # shared is a leak.
    assert {result.graph.node(n).action for n in shared} == {
        "topology_node", "place_post", "resolve_post_embedment"}
    assert all(result.graph.node(n).payload.get("node_id") in (None, "n2")
               for n in shared), "only the node they actually share"


def test_an_element_of_another_section_is_not_listed_on_a_shared_decision():
    """A decision reported to a section lists the elements of THAT section: a
    node post's decision reaches both, and neither is told it owns the other's."""
    topo, result = _corner()
    a = decisions_for_section(result.graph, result.strategy, topo, "runA")
    for d in a.decisions:
        assert not any("@runB" in e for e in d.elements)


def test_a_decision_names_the_rule_that_governed_it():
    """`governed_by` was computed by this view and asserted by nothing — blanking
    both edge lists left every test green while the reader lost which rule
    decided the layout. The decision graph IS the explanation (foundation §15),
    and a rule reference is the load-bearing half of it."""
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "run1")
    layout = next(d for d in got.decisions if d.action == "layout_spans")
    assert "K-MAXSPAN" in " ".join(layout.governed_by)
    assert any(d.governed_by for d in got.decisions if d.action == "place_post")


def test_a_defeated_version_is_named_where_it_lost():
    """A `defeated` edge cites the LOSING version (CLAUDE.md), and no fixture in
    the suite produced one — the field was structurally dead. A soft maximum
    that loses to the hard one is exactly the case a reader needs to see, or the
    graph reports a choice with no rival."""
    from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
    kb = demo_knowledge()
    soft = KnowledgeVersion(
        object_id="K-SOFT-MAX", version=1, type="preference",
        actions=[SetParam(param="max_span_mm", value=2000)],
        title="prefer shorter spans", scope={},
    )
    topo = straight_topology(5000)
    result = generate(topo, KnowledgeBase(versions=[*kb.versions, soft]),
                      demo_catalog(), parts=PARTS)
    got = decisions_for_section(result.graph, result.strategy, topo, "run1")
    beaten = [d for d in got.decisions if d.defeated]
    assert beaten, "nothing lost, so this fixture proves nothing about defeat"
    assert any("K-SOFT-MAX" in " ".join(d.defeated) for d in beaten)


def test_the_reader_gets_their_own_display_unit():
    """Hardcoding mm left every test green while half the sentences carried the
    wrong number for a reader working in cm. The same two rules `units.js`
    follows, applied to server-rendered prose."""
    topo, result = _straight()
    mm = decisions_for_section(result.graph, result.strategy, topo, "run1")
    cm = decisions_for_section(result.graph, result.strategy, topo, "run1",
                               units="cm")
    assert [d.node_id for d in mm.decisions] == [d.node_id for d in cm.decisions]
    assert [d.sentence for d in mm.decisions] != [d.sentence for d in cm.decisions]
    assert any("6000 mm" in d.sentence for d in mm.decisions)
    assert any("600 cm" in d.sentence for d in cm.decisions)


def test_the_order_is_the_ORDINAL_not_the_order_they_are_stored_in():
    """`graph.nodes` happens to be appended in ordinal order, so asserting the
    result is sorted proved nothing — insertion order passes it too. Shuffling
    the stored list is what tells the two apart."""
    import random
    topo, result = _straight()
    straight = decisions_for_section(result.graph, result.strategy, topo, "run1")
    shuffled = result.graph.model_copy(deep=True)
    random.Random(0).shuffle(shuffled.nodes)
    assert [d.node_id for d in
            decisions_for_section(shuffled, result.strategy, topo, "run1").decisions] \
        == [d.node_id for d in straight.decisions]


def test_a_knowledge_object_is_a_source_and_not_a_step():
    """It is already named on every decision it governed. Listing it again would
    put "K-MAXSPAN exists" in the story of every section that obeyed it."""
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "run1")
    # `knowledge_version` is the ACTION; the kind is `input_fact` like any other
    # materialised evidence. Checking the kind was checking nothing.
    assert any(n.action == "knowledge_version" for n in result.graph.nodes), \
        "the graph has no knowledge sources, so this proves nothing"
    assert "knowledge_version" not in {d.action for d in got.decisions}


def test_a_project_wide_choice_belongs_to_no_section():
    """`resolve_demand_products` picks the company's default rail, screw,
    concrete and cap ONCE for every run. Reporting it per section would present
    one choice as several, each looking like a decision made about that stretch."""
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "run1")
    assert "resolve_demand_products" not in {d.action for d in got.decisions}
    assert any(n.action == "resolve_demand_products" for n in result.graph.nodes)


def test_a_section_nobody_drew_has_no_decisions_rather_than_an_error():
    topo, result = _straight()
    got = decisions_for_section(result.graph, result.strategy, topo, "runZ")
    assert got.section_id == "runZ"
    assert got.decisions == []


def test_the_view_is_pure_and_never_mutates_the_graph():
    """Reading an explanation must not change one. The same rule
    `decisions/supply.py` follows for the node it derives at read time."""
    topo, result = _straight()
    before = result.graph.model_dump_json()
    decisions_for_section(result.graph, result.strategy, topo, "run1")
    decisions_for_section(result.graph, result.strategy, topo, "run1", lang="he")
    assert result.graph.model_dump_json() == before
