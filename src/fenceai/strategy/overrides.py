"""User overrides: first-class, anchored to topology coordinates (ADR-0004).

Never reference generated element ids — anchors are (run_id, station/interval, kind).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.core.units import Mm


class PinPost(BaseModel):
    kind: Literal["pin_post"] = "pin_post"
    station_mm: Mm


class SuppressPost(BaseModel):
    kind: Literal["suppress_post"] = "suppress_post"
    station_mm: Mm


class ForcePostSku(BaseModel):
    kind: Literal["force_post_sku"] = "force_post_sku"
    station_mm: Mm
    sku: str


class ForceMounting(BaseModel):
    kind: Literal["force_mounting"] = "force_mounting"
    station_mm: Mm
    mounting: Literal["ground", "masonry"]


class ForceVertical(BaseModel):
    kind: Literal["force_vertical"] = "force_vertical"
    start_station_mm: Mm
    end_station_mm: Mm
    mode: Literal["level", "stepped", "raked"]


Directive = Annotated[
    Union[PinPost, SuppressPost, ForcePostSku, ForceMounting, ForceVertical],
    Field(discriminator="kind"),
]


class Override(BaseModel):
    id: str
    run_id: str  # topology run anchor
    directive: Directive
    status: Literal["active", "orphaned"] = "active"
    origin: Literal["user", "correction"] = "user"
    origin_ref: str | None = None  # correction id when origin == correction
    author: str = "user"
    created_at: str = ""
    note: str | None = None
