"""Knowledge objects: typed, scoped, versioned (ADR-0005/0006, knowledge-system.md)."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.core.units import Mm
from fenceai.knowledge.ast import Expr, field_paths
from fenceai.knowledge.source_policy import AdmittedBy

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


class SetToken(BaseModel):
    """A parameter whose value is a WORD from a closed set, not a number.

    `SetParam.value` is an `int`, so `slope_method = stepped_only` had nowhere to
    land — one of the five mechanisms the self-audit found specified and unbuilt.
    Coercing it into `SetParam` would mean an integer code for a word, which is
    the enum-in-disguise the contract refuses at the boundary: `not_rackable` is
    not an angle, it is a different parameter, and a table that mixed the two
    would make every consumer branch on the type of every cell.

    A separate action rather than a union-typed `value` on `SetParam`, because a
    resolver asking for a length and receiving a word should not typecheck. The
    two never compete: a table declares `value_type` ONCE, so a parameter is a
    quantity or a token for the whole table and cannot be both.
    """

    kind: Literal["set_token"] = "set_token"
    param: str
    value: str


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
        SetToken,
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
    # WHO wrote this rule, which decides what a disagreeing tie MEANS.
    #
    # Two rules we authored that tie and disagree cannot both be right and
    # nobody outside this repo can fix it: that is a build error, and raising is
    # the correct treatment (ADR-0005). Two rows the Knowledge Platform
    # published that tie and disagree is not our bug and not fixable here — it
    # is a `Conflict`, a warned line and a review task (contract §3.2.4: never
    # fail a run over a gap).
    #
    # The default is `authored` because every rule in this codebase today was
    # written by us, and because the safe direction for an unset field is the
    # one that keeps the build error rather than the one that silences it.
    origin: Literal["authored", "published"] = "authored"
    scope: dict[str, str] = {}  # bound dimensions: project_id, series, surface, context...
    condition: Expr | None = None
    actions: list[Action] = []
    title: str = ""
    title_i18n: dict[str, str] = {}  # optional localized titles; empty = fallback to title
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

    def display_title(self, lang: str) -> str:
        return self.title_i18n.get(lang) or self.title

    @classmethod
    def from_published(cls, **fields) -> "KnowledgeVersion":
        """A row that came out of a Knowledge Platform snapshot.

        THE SEAM, and it exists because the default is a trap. `origin` defaults
        to `authored`, which is the safe direction for a field nobody sets yet —
        but it means the snapshot loader (build order item 5) can forget it and
        produce a base that looks entirely home-grown. Two published rows would
        then tie, disagree, and RAISE, which is the exact defect the field was
        added to close, silently reinstated with no test failing: there are no
        published rows in `demo_knowledge()` to notice.

        So the loader must build its rows through here rather than through the
        constructor. `origin` is not accepted as an argument — passing it would
        make this a suggestion rather than a guarantee.
        """
        if "origin" in fields:
            raise ValueError("from_published sets origin; do not pass it")
        return cls(**fields, origin="published")

    def effective_authority(self) -> int:
        return self.authority if self.authority is not None else DEFAULT_AUTHORITY[self.type]

    def specificity(self) -> int:
        """How narrowly this rule is aimed — bound scope dimensions PLUS the
        context fields its condition tests.

        Conditions used to count for nothing, and that made the most natural
        authoring act in the system a build error: *"we already say the maximum
        is 1500; in Exposure C say 1200"* produced two rules of the same type at
        the same authority, one conditioned and one not. `_beats` returned False
        both ways, and inside the hard band a disagreeing tie is a
        `GenerationFailure` — so adding a perfectly ordinary conditioned rule
        bricked every project until someone reverse-engineered the authority
        ladder and hand-tuned `authority=`.

        A rule that applies sometimes IS more specific than one that always
        applies, which is the same principle `len(self.scope)` already encodes:
        scope narrows by dimension, a condition narrows by value. Counting the
        distinct field PATHS rather than the node count keeps it a measure of how
        many things a rule pins down, so `a == 1 AND a == 1` does not outrank
        `a == 1 AND b == 2`.
        """
        return len(self.scope) + len(field_paths(self.condition) if self.condition else ())


class KnowledgeBase(BaseModel):
    """The active snapshot handed to a generation run."""

    versions: list[KnowledgeVersion] = []
    # Which source admitted each published version, keyed `"OBJ@vN"` — the run's
    # answer under §1.4, and the reason it rides HERE rather than on
    # `KnowledgeVersion`.
    #
    # `admitted_by` is an output of a run, not a property of published data. A
    # field for it on the version would be a place to record an answer that
    # depends on the task the value is being used for, which is exactly the
    # confusion amendment 001 removed from the contract once already. It rides on
    # the base because the base is what `generate()` already receives, so nothing
    # about that signature changes and `generate()` stays pure.
    #
    # Empty for authored knowledge, and correctly so: `demo_knowledge()` has no
    # provenance to judge, and an absent verdict means "not judged" rather than
    # "judged and passed". A renderer must show those differently.
    admitted: dict[str, AdmittedBy] = {}
    # Values this run DECLINED to trust, by parameter name, in mm.
    #
    # A refused source is not silence, and the difference decides a number. The
    # `max_span_mm` fallback exists for silence — "nothing covered this exposure
    # category" — and is conservative relative to that. "A source we have not
    # verified told us 858 mm and we declined to believe it" is a different fact,
    # and treating it as silence lays out bays WIDER than the document we refused
    # said was safe. `FALLBACK_MAX_SPAN_MM`'s own note already forbids that: *"a
    # fallback that guessed WIDER would be a fallback that could fall down."*
    #
    # Which DIRECTION is safe is not general — lower is safer for a span limit and
    # higher for a rail separation — so nothing here interprets these. They are
    # carried for the site that knows its own parameter, which is the same rule
    # the generator's hard-tie handling already follows.
    declined: dict[str, list[int]] = {}

    def admitted_for(self, version: "KnowledgeVersion") -> "AdmittedBy | None":
        """The verdict for one version, or None where none was recorded."""
        # `ref` rather than a rebuilt string: `"OBJ@vN"` is the format the
        # decision graph's `governed_by` edges already use, and a second place
        # that spells it is a second place that can spell it differently. It
        # already did, once, and the symptom was a verdict that silently reached
        # no graph node at all.
        return self.admitted.get(version.ref)

    def active(self) -> list[KnowledgeVersion]:
        return [v for v in self.versions if v.status == "active"]

    def snapshot_set(self) -> list[tuple[str, int]]:
        return sorted((v.object_id, v.version) for v in self.active())

    def snapshot_hash(self) -> str:
        payload = json.dumps(self.snapshot_set()).encode()
        return hashlib.sha256(payload).hexdigest()[:16]
