"""Knowledge objects: typed, scoped, versioned (ADR-0005/0006, knowledge-system.md)."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.core.units import Mm
from fenceai.knowledge.ast import Expr

KnowledgeType = Literal[
    "fact", "hard_constraint", "company_rule", "preference", "heuristic", "override", "candidate"
]

# Lower tier = higher authority (knowledge-system.md).
DEFAULT_AUTHORITY: dict[str, int] = {
    "hard_constraint": 1,
    "override": 2,
    "company_rule": 3,
    "fact": 3,  # facts are inputs, not rules; tier used only if two facts collide
    "preference": 4,
    "heuristic": 5,
    "candidate": 99,  # never evaluated while proposed
}


# --- typed actions ---------------------------------------------------------

class SetParam(BaseModel):
    kind: Literal["set_param"] = "set_param"
    param: str  # e.g. "max_span_mm", "screws_per_span", "rails_per_span"
    value: int


class RequireMounting(BaseModel):
    kind: Literal["require_mounting"] = "require_mounting"
    surface: str  # base surface this applies to
    mounting: Literal["ground", "masonry"]
    sku: str | None = None


class RequirePostReinforcement(BaseModel):
    kind: Literal["require_post_reinforcement"] = "require_post_reinforcement"
    context: Literal["gate"]
    sku: str | None = None


class PreferEqualSpans(BaseModel):
    kind: Literal["prefer_equal_spans"] = "prefer_equal_spans"
    weight: int = 1


class PreferMinSpanWidth(BaseModel):
    kind: Literal["prefer_min_span_width"] = "prefer_min_span_width"
    min_mm: Mm
    weight: int = 1


class PreferSpanWidth(BaseModel):
    kind: Literal["prefer_span_width"] = "prefer_span_width"
    width_mm: Mm
    weight: int = 1


class PreferVertical(BaseModel):
    kind: Literal["prefer_vertical"] = "prefer_vertical"
    mode: Literal["level", "stepped", "raked"]
    weight: int = 1


class DefaultComponent(BaseModel):
    """Default product selection for a role — selection is knowledge, never a code
    literal (architecture-critic finding 4)."""

    kind: Literal["default_component"] = "default_component"
    role: str  # "post_ground" | "post_masonry" | "post_reinforced" | ...
    sku: str


class AddNote(BaseModel):
    kind: Literal["add_note"] = "add_note"
    text: str


class FlagForReview(BaseModel):
    kind: Literal["flag_for_review"] = "flag_for_review"
    reason: str


Action = Annotated[
    Union[
        SetParam,
        RequireMounting,
        RequirePostReinforcement,
        PreferEqualSpans,
        PreferMinSpanWidth,
        PreferSpanWidth,
        PreferVertical,
        DefaultComponent,
        AddNote,
        FlagForReview,
    ],
    Field(discriminator="kind"),
]


class RuleExample(BaseModel):
    """Executable example/counterexample stored on the version (knowledge-system.md)."""

    description: str
    ctx: dict
    expect_applicable: bool


class KnowledgeVersion(BaseModel):
    object_id: str
    version: int
    type: KnowledgeType
    authority: int | None = None  # explicit override of DEFAULT_AUTHORITY
    scope: dict[str, str] = {}  # bound dimensions: project_id, series, surface, context...
    condition: Expr | None = None
    actions: list[Action] = []
    title: str = ""
    source_text: str | None = None  # verbatim human words, immutable
    derived_from: list[str] = []  # version refs / correction ids / interpretation ids
    attributed_to: str = "system"
    created_at: str = ""
    status: Literal["draft", "active", "retired", "proposed", "rejected"] = "active"
    overrides_objects: list[str] = []  # explicit superiority links
    examples: list[RuleExample] = []

    @property
    def ref(self) -> str:
        return f"{self.object_id}@v{self.version}"

    def effective_authority(self) -> int:
        return self.authority if self.authority is not None else DEFAULT_AUTHORITY[self.type]

    def specificity(self) -> int:
        return len(self.scope)


class KnowledgeBase(BaseModel):
    """The active snapshot handed to a generation run."""

    versions: list[KnowledgeVersion] = []

    def active(self) -> list[KnowledgeVersion]:
        return [v for v in self.versions if v.status == "active"]

    def snapshot_set(self) -> list[tuple[str, int]]:
        return sorted((v.object_id, v.version) for v in self.active())

    def snapshot_hash(self) -> str:
        payload = json.dumps(self.snapshot_set()).encode()
        return hashlib.sha256(payload).hexdigest()[:16]
