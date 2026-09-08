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
    # `knowledge_version` is the one node whose payload IS its content — a
    # knowledge ref, printed verbatim. The other three input facts used to be
    # here too, rendering their raw payload dict; the section view puts them at
    # the top of what a person reads, so they became sentences and this test
    # says the stronger thing about them.
    embeds_its_payload = {"knowledge_version"}
    for node in result.graph.nodes:
        en = explain_node(result.graph, node, lang="en")
        he = explain_node(result.graph, node, lang="he")
        assert en and he
        if node.action in embeds_its_payload:
            assert node.action in en and node.action in he
        else:
            assert "{" not in en and "{" not in he, (node.action, en, he)
            # a raw payload DICT specifically; prose legitimately quotes a value
            # ("Vertical mode 'level' chosen"), so the marker is `{'`
            assert "{'" not in en and "{'" not in he, (node.action, en, he)


def test_template_key_parity():
    """A key present in one language but not the other is a live KeyError waiting
    in the /explain endpoint (test-review finding 1a)."""
    from fenceai.decisions.explain import TEMPLATES

    assert set(TEMPLATES["en"]) == set(TEMPLATES["he"])


def _corroborating_knowledge():
    """Demo knowledge plus a SECOND manufacturer sheet stating the same 1800 mm.

    Two `hard_constraint` rows, same authority, same (empty) scope, different
    object ids and the same value: neither `_beats` the other and their values
    agree, which is the one shape that reaches `evaluator.py`'s `values_agree`
    branch — the loser was never beaten, it independently said the same thing.
    """
    from fenceai.knowledge.model import KnowledgeVersion, SetParam

    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-MAXSPAN-B", version=1, type="hard_constraint",
        title="Second manufacturer sheet, same 1800 mm max span",
        title_i18n={"he": 'גיליון יצרן שני, אותו מפתח מרבי 1800 מ"מ'},
        actions=[SetParam(param="max_span_mm", value=1800)],
        attributed_to="manufacturer",
    ))
    return kb


def _branch_fixtures():
    """Graphs that exercise the template branches the demo graph never reaches:
    sliver_span, knowledge_conflict, node_surface_disagreement, wall/step span
    fragments, defeated edges, and the `corroborated` edge two agreeing sources
    draw (test-review finding 1b)."""
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

    # corroborated edges (two sources state the same maximum span)
    yield pytest.param(generate(straight_topology(5000), _corroborating_knowledge(), catalog),
                       "resolve_max_span", id="corroborated")


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


def test_corroborated_edge_is_drawn_and_reads_as_agreement_not_defeat():
    """Two sources stating the same limit is agreement, and the graph has to say
    so: a `corroborated` edge, no `defeated` edge anywhere, and a sentence that
    credits the second source rather than reporting a contest it lost.

    The `defeated`/`corroborated` distinction was untestable from the evaluator
    alone — `Firing.corroborated_by` is the cheap half. Forcing both
    `corroborated=[...]` arguments in `strategy/generator.py` to `[]` left the
    whole suite green, so the `EdgeType` member, the edge-drawing branch in
    `decisions/graph.py` and both `_corroborated` templates were dead. This is
    the test that dies with them.
    """
    result = generate(straight_topology(5000), _corroborating_knowledge(), demo_catalog())
    firing = next(n for n in result.graph.nodes if n.action == "resolve_max_span")
    in_edges = result.graph.in_edges(firing.id)
    assert [e.knowledge_ref for e in in_edges if e.type == "corroborated"] == ["K-MAXSPAN-B@v1"]
    assert [e.knowledge_ref for e in in_edges if e.type == "governed_by"] == ["K-MAXSPAN@v1"]
    # nothing here was beaten — not on this node, and not anywhere in the graph
    assert not any(e.type == "defeated" for e in result.graph.edges)
    assert not result.strategy.warnings  # ...and agreement is not a conflict

    en = explain_node(result.graph, firing, lang="en")
    he = explain_node(result.graph, firing, lang="he")
    assert "Corroborated by K-MAXSPAN-B@v1" in en
    assert "מאושש על ידי" in he and "K-MAXSPAN-B@v1" in he  # ref verbatim in Hebrew
    assert "Defeated" not in en and "גבר על" not in he


def test_rows_that_state_the_winners_value_exactly_are_never_defeated():
    """Agreement is a PAIRWISE fact, and it used to be measured as a set.

    `resolve_param` computed `same_value = len({a.effective_milli() ...}) <= 1`
    over every relevant firing and passed it to `resolve` as one boolean, which
    then decided corroborate-vs-defeat for EVERY pair. Add one dissenting sheet
    to four that state exactly the same limit and the flag went false for all of
    them: the rows byte-identical to the winner each got `defeated_by`, a
    `defeated` edge and a `hard=True` conflict — "K-SHEET-B was defeated by
    K-MAXSPAN", about two rows stating the same 1800 mm. That is a claim about
    the sources which is false, and it is exactly the failure the `corroborated`
    edge was added to stop; the same graph then carried error warnings, shipped
    to the publisher as review tasks, for a contest that never happened.

    `resolve` now asks its `stated` reader per pair, against the current winner,
    so only the row that really dissented loses.
    """
    from fenceai.knowledge.model import KnowledgeVersion, SetParam

    def published(object_id: str, value: int) -> KnowledgeVersion:
        return KnowledgeVersion.from_published(
            object_id=object_id, version=1, type="hard_constraint",
            actions=[SetParam(param="max_span_mm", value=value)])

    kb = demo_knowledge()  # K-MAXSPAN@v1 states 1800 and wins the tie-break
    kb.versions += [published("K-SHEET-B", 1800),   # says exactly what the winner says
                    published("K-SHEET-C", 1800),   # ...so does this one
                    published("K-SHEET-D", 1500)]   # the only real dissenter
    result = generate(straight_topology(5000), kb, demo_catalog())
    firing = next(n for n in result.graph.nodes if n.action == "resolve_max_span")
    edges = {e.knowledge_ref: e.type for e in result.graph.in_edges(firing.id)}
    assert edges["K-SHEET-B@v1"] == "corroborated"
    assert edges["K-SHEET-C@v1"] == "corroborated"
    assert edges["K-SHEET-D@v1"] == "defeated"  # this one really did lose
    contested = {ref for w in result.strategy.warnings if w.code == "knowledge_conflict"
                 for ref in w.params["contenders"].split(", ")}
    assert "K-SHEET-B@v1" not in contested and "K-SHEET-C@v1" not in contested


def test_pinned_suffix_localizes():
    knowledge, catalog = demo_knowledge(), demo_catalog()
    ov = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=1000))
    result = generate(straight_topology(6000), knowledge, catalog, overrides=[ov])
    pinned = next(n for n in result.graph.nodes if n.status == "pinned")
    assert "pinned by a user override" in explain_node(result.graph, pinned, lang="en")
    assert "ננעצה" in explain_node(result.graph, pinned, lang="he")


def test_explanations_render_in_the_readers_unit():
    """Same graph, same structure — only the rendered unit changes. The graph
    itself keeps int mm (ADR-0002); `units` is a display choice, like `lang`."""
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(6000), knowledge, catalog)
    post = next(p for p in result.strategy.posts if p.station_mm)
    mm = explain_element(result.graph, post.id, lang="en")
    cm = explain_element(result.graph, post.id, lang="en", units="cm")
    assert len(mm) == len(cm)
    assert any(f"station {post.station_mm} mm" in line for line in mm)
    assert any(f"station {post.station_mm // 10} cm" in line for line in cm)
    assert not any(" mm" in line for line in cm)


def test_centimetre_rendering_keeps_one_decimal_without_float_noise():
    from fenceai.decisions.explain import _display

    assert _display(1234, "cm") == 123.4
    assert _display(1200, "cm") == 120 and str(_display(1200, "cm")) == "120"
    assert _display(5, "cm") == 0.5
    assert _display(1234, "mm") == 1234
    assert _display("POST-S", "cm") == "POST-S"  # non-numeric params pass through


def test_hebrew_prose_uses_hebrew_enum_words():
    """A Hebrew sentence must not carry raw English enum values (post kind,
    mounting, base surface) — only ids/SKUs/refs stay Latin."""
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(6000), knowledge, catalog)
    post = next(p for p in result.strategy.posts if p.kind == "line")
    he = explain_node(
        result.graph,
        next(n for n in result.graph.nodes_for_element(post.id) if n.action == "place_post"),
        lang="he",
    )
    assert "שורה" in he and "קרקע" in he
    assert "line" not in he and "soil" not in he
    assert "POST-S" in he  # SKU still verbatim


def test_every_enum_value_has_a_hebrew_word():
    """Any Literal the domain can produce must have a Hebrew word, or Hebrew
    prose silently falls back to the English enum name."""
    from typing import get_args

    from fenceai.decisions.explain import _ENUM_WORDS
    from fenceai.fencemodel.model import FrameSlot
    from fenceai.strategy.model import Post, Span
    from fenceai.topology.model import BasePayload, PostTiltPayload, TopLinePayload

    values = set()
    for model, field in [(Post, "kind"), (Post, "mounting"), (Span, "vertical"),
                         (BasePayload, "surface"), (PostTiltPayload, "mode"),
                         (TopLinePayload, "mode"),
                         # the authored continuity assertion is quoted INSIDE the
                         # `continuity_override_disagrees` sentence, so its values
                         # are words a Hebrew reader reads, not ids
                         (FrameSlot, "continuity")]:
        values |= set(get_args(model.model_fields[field].annotation))
    missing = sorted(v for v in values if v not in _ENUM_WORDS["he"])
    assert not missing, missing
