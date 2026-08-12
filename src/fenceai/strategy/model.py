"""Generated construction strategy (foundation §4). Regenerated wholesale (ADR-0004)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.decisions.graph import DecisionGraph
from fenceai.fencemodel.resolve import ResolvedPanel


class Post(BaseModel):
    id: str
    run_ref: str  # topology run id, or "node:<id>" for shared node posts
    station_mm: Mm  # station within run; 0 for node posts
    kind: Literal["end", "corner", "line", "gate", "junction", "transition"]
    reinforced: bool = False
    mounting: Literal["ground", "masonry"] = "ground"
    sku: str = ""
    ground_z_mm: Mm = 0
    # The elevation the post STANDS on: the top of a built base (wall/concrete)
    # where one carries the fence, the ground otherwise. ground_z_mm stays the
    # true ground, which is what embedment is measured into. None = same as the
    # ground (also how strategies generated before this field read).
    base_z_mm: Mm | None = None
    tilt_deg: int = 0  # degrees from vertical; 0 = plumb (the default and the norm)
    pinned: bool = False


class Span(BaseModel):
    id: str
    run_ref: str
    start_station_mm: Mm
    end_station_mm: Mm
    width_mm: Mm  # plan (chord) width
    slope_len_mm: Mm  # true length along grade (== width for level/stepped)
    vertical: Literal["level", "stepped", "raked"] = "level"
    height_mm: Mm = 1800
    bottom_z_start_mm: Mm = 0
    bottom_z_end_mm: Mm = 0
    rail_count: int = 2
    screws_count: int = 8  # resolved from knowledge during generation (K-SCREWS)
    rail_cut_basis: Literal["width", "slope"] = "width"
    # What this bay is made of, resolved from the fence model at generation.
    # rail_count/screws_count stay until a migration back-fills `panel` onto
    # stored runs: a run re-read without either would silently default to 2.
    panel: ResolvedPanel | None = None


class Gate(BaseModel):
    id: str
    run_ref: str
    start_station_mm: Mm
    end_station_mm: Mm
    kit_sku: str


class StrategyWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str  # English fallback; clients localize from code + params
    params: dict[str, str | int] = {}  # the values interpolated into message
    element_refs: list[str] = []
    decision_ref: str | None = None


class Strategy(BaseModel):
    id: str
    status: Literal["proposed", "accepted", "superseded"] = "proposed"
    posts: list[Post] = []
    spans: list[Span] = []
    gates: list[Gate] = []
    warnings: list[StrategyWarning] = []

    def element_ids(self) -> list[str]:
        return (
            [p.id for p in self.posts] + [s.id for s in self.spans] + [g.id for g in self.gates]
        )


class GenerationRun(BaseModel):
    id: str
    project_id: str = ""
    topology_revision: int = 0
    knowledge_snapshot: list[tuple[str, int]] = []
    snapshot_hash: str = ""
    overrides_applied: list[str] = []
    policy: dict = {}
    # demand product selection resolved from knowledge at generation time
    # (DefaultComponent roles rail/screw/concrete/cap) — consumed by derive_requirements
    demand_skus: dict[str, str] = {}
    created_at: str = ""


class GenerationResult(BaseModel):
    run: GenerationRun
    strategy: Strategy
    graph: DecisionGraph
    # overrides that no longer matched the topology — reported, never mutated on the
    # caller's objects (generate() is pure, ADR-0004)
    orphaned_overrides: list[str] = []
