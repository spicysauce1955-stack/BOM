"""Golden scenarios S06, S13, S14 (docs/scenarios/golden-scenarios.md)."""

from __future__ import annotations

from fenceai.ai.stub import StubInterpreter
from fenceai.knowledge.model import KnowledgeVersion, PreferSpanWidth
from fenceai.project.intents import confirm_intent
from fenceai.project.model import Annotation, Project
from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    BasePayload,
    HeightIntentPayload,
    WallProfilePayload,
)
from tests.conftest import add_interval_event, straight_topology


def test_s06_wall_profile_varies_span_heights(knowledge, catalog):
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "ev_base", 0, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(
        topo, "run1", "ev_wall", 0, 6000, WallProfilePayload(top_z_start_mm=0, top_z_end_mm=400)
    )
    add_interval_event(topo, "run1", "ev_height", 0, 6000, HeightIntentPayload(height_mm=1800))
    result = generate(topo, knowledge, catalog)
    s = result.strategy

    # wall top rises 0->400; privacy intent 1800 => panel heights shrink as wall grows
    assert [sp.height_mm for sp in s.spans] == [1750, 1650, 1550, 1450]
    assert all(p.sku == "POST-M" for p in s.posts)

    span_decisions = [n for n in result.graph.nodes if n.action == "create_span"]
    for d in span_decisions:
        assert d.payload["height_source"] == "ev_height"  # cites the intent event
        assert d.payload["adjusted_by_wall_profile"] == "ev_wall"  # and the wall profile


def test_s13_conflicting_preferences_surfaced_hard_constraint_respected(knowledge, catalog):
    knowledge.versions.append(
        KnowledgeVersion(
            object_id="K-1800", version=1, type="preference",
            title="Spans exactly 1800 for series X",
            actions=[PreferSpanWidth(width_mm=1800)],
        )
    )
    result = generate(straight_topology(5000), knowledge, catalog)
    s = result.strategy

    # hard constraint never violated
    assert all(sp.width_mm <= 1800 for sp in s.spans)
    # the tie between K-EQUAL and K-1800 is surfaced, not silently resolved
    conflict = next(w for w in s.warnings if w.code == "knowledge_conflict")
    assert "K-1800@v1" in conflict.message and "K-EQUAL@v1" in conflict.message
    conflict_node = result.graph.node(conflict.decision_ref)
    assert set(conflict_node.payload["contenders"]) == {"K-1800@v1", "K-EQUAL@v1"}

    # deterministic winner applied; loser's layout recorded as the alternative
    assert [sp.width_mm for sp in s.spans] == [1800, 1800, 1400]
    layout = next(n for n in result.graph.nodes if n.action == "layout_spans")
    assert layout.payload["alternatives"][0]["widths"] == [1667, 1667, 1666]


def test_s14_annotation_to_confirmed_intent(knowledge, catalog):
    topo = straight_topology(3000)
    project = Project(id="p1", name="demo", topology=topo)
    annotation = Annotation(
        id="ann1", target_ref="run:run1",
        text="keep the top aligned with the neighbour's fence (approx. 1750)",
    )
    project.annotations.append(annotation)

    record = StubInterpreter().interpret(annotation)
    annotation.interpretations.append(record)

    # proposal shape: verbatim text, enum confidence, proposed status
    assert len(record.candidates) == 1
    intent = record.candidates[0]
    assert intent.kind == "top_line"
    assert intent.params == {"mode": "level", "z_mm": 1750}
    assert intent.source_text == annotation.text  # verbatim
    assert intent.confidence == "medium"  # "approx" hedging
    assert intent.status == "proposed"

    # unconfirmed intents change nothing
    before = generate(project.topology, knowledge, catalog)
    assert all(sp.height_mm == 1800 for sp in before.strategy.spans)

    # confirmation materializes a first-class event with provenance
    event_id = confirm_intent(project, "ann1", intent.id, "run1", confirmed_by="expert-jane")
    assert intent.status == "confirmed"
    assert intent.confirmed_by == "expert-jane"
    event = next(e for e in topo.run("run1").interval_events if e.id == event_id)
    assert event.payload.kind == "top_line"
    assert event.payload.source == record.id  # chains back to interpretation + annotation

    after = generate(project.topology, knowledge, catalog)
    assert all(sp.height_mm == 1750 for sp in after.strategy.spans)
    span_decisions = [n for n in after.graph.nodes if n.action == "create_span"]
    assert all(d.payload["height_source"] == event_id for d in span_decisions)

    # original text still immutable and verbatim
    assert project.annotations[0].text == "keep the top aligned with the neighbour's fence (approx. 1750)"


def test_s14_unknown_text_is_surfaced_not_dropped():
    annotation = Annotation(id="ann2", target_ref="project", text="der Zaun muss gut aussehen")
    record = StubInterpreter().interpret(annotation)
    assert record.candidates == []
    assert record.unparsed_spans == [annotation.text]
