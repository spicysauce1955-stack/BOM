"""AI interpretation records: proposals, never authority (ADR-0009).

Original text is preserved verbatim; every candidate carries the exact source span,
enum confidence, and a status gate — only `confirmed` intents ever affect generation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.units import Mm

IntentKind = Literal["height_intent", "top_line", "post_request", "material_preference", "other"]


class CandidateIntent(BaseModel):
    id: str
    kind: IntentKind
    params: dict[str, int | str] = {}
    source_text: str  # verbatim span from the annotation — never paraphrased
    confidence: Literal["high", "medium", "low"]
    ambiguity_note: str | None = None
    status: Literal["proposed", "confirmed", "rejected"] = "proposed"
    confirmed_by: str | None = None


class InterpretationRecord(BaseModel):
    id: str
    annotation_id: str
    interpreter: str  # "stub" | "claude:<model>"
    created_at: str = ""
    candidates: list[CandidateIntent] = []
    unparsed_spans: list[str] = []  # surfaced, never dropped


class CritiqueNote(BaseModel):
    element_refs: list[str] = []
    severity: Literal["info", "warning"] = "info"
    text: str  # English fallback; clients localize from code + params
    code: str = "generic"
    params: dict[str, str | int] = {}


class ProposedRule(BaseModel):
    """Wire model the KnowledgeProposer returns before it becomes a KnowledgeVersion."""

    title: str
    type: Literal["company_rule", "preference", "heuristic"]
    scope: dict[str, str] = {}
    condition_sketch: str  # human-readable; structured AST authored at review time
    rationale: str
    supporting_corrections: list[str] = []
    proposed_height_mm: Mm | None = None
