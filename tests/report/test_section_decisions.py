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


def test_an_element_of_another_section_is_not_listed_on_a_shared_decision():
    """A decision reported to a section lists the elements of THAT section: a
    node post's decision reaches both, and neither is told it owns the other's."""
    topo, result = _corner()
    a = decisions_for_section(result.graph, result.strategy, topo, "runA")
    for d in a.decisions:
        assert not any("@runB" in e for e in d.elements)


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
