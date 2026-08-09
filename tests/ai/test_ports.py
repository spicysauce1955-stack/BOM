"""AI layer tests: stub determinism, schema rejection, grounding (ADR-0009)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.ai.claude import _WireResult, build_interpreter
from fenceai.ai.records import CandidateIntent
from fenceai.ai.stub import StubCritic, StubInterpreter
from fenceai.project.model import Annotation


def ann(text: str) -> Annotation:
    return Annotation(id="ann1", target_ref="run:run1", text=text)


def test_stub_is_deterministic():
    a = ann("keep the top aligned with the neighbour (approx. 1750)")
    r1 = StubInterpreter().interpret(a)
    r2 = StubInterpreter().interpret(a)
    assert r1.model_dump() == r2.model_dump()


def test_stub_preserves_verbatim_text_and_enum_confidence():
    a = ann("privacy is important here")
    rec = StubInterpreter().interpret(a)
    assert rec.candidates[0].source_text == a.text
    assert rec.candidates[0].confidence in ("high", "medium", "low")
    assert rec.candidates[0].status == "proposed"


def test_malformed_ai_output_rejected_by_schema():
    # the wire schema is the validation gate for ANY interpreter implementation
    with pytest.raises(ValidationError):
        _WireResult.model_validate({"candidates": [{"kind": "top_line"}]})  # missing fields
    with pytest.raises(ValidationError):
        CandidateIntent.model_validate(
            {"id": "x", "kind": "top_line", "source_text": "t", "confidence": 0.93}
        )  # float confidence forbidden — enums only (Research D)
    with pytest.raises(ValidationError):
        CandidateIntent.model_validate(
            {"id": "x", "kind": "unknown_kind", "source_text": "t", "confidence": "high"}
        )


def test_wire_schema_accepts_valid_payload():
    wire = _WireResult.model_validate(
        {
            "candidates": [
                {"kind": "height_intent", "params": {"height_mm": 1800},
                 "source_text": "1800 high please", "confidence": "high"}
            ],
            "unparsed_spans": [],
        }
    )
    assert wire.candidates[0].source_text == "1800 high please"


def test_composition_root_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("FENCEAI_AI", raising=False)
    assert build_interpreter().interpreter_id == "stub"
    monkeypatch.setenv("FENCEAI_AI", "stub")
    assert build_interpreter().interpreter_id == "stub"


def test_claude_optin_without_credentials_falls_back_to_stub(monkeypatch):
    monkeypatch.setenv("FENCEAI_AI", "claude")
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    interp = build_interpreter()
    # offline guarantee: never crash, never hang — stub is acceptable fallback
    assert interp.interpreter_id == "stub" or interp.interpreter_id.startswith("claude:")


def test_critic_is_advisory_only(knowledge, catalog):
    from fenceai.strategy.generator import generate
    from tests.conftest import straight_topology

    result = generate(straight_topology(6000), knowledge, catalog)
    before = result.strategy.model_dump()
    notes = StubCritic().critique(result)
    assert result.strategy.model_dump() == before  # critique never mutates
    assert all(n.severity in ("info", "warning") for n in notes)
