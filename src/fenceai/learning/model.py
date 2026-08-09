"""Expert corrections and the knowledge-candidate review workflow (knowledge-system.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Correction(BaseModel):
    """Immutable capture of an expert changing a generated result, with context."""

    id: str
    project_id: str
    generation_run_id: str
    decision_ref: str | None = None
    element_ref: str | None = None
    before: dict = {}
    after: dict = {}
    comment: str | None = None  # verbatim, immutable
    author: str = "expert"
    created_at: str = ""


class ReviewAction(BaseModel):
    action: Literal["approve", "reject", "edit_approve", "scope_restrict"]
    reviewer: str
    reason: str | None = None
    edited_scope: dict[str, str] | None = None
    at: str = ""
