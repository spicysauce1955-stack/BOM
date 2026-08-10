"""Warnings and critiques carry code + params for client-side localization (UI v2 §4/§6).

`params` is additive: the English `message`/`text` stays as the fallback.
"""

from __future__ import annotations

from fenceai.ai.stub import StubCritic
from fenceai.knowledge.model import KnowledgeVersion, PreferSpanWidth
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import Override, PinPost
from fenceai.topology.model import BasePayload, GatePayload, Node, Run, Topology
from tests.conftest import add_interval_event, add_point_event, straight_topology


def test_warnings_carry_codes_and_params(knowledge, catalog):
    ov = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=99999))
    result = generate(straight_topology(6000), knowledge, catalog, overrides=[ov])
    w = next(w for w in result.strategy.warnings if w.code == "orphaned_override")
    assert w.params["override_id"] == "ov1"
    r2 = generate(straight_topology(400), knowledge, catalog)
    s = next(w for w in r2.strategy.warnings if w.code == "sliver_span")
    assert s.params == {"span_id": "span@run1:0-400", "width_mm": 400, "min_mm": 500}


def test_orphaned_override_params_carry_directive(knowledge, catalog):
    ov = Override(id="ov1", run_id="run1", directive=PinPost(station_mm=99999))
    result = generate(straight_topology(6000), knowledge, catalog, overrides=[ov])
    w = next(w for w in result.strategy.warnings if w.code == "orphaned_override")
    assert w.params == {"override_id": "ov1", "directive": "pin_post"}
    assert "ov1" in w.message  # English fallback intact


def test_unknown_product_params_carry_sku(knowledge, catalog):
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "ev_gate", 2000, GatePayload(width_mm=1000, kit_sku="NO-SUCH-KIT"))
    result = generate(topo, knowledge, catalog)
    w = next(w for w in result.strategy.warnings if w.code == "unknown_product")
    assert w.params == {"sku": "NO-SUCH-KIT"}


def test_knowledge_conflict_params_carry_slot_and_contenders(knowledge, catalog):
    knowledge.versions.append(
        KnowledgeVersion(
            object_id="K-1800", version=1, type="preference",
            title="Spans exactly 1800",
            actions=[PreferSpanWidth(width_mm=1800)],
        )
    )
    result = generate(straight_topology(5000), knowledge, catalog)
    w = next(w for w in result.strategy.warnings if w.code == "knowledge_conflict")
    assert w.params["slot"] == "span_layout_preference"
    assert set(w.params["contenders"].split(", ")) == {"K-1800@v1", "K-EQUAL@v1"}


def test_node_surface_disagreement_params(knowledge, catalog):
    topo = Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=3000, y_mm=0),
            Node(id="n3", x_mm=3000, y_mm=3000),
        ],
        runs=[
            Run(id="run1", start_node_id="n1", end_node_id="n2"),
            Run(id="run2", start_node_id="n2", end_node_id="n3"),
        ],
    )
    add_interval_event(topo, "run2", "ev_base", 0, 3000, BasePayload(surface="masonry_wall"))
    result = generate(topo, knowledge, catalog)
    w = next(w for w in result.strategy.warnings if w.code == "node_surface_disagreement")
    assert w.params == {
        "node_id": "n2",
        "surfaces": "masonry_wall, soil",
        "chosen": "masonry_wall",
    }


def test_critique_notes_carry_code_and_params(knowledge, catalog):
    result = generate(straight_topology(400), knowledge, catalog)
    notes = StubCritic().critique(result)
    note = next(n for n in notes if n.code == "narrow_span")
    assert note.params == {"span_id": "span@run1:0-400", "width_mm": 400}
    assert "span@run1:0-400" in note.text  # English fallback intact
