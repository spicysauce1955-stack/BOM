"""Claude adapter for the AI ports (ADR-0009).

Constructed only when FENCEAI_AI=claude and a client can be built; everything else
uses the stub. Structured output via Pydantic schemas; 2-attempt semantic retry;
provenance stamps the model id.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ValidationError

from fenceai.ai.records import CandidateIntent, InterpretationRecord
from fenceai.project.model import Annotation

DEFAULT_MODEL = "claude-opus-5"

_SYSTEM = """You interpret annotations on fence-construction projects into structured
candidate intents. Rules:
- source_text must be the VERBATIM span of the annotation that supports the intent.
- Text you cannot map to a known intent kind goes into unparsed_spans, never dropped.
- confidence is "high" only when the text is unambiguous and contains explicit values.
- You propose; humans confirm. Never invent values not present or clearly implied.
- Annotations may be in Hebrew; keep source_text verbatim in the original language."""


class _WireIntent(BaseModel):
    kind: str
    params: dict[str, int | str] = {}
    source_text: str
    confidence: str
    ambiguity_note: str | None = None


class _WireResult(BaseModel):
    candidates: list[_WireIntent] = []
    unparsed_spans: list[str] = []


class ClaudeInterpreter:
    def __init__(self, model: str = DEFAULT_MODEL):
        import anthropic  # deferred so offline installs never touch it

        self._client = anthropic.Anthropic()
        self.model = model
        self.interpreter_id = f"claude:{model}"

    def interpret(self, annotation: Annotation) -> InterpretationRecord:
        errors: str | None = None
        rec_no = len(annotation.interpretations) + 1
        for _attempt in range(2):
            wire = self._call(annotation.text, errors)
            try:
                candidates = [
                    CandidateIntent(
                        id=f"intent_{annotation.id}_{rec_no}_{i + 1}",
                        kind=c.kind,  # type: ignore[arg-type]
                        params=c.params,
                        source_text=c.source_text,
                        confidence=c.confidence,  # type: ignore[arg-type]
                        ambiguity_note=c.ambiguity_note,
                    )
                    for i, c in enumerate(wire.candidates)
                    if c.source_text in annotation.text  # ground: span must be verbatim
                ]
                return InterpretationRecord(
                    id=f"interp_{annotation.id}_{rec_no}",
                    annotation_id=annotation.id,
                    interpreter=self.interpreter_id,
                    candidates=candidates,
                    unparsed_spans=wire.unparsed_spans,
                )
            except ValidationError as e:
                errors = str(e)
        # degrade: needs human interpretation (Research D retry cap)
        return InterpretationRecord(
            id=f"interp_{annotation.id}_{rec_no}",
            annotation_id=annotation.id,
            interpreter=self.interpreter_id,
            candidates=[],
            unparsed_spans=[annotation.text],
        )

    def _call(self, text: str, prior_errors: str | None) -> _WireResult:
        user = f"Annotation text:\n{text}"
        if prior_errors:
            user += f"\n\nYour previous output failed validation:\n{prior_errors}\nEmit corrected output."
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_format=_WireResult,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValidationError.from_exception_data("empty", [])
        return parsed


def build_interpreter():
    """Composition-root selection: claude only on explicit opt-in + constructible client."""
    if os.environ.get("FENCEAI_AI", "stub").lower() == "claude":
        try:
            return ClaudeInterpreter(os.environ.get("FENCEAI_AI_MODEL", DEFAULT_MODEL))
        except Exception:
            pass  # fall through to stub — the system must work offline (ADR-0009)
    from fenceai.ai.stub import StubInterpreter

    return StubInterpreter()
