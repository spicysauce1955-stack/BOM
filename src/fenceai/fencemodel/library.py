"""The set of models a project may choose from, and what a choice resolves to.

Pure and deterministic, like `KnowledgeBase`: the store hands over every row and
this decides what "the current M-SLAT" means. Resolution lives here rather than
in the store so a caller holding an in-memory library — a test, a preview, a
generator handed a snapshot — gets the same answer as one reading SQLite.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel

from fenceai.fencemodel.model import FenceModel


def content_hash(model: FenceModel) -> str:
    """The third component of a run's model snapshot, beside `(id, version)`.

    The pair alone does not identify a document: a draft's content changes under
    a fixed `(id, version)`, so a run stamped with the pair could be regenerated
    against a panel it never saw (`docs/v1-known-limitations.md`). Pydantic
    serialises in field order, so the same document always hashes the same.
    """
    return hashlib.sha256(model.model_dump_json().encode()).hexdigest()[:12]


class ModelListing(BaseModel):
    """One row per model id, for a chooser.

    `active_version` is what a project picking this model without a pin would
    get — `None` when nothing is published, which is how a draft-only model
    reads as not yet selectable instead of disappearing from the list.

    `draft_version` and `versions` exist for the EDITOR rather than the chooser.
    "Edit this model" must open the draft that already exists instead of opening
    a second one, and "duplicate from a version" must offer the versions there
    are; with only `has_draft` the client would have to guess a version number,
    and `active_version + 1` is a guess that is wrong the moment a version above
    the active one was retired.
    """

    id: str
    active_version: int | None
    draft_version: int | None = None
    has_draft: bool
    versions: list[int] = []
    name_i18n: dict[str, str] = {}
    status: Literal["draft", "active", "retired"]


class FenceModelLibrary(BaseModel):
    models: list[FenceModel] = []

    def latest_active(self, model_id: str) -> FenceModel | None:
        return max(
            (m for m in self.models if m.id == model_id and m.status == "active"),
            key=lambda m: m.version,
            default=None,
        )

    def get(self, model_id: str, version: int) -> FenceModel | None:
        for m in self.models:
            if m.id == model_id and m.version == version:
                return m
        return None

    def by_ref(self, model_ref: str) -> FenceModel | None:
        """`"M-VINYL@v1"` -> the document, or `None` for a ref nothing answers.

        Here rather than at each caller because a ref is this library's format:
        `FenceModel.ref` writes it and the read models parse it. `None` rather
        than a raise, because a caller collecting a plan's documents wants to skip
        the one it cannot find.

        **There is one other reader and it is not going away.**
        `fencemodel/preview.py::_ref_parts` parses the same shape and RAISES
        `ReadRefused(code="run_predates_fence_model")`, because it is re-reading a
        stored run and owes the reader a coded refusal rather than a `None` that
        turns into an empty page. The first version of this docstring claimed to
        be the single parser and the architecture review caught it. Two readers,
        two return contracts, one format — and if a third appears, that is when
        the format is worth extracting rather than the callers being made to
        share a signature neither wants.
        """
        model_id, _, version = model_ref.rpartition("@v")
        if not model_id or not version.isdigit():
            return None
        return self.get(model_id, int(version))

    def resolve(self, model_id: str, version_pin: int | None) -> FenceModel | None:
        """A pin outranks status: a run that stamped M-SLAT@v2 must regenerate to
        the same panel after v2 is retired, or retiring a version would rewrite
        what accepted quotes meant. Only an unpinned choice follows the line."""
        if version_pin is not None:
            return self.get(model_id, version_pin)
        return self.latest_active(model_id)

    def listing(self) -> list[ModelListing]:
        rows = []
        for model_id in sorted({m.id for m in self.models}):
            versions = [m for m in self.models if m.id == model_id]
            active = self.latest_active(model_id)
            # Name and status come from the version a chooser would actually
            # get, falling back to the newest one there is, so the row never
            # describes a document nobody can select.
            shown = active or max(versions, key=lambda m: m.version)
            # The HIGHEST draft, so a library that somehow carries two of them
            # names the one a new save would land on rather than an older one.
            draft = max((m.version for m in versions if m.status == "draft"), default=None)
            rows.append(ModelListing(
                id=model_id,
                active_version=active.version if active else None,
                draft_version=draft,
                versions=sorted(m.version for m in versions),
                has_draft=draft is not None,
                name_i18n=shown.name_i18n,
                status=shown.status,
            ))
        return rows
