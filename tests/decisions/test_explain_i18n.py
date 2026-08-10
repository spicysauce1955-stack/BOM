"""Explanations render from per-language template tables (UI v2 §4).

Same decision graph, same structure — only the language changes. Knowledge refs
and SKUs stay verbatim (Latin) inside Hebrew sentences.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.decisions.explain import explain_element, explain_node
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import Override, PinPost
from fenceai.topology.model import GatePayload
from tests.conftest import add_point_event, straight_topology


def test_explanations_localize():
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(6000), knowledge, catalog)
    post_id = result.strategy.posts[0].id
    en = explain_element(result.graph, post_id, lang="en")
    he = explain_element(result.graph, post_id, lang="he")
    assert any("Post at station" in l for l in en)
    assert any("עמוד בתחנה" in l for l in he)
    assert any("POST-S" in l for l in he)  # SKUs verbatim inside Hebrew
    assert len(en) == len(he)              # same structure, different language


def test_english_default_matches_previous_output():
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(6000), knowledge, catalog)
    span_id = result.strategy.spans[0].id
    lines = explain_element(result.graph, span_id)  # no lang -> en
    assert lines == explain_element(result.graph, span_id, lang="en")
    assert any("Span of" in l for l in lines)
    assert any("Governed by K-MAXSPAN@v1" in l for l in lines)


def test_every_graph_node_has_hebrew_and_english_templates():
    """Every action the demo graph produces renders in both languages with no
    raw '{' left over (all placeholders resolved) and refs verbatim."""
    knowledge, catalog = demo_knowledge(), demo_catalog()
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "ev_gate", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    ov = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=1000))
    result = generate(topo, knowledge, catalog, overrides=[ov])
    input_facts = {"topology_node", "run_geometry", "gate_event", "knowledge_version"}
    for node in result.graph.nodes:
        en = explain_node(result.graph, node, lang="en")
        he = explain_node(result.graph, node, lang="he")
        assert en and he
        if node.action in input_facts:  # these embed the raw payload dict verbatim
            assert node.action in en and node.action in he
        else:
            assert "{" not in en and "{" not in he, (node.action, en, he)


def test_pinned_suffix_localizes():
    knowledge, catalog = demo_knowledge(), demo_catalog()
    ov = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=1000))
    result = generate(straight_topology(6000), knowledge, catalog, overrides=[ov])
    pinned = next(n for n in result.graph.nodes if n.status == "pinned")
    assert "pinned by a user override" in explain_node(result.graph, pinned, lang="en")
    assert "ננעצה" in explain_node(result.graph, pinned, lang="he")
