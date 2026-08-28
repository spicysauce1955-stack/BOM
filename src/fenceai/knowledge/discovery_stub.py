"""Fixture-backed stand-in for the Knowledge Platform's Discovery API
(`GET /source-refs/{id}` and the agreed `POST /source-refs:batch`).

PROVENANCE: `fenceai/knowledge/fixtures/source-ref-examples.json` is a
byte-identical vendored copy of fence-rag's
`docs/integration/fixtures/source-ref-examples.json` — seven example responses
built from real rows in their extraction store (real ids, hashes, pixel
dimensions, OCR confidences, quotes, reader names; only a handful of fields are
explicitly marked invented in the fixture's own `_fixture.invented_values`).
It is NOT real published evidence and it is expected to be REPLACED once the
real Discovery API exists — fence-rag's endpoint is design-only as of
2026-08-24 (see their `docs/integration/source-refs-design.md`, whose own
header records the id scheme as superseded and the crop reasoning as current).

This module mirrors the spirit of `fenceai/ai/stub.py`: a real module standing
in for a port that does not exist yet, deterministic and offline, so the rest
of the system can treat it as interchangeable with the real thing later. It
does NOT plug into the `fenceai/ai/` port system — Discovery is not an AI
port, and this is small enough not to need one of its own.

Frontend design doc: docs/superpowers/specs/2026-08-23-frontend-design.md §3
("Build the viewer against that file before the discovery API exists").
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "source-ref-examples.json"


# ---------------------------------------------------------------------------
# The response shape, grounded in the fixture's actual fields (source-refs-
# design.md §3) — not invented. Every field below is read from a real key
# somewhere in the seven vendored records; nothing here is speculative beyond
# what the fixture itself already carries.
# ---------------------------------------------------------------------------


class SourceVersion(BaseModel):
    version_id: str
    sha256: str
    file_size_bytes: int
    page_count: int


class SupersededByEntry(BaseModel):
    document_id: str
    basis: str
    confidence: float


class SourceDocStatus(BaseModel):
    # §3.1: a block, never a bare string — 92% of this corpus is "unknown" and
    # a status shown without its basis is how a superseded approval gets read
    # as current (record 5's whole point).
    version_status: Literal["active", "superseded", "unknown"]
    version_status_basis: str | None = None
    issue_date: str | None = None
    expiration_date: str | None = None
    superseded_by: list[SupersededByEntry] = []
    same_content_as: list[str] = []


class SourceDocument(BaseModel):
    document_id: str
    title: str
    manufacturer: str
    product_family: str | None = None
    doc_type: str
    corpus_track: str
    structural: bool
    source_path: str
    version: SourceVersion
    status: SourceDocStatus


class Locus(BaseModel):
    page_no: int
    page_width_pt: float
    page_height_pt: float
    # only carried on the one CAD-PNG record (#6), where page dimensions are
    # pixels rather than points and the 72 dpi arithmetic only works because
    # 72/72 == 1 — see source-refs-design.md §4.1 trap 1.
    page_units: str | None = None
    bbox_pt: list[float] | None = None
    bbox_space: str
    rotation_already_applied: bool


class SourceText(BaseModel):
    quote: str | None = None
    quote_absent_reason: str | None = None
    quote_is_verbatim_substring_of: str | None = None
    text_source: str | None = None
    ocr_confidence: float | None = None
    element_id: str | None = None
    element_type: str | None = None
    heading_path: list[str] = []


class VisualReading(BaseModel):
    """`kind: visual_reading` only (record #4) — a named reader's cell reading,
    no quote and no element at all. Stronger than `page` and must not be let
    to look like it (source-refs-design.md §2)."""

    reader: str
    reader_kind: str
    table_kind: str
    row_index: int
    col_index: int
    row_label: str
    col_label: str
    value_raw: str
    illegible: bool
    reading_confidence: str
    cell_bbox_px: list[int] | None = None
    cell_bbox_absent_reason: str | None = None
    reader_notes: str | None = None


class ImageCrop(BaseModel):
    url: str
    width_px: int
    height_px: int
    dpi: int
    bbox_px: list[int] | None = None
    pad_px: int
    sha256: str


class ImagePage(BaseModel):
    url: str
    width_px: int
    height_px: int
    dpi: int
    sha256: str


class SourceImage(BaseModel):
    status: Literal["available", "source_not_fetched", "not_applicable", "failed"]
    reason: str | None = None
    crop: ImageCrop | None = None
    page: ImagePage | None = None
    tool_fingerprint: str | None = None


class DerivedFrom(BaseModel):
    """`kind: derived` only (record #7) — a hand-researched dataset assertion
    with no document and no page at all."""

    origin: str
    dataset_path: str
    json_pointer: str
    value_raw: str
    dataset_note: str | None = None


class SourceWarning(BaseModel):
    code: str
    params: dict[str, Any] = {}


class SourceRefResolved(BaseModel):
    """One resolved `SourceRef` — the five kinds `source-refs-design.md` §2
    argues for. `document`/`derived_from`/`locus`/`reading` are all optional
    because no single record carries all of them; which ones are present is
    itself part of what the record says (`derived` has neither document image
    nor locus; `page` and `element_quote` have no `reading`)."""

    source_ref_id: str
    kind: Literal["element_quote", "table_cell", "page", "visual_reading", "derived"]
    contract_version: str
    retain_until: str | None = None
    document: SourceDocument | None = None
    derived_from: DerivedFrom | None = None
    locus: Locus | None = None
    text: SourceText
    reading: VisualReading | None = None
    image: SourceImage
    warnings: list[SourceWarning] = []


@lru_cache(maxsize=1)
def _fixture_records() -> dict[str, SourceRefResolved]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    out: dict[str, SourceRefResolved] = {}
    for rec in raw["source_refs"]:
        # `_note` is the fixture's own human commentary, not part of the
        # response shape a real Discovery API would return — Pydantic drops
        # unknown fields by default, so it is simply not modeled above.
        parsed = SourceRefResolved.model_validate(rec)
        out[parsed.source_ref_id] = parsed
    return out


def resolve_batch(ids: list[str]) -> tuple[list[SourceRefResolved], list[str]]:
    """Resolve a batch of opaque `SourceRef.id` strings against the vendored
    fixture. Fixture-backed today, not a live Discovery API.

    An id this seven-record fixture does not carry is not an error — it is the
    honest answer that today's stub does not have that piece of evidence, so
    it comes back in the second list rather than raising. `id` stays opaque
    throughout: this never parses it, only looks it up.
    """
    records = _fixture_records()
    resolved: list[SourceRefResolved] = []
    not_found: list[str] = []
    for source_ref_id in ids:
        rec = records.get(source_ref_id)
        if rec is None:
            not_found.append(source_ref_id)
        else:
            resolved.append(rec)
    return resolved, not_found
