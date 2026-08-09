"""Construction topology: user-authored physical reality (ADR-0003).

Nodes + run-edges of int-mm vertex polylines; varying properties live in
station-addressed events, never baked into geometry. Stationing is derived.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from fenceai.core.units import Mm


class Node(BaseModel):
    id: str
    x_mm: Mm
    y_mm: Mm
    kind: Literal["terminal", "junction"] = "terminal"


class Anchor(BaseModel):
    """Station anchor stored as (segment, offset) so events re-anchor proportionally
    within their originating segment when geometry is edited (ADR-0003)."""

    segment_index: int
    offset_mm: Mm
    seg_len_at_authoring_mm: Mm


# --- point event payloads -------------------------------------------------

class GatePayload(BaseModel):
    kind: Literal["gate"] = "gate"
    width_mm: Mm
    kit_sku: str | None = None


class ObstaclePayload(BaseModel):
    kind: Literal["obstacle"] = "obstacle"
    description: str = ""


class ExistingFoundationPayload(BaseModel):
    kind: Literal["existing_foundation"] = "existing_foundation"


class ElevationSamplePayload(BaseModel):
    kind: Literal["elevation_sample"] = "elevation_sample"
    z_mm: Mm


class CornerOverridePayload(BaseModel):
    kind: Literal["corner_override"] = "corner_override"
    is_corner: bool


PointPayload = Annotated[
    Union[
        GatePayload,
        ObstaclePayload,
        ExistingFoundationPayload,
        ElevationSamplePayload,
        CornerOverridePayload,
    ],
    Field(discriminator="kind"),
]


class PointEvent(BaseModel):
    id: str
    anchor: Anchor
    payload: PointPayload


# --- interval event payloads ----------------------------------------------

BaseSurface = Literal["soil", "concrete", "masonry_wall"]


class BasePayload(BaseModel):
    kind: Literal["base"] = "base"
    surface: BaseSurface


class HeightIntentPayload(BaseModel):
    kind: Literal["height_intent"] = "height_intent"
    height_mm: Mm
    source: str = "user"  # "user" | interpretation record id


class TopLinePayload(BaseModel):
    kind: Literal["top_line"] = "top_line"
    mode: Literal["follow", "level", "stepped"]
    z_mm: Mm | None = None
    source: str = "user"


class WallProfilePayload(BaseModel):
    kind: Literal["wall_profile"] = "wall_profile"
    top_z_start_mm: Mm
    top_z_end_mm: Mm


IntervalPayload = Annotated[
    Union[BasePayload, HeightIntentPayload, TopLinePayload, WallProfilePayload],
    Field(discriminator="kind"),
]


class IntervalEvent(BaseModel):
    id: str
    start_anchor: Anchor
    end_anchor: Anchor
    payload: IntervalPayload


class Run(BaseModel):
    id: str
    start_node_id: str
    end_node_id: str
    interior_vertices: list[tuple[Mm, Mm]] = []
    point_events: list[PointEvent] = []
    interval_events: list[IntervalEvent] = []


class Topology(BaseModel):
    revision: int = 0
    nodes: list[Node] = []
    runs: list[Run] = []

    @model_validator(mode="after")
    def _integrity(self) -> "Topology":
        """Duplicate ids silently merge distinct objects downstream — reject at the
        model boundary so a bad PUT becomes a 422, never corrupted geometry
        (final architecture review, finding 1)."""
        node_ids = [n.id for n in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("duplicate node ids in topology")
        run_ids = [r.id for r in self.runs]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("duplicate run ids in topology")
        event_ids = [
            e.id for r in self.runs for e in [*r.point_events, *r.interval_events]
        ]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("duplicate event ids in topology")
        known = set(node_ids)
        for r in self.runs:
            if r.start_node_id not in known or r.end_node_id not in known:
                raise ValueError(f"run {r.id} references a missing node")
        return self

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def run(self, run_id: str) -> Run:
        for r in self.runs:
            if r.id == run_id:
                return r
        raise KeyError(run_id)
