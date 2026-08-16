"""Persisted quotes: immutable BOM snapshots (v1-known-limitations trigger: real
quoting needs a stable document, not a recomputation).

A quote captures the exact requirements + BOM computed at a moment, pegged to the
generation run (which already stamps the knowledge snapshot) and to the inventory
content hash. Content is append-only; only lifecycle status changes:
draft -> accepted -> superseded (accepting supersedes the previously accepted
quote of the same project).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.units import Cents
from fenceai.fulfillment.lines import ResolvedSupplyLine
from fenceai.fulfillment.fulfill import Bom


class Quote(BaseModel):
    id: str
    project_id: str
    run_id: str
    label: str = ""
    created_at: str = ""
    status: Literal["draft", "accepted", "superseded"] = "draft"
    inventory_hash: str = ""
    knowledge_snapshot_hash: str = ""
    # the catalog content the run resolved products and prices against. Provenance
    # for the frozen document, beside the knowledge snapshot: the quote itself is
    # already immutable (requirements and bom are persisted in full), so this
    # records what it MEANT, it does not guard it.
    catalog_hash: str = ""
    requirements: list[ResolvedSupplyLine] = []
    bom: Bom
    total_cents: Cents = 0


QUOTE_STATUS_TRANSITIONS = {
    "draft": {"accepted", "superseded"},
    "accepted": {"superseded"},
}
