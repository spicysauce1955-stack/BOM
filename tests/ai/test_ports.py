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
                {"kind": "height_intent", "height_mm": 1800,
                 "source_text": "1800 high please", "confidence": "high"}
            ],
            "unparsed_spans": [],
        }
    )
    assert wire.candidates[0].source_text == "1800 high please"
    # typed wire fields fold into the domain params dict (structured outputs
    # forbid free-form dicts — additionalProperties:false)
    assert wire.candidates[0].to_params() == {"height_mm": 1800}
    top = _WireResult.model_validate(
        {"candidates": [{"kind": "top_line", "mode": "level", "z_mm": 1750,
                         "source_text": "x", "confidence": "medium"}]}
    )
    assert top.candidates[0].to_params() == {"z_mm": 1750, "mode": "level"}


def test_composition_root_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("FENCEAI_AI", raising=False)
    assert build_interpreter().interpreter_id == "stub"
    monkeypatch.setenv("FENCEAI_AI", "stub")
    assert build_interpreter().interpreter_id == "stub"


def test_claude_optin_without_credentials_falls_back_to_stub(monkeypatch):
    monkeypatch.setenv("FENCEAI_AI", "claude")
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        "anthropic.Anthropic",
        _raise_missing_key,
        raising=False,
    )
    # offline guarantee: with no constructible client the composition root must
    # land on the stub — exactly, not "either"
    assert build_interpreter().interpreter_id == "stub"


def _raise_missing_key(*args, **kwargs):
    raise RuntimeError("no credentials")


def test_reinterpretation_ids_never_collide():
    """Re-interpreting the same annotation must mint distinct intent ids so
    confirmation can never resolve to a stale record (final review, finding 3)."""
    a = ann("keep the top aligned with the neighbour (approx. 1750)")
    r1 = StubInterpreter().interpret(a)
    a.interpretations.append(r1)
    r2 = StubInterpreter().interpret(a)
    a.interpretations.append(r2)
    ids1 = {c.id for c in r1.candidates}
    ids2 = {c.id for c in r2.candidates}
    assert ids1 and ids2 and ids1.isdisjoint(ids2)
    assert r1.id != r2.id


def _correction(comment: str) -> "Correction":
    from fenceai.learning.model import Correction

    return Correction(id="c1", project_id="p1", generation_run_id="run1", comment=comment)


def test_proposer_reads_the_demo_vocabulary_in_hebrew_too():
    """The stub filtered on the literal English substring "foundation", so in a
    Hebrew-first product an expert's correction never became a candidate
    (persona-lab B1). CLAUDE.md: the stub understands the demo vocabulary in
    English AND Hebrew."""
    from fenceai.ai.stub import StubProposer

    he = StubProposer().propose([_correction("העמוד צריך לשבת על היסוד הקיים כאן")])
    en = StubProposer().propose([_correction("move the post onto the existing foundation")])
    assert len(he) == len(en) == 1
    assert he[0].status == "proposed" and he[0].type == "candidate"
    assert he[0].source_text == "העמוד צריך לשבת על היסוד הקיים כאן"  # verbatim
    assert he[0].display_title("he") != he[0].display_title("en")  # localized title


def test_an_approved_candidate_keeps_a_clean_title_in_both_languages():
    """Promotion drops the "(candidate)" marker — in every language the candidate
    carries one, or the Hebrew reader sees a live rule still labelled a proposal."""
    from fenceai.ai.stub import StubProposer
    from fenceai.learning.model import ReviewAction
    from fenceai.learning.review import apply_review

    candidate = StubProposer().propose([_correction("יש כאן יסוד קיים")])[0]
    approved = apply_review(candidate, ReviewAction(action="approve", reviewer="expert"))
    assert "(candidate)" not in approved.display_title("en")
    assert "מועמד" not in approved.display_title("he")
    assert approved.display_title("he") != approved.display_title("en")


def test_proposer_still_ignores_unrelated_corrections():
    from fenceai.ai.stub import StubProposer

    assert StubProposer().propose([_correction("הזזתי את המפתח קצת שמאלה")]) == []
    assert StubProposer().propose([_correction("moved the span a bit left")]) == []


def test_critic_is_advisory_only(knowledge, catalog):
    from fenceai.strategy.generator import generate
    from tests.conftest import straight_topology

    result = generate(straight_topology(6000), knowledge, catalog)
    before = result.strategy.model_dump()
    notes = StubCritic().critique(result)
    assert result.strategy.model_dump() == before  # critique never mutates
    assert all(n.severity in ("info", "warning") for n in notes)
