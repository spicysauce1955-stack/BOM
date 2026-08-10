"""S14-Hebrew: the stub interpreter understands the Hebrew demo vocabulary offline
(UI v2 §4). Capped — mirrors the English demo set only; verbatim Hebrew preserved.
"""

from __future__ import annotations

from fenceai.ai.stub import StubInterpreter
from fenceai.project.intents import confirm_intent
from fenceai.project.model import Annotation, Project
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _interpret(text: str):
    ann = Annotation(id="ann1", target_ref="run:run1", text=text)
    return StubInterpreter().interpret(ann)


def test_s14_hebrew_annotation_offline(knowledge, catalog):
    topo = straight_topology(3000)
    project = Project(id="p1", name="demo", topology=topo)
    ann = Annotation(id="ann1", target_ref="run:run1",
                     text="ליישר את החלק העליון עם הגדר של השכן (בערך 1750)")
    project.annotations.append(ann)
    rec = StubInterpreter().interpret(ann)
    ann.interpretations.append(rec)
    intent = rec.candidates[0]
    assert intent.kind == "top_line"
    assert intent.params == {"mode": "level", "z_mm": 1750}
    assert intent.confidence == "medium"          # בערך = hedging
    assert intent.source_text == ann.text          # verbatim Hebrew
    confirm_intent(project, "ann1", intent.id, "run1")
    after = generate(project.topology, knowledge, catalog)
    assert all(sp.height_mm == 1750 for sp in after.strategy.spans)


def test_hebrew_height_intent():
    rec = _interpret('גובה 1500 מ"מ בבקשה')
    intent = rec.candidates[0]
    assert intent.kind == "height_intent"
    assert intent.params == {"height_mm": 1500}
    assert intent.confidence == "high"  # no hedging


def test_hebrew_height_intent_hedged():
    rec = _interpret("גובה בסביבות 1600")
    intent = rec.candidates[0]
    assert intent.kind == "height_intent"
    assert intent.params == {"height_mm": 1600}
    assert intent.confidence == "medium"  # בסביבות = hedging
    assert intent.ambiguity_note


def test_hebrew_privacy_maps_to_default_height():
    rec = _interpret("חשוב לנו שתהיה פרטיות מהשכנים")
    intent = rec.candidates[0]
    assert intent.kind == "height_intent"
    assert intent.params == {"height_mm": 1800}
    assert intent.confidence == "low"


def test_hebrew_post_request():
    rec = _interpret("צריך עמוד בתחנה 1200")
    intent = rec.candidates[0]
    assert intent.kind == "post_request"
    assert intent.params == {"station_mm": 1200}
    assert intent.confidence == "medium"

    rec2 = _interpret("שים עמוד כאן")
    intent2 = rec2.candidates[0]
    assert intent2.kind == "post_request"
    assert intent2.params == {}
    assert intent2.confidence == "low"


def test_unknown_hebrew_text_surfaced_not_dropped():
    rec = _interpret("שהגדר תיראה יפה")
    assert rec.candidates == []
    assert rec.unparsed_spans == ["שהגדר תיראה יפה"]
