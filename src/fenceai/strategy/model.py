"""Generated construction strategy (foundation §4). Regenerated wholesale (ADR-0004)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from fenceai.core.gaps import Gap
from fenceai.strategy.choices import ChoiceSet
from fenceai.core.units import Mm
from fenceai.decisions.graph import DecisionGraph
from fenceai.fencemodel.resolve import ResolvedPanel
from fenceai.strategy.continuity import MemberRunPlan


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


class MemberRun(MemberRunPlan):
    """A member that is ONE piece across several bays — obligation 14's answer,
    recorded so nothing downstream has to ask the question again.

    A rail threaded through an intermediate post belongs to no bay (contract
    §3.1.12), so it cannot live on a `Span` the way `rail_count` does. It hangs
    off the strategy beside the posts and the bays, and names the spans it
    covers — which is what lets demand emit ONE line pegged to all of them
    instead of one line per bay, and what stops the BOM over-ordering by exactly
    the factor the obligation is about.

    A SUBCLASS of the derivation's own output rather than a restatement of it:
    two hand-kept copies of this shape is how the cut length on the plan and the
    cut length on the drawing come to differ. All this adds is identity — an id
    to peg to and the run it belongs to.

    The derivation's INPUTS ride along (`stock_length_mm`, `authored`, `basis`)
    because "why is this one piece" is a question a reader asks of the cut list,
    and the `derive_continuity` decision node is built from these fields.
    """

    id: str
    run_ref: str


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
    # Holes in what knowledge told us, carried alongside the plan built anyway
    # (contract §3.2.4). Here rather than on `GenerationResult` because a gap
    # travels with the thing it affected: every gap in this list is paired with
    # a warning above and a `gap` node in the graph, and a reader holding a
    # stored strategy can already see all three. `POST /gaps` reports from here.
    gaps: list[Gap] = []
    # Members that are one piece across several bays. Empty is the normal case
    # and the one every fence built before obligation 14 has: nothing is
    # continuous unless the model details it to pass a post AND the stock it is
    # bought in reaches. See `strategy/continuity.py`.
    member_runs: list[MemberRun] = []

    def element_ids(self) -> list[str]:
        # Member runs are here for the same reason posts and bays are: they have
        # an id, the decision graph scopes a node to it, and `/explain/{element}`
        # answers for it. Nothing PEGS to one — a demand line for a continuous
        # member pegs to the bays it crosses, which is what keeps the structure
        # sheet able to show it under each — so adding them widens what can be
        # explained without widening what has to be accounted for.
        return (
            [p.id for p in self.posts] + [s.id for s in self.spans]
            + [g.id for g in self.gates] + [m.id for m in self.member_runs]
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

    `content_hash` guards against a version NUMBER being reused. It is NOT the
    draft argument `ModelUse.content_hash` makes — that one is true of a model and
    false of a part: `resolve_model_parts` resolves `latest_active` and nothing
    else, so a draft is never in a snapshot and a draft moving under a fixed
    `(part_id, version)` is a thing no run can observe.

    What a run CAN observe is two libraries that both call something
    `rail-3000@v1` and mean different documents — a restored database, an import,
    a seed that diverged from the one a run was generated against. Without the
    hash those two runs share a digest, the second `INSERT OR IGNORE` drops
    silently, and every later read serves the first run's answer for the second
    run's fence. That is the failure, and it is the reason the field is a digest
    input rather than a decoration. Defensive, in the honest sense: nothing in
    this codebase reuses a version number today, and the cost of carrying the
    hash is sixteen characters against a corruption nothing else would report.
    """

    part_id: str
    version: int
    content_hash: str = ""

    def sort_key(self) -> tuple:
        return (self.part_id, self.version, self.content_hash)


class GenerationRun(BaseModel):
    id: str
    project_id: str = ""
    # How many extra generations this run spent costing the alternatives it
    # offers. Recorded rather than capped: the cost is `1 + n` by construction
    # (a probe never probes), and a number on the run is how a runaway becomes
    # visible instead of expensive.
    probe_count: int = 0
    topology_revision: int = 0
    # The site conditions this run was generated against. Same job as
    # `topology_revision` and guarded the same way: a derived view laid over
    # conditions that have moved since describes a different fence, and site
    # conditions are NOT part of the topology, so the `topology_changed` guard
    # cannot see them. Change a project from Exposure B to C and the span limit
    # changes, posts move — and without this the structure sheet renders the old
    # layout without complaint. 0 is a run generated before site conditions
    # existed, which is exactly what it was generated against.
    #
    # REPORTED, never guarded on. A revision counts SAVES, and a save that
    # changes nothing still moves it — see `site_facts` below.
    site_revision: int = 0
    # The site facts this run was actually built from: what the guard compares,
    # and what makes the run explainable.
    #
    # A counter could not do this job, and the way it failed is worth keeping.
    # The digest hashes the FACTS — two runs of one fence must share an id — so
    # re-saving IDENTICAL site conditions bumped the revision, regenerated to the
    # same run id, and `INSERT OR IGNORE` kept the stored document carrying the
    # old number. Every derived view then answered 409 for ever, with no user
    # action able to repair it; the generate response even reported the new
    # revision while the store held the old one. Guard and digest have to agree
    # on what "the site" means, and the facts are that meaning.
    #
    # It also answers foundation §15. "Why is this bay 1200 mm" resolves to a
    # rule whose condition is `site.exposure_category == "C"`, and without this
    # nothing persisted said the site WAS C: `Project.site` is mutable and keeps
    # no history, so the run's own explanation became unreconstructible the
    # moment somebody edited the form.
    site_facts: dict = {}
    knowledge_snapshot: list[tuple[str, int]] = []
    snapshot_hash: str = ""
    # The PUBLISHER's snapshot id (§1.2), and it is what §3.2 obligation 1 asks
    # for: *"pin a snapshot hash on every run; re-fetch historical runs by hash,
    # never re-resolve."*
    #
    # `snapshot_hash` above does NOT satisfy that and never could — it is our own
    # digest of the `(object_id, version)` list, so it answers "which knowledge
    # objects" including authored ones, and cannot be handed back to the
    # publisher to fetch anything. Both are kept because they answer different
    # questions; only this one is the promise.
    #
    # Empty on a run against authored knowledge alone, which is every run until a
    # snapshot is loaded.
    snapshot_id: str = ""
    overrides_applied: list[str] = []
    policy: dict = {}
    # demand product selection resolved from knowledge at generation time
    # (DefaultComponent roles rail/screw/concrete/cap) — consumed by derive_requirements
    demand_skus: dict[str, str] = {}
    # which supply-resolution preset this run was GENERATED under. Reported, not
    # identity: it left the digest in digest-v3, because a design is what it is
    # regardless of how it will be bought. It is also NOT the source of truth for
    # a read — `save_run` is INSERT OR IGNORE, so on an unchanged fence this
    # field is frozen at the FIRST generation for ever. Read paths take the live
    # preset from the project's policy and record it on the SupplyRun.
    objective_preset: str = "least_cost"
    # the fence models this run actually drew from — part of what "generated from"
    # means, so it belongs in the run id (run identity, task 10)
    model_snapshot: list[ModelUse] = []
    # the parts this run resolved — a model names a part_id and NOT a version, so
    # two runs of the identical model document mean different fences the moment a
    # part moves. That makes this part of what "generated from" means, and it goes
    # into the run id on `model_snapshot`'s argument. `[]` is a run generated
    # before parts existed and needs no validator, because it is the default —
    # the same readable-old-runs convention `catalog_skus` keeps.
    part_snapshot: list[PartUse] = []
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
    # The questions this run carries: where two or more answers were admissible
    # and nothing in the data preferred one. DERIVED, never stored — a question
    # is about the current geometry and knowledge, and is rebuilt every
    # generation. The person's ANSWER is what persists, on the project.
    choice_sets: list[ChoiceSet] = []
