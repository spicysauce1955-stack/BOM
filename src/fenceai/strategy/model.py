"""Generated construction strategy (foundation §4). Regenerated wholesale (ADR-0004)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

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
    # How far below ground_z_mm this post is set, and the SAME number the length
    # check spent (`_check_post_lengths` writes it there, from the value it
    # resolves): a drawing that showed a different footing depth than the length
    # the post was checked against would be a drawing of a different fence.
    # 0 is a fact, not a blank — a masonry-mounted post is bolted to what it
    # stands on and embeds nothing. (A strategy generated before this field
    # reads 0 for its ground posts too; regenerating restores the truth.)
    embed_mm: Mm = 0
    # The other half of the same length check, and here for the same reason.
    # `top_z_mm` is the elevation this post carries — the highest top of the bays
    # that meet it — and `exposed_mm` is how much POST that takes above what it
    # stands on, which on a tilted post is the longer of the two. Both are
    # written by `_check_post_lengths` from the values it measured the product
    # against, so a run that warns "this post is 200 mm short" cannot also be
    # drawn with a post that looks fine.
    #
    # None means the check never measured this post: it has no adjacent bay (the
    # node post of a run whose first bay is a gate). 0 would be a different
    # claim — a post standing flush with what it stands on.
    exposed_mm: Mm | None = None
    top_z_mm: Mm | None = None
    tilt_deg: int = 0  # degrees from vertical; 0 = plumb (the default and the norm)
    pinned: bool = False
    # The cap this post's MODEL asked for. "" means the model had no opinion and
    # demand falls back to the company default, which is what every fence built
    # before models owned their posts used.
    cap_sku: str = ""


class Span(BaseModel):
    id: str
    run_ref: str
    start_station_mm: Mm
    end_station_mm: Mm
    width_mm: Mm  # plan (chord) width, centre-to-centre between its two posts
    # The opening between the two post FACES — what an infill is actually fitted
    # across and what `clear_between_posts` measures. Computed ONCE here, during
    # generation, from the posts that bound the bay, because the panel preview
    # and the read models re-read a stored run and must fit the panel to the same
    # number it was built to; a second derivation downstream is how a drawing and
    # a cut list end up a post-face apart.
    #
    # None means "generated before the opening was computed" — those runs read
    # their bays at centre-to-centre, which is what they were actually built to.
    # 0 would be a different and false claim: a bay with no opening at all.
    clear_width_mm: Mm | None = None
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


class ModelUse(BaseModel):
    """One fence model, as this run actually drew from it.

    `content_hash` is here because `(id, version)` is not enough: a draft version's
    document may be edited in place under a fixed ref, so without the hash a model
    edit leaves the run-id digest untouched and `INSERT OR IGNORE` serves the old
    stored document under a reused id — two views of one run disagreeing forever.
    `options` are in for the same reason: pick a different colour and the SKUs
    beneath it change.

    `source` is deliberately NOT here. Where a choice came from (an interval event,
    the project default, the built-in fallback) is provenance, and provenance lives
    in the decision graph. On the run it would only split the digest between two
    runs that build the identical fence.
    """

    model_id: str
    version: int
    content_hash: str = ""
    options: dict[str, str | int] = {}

    def sort_key(self) -> tuple:
        return (self.model_id, self.version, self.content_hash,
                tuple(sorted((k, str(v)) for k, v in self.options.items())))


class PartUse(BaseModel):
    """One part, as a run actually resolved it — `parts.resolve`'s report.

    `content_hash` is here for the same reason `ModelUse.content_hash` is: a draft
    version's document may move under a fixed `(part_id, version)`, so the number
    alone is not enough to say what a run drew on. An active version's hash is
    redundant with its immutability but costs nothing to carry, and a uniform shape
    is what lets `GenerationRun.part_snapshot` (Task 7) stamp both alike.
    """

    part_id: str
    version: int
    content_hash: str = ""

    def sort_key(self) -> tuple:
        return (self.part_id, self.version, self.content_hash)


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
    objective_preset: str = "least_cost"  # which supply-resolution preset resolve_supply uses
    # the fence models this run actually drew from — part of what "generated from"
    # means, so it belongs in the run id (run identity, task 10)
    model_snapshot: list[ModelUse] = []
    # catalog content hash at generation time — /bom and /structure refuse to
    # re-read a stored run against a catalog that no longer matches it
    catalog_hash: str = ""
    # the Product SHAPE that hash was computed over. "" is a run generated before
    # the shape was recorded, which is exactly the population a schema migration
    # must be able to name.
    catalog_schema_version: str = ""
    # the products this run actually named — what `catalog_hash` covers. Empty
    # means "hashed over the whole catalog", which is how a run stamped before
    # the hash was narrowed still reads: its stored hash is only comparable
    # against the same broad computation.
    catalog_skus: list[str] = []
    created_at: str = ""

    @field_validator("model_snapshot", mode="before")
    @classmethod
    def _upgrade_model_snapshot(cls, v):
        """Runs are stored as whole JSON documents and re-read with
        model_validate_json, so a shape change makes every earlier run unreadable
        rather than merely out of date. `model_snapshot` shipped as [(id, version)];
        a 2-element sequence is read as one, with an empty content hash meaning
        "generated before content was hashed" — never a hash that could collide
        with a real one."""
        if not isinstance(v, list):
            return v
        return [
            {"model_id": item[0], "version": item[1]}
            if isinstance(item, (list, tuple)) and len(item) == 2
            else item
            for item in v
        ]


class GenerationResult(BaseModel):
    run: GenerationRun
    strategy: Strategy
    graph: DecisionGraph
    # overrides that no longer matched the topology — reported, never mutated on the
    # caller's objects (generate() is pure, ADR-0004)
    orphaned_overrides: list[str] = []
