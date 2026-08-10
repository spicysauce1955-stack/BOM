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


def test_template_key_parity():
    """A key present in one language but not the other is a live KeyError waiting
    in the /explain endpoint (test-review finding 1a)."""
    from fenceai.decisions.explain import TEMPLATES

    assert set(TEMPLATES["en"]) == set(TEMPLATES["he"])


def _branch_fixtures():
    """Graphs that exercise the template branches the demo graph never reaches:
    sliver_span, knowledge_conflict, node_surface_disagreement, wall/step span
    fragments, and defeated edges (test-review finding 1b)."""
    import pytest

    from fenceai.knowledge.model import KnowledgeVersion, PreferSpanWidth, SetParam
    from fenceai.topology.model import (
        BasePayload, ElevationSamplePayload, HeightIntentPayload, Node, Run,
        Topology, WallProfilePayload,
    )
    from tests.conftest import add_interval_event

    catalog = demo_catalog()

    # sliver_span
    yield pytest.param(
        generate(straight_topology(400), demo_knowledge(), catalog), "sliver_span", id="sliver")

    # knowledge_conflict (K-EQUAL vs K-1800 tie) + defeated edges (soft max_span loses)
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-1800", version=1, type="preference",
        actions=[PreferSpanWidth(width_mm=1800)]))
    kb.versions.append(KnowledgeVersion(
        object_id="K-SOFT-MAX", version=1, type="preference",
        actions=[SetParam(param="max_span_mm", value=2000)]))
    yield pytest.param(generate(straight_topology(5000), kb, catalog),
                       "knowledge_conflict", id="conflict-and-defeated")

    # node_surface_disagreement: two runs meet at n2 with different bases
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=4000, y_mm=0),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")])
    add_interval_event(topo, "runB", "b1", 0, 3000, BasePayload(surface="masonry_wall"))
    yield pytest.param(generate(topo, demo_knowledge(), catalog),
                       "node_surface_disagreement", id="surface-disagreement")

    # wall-adjusted span heights (create_span wall fragment)
    wall = straight_topology(6000)
    add_interval_event(wall, "run1", "wb", 0, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(wall, "run1", "wp", 0, 6000,
                       WallProfilePayload(top_z_start_mm=0, top_z_end_mm=400))
    add_interval_event(wall, "run1", "hi", 0, 6000, HeightIntentPayload(height_mm=1800))
    yield pytest.param(generate(wall, demo_knowledge(), catalog), "create_span", id="wall-span")

    # stepped span heights (create_span step fragment)
    slope = straight_topology(6000)
    add_point_event(slope, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(slope, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))
    yield pytest.param(generate(slope, demo_knowledge(), catalog), "create_span", id="stepped-span")


import pytest  # noqa: E402


@pytest.mark.parametrize("result,expected_action", list(_branch_fixtures()))
@pytest.mark.parametrize("lang", ["en", "he"])
def test_rare_template_branches_render(result, expected_action, lang):
    input_facts = {"topology_node", "run_geometry", "gate_event", "knowledge_version"}
    assert any(n.action == expected_action for n in result.graph.nodes)
    for node in result.graph.nodes:
        line = explain_node(result.graph, node, lang=lang)
        assert line, (node.action, lang)
        if node.action not in input_facts:
            assert "{" not in line, (node.action, lang, line)


def test_defeated_suffix_renders_in_both_languages():
    from fenceai.knowledge.model import KnowledgeVersion, SetParam

    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-SOFT-MAX", version=1, type="preference",
        actions=[SetParam(param="max_span_mm", value=2000)]))
    result = generate(straight_topology(5000), kb, demo_catalog())
    firing = next(n for n in result.graph.nodes if n.action == "resolve_max_span")
    assert any(e.type == "defeated" for e in result.graph.in_edges(firing.id))
    assert "K-SOFT-MAX@v1" in explain_node(result.graph, firing, lang="en")
    assert "K-SOFT-MAX@v1" in explain_node(result.graph, firing, lang="he")


def test_pinned_suffix_localizes():
    knowledge, catalog = demo_knowledge(), demo_catalog()
    ov = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=1000))
    result = generate(straight_topology(6000), knowledge, catalog, overrides=[ov])
    pinned = next(n for n in result.graph.nodes if n.status == "pinned")
    assert "pinned by a user override" in explain_node(result.graph, pinned, lang="en")
    assert "ננעצה" in explain_node(result.graph, pinned, lang="he")
