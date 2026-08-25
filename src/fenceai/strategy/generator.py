"""Strategy generation: pure, deterministic pipeline (ADR-0004, foundation §7).

generate(topology, knowledge, catalog, overrides, policy) -> GenerationResult.

Discipline (post-spike architecture review):
- pure: inputs are never mutated; orphaned overrides are reported in the result;
- every behavioral choice flows through knowledge resolution — product selection,
  layout preferences, vertical mode, quantities — with the winning/defeated version
  refs recorded as decision-graph edges (no cite-but-hardcode);
- override anchors match generated stations within SNAP_TOLERANCE_MM;
- elements are never mutated after their decision node is recorded.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field as dataclass_field

from fenceai.catalog.model import CATALOG_SCHEMA_VERSION, Catalog, catalog_hash
from fenceai.core.errors import GenerationFailure
from fenceai.core.gaps import Gap, GapSubject
from fenceai.core.units import SNAP_TOLERANCE_MM, Mm, slope_len_mm
from fenceai.decisions.graph import GraphBuilder
from fenceai.fencemodel.demo import legacy_model
from fenceai.fencemodel.library import FenceModelLibrary, content_hash
from fenceai.fencemodel.match import (
    chosen_post_facts, item_value, match_eligibility, match_spec, panel_facts,
    post_panel_facts, sole_excluding_term,
)
from fenceai.fencemodel.model import FenceModel, unknown_skus, validate_model
from fenceai.fencemodel.resolve import (
    PanelContext, ResolvedPanel, choose_variant, choose_variant_by, clear_opening_mm,
    height_supported, rail_positions_mm, resolve_panel,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.ast import field_paths
from fenceai.knowledge.evaluator import (
    Resolution,
    preference_firings,
    resolve as evaluator_resolve,
    resolve_actions,
    resolve_param,
)
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.parts.model import PartLibrary
from fenceai.project.model import SiteConditions
from fenceai.parts.resolve import resolve_model_parts
from fenceai.strategy.layout import boundaries, layout_segment
from fenceai.strategy.model import (
    Gate,
    GenerationResult,
    GenerationRun,
    ModelUse,
    PartUse,
    Post,
    Span,
    Strategy,
    StrategyWarning,
)
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Run, Topology
from fenceai.topology.station import (
    anchor_station,
    base_surface_at,
    base_top_at,
    base_top_step_stations,
    base_transition_stations,
    fence_model_at,
    fence_model_transition_stations,
    ground_step_stations,
    local_slope_permille,
    corner_stations,
    ground_z,
    max_slope_permille,
    node_turn_deg,
    run_length,
)
from fenceai.topology.station import CORNER_ANGLE_DEG

# "fewest_new_stock" here (pre-ADR-0007) predates fulfillment/supply.py's Preset
# vocabulary (`Literal["least_cost", "honour_priority"]`, added later in
# 7c73ec6) and was never wired to a tier those two presets implement — it named
# a cut-planning tier-list concept (material-optimization.md), not a
# resolve_supply preset. It only ever "worked" because `_choose` silently
# treated any unrecognised preset as least-cost. Now that resolve_supply
# refuses an unrecognised preset loudly (task 10 fix round 1, finding 3), the
# honest default is the vocabulary's own default, not the vestigial name.
DEFAULT_POLICY: dict = {"default_height_mm": 1800, "objective_preset": "least_cost"}

# What the ENGINE does, as part of what a run means.
#
# The digest held data versions — topology, knowledge, models, catalog — and no
# algorithm version at all, so a legitimate change to how a fence is laid out
# produced a different strategy under the SAME id, and `save_run`'s
# INSERT OR IGNORE then served the old stored document for ever. Deliberately not
# a git commit: most commits change nothing a run means, and an identity that
# churns on every push makes every stored run unreadable for no reason.
#
# Bump PLANNING_BEHAVIOR_VERSION when generation's OUTPUT changes for unchanged
# inputs — a different post rule, a different layout, a different panel
# resolution. Bump RUN_DIGEST_VERSION when the digest's own inputs or
# serialisation change, which is what makes two genuinely different runs able to
# hash the same.
#
# There is deliberately NO fulfillment version here, and now there is somewhere
# for it to live: `SUPPLY_BEHAVIOR_VERSION` in `fulfillment/supply_run.py`. A
# run's stored document is the strategy and its graph; what that strategy COSTS
# is a function of mutable inventory and is named by a SupplyRun. Putting a
# supply version in the DESIGN digest would deepen exactly the conflation the
# split removed.
# v2: a resolved fixing slot carries its `basis` and `qty_per_basis`, from which
# the elevation derives where the fasteners land. Panel resolution's OUTPUT
# therefore changed for unchanged inputs, which is exactly what this constant is
# for — without the bump an existing project regenerates to the same run id,
# `save_run`'s INSERT OR IGNORE keeps the document that predates the fields, and
# its bays draw no fasteners for ever with no user action able to repair it.
PLANNING_BEHAVIOR_VERSION = "planning-v4"
# v4: `specificity()` counts the field paths a rule's CONDITION tests, not only
# its bound scope dimensions. A conditioned rule now outranks an unconditioned one
# at the same authority, where before they tied — and inside the hard band a
# disagreeing tie is a failure, so "we say 1500; in Exposure C say 1200" used to
# brick every project. Precedence deciding differently is an output change for
# unchanged inputs.
# v3: site conditions bind into every evaluation context, so a rule conditioned on
# `site.*` now fires where it previously could not — the same project against the
# same knowledge can resolve a different span limit. That is an OUTPUT change for
# unchanged inputs, which is exactly what this version exists to record.
# v2: `part_snapshot` joined the digest's inputs. A model names a part_id and not a
# version, so two runs of the identical model document — same id, same content hash
# — are different fences once a part moves under them. Without the bump they hash
# the same and `save_run`'s INSERT OR IGNORE serves the first one's document for the
# second one's fence.
# v3: `objective_preset` LEFT the digest, from BOTH places it occupied — by name,
# and inside `policy`, which DEFAULT_POLICY always populates. A design is what it
# is regardless of how it will be bought. This is one deliberate discontinuity:
# stored runs keep their ids and stay readable, and a regeneration of an
# unchanged project mints a new id ONCE, at this boundary. Digest stability is a
# property WITHIN a version and is not weakened by the bump — what the bump
# strands is comments anchored to already-persisted run ids, once. Against that,
# switching the preset used to strand a thread EVERY time it was switched.
# v4: `site_facts` joined the digest's inputs — two projects that differ only in
# their site are different fences and must not share a run id. (It joined in the
# same commit that cut planning-v3, which moved every digest anyway; bumping this
# too is what lets a later reader see that v3's INPUTS changed and not just its
# behaviour, which is the whole reason the two constants are separate.)
RUN_DIGEST_VERSION = "digest-v4"

# The catalog attribute by which a product declares the opening width it fits.
# Fit is DATA, like Product.attrs["length_mm"] for posts: a SKU is an opaque id and
# "GATE-KIT-1000" is a naming accident of one catalog, never a width to parse.
KIT_OPENING_ATTR = "opening_width_mm"


def _near(a: Mm, b: Mm) -> bool:
    return abs(a - b) <= SNAP_TOLERANCE_MM


def _declared_opening(catalog: Catalog, sku: str) -> Mm | None:
    """The opening width a catalog product declares it fits, or None if it says
    nothing — an undeclared product is never second-guessed."""
    product = catalog.products.get(sku)
    value = product.capabilities.opening_width_mm if product else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _kit_for_opening(catalog: Catalog, opening_mm: Mm) -> str:
    """The catalog product declaring that it fits this opening ("" if none).
    Deterministic: lowest sku wins when a catalog offers several."""
    fits = sorted(
        sku for sku in catalog.products
        if _declared_opening(catalog, sku) == opening_mm
    )
    return fits[0] if fits else ""


def generate(
    topology: Topology,
    knowledge: KnowledgeBase,
    catalog: Catalog,
    overrides: list[Override] | None = None,
    policy: dict | None = None,
    project_id: str = "",
    models: FenceModelLibrary | None = None,
    default_model: FenceModelChoice | None = None,
    parts: PartLibrary | None = None,
    site: SiteConditions | None = None,
) -> GenerationResult:
    """`parts` is threaded in exactly as `models` is, and for the same reason:
    `generate()` is pure (ADR-0004), so it may not reach for a store. `None` means
    the caller has no library — the model documents are then used exactly as
    authored, which is what every call site predating parts meant."""
    overrides = overrides or []
    models = models or FenceModelLibrary()
    policy = {**DEFAULT_POLICY, **(policy or {})}
    # Bound ONCE, here, and threaded read-only from this point: `generate()` is
    # pure (ADR-0004), so it may not reach for the project. Unset dimensions are
    # OMITTED by `.facts()` rather than sent as None, which is what makes a rule
    # conditioned on one *not applicable* instead of false.
    site_facts = site.facts() if site is not None else {}
    # Created once and threaded read-write into every resolution. Drained in ONE
    # place below, after the strategy exists to hang the warnings on.
    sink = ConflictSink()
    builder = GraphBuilder()
    strategy = Strategy(id="strategy")
    applied: set[str] = set()
    # dimensions known for the whole run; narrower ones (surface, context) are
    # bound where they become facts
    scope = bind_scope({"project_id": project_id})

    demand_skus, demand_refs = _resolve_demand_skus(knowledge, scope, site_facts, sink)
    builder.add(
        "quantity", "resolve_demand_products",
        payload=dict(demand_skus),
        governed_by=demand_refs,
    )

    # One part resolution per model ref for the WHOLE run, shared by every post
    # match. `resolve_model_parts` is pure in `(model, parts)` and `parts` does not
    # move during a generation, so this is a memo and not a second answer.
    resolved_posts: dict[str, FenceModel] = {}
    _generate_node_posts(
        topology, knowledge, scope, site_facts, sink, catalog, overrides, policy, builder,
        strategy, applied, models, default_model, parts, resolved_posts,
    )
    # every fence model actually drawn from, across all runs — part of the run id
    # (a model swap changes what the run means even though the digest's other
    # inputs are untouched)
    models_used: list[ModelUse] = []
    # and every part those models named, at the version this run resolved. Same
    # argument one level down: a model names a part_id and not a version, so the
    # part is the other half of "which document did this fence come from".
    parts_used: list[PartUse] = []
    for run in topology.runs:
        _generate_run(
            topology, run, knowledge, scope, site_facts, sink, catalog, overrides, policy,
            builder, strategy, applied, demand_skus, models_used,
            models, default_model, parts, parts_used, resolved_posts,
        )

    _check_post_lengths(topology, knowledge, scope, site_facts, sink, catalog, builder, strategy)
    _report_unfilled_posts(strategy, builder)
    _report_missing_site_conditions(
        knowledge, site_facts, scope, {u.model_id for u in models_used},
        strategy, builder,
    )
    # Every conflict the run produced, surfaced together. Three sites used to do
    # this inline and the other ten dropped theirs; draining here is what makes
    # "a Conflict cannot be silently discarded" structural rather than a habit.
    _surface_conflicts(sink, builder, strategy)

    orphaned = [ov.id for ov in overrides if ov.id not in applied]
    for ov_id in orphaned:
        ov = next(o for o in overrides if o.id == ov_id)
        strategy.warnings.append(
            StrategyWarning(
                code="orphaned_override", severity="warning",
                message=f"Override {ov.id} ({ov.directive.kind}) no longer matches the "
                        "topology and was not applied.",
                params={"override_id": ov.id, "directive": ov.directive.kind},
            )
        )

    graph = builder.build()
    run_meta = GenerationRun(
        id="run",
        project_id=project_id,
        topology_revision=topology.revision,
        # what the run was generated AGAINST, so a derived view can refuse to be
        # laid over conditions that have moved since (409 site_conditions_changed)
        site_revision=site.revision if site is not None else 0,
        # ...and the FACTS, which are what the guard compares. The revision is
        # reported beside them and never guarded on.
        site_facts=dict(site_facts),
        knowledge_snapshot=knowledge.snapshot_set(),
        snapshot_hash=knowledge.snapshot_hash(),
        overrides_applied=sorted(applied),
        policy=policy,
        demand_skus=demand_skus,
    )
    # anything that changes what the run MEANS belongs in the digest, or
    # INSERT OR IGNORE (store/db.py) serves a stale document under a reused id:
    # - model_snapshot: which fence model(s)/versions the run actually drew from
    # - catalog_hash: the catalog content the run resolved products against
    #
    # `objective_preset` is deliberately NOT here, and it used to be here TWICE:
    # once by name and once inside `policy`, which DEFAULT_POLICY always
    # populates — so removing only the named one left the id unmoved and the
    # change inert while looking done. It is read by nothing in generate() — only
    # by resolve_supply, the panel preview and the impact preview — so keeping it
    # made the design id move for a SUPPLY reason. It belongs to the supply
    # identity (fulfillment/supply_run.py), beside the inventory and the prices.
    run_meta.model_snapshot = sorted(
        {u.sort_key(): u for u in models_used}.values(), key=ModelUse.sort_key
    )
    # - part_snapshot: which part version each named slot resolved to. Deduped and
    #   sorted for the same reason the models are: the same part reached through
    #   two segments is one fact about the run, and an order that varied with the
    #   walk would split the digest between two identical fences.
    run_meta.part_snapshot = sorted(
        {u.sort_key(): u for u in parts_used}.values(), key=PartUse.sort_key
    )
    run_meta.catalog_skus = _skus_used(strategy, demand_skus)
    run_meta.catalog_hash = catalog_hash(catalog, run_meta.catalog_skus)
    run_meta.catalog_schema_version = CATALOG_SCHEMA_VERSION
    # `policy` was already merged with DEFAULT_POLICY above, so the key always
    # exists — a `.get(..., "least_cost")` fallback here could never fire; direct
    # indexing says so instead of implying a fallback that is dead on arrival.
    run_meta.objective_preset = policy["objective_preset"]
    # exactly ONE key is stripped. `policy` carries design inputs too
    # (default_height_mm), and dropping the whole dict would make two genuinely
    # different fences hash the same — the opposite mistake, and the worse one.
    design_policy = {k: v for k, v in policy.items() if k != "objective_preset"}
    run_meta.id = "run_" + hashlib.sha256(
        json.dumps(
            # project_id is BOUND AS A SCOPE DIMENSION (bind_scope, above), so a
            # project-scoped rule changes the fence without changing any other
            # digest input. Two projects with the same topology then collide, and
            # `save_run`'s INSERT OR IGNORE drops the second silently: its user
            # presses Generate, sees their own answer in the response, and every
            # later read serves the other project's fence.
            [project_id, topology.model_dump(), run_meta.knowledge_snapshot,
             [o.model_dump() for o in overrides], design_policy,
             [u.model_dump() for u in run_meta.model_snapshot], run_meta.catalog_hash,
             [u.model_dump() for u in run_meta.part_snapshot],
             # The site FACTS, not `site_revision`. A revision is a counter that
             # moves when somebody saves the form, so hashing it would split the
             # digest between two runs of an identical fence; the facts are what
             # actually changed the answer. Exposure B and C are different
             # fences, and `save_run` is INSERT OR IGNORE — without this they
             # share an id and every later read of the second serves the first.
             site_facts,
             PLANNING_BEHAVIOR_VERSION, RUN_DIGEST_VERSION],
            sort_keys=True, default=str,
        ).encode()
    ).hexdigest()[:12]
    return GenerationResult(
        run=run_meta, strategy=strategy, graph=graph, orphaned_overrides=orphaned
    )


# --- knowledge-resolved selection helpers -----------------------------------

def _skus_used(strategy: Strategy, demand_skus: dict[str, str]) -> list[str]:
    """Every product this run named, from the run itself rather than from a list
    someone has to remember to extend.

    Eligibility MEMBERS, not just the chosen sku: the choice among them is made
    at read time by `resolve_supply`, so a run depends on the content of every
    candidate it may still pick — a rival's price changing is exactly a reason
    for the stored answer to be re-checked rather than silently kept.
    """
    skus = {p.sku for p in strategy.posts if p.sku}
    # The cap too, and it stopped being covered by `demand_skus` the moment a
    # MODEL could name its own: knowledge's `post_cap` is in that dict, a model's
    # cap is not, so a run buying CAP-V-90 recorded nothing that would make
    # repricing CAP-V-90 refuse the stored answer.
    skus |= {p.cap_sku for p in strategy.posts if p.cap_sku}
    skus |= {g.kit_sku for g in strategy.gates if g.kit_sku}
    skus |= set(demand_skus.values())
    for span in strategy.spans:
        if span.panel is None:
            continue
        for slot in span.panel.slots:
            skus |= {m.sku for m in slot.eligibility.members}
            if slot.sku:
                skus.add(slot.sku)
    return sorted(skus)


def bind_scope(*bindings: dict) -> dict[str, str]:
    """Bind evaluation-scope dimensions from the facts of this generation.

    A *dimension* is nothing more than a key/value pair present in the generation
    context — there is no enum of allowed dimensions and nothing here is specific
    to a catalog, a product family or to fences. A fact that is absent or empty
    leaves its dimension UNBOUND, so a rule scoped to it cannot match
    (`evaluator._scope_matches` compares `scope_ctx.get(k) == v`).
    """
    out: dict[str, str] = {}
    for binding in bindings:
        for key, value in binding.items():
            if value is None or value == "":
                continue
            out[key] = str(value)
    return out


class ConflictSink(list):
    """Every `Conflict` a run produces, in one place, so none can be dropped.

    Conflicts were surfaced at three of the ~13 resolution sites and discarded at
    the rest — `_resolve_mounting`, `_resolve_reinforcement`,
    `_resolve_default_post`, `_resolve_demand_skus`, `_resolve_quantity` and the
    panel limits all read `res.winner` and threw `res.conflicts` away. That was
    survivable while every hard-band tie RAISED. It stopped being survivable when
    a tie involving a published row became a flagged pick (contract §3.2.4): a
    published `require_mounting` disagreeing with an authored one now picks a
    winner by tie-break order and, at those sites, reported nothing at all —
    ground versus masonry, decided silently, on a run nobody warned.

    A sink rather than a return value, because the failure mode is FORGETTING:
    threading conflicts back up through six helpers means six chances to drop one,
    and the one that gets dropped is invisible. Passed once, everything lands in
    it, and `generate()` drains it in one place.

    A plain `list` subclass so it is obvious what it is at every call site, and so
    a caller cannot accidentally treat it as a value to be returned.
    """


def _post_ctx(
    scope: dict[str, str], site: dict, surface: str, context: str = ""
) -> dict:
    return {
        "scope": bind_scope(scope, {"surface": surface, "context": context}),
        "post": {"surface": surface, "context": context},
        # Whole-site facts, in EVERY context and never only in some: a site fact
        # that reached the bays and not the posts beside them would be a fence
        # built to two different sites. Threaded rather than read from anywhere,
        # because `generate()` is pure (ADR-0004).
        "site": site,
    }


def _resolve_mounting(
    kb: KnowledgeBase, scope: dict[str, str], site: dict, sink: ConflictSink, surface: str
) -> tuple[str, str | None, list[str]]:
    """(mounting, rule sku, governed refs) for a base surface — slot-scoped so rules
    for other surfaces never compete (critic finding 5)."""
    res = resolve_actions(
        kb, _post_ctx(scope, site, surface), "require_mounting",
        match=lambda a: a.surface == surface,
    )
    sink.extend(res.conflicts)
    if res.winner:
        act = res.winner.actions[0]
        return act.mounting, act.sku, [res.winner.version.ref]
    return "ground", None, []


def _resolve_reinforcement(
    kb: KnowledgeBase, scope: dict[str, str], site: dict, sink: ConflictSink
) -> tuple[str | None, list[str]]:
    """(reinforced-post sku, governed refs) for gate context, or (None, [])."""
    res = resolve_actions(
        kb, _post_ctx(scope, site, "", context="gate"), "require_post_reinforcement",
        match=lambda a: a.context == "gate",
    )
    sink.extend(res.conflicts)
    if res.winner:
        return res.winner.actions[0].sku, [res.winner.version.ref]
    return None, []


def _resolve_default_post(
    kb: KnowledgeBase, scope: dict[str, str], site: dict, sink: ConflictSink, surface: str
) -> tuple[str, list[str]]:
    res = resolve_actions(
        kb, _post_ctx(scope, site, surface), "default_component",
        match=lambda a: a.role == "post_ground",
    )
    sink.extend(res.conflicts)
    if res.winner:
        return res.winner.actions[0].sku, [res.winner.version.ref]
    # Knowledge names no default ground post. This used to raise — a run failed
    # over a gap, which contract §3.2.4 forbids. The post still STANDS where the
    # geometry puts it; only its product is unknown, and "" is how demand already
    # says that: `chosen("")` yields an eligibility nothing satisfies, the line
    # lands in `priced.unresolved`, and /bom reports it rather than refusing.
    # `_report_unfilled_posts` files the gap once for the run.
    return "", []


DEMAND_ROLE_DEFAULTS = {
    "rail": ("rail_sku", "RAIL-3000"),
    "screw": ("screw_sku", "SCREW-S10"),
    "concrete": ("concrete_sku", "CONC-25"),
    "cap": ("cap_sku", "POST-CAP"),
}


def _resolve_demand_skus(
    kb: KnowledgeBase, scope: dict[str, str], site: dict, sink: ConflictSink
) -> tuple[dict[str, str], list[str]]:
    """Demand product selection is knowledge (DefaultComponent roles), never a
    code literal — swapping the whole fence system (e.g. to a Barrette catalog)
    is a rule change. Falls back to the demo defaults when no rule exists."""
    skus: dict[str, str] = {}
    refs: list[str] = []
    for role, (key, fallback) in DEMAND_ROLE_DEFAULTS.items():
        res = resolve_actions(
            kb, _post_ctx(scope, site, ""),
            "default_component", match=lambda a, role=role: a.role == role,
        )
        sink.extend(res.conflicts)
        if res.winner:
            skus[key] = res.winner.actions[0].sku
            refs.append(res.winner.version.ref)
        else:
            skus[key] = fallback
    return skus, refs


def _resolve_quantity(
    kb: KnowledgeBase, ctx: dict, param: str, default: int, sink: ConflictSink,
) -> tuple[int, list[str]]:
    res = resolve_param(kb, ctx, param)
    sink.extend(res.conflicts)
    if res.winner:
        return (
            next(a.value for a in res.winner.actions if a.kind == "set_param"),
            [res.winner.version.ref],
        )
    return default, []


def _matched_force_overrides(
    overrides: list[Override], run_id: str, station: Mm
) -> tuple[str | None, str | None, list[Override]]:
    """(forced_sku, forced_mounting, matched overrides) at a station, within tolerance."""
    forced_sku = forced_mounting = None
    matched: list[Override] = []
    for ov in overrides:
        if ov.run_id != run_id:
            continue
        d = ov.directive
        if d.kind == "force_post_sku" and _near(d.station_mm, station):
            forced_sku = d.sku
            matched.append(ov)
        elif d.kind == "force_mounting" and _near(d.station_mm, station):
            forced_mounting = d.mounting
            matched.append(ov)
    return forced_sku, forced_mounting, matched



def _post_tilt_at(topo: Topology, run: Run, station: Mm) -> tuple[int, str | None]:
    """(tilt_deg, event id) for a post at this station, from the section's
    post_tilt event. Plumb (0) when no event. 'perpendicular' derives the angle
    from the local ground gradient, clamped to ±45°."""
    import math

    ev, _, _ = _interval_at(topo, run, station, "post_tilt")
    if ev is None or ev.payload.mode == "plumb":
        return 0, ev.id if ev is not None else None
    if ev.payload.mode == "custom":
        return ev.payload.tilt_deg, ev.id
    slope = local_slope_permille(topo, run, station)
    deg = round(math.degrees(math.atan(slope / 1000)))
    return max(-45, min(45, deg)), ev.id


def _stand_z(topo: Topology, run: Run, station: Mm) -> Mm:
    """The elevation a post STANDS on. Where a BUILT base carries the fence, the
    panels rest on the base top (see the span bottoms) and so does the post —
    measuring the post from the ground would run it straight through the wall."""
    gz = ground_z(topo, run, station)
    if base_surface_at(topo, run, station) in BUILT_BASES:
        top = base_top_at(topo, run, station)
        if top is not None:
            return gz + top[0]
    return gz



def _forced_vertical(force_vertical_ovs: list[Override], station: Mm) -> Override | None:
    """The `force_vertical` override covering this station, if one does.

    One matcher, two consumers: a bay, which records the override as applied and
    writes a decision node for it, and a post's panel facts, which only READ the
    mode the bay will be built to. A second copy of the interval test would be a
    second place for the two to disagree about which bays an override covers.
    """
    for ov in force_vertical_ovs:
        d = ov.directive
        if d.start_station_mm <= station <= d.end_station_mm:
            return ov
    return None


@dataclass(frozen=True)
class _PostFacts:
    """The panel facts a post's predicate may read, answerable at any station.

    Built once per run and asked per post, because everything it needs is either
    a property of the run (its knowledge scope, its vertical mode, its policy) or
    a question of the station (height, and therefore rail positions).

    THE cycle rule lives in what this class does NOT carry: no width, of either
    kind. A bay's clear opening is measured to its posts' faces, so a post chosen
    by that opening would be choosing itself. Everything below follows from the
    bay's HEIGHT, which is settled before any post is known:

        height -> rail positions -> post -> clear width -> infill fit

    The post's own KIND is passed to `at()` rather than held here, because it is
    the one fact that varies per STATION and not per run: end, corner, line, gate
    or transition is what decides which faces a routed post is cut on, and it
    comes from the topology rather than from any bay — so it joins the facts
    without joining the cycle.
    """

    topo: Topology
    run: Run
    kb: KnowledgeBase
    scope: dict[str, str]
    site: dict
    sink: ConflictSink
    run_ctx: dict
    policy: dict
    vertical: str
    force_vertical: list[Override]
    # model ref -> the count params its panels resolve under. Memoised because a
    # run asks this once per POST and the answer is per model: the knowledge
    # resolution behind `rails_per_span` is the same call `segment_model` makes.
    _params: dict[str, dict[str, int]] = dataclass_field(default_factory=dict)

    def at(self, model: FenceModel, station: Mm, kind: str) -> dict:
        gz = ground_z(self.topo, self.run, station)
        height, _src, _extra = _span_height(
            self.topo, self.run, station, gz, gz, self.policy
        )
        ov = _forced_vertical(self.force_vertical, station)
        vertical = ov.directive.mode if ov is not None else self.vertical
        # Which spec, asked with what a post's station can answer. A variant whose
        # condition reads the bay's WIDTH comes back "not applicable" here, which
        # is why `validate_model` refuses that variant on a model whose post is
        # matched on `rail_positions_mm` — the alternative is a post chosen
        # against rails the fence does not build.
        spec = choose_variant_by(
            model, {"panel": {"height_mm": height, "vertical": vertical}}
        ).spec
        return post_panel_facts(
            model_id=model.id, height_mm=height, vertical=vertical,
            rail_positions_mm=rail_positions_mm(spec, height, self.count_params(model)),
            kind=kind,
        )

    def count_params(self, model: FenceModel) -> dict[str, int]:
        cached = self._params.get(model.ref)
        if cached is None:
            seg_kb, seg_ctx = _segment_view(
                self.kb, self.scope, self.site, self.sink, self.run_ctx, model)
            cached = {
                "rails_per_span": _resolve_quantity(
                    seg_kb, seg_ctx, "rails_per_span", DEFAULT_RAILS_PER_SPAN,
                    self.sink)[0],
                "screws_per_span": _resolve_quantity(
                    seg_kb, seg_ctx, "screws_per_span", DEFAULT_SCREWS_PER_SPAN,
                    self.sink)[0],
            }
            self._params[model.ref] = cached
        return cached


def _run_post_facts(
    topo: Topology,
    run: Run,
    kb: KnowledgeBase,
    scope: dict[str, str],
    site: dict,
    sink: ConflictSink,
    overrides: list[Override],
    policy: dict,
) -> tuple[_PostFacts, Resolution, list[str], list[str]]:
    """One construction of a run's post facts, and the vertical resolution behind
    them: `(facts, resolution, governing refs, defeated refs)`.

    Node posts are generated before any run is walked and take only the first
    value; `_generate_run` takes all four, because the `choose_vertical_mode` node
    it writes cites the refs and reports the conflicts. Resolving the mode twice
    for one run would be two answers that could differ.
    """
    run_ctx = {"length_mm": run_length(topo, run),
               "slope_permille": max_slope_permille(topo, run)}
    vertical, refs, defeated, res = _vertical_mode(
        kb, {"scope": bind_scope(scope), "run": run_ctx, "site": site},
        run_ctx["slope_permille"],
    )
    facts = _PostFacts(
        topo=topo, run=run, kb=kb, scope=scope, site=site, sink=sink, run_ctx=run_ctx,
        policy=policy,
        vertical=vertical,
        force_vertical=[ov for ov in overrides if ov.run_id == run.id
                        and ov.directive.kind == "force_vertical"],
    )
    return facts, res, refs, defeated


@dataclass(frozen=True)
class _PostSide:
    """One bay a post stands beside.

    `sample_station` is a station INSIDE that bay, which is where the MODEL is
    sampled; `station` is the post's own, which is where the panel facts are
    asked. The two differ by a millimetre at the bay that ENDS here, because
    `fence_model_at` is half-open and answers for the bay that STARTS at a
    station — the same convention every other station question uses.
    """

    facts: _PostFacts
    station: Mm
    sample_station: Mm
    kind: str


def _post_sides(
    facts: _PostFacts, station: Mm, run_len: Mm, kind: str,
) -> list[_PostSide]:
    """The bays an interior post of one run stands between — one at each end of
    the run, two everywhere else.

    `kind` is the post's, not the side's: one post has one position, and both
    sides of it are being asked about the SAME post. Passed down rather than
    re-derived here, so the kind a predicate matches on is the kind the element
    is finally written with.
    """
    sides = []
    if station > 0:
        sides.append(_PostSide(facts, station, station - 1, kind))
    if station < run_len:
        sides.append(_PostSide(facts, station, station, kind))
    return sides


@dataclass(frozen=True)
class _ModelPost:
    """What the model(s) at one post asked for.

    The cap is a FUNCTION of the post rather than a sku, because which post
    finally stands here is not this function's decision: `_make_post` puts a
    forced sku, a masonry mount and a gate reinforcement above the model's post,
    each of them a post doing a different job. A cap resolved against the post
    the model WANTED is a cap for a post that is not on the drawing — and it is
    a wrong line on the BOM rather than a missing one, since it prices and fits
    nothing. So the answer is deferred to the one place that knows.

    It returns `(cap sku, the model refs that asked and got nothing, the
    candidates it passed over)`. The failure travels rather than being raised
    because a cap is cosmetic: every other unsupplied slot is a warning and an
    `unresolved` line, and a post is the exception (without one there is no fence
    to be one part short of).

    `post_rejected` and the cap's third element are what make the choice
    explainable. Both were computed and thrown away at `[0]`, so a post and a cap
    reached the BOM with no node in the graph naming what they beat — the gap
    `decisions/supply.py`'s docstring declares closed. They stay HERE, in
    generation, rather than travelling to `resolve_supply` with the rails,
    because a post's sku drives geometry: its face width sets the bay's clear
    width and its declared length reaches the setting-out sheet. Resolved at read
    time the drawing would move when the yard moved (ADR-0011).
    """

    post_sku: str | None = None
    post_rejected: list[str] = dataclass_field(default_factory=list)
    cap_for: Callable[[str], tuple[str | None, str | None, list[str]]] | None = None


def _model_post_skus(
    library: FenceModelLibrary,
    default_model: FenceModelChoice | None,
    catalog: Catalog,
    parts: PartLibrary | None,
    sides: list[_PostSide],
    resolved: dict[str, FenceModel] | None = None,
) -> _ModelPost:
    """The post and cap the MODEL(S) at this post ask for, if any of them asks.

    A post at a `fence_model` boundary — or a node post shared by two runs — is
    adjacent to bays built to two different models, and BOTH of their post specs
    apply to the one post — both asked about the same station and the same
    POSITION, because a corner is a corner to whichever line is turning it. This
    is not an arbitration: the candidate set is the INTERSECTION of their matched
    sets, an item covering both is the ordinary case
    and the whole point of matching by spec, and an empty intersection is a true
    fact about that fence rather than a tie to be broken. One side opinionated and
    the other `post=None` leaves the opinionated side's spec, because None is no
    opinion; neither opinionated leaves the knowledge path untouched.

    The cap is matched against the post ALREADY CHOSEN, which is the whole reason
    `cap` nests inside `PostSlot`. It is the model's post it reads, not whatever
    `_make_post` finally writes: a masonry or gate-reinforced post is doing a
    different job and beats the model's choice, and a cap is the model's answer
    about the model's post.

    Choosing among several matched candidates is `sorted-first`, not cost-based:
    a post is one line and the cut-plan coupling that makes `select_supply` worth
    running does not apply to an indivisible each. Recorded in the limitations
    rather than faked — a post line still carries its full eligibility into
    demand, so the choice remains explainable there.

    `resolved` is the run's part-resolution memo, threaded in for the same reason
    `segment_model` keeps one: resolving a document is a `model_copy(deep=True)`
    plus a recompile of every part spec, and this function ran it once per post
    SIDE — 135 resolutions for 68 posts on a 120 m run, half of them thrown away
    by the dedup on the very next line. The memo changes nothing about what is
    computed: `resolve_model_parts` is a pure function of `(model, parts)`, and
    `parts` is one library for the whole run.
    """
    claims: list[tuple[FenceModel, dict, list[str]]] = []
    for side in sides:
        choice = (fence_model_at(side.facts.topo, side.facts.run, side.sample_station)
                  or default_model)
        if choice is None:
            continue
        model = library.resolve(choice.model_id, choice.version_pin)
        if model is None or model.post is None:
            continue
        # Asked BEFORE resolution now, where it costs nothing: resolution copies
        # the document and never touches its id or version, so the ref it dedupes
        # on is the same either way — and the side whose claim is dropped no
        # longer pays for a resolution first.
        if any(m.ref == model.ref for m, _, _ in claims):
            continue        # both bays are the same model: one claim, not two
        # The post slot's predicate comes from the part it names, so the document is
        # compiled BEFORE it is matched — here as well as in `segment_model`, because
        # a node post is the one match that does not reach the model through a
        # segment. Nothing about the DAG moves: this is still strictly upstream of
        # `_matched`, which is where `match_spec`'s covering rule lives.
        model = _post_model(model, parts, resolved)
        panel = side.facts.at(model, side.station, side.kind)
        claims.append((model, panel, _matched_members(
            model.post.requirement.eligibility, catalog, panel)))
    if not claims:
        return _ModelPost()

    station = sides[0].station
    posts = _preferred([members for _, _, members in claims])
    if not posts:
        raise _no_post_failure(
            [(m, p, [x.sku for x in ms]) for m, p, ms in claims], catalog, station)

    capped = [(model, panel) for model, panel, _ in claims if model.post.cap is not None]
    if not capped:
        # no line here has an opinion about caps
        return _ModelPost(post_sku=posts[0], post_rejected=posts[1:])

    def cap_for(stood_sku: str) -> tuple[str | None, str | None, list[str]]:
        """The cap for the post that is ACTUALLY standing here.

        Intersected across every claiming model, exactly as the post is: both
        lines' cap specs apply to the one cap on the one post between them. The
        candidates it did NOT take travel back with it, because a cap that
        reaches the BOM with no record of what it beat is a priced choice the
        graph cannot account for."""
        stood = catalog.products.get(stood_sku)
        caps = [(model.ref, _matched_members(
            model.post.cap.eligibility, catalog,
            {**panel,
             **(chosen_post_facts(stood, panel["post"]) if stood is not None else {})},
        )) for model, panel in capped]
        agreed = _preferred([members for _, members in caps])
        if agreed:
            return agreed[0], None, agreed[1:]
        return None, ", ".join(sorted(ref for ref, _ in caps)), []

    return _ModelPost(post_sku=posts[0], post_rejected=posts[1:], cap_for=cap_for)


def _post_model(
    model: FenceModel, parts: PartLibrary | None, resolved: dict | None
) -> FenceModel:
    """The resolved document for a post match, memoised per run.

    The returned document is SHARED between every post that reaches the same
    model ref, which is safe only because nothing on this path writes to it:
    `_PostFacts.at` and `_matched` read the spec and the eligibility and return
    new objects. It is the same bargain `segment_model` already makes when it
    hands one `_SegmentModel` to every bay of a segment.

    `resolved is None` is a caller with no memo — the behaviour before the memo
    existed, kept so the function is testable without one.
    """
    if parts is None or resolved is None:
        return _with_parts(model, parts)[0]
    hit = resolved.get(model.ref)
    if hit is None:
        # Never caches a failure: `_with_parts` raises for a part with no active
        # version, and that refusal has to reach every post that asks, not just
        # the first.
        hit = resolved[model.ref] = _with_parts(model, parts)[0]
    return hit


def _cap_unsupplied(
    strategy: Strategy, asked: str | None, post_id: str, station: Mm,
) -> None:
    """A model asked for a cap and nothing covers the spec — against the post
    that ACTUALLY stands here, which is what `_make_post` hands back.

    The same code as the post's failure and a different severity, which is the
    whole distinction: a cap is cosmetic, so this is a note on an answer rather
    than a refusal of it."""
    if asked is None:
        return
    strategy.warnings.append(StrategyWarning(
        code="no_item_covers_part_spec", severity="warning",
        message=f"No item in the catalog covers {asked}'s cap specification at "
                f"station {station}; the post is uncapped.",
        params={"model": asked, "station_mm": station,
                "slot_key": "cap", "role": "cap"},
        element_refs=[post_id],
    ))


def _matched(eligibility, catalog: Catalog, facts: dict) -> list[str]:
    return [m.sku for m in match_eligibility(eligibility, catalog, facts).members]


def _matched_members(eligibility, catalog: Catalog, facts: dict) -> list:
    """`_matched`, keeping the PRIORITY — the company's stated preference.

    `_matched` drops it, which was fine while every consumer took `[0]` of a
    sorted set and threw the order away anyway. That is the bug: a slot offering
    two products got whichever sku sorted first, so a declared first preference
    lost to the letter it starts with.
    """
    return list(match_eligibility(eligibility, catalog, facts).members)


def _preferred(claims: list[list]) -> list[str]:
    """The candidates EVERY claim accepts, best first.

    Two models can claim one post — a boundary between two lines — and both
    specs apply to the one post standing between them. Each ranks the common
    candidates by its own `priority`; if they all rank them the SAME way, that
    order is the company's answer and it is used.

    If they disagree there is no honest winner, so the tie breaks alphabetically
    — which is what this code did unconditionally before. Deliberately NOT
    "first claim wins": claims are built by walking the drawing, so that would
    make which cap gets bought depend on the shape of the fence, and a
    preference honoured for a reason nobody can state is worse than a tie
    admitted.

    Predicate-authored eligibility comes back from `match_eligibility` over
    `sorted(catalog.products)` with every priority at its default, so every claim
    ranks it identically and identically to `sorted()` — those slots keep exactly
    today's behaviour, which is why no golden file moves.
    """
    common = set.intersection(*(set(m.sku for m in ms) for ms in claims))
    if not common:
        return []
    orders = {
        tuple(sorted(common, key=lambda sku: (rank.get(sku, 0), sku)))
        for rank in ({m.sku: m.priority for m in ms} for ms in claims)
    }
    return list(orders.pop()) if len(orders) == 1 else sorted(common)


def _no_post_failure(
    claims: list[tuple[FenceModel, dict, list[str]]], catalog: Catalog, station: Mm,
) -> GenerationFailure:
    """Which of the two post errors this is. They do not overlap, and the
    distinction is the whole value of the diagnostic.

    A post is an ERROR and not a warning, unlike every other unsupplied slot: an
    unsupplied rail is a panel visibly one part short, and a post is not a line
    item — without one there is no fence to be short of.
    """
    empty = [(model, panel) for model, panel, skus in claims if not skus]
    if not empty:
        # Every side found candidates and no product satisfies them all. Not an
        # arbitration and not a near miss — a genuine disagreement between two
        # product lines about the post that has to serve both.
        refs = ", ".join(sorted(m.ref for m, _, _ in claims))
        return GenerationFailure(
            f"The bays either side of station {station} are built to {refs}, and no "
            f"post in the catalog satisfies both specifications.",
            code="post_spec_conflict", station_mm=station, models=refs,
        )
    model, panel = empty[0]
    predicate = model.post.requirement.eligibility.predicate
    diagnosis = (sole_excluding_term(predicate, catalog, panel)
                 if predicate is not None else None)
    if diagnosis is not None:
        term, near_miss = diagnosis
        paths = sorted(field_paths(term))
        if "panel.rail_positions_mm" in paths:
            # Routing ALONE excluded every candidate. A routed post's holes are
            # punched at the factory, so this is not a worse choice — it is a
            # fence that cannot be assembled, and the sentence can name both
            # position sets because exactly one term is responsible for the gap.
            wanted = _mm_list(panel["panel"]["rail_positions_mm"])
            found = sorted({
                _mm_list(item_value(catalog.products[sku], path))
                for sku in near_miss for path in paths if path.startswith("item.")
            })
            return GenerationFailure(
                f"The panel at station {station} wants rails at {wanted}, and "
                f"{model.ref}'s posts are routed at {'; '.join(found)}.",
                code="post_routing_mismatch", station_mm=station, model=model.ref,
                # semicolons BETWEEN products, commas WITHIN one position set —
                # "200, 1700, 250, 1750" reads as one four-hole post
                wanted=wanted, routed="; ".join(found),
            )
    return GenerationFailure(
        f"No item in the catalog covers {model.ref}'s post specification at "
        f"station {station}.",
        code="no_item_covers_part_spec", station_mm=station, model=model.ref,
        slot_key=model.post.key, role=model.post.requirement.role,
    )


def _mm_list(value) -> str:
    """A position set as a sentence fragment. Deliberately unitless: the client
    renders `{...}` values in the reader's display unit, and a literal "mm" here
    would keep saying mm after they switch to cm."""
    return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)


def _make_post(
    builder: GraphBuilder,
    kb: KnowledgeBase,
    scope: dict[str, str],
    site: dict,
    sink: ConflictSink,
    *,
    post_id: str,
    run_ref: str,
    station: Mm,
    kind: str,
    surface: str,
    ground_z_mm: Mm,
    base_z_mm: Mm | None = None,
    inputs: list[str],
    reinforced: bool = False,
    reinforcement_refs: list[str] | None = None,
    reinforced_sku: str | None = None,
    pinned: bool = False,
    forced_sku: str | None = None,
    forced_mounting: str | None = None,
    override_nodes: list[str] | None = None,
    tilt_deg: int = 0,
    model_post: str | None = None,
    model_post_rejected: list[str] | None = None,
    model_cap: Callable[[str], tuple[str | None, str | None, list[str]]] | None = None,
) -> tuple[Post, str | None]:
    """Create a post; every selection resolved from knowledge BEFORE the decision
    node is recorded — elements are never mutated afterwards (critic finding 4).

    Returns the post and, when a model asked for a cap that nothing covers, the
    refs that asked — the caller files that warning, because it is the one
    holding the strategy. The cap is resolved HERE and not by the caller for the
    same reason the post's sku is: the precedence below is what decides which
    post stands, and a cap chosen before it would be a cap for another post."""
    mounting, mount_sku, governed = _resolve_mounting(kb, scope, site, sink, surface)
    if forced_mounting:
        mounting = forced_mounting
    if forced_sku:
        sku = forced_sku
        sku_refs: list[str] = []
    elif mounting == "masonry" and mount_sku:
        sku = mount_sku
        sku_refs = []
    elif reinforced and reinforced_sku:
        sku = reinforced_sku
        sku_refs = []
    elif model_post is not None:
        # The MODEL's ordinary post. Deliberately below the three above: a forced
        # sku is an explicit user patch, and a masonry or gate-reinforced post is
        # doing a different JOB from the one a product line ships — bolted to a
        # wall, or carrying a leaf. A line that has no variant for those cases
        # would otherwise silently replace a post chosen for its situation.
        sku = model_post
        sku_refs = []
        rejected = list(model_post_rejected or [])
    else:
        sku, sku_refs = _resolve_default_post(kb, scope, site, sink, surface)
    # Only the MODEL's post had a field of candidates to pass over. A forced sku,
    # a masonry mount, a gate reinforcement and the knowledge default each name
    # ONE product for their own reason, and reporting the model's rejects beside
    # one of those would credit this post with a comparison it never made.
    if sku != model_post:
        rejected = []
    cap_sku, cap_unsupplied, cap_rejected = (
        model_cap(sku) if model_cap else (None, None, []))
    post = Post(
        id=post_id, run_ref=run_ref, station_mm=station, kind=kind,  # type: ignore[arg-type]
        reinforced=reinforced, mounting=mounting, sku=sku,  # type: ignore[arg-type]
        ground_z_mm=ground_z_mm, base_z_mm=base_z_mm, tilt_deg=tilt_deg, pinned=pinned,
        cap_sku=cap_sku or "",
    )
    builder.add(
        "structural", "place_post",
        payload={"station_mm": station, "kind": kind, "surface": surface,
                 "mounting": mounting, "sku": sku,
                 # What this post and its cap were bought INSTEAD OF. Omitted
                 # when there was nothing to compare: a `rejected: []` beside a
                 # chosen sku reads as "we looked and the field was empty", and
                 # every shipped model has exactly one eligible member per slot,
                 # so the empty key would be on every node of every run.
                 **({"rejected": rejected} if rejected else {}),
                 **({"cap_sku": cap_sku} if cap_sku else {}),
                 **({"cap_rejected": cap_rejected} if cap_rejected else {}),
                 **({"base_z_mm": base_z_mm} if base_z_mm is not None
                    and base_z_mm != ground_z_mm else {}),
                 **({"tilt_deg": tilt_deg} if tilt_deg else {})},
        scope_refs=[post.id],
        inputs=inputs + (override_nodes or []),
        governed_by=governed + (reinforcement_refs or []) + sku_refs,
        status="pinned" if pinned else "proposed",
    )
    return post, cap_unsupplied


# --- node posts ---------------------------------------------------------------

def _generate_node_posts(
    topology: Topology,
    kb: KnowledgeBase,
    scope: dict[str, str],
    site: dict,
    sink: ConflictSink,
    catalog: Catalog,
    overrides: list[Override],
    policy: dict,
    builder: GraphBuilder,
    strategy: Strategy,
    applied: set[str],
    library: FenceModelLibrary | None = None,
    default_model: FenceModelChoice | None = None,
    parts: PartLibrary | None = None,
    resolved_posts: dict | None = None,
) -> None:
    touches_by_node: dict[str, list[tuple[Run, Mm]]] = {}
    for run in topology.runs:
        touches_by_node.setdefault(run.start_node_id, []).append((run, 0))
        touches_by_node.setdefault(run.end_node_id, []).append(
            (run, run_length(topology, run))
        )

    reinf_sku, reinf_refs = _resolve_reinforcement(kb, scope, site, sink)

    for node in topology.nodes:
        touches = sorted(touches_by_node.get(node.id, []), key=lambda t: t[0].id)
        if not touches:
            continue
        # context from ALL incident runs (critic finding 9)
        surfaces = sorted({base_surface_at(topology, r, s) for r, s in touches})
        surface = "masonry_wall" if "masonry_wall" in surfaces else surfaces[0]
        conflict_inputs: list[str] = []
        if len(surfaces) > 1:
            cnode = builder.add(
                "conflict", "node_surface_disagreement",
                payload={"node_id": node.id, "surfaces": surfaces, "chosen": surface},
            )
            strategy.warnings.append(
                StrategyWarning(
                    code="node_surface_disagreement", severity="warning",
                    message=f"Runs meeting at node {node.id} disagree on base surface "
                            f"({', '.join(surfaces)}); using {surface}.",
                    params={"node_id": node.id, "surfaces": ", ".join(surfaces),
                            "chosen": surface},
                    decision_ref=cnode.id,
                )
            )
            conflict_inputs = [cnode.id]

        # gate adjacency: a gate edge at a run terminus reinforces the node post
        reinforced = False
        for r, s in touches:
            for ev in r.point_events:
                if ev.payload.kind == "gate":
                    gs = anchor_station(topology, r, ev.anchor)
                    ge = min(gs + ev.payload.width_mm, run_length(topology, r))
                    if _near(gs, s) or _near(ge, s):
                        reinforced = True

        forced_sku = forced_mounting = None
        matched_all: list[Override] = []
        for r, s in touches:
            fs, fm, matched = _matched_force_overrides(overrides, r.id, s)
            forced_sku = fs or forced_sku
            forced_mounting = fm or forced_mounting
            matched_all += matched
        override_nodes = []
        for ov in matched_all:
            applied.add(ov.id)
            override_nodes.append(
                builder.add(
                    "override_applied", ov.directive.kind,
                    payload={"override_id": ov.id, "node_id": node.id},
                ).id
            )

        run0, station0 = touches[0]
        # A two-run node is a corner only if the fence actually TURNS there.
        # `finishDraft` makes one run per drawn segment, so every intermediate
        # click on a straight line is a two-run node — and while `kind` was only
        # a label, calling those corners cost nothing. It is a PART NUMBER now:
        # a vinyl corner post is routed on two ADJACENT faces, so a straight
        # node classified `corner` buys a post that physically cannot receive
        # both its rails, priced and on the BOM. Same threshold, and the same
        # measurement, as the interior-vertex path in `corner_stations`.
        if len(touches) == 1:
            kind = "end"
        elif len(touches) == 2:
            kind = ("corner"
                    if node_turn_deg(topology, node.id, touches) > CORNER_ANGLE_DEG
                    else "line")
        else:
            kind = "junction"
        fact = builder.add(
            "input_fact", "topology_node",
            payload={"node_id": node.id, "x_mm": node.x_mm, "y_mm": node.y_mm,
                     "runs": len(touches)},
        )
        # A node post is adjacent to a bay on EVERY run that touches it, and all
        # of their models claim it — the same intersection an interior boundary
        # post gets. The facts are asked per run, because a terminus of one run
        # and the mid-run station of another need not be at the same height.
        model_post = _ModelPost()
        if library is not None:
            model_post = _model_post_skus(
                library, default_model, catalog, parts,
                [_PostSide(
                    _run_post_facts(topology, r, kb, scope, site, sink, overrides, policy)[0],
                    s, s if s == 0 else s - 1, kind,
                ) for r, s in touches],
                resolved_posts,
            )
        post, cap_gap = _make_post(
            builder, kb, scope, site, sink,
            model_post=model_post.post_sku, model_post_rejected=model_post.post_rejected,
            model_cap=model_post.cap_for,
            post_id=f"post@node:{node.id}", run_ref=f"node:{node.id}",
            station=station0, kind=kind, surface=surface,
            ground_z_mm=ground_z(topology, run0, station0),
            base_z_mm=_stand_z(topology, run0, station0),
            inputs=[fact.id] + conflict_inputs,
            reinforced=reinforced and surface != "masonry_wall",
            reinforcement_refs=reinf_refs if reinforced else [],
            reinforced_sku=reinf_sku,
            forced_sku=forced_sku, forced_mounting=forced_mounting,
            override_nodes=override_nodes,
        )
        _cap_unsupplied(strategy, cap_gap, post.id, station0)
        strategy.posts.append(post)


# --- per-run generation --------------------------------------------------------

def _with_parts(
    model: FenceModel, parts: PartLibrary | None
) -> tuple[FenceModel, list[PartUse]]:
    """The model document with its part references compiled into predicates.

    Strictly UPSTREAM of every `match_spec`/`_matched` below, which is the point:
    the `height -> rail positions -> post -> clear width -> infill` DAG does not
    move, and neither does anything else in this module's ordering. Compilation
    happens, and then everything downstream is what it was.

    `parts is None` returns the document untouched — a caller with no library gets
    exactly the behaviour it had before parts existed. Returns a NEW document
    (`resolve_model_parts` copies), because `generate()` is pure and the library's
    stored model must not acquire a resolved predicate as a side effect of a run.

    The `ValueError` is the one a part with no active version raises.
    `_validate_resolved_model` normally reports it first, in the voice a route can
    render; this is the net under the paths that never validated — a node post
    resolves its model before any segment does.
    """
    if parts is None:
        return model, []
    try:
        return resolve_model_parts(model, parts)
    except ValueError as e:
        raise GenerationFailure(
            f"fence model {model.ref} cannot be used: {e}",
            code="fence_model_invalid",
            model_ref=model.ref, errors=str(e), n=1,
        )


def _validate_resolved_model(
    model: FenceModel, catalog: Catalog, parts: PartLibrary | None = None
) -> None:
    """The production caller `validate_model` did not have.

    Models are only ever built by `legacy_model()`, which bypassed validation
    entirely, so every load-time gate on the fence-model branch — the unbuilt
    feature refusals, the per-member advance bound, the SKU and length checks —
    was enforced by tests alone. That is tolerable while exactly one built-in
    model exists and becomes load-bearing the moment a model can be authored;
    a gate with no caller is a gate that has never run against real data.

    A `GenerationFailure`, not a warning, and not a `StrategyWarning` on the
    strategy. Every error this returns means the panel that WOULD be built is
    not the panel that was authored:

      * an unbuilt feature (`Eligibility.group`, `Eligibility.predicate`,
        `InfillSpec.supply`, …) is ignored by `resolve_panel`, so the run is
        silently a different fence — the precise failure mode `_unsupported_
        features` exists to prevent, and surfacing it as a survivable note
        would reinstate it with a yellow triangle instead of a green light;
      * a member whose net advance is not positive makes `fit_pattern` loop
        forever, so there is no answer to soften;
      * an eligible sku absent from the catalog, or one that cannot supply the
        length its slot asks for, makes the BOM name a product that cannot do
        the job.

    None of those is survivable, which is exactly the line `GenerationFailure`
    draws against a Conflict (`core/errors.py`, knowledge-system.md). The route
    already maps it to 422.

    Cost: it does not touch the topology, so it does not grow with the fence — it
    runs once per distinct model CHOICE on a run (memoised in `segment_model`),
    never once per segment and never once per span, and a run built entirely to
    one model validates once.

    It is NOT O(model) any more, and the `M-LEGACY` measurement this paragraph used
    to quote was the one model that could never show it: a model naming no part
    reaches the catalog by dict lookup only, and it still costs 2.9 us. A model
    whose slots name PARTS asks the matcher "would anything satisfy this?" per
    slot, which is a full-catalog scan — 334 us for `M-VINYL` against a four-bay
    `generate()` of 3.3 ms (10%), and 23 ms against a 4623-product catalog. That
    is the price of refusing at authoring what would otherwise be
    `no_eligible_item` on every bay of every job, and the scan itself is what
    `match._item_ctx`'s memo made affordable.

    Still no cache HERE, and now for a reason that survives the numbers: the memo
    that would pay for itself is one over the model choice, and `segment_model`
    already holds it.
    """
    errors = validate_model(model, catalog, parts)
    if not errors:
        return
    # The failure a USER can cause gets a code its locale bundle can render: a
    # DefaultComponent's sku is a free-text field, and "the action failed (422)"
    # names neither the sku nor the fact that a sku is the problem — while the
    # strategy the user was working on is gone. The remaining errors are English
    # authoring text for someone editing a model, which no route can do yet.
    missing = unknown_skus(model, catalog)
    if missing:
        raise GenerationFailure(
            f"fence model {model.ref} names {len(missing)} sku(s) the catalog does "
            f"not stock: {', '.join(missing)}",
            code="fence_model_unknown_sku",
            skus=", ".join(missing), model_ref=model.ref, n=len(missing),
        )
    raise GenerationFailure(
        f"fence model {model.ref} cannot be used: " + "; ".join(errors),
        code="fence_model_invalid",
        model_ref=model.ref, errors="; ".join(errors), n=len(errors),
    )


@dataclass(frozen=True)
class _SegmentModel:
    """A model choice, resolved once and reused by every segment that makes it."""

    model: FenceModel
    use: ModelUse
    options: dict[str, str | int]
    select_node_id: str
    max_span: Mm
    # "" when no rule covered it and `max_span` is the fallback basis below —
    # an empty ref rather than an invented one, because every `governed_by` edge
    # citing it would otherwise name a rule nobody wrote.
    max_span_ref: str
    firing_node_id: str
    rails_per_span: int
    screws_per_span: int
    quantity_refs: list[str]
    # a manufactured bay width, when the model's line ships as pre-assembled
    # panels: not a preference, so it does not compete with one
    exact_span: Mm | None = None
    exact_span_ref: str | None = None
    # No rule covered `max_span_mm` here, so `max_span` is FALLBACK_MAX_SPAN_MM
    # and every bay laid out to it is warned. Carried on the segment model
    # because the gap is discovered where the parameter resolves and reported
    # where the bays it affected are known.
    max_span_assumed: bool = False
    # WHICH basis, when there was no rule: our invented fallback, or the width
    # the model's own line is manufactured in. They are not the same claim and a
    # warning that called the second one "a fallback" would be telling the reader
    # we guessed a number the manufacturer stated.
    max_span_basis: Literal["rule", "fallback", "manufactured_width"] = "rule"


LEGACY_MODEL_ID = "M-LEGACY"
LEGACY_MODEL_VERSION = 1

# The counts a model contributes when no knowledge names them. Constants because
# a bay and the POST beside it must resolve the same number: the rail count
# decides where the rails sit, and a routed post is matched against exactly those
# positions. Two spellings of `2` would be a post routed for a panel nobody built.
DEFAULT_RAILS_PER_SPAN = 2
DEFAULT_SCREWS_PER_SPAN = 8

# The span basis a run is laid out to when NO rule covers `max_span_mm`.
#
# This is not a safety limit and must never be read as one. It is a provisional
# layout basis that exists so an uncovered exposure category produces a plan with
# a visible hole in it rather than no plan at all (contract §3.2.4). Every bay
# built to it carries `warning.uncovered_max_span` and the run carries a `Gap`
# naming the row that would close it, so the number is never the quiet answer —
# it is the loud one.
#
# 1800 mm because it is the most conservative figure in the demo knowledge and
# a fence laid out tighter than it needs to be is a fence that stands up. A
# fallback that guessed WIDER would be a fallback that could fall down.
FALLBACK_MAX_SPAN_MM = 1800


def _policy_knowledge(model: FenceModel) -> list[KnowledgeVersion]:
    """A model's `layout_policy` as knowledge versions scoped to its own series.

    The model gets NO private channel into the generator (fence-model spec §"Two
    touch points"): what it asks of the span layout enters the same evaluator as
    a company rule, resolves by the same tiers, and loses out loud when it loses.

    Authority is per CONTRIBUTION, never per model, and that is the whole reason
    the contribution carries its own `knowledge_type`: `DEFAULT_AUTHORITY` puts
    hard_constraint at 1 and company_rule at 3, so emitting a manufacturer's
    maximum span and a nominal panel width at one authority makes exactly one of
    them wrong — an unbeatable preference, or a beatable safety limit.

    The ref reads `M-SLAT#max_span_mm@v1`: a knowledge-shaped id that cannot
    collide with an authored knowledge object, so a `governed_by` edge citing one
    is legible as "the model asked for this" rather than as a rule someone could
    go and edit. These versions are never stored — the run's model snapshot
    (id, version, content hash) is what makes them reproducible.
    """
    return [
        KnowledgeVersion(
            object_id=f"{model.id}#{c.param}",
            version=model.version,
            type=c.knowledge_type,
            authority=c.authority,
            scope={"series": model.id},
            actions=[SetParam(param=c.param, value=c.value)],
            title=f"{model.ref} model policy: {c.param} = {c.value}",
            title_i18n={"he": f"מדיניות הדגם {model.ref}: {c.param} = {c.value}"},
            attributed_to="fence_model",
            derived_from=[model.ref],
        )
        for c in model.layout_policy
    ]


def _segment_view(
    kb: KnowledgeBase, scope: dict[str, str], site: dict, sink: ConflictSink, run_ctx: dict,
    model: FenceModel,
) -> tuple[KnowledgeBase, dict]:
    """The knowledge and the context a model's numbers resolve under.

    `series` is the dimension a knowledge rule needs to say "spans exactly 1800 on
    that product line", and a model's own `layout_policy` joins the base as
    knowledge rather than through a private channel. The run's KnowledgeBase is
    never mutated — `generate()` does not touch its inputs — so this is a per-model
    VIEW of it and one model's asks cannot survive into the next.

    One function because two callers ask the same question about one model: the
    segment that lays out its bays, and the post that stands beside them.
    """
    seg_kb = (KnowledgeBase(versions=[*kb.versions, *_policy_knowledge(model)])
              if model.layout_policy else kb)
    return seg_kb, {"scope": bind_scope(scope, {"series": model.id}),
                    "run": run_ctx, "site": site}


def _vertical_mode(
    kb: KnowledgeBase, ctx: dict, slope_permille: int,
) -> tuple[str, list[str], list[str], Resolution]:
    """This run's vertical mode: (mode, governing refs, defeated refs, resolution).

    Pulled out of `_generate_run` because a post's panel facts need the answer
    BEFORE the run's own decision node is written — a post is resolved before any
    bay exists, and `panel.vertical` is one of the facts its predicate may read.
    The caller still owns the node and the conflicts; this owns the answer, so
    there is exactly one of it.
    """
    vert_firings = preference_firings(kb, ctx, {"prefer_vertical"})
    modes = {a.mode for f in vert_firings for a in f.actions if a.kind == "prefer_vertical"}
    res: Resolution = evaluator_resolve(
        vert_firings, "vertical_mode", values_agree=len(modes) <= 1
    )
    if res.winner:
        mode = next(a.mode for a in res.winner.actions if a.kind == "prefer_vertical")
        return (mode, [res.winner.version.ref],
                [f.version.ref for f in res.firings if f.defeated_by], res)
    return ("level" if slope_permille == 0 else "raked", [], [], res)


def _pick_model(
    library: FenceModelLibrary,
    choice: FenceModelChoice | None,
    default_choice: FenceModelChoice | None,
    demand_skus: dict[str, str],
) -> tuple[FenceModel, str]:
    """(model, where the choice came from) for one stretch of fence.

    An interval event beats the project default, which beats the built-in
    compatibility model — the same precedence base and height already use.

    M-LEGACY is a deliberate exception and the only one: it is rebuilt from the
    run's resolved demand skus rather than served from the library, because its
    eligibility exists to carry whatever `DefaultComponent` knowledge resolved to.
    A stored M-LEGACY document naming RAIL-3000 would quietly outrank a rule that
    changed the rail — the failure this seam exists to prevent. Every other model
    names its own products, which is the whole point of authoring one.
    """
    effective = choice or default_choice
    source = "event" if choice else ("project" if default_choice else "builtin")
    legacy = lambda: legacy_model(  # noqa: E731
        rail_sku=demand_skus.get("rail_sku", "RAIL-3000"),
        screw_sku=demand_skus.get("screw_sku", "SCREW-S10"),
    )
    if effective is None:
        return legacy(), source
    if effective.model_id == LEGACY_MODEL_ID:
        # M-LEGACY has exactly one version, for ever: the route reserves the id
        # (`_reserved`), so nothing can publish a v2 the picker would offer and
        # this seam would then ignore. A pin naming any other version is a
        # refusal rather than a silent fallback — accepting it here is how the
        # picker, the preview and the impact report end up agreeing on a model
        # generation refuses to build.
        if effective.version_pin not in (None, LEGACY_MODEL_VERSION):
            raise GenerationFailure(
                f"fence model {LEGACY_MODEL_ID}@v{effective.version_pin} does not "
                f"exist: the compatibility model has only v{LEGACY_MODEL_VERSION}",
                code="fence_model_not_found",
                model_id=LEGACY_MODEL_ID, version_pin=effective.version_pin,
            )
        return legacy(), source
    model = library.resolve(effective.model_id, effective.version_pin)
    if model is None:
        pinned = "" if effective.version_pin is None else f"@v{effective.version_pin}"
        raise GenerationFailure(
            f"fence model {effective.model_id}{pinned} is not available: it does not "
            "exist, or no version of it is active",
            code="fence_model_not_found",
            model_id=effective.model_id,
            version_pin=effective.version_pin if effective.version_pin is not None else "",
        )
    return model, source


def _post_at(strategy: Strategy, run: Run, station: Mm, run_len: Mm):
    """The post standing at this station of this run, if one does.

    A run END is a shared node post, recorded against the NODE (`node:<id>`)
    rather than against either run that meets there — one corner has one post,
    and two runs must not each contribute their own face to it.
    """
    for post in strategy.posts:
        if post.run_ref == run.id and post.station_mm == station:
            return post
    node_id = (run.start_node_id if station == 0 else
               run.end_node_id if station == run_len else None)
    if node_id is None:
        return None
    return next((p for p in strategy.posts if p.run_ref == f"node:{node_id}"), None)


def _post_face_width(strategy: Strategy, run: Run, station: Mm, run_len: Mm,
                     catalog: Catalog) -> Mm:
    """How wide the post at this station is as SEEN — its extent along the run.

    0 when there is no post, no product, or the product declares no
    `face_width_mm`; `clear_opening_mm` documents why that is a zero and not a
    nominal.
    """
    post = _post_at(strategy, run, station, run_len)
    product = catalog.products.get(post.sku) if post is not None and post.sku else None
    face = product.capabilities.face_width_mm if product is not None else None
    return face or 0


def _generate_run(
    topo: Topology,
    run: Run,
    kb: KnowledgeBase,
    scope: dict[str, str],
    site: dict,
    sink: ConflictSink,
    catalog: Catalog,
    overrides: list[Override],
    policy: dict,
    builder: GraphBuilder,
    strategy: Strategy,
    applied: set[str],
    demand_skus: dict[str, str],
    models_used: list[ModelUse],
    library: FenceModelLibrary,
    default_model: FenceModelChoice | None,
    parts: PartLibrary | None,
    parts_used: list[PartUse],
    resolved_posts: dict | None = None,
) -> None:
    length = run_length(topo, run)
    slope_permille = max_slope_permille(topo, run)
    run_fact = builder.add(
        "input_fact", "run_geometry",
        payload={"run_id": run.id, "length_mm": length, "slope_permille": slope_permille},
    )
    ctx = {
        "scope": bind_scope(scope),
        "run": {"length_mm": length, "slope_permille": slope_permille},
        "site": site,
    }

    # -- the model, and everything scoped to it --------------------------------
    # A fence_model interval event may change the model partway along the run, so
    # the model — and the numbers resolved under its `series` scope — belong to a
    # SEGMENT, not to the run. Memoised on the choice: with no event and no project
    # default there is exactly one choice, hence one validation, one select_model
    # node and one resolve_max_span node, which is what every run had before a
    # model could be chosen at all.
    #
    # Resolution is lazy, on first use by a segment. Resolving eagerly would emit a
    # select_model node and count a model in the run's snapshot for a model that no
    # bay is built to — the graph is the explanation, and it must not describe a
    # choice the fence never made.
    resolved: dict[tuple | None, _SegmentModel] = {}

    def segment_model(choice: FenceModelChoice | None) -> _SegmentModel:
        key = choice.key() if choice else None
        cached = resolved.get(key)
        if cached is not None:
            return cached

        # the EFFECTIVE choice, because the options belong to whichever choice
        # actually applied — reading them off the interval event alone silently
        # drops every option a project default carried
        effective = choice or default_model
        options = dict(effective.options) if effective else {}
        model, source = _pick_model(library, choice, default_model, demand_skus)
        # Validation reads the document a bay will actually be built from, so it
        # resolves the same references this line does — see `validate_model`. It
        # runs first because it is the one that reports a broken part reference
        # with a code a route can render.
        _validate_resolved_model(model, catalog, parts)
        # The model's part references become predicates HERE, at the moment the
        # document is chosen for a segment, and the resolved document is what every
        # line below uses. Upstream of `match_spec` and of `resolve_panel`: the
        # `height -> rail positions -> post -> clear width -> infill` DAG is
        # untouched, and so is the order of this function's phases.
        model, part_uses = _with_parts(model, parts)
        # `series` is the dimension a knowledge rule needs to say "spans exactly
        # 1800 on that product line" — blocked until a model id was a fact of
        # generation (plan/current-status.md, the two blocked dimensions). The
        # model's layout policy joins the knowledge BEFORE anything under this
        # scope is resolved: a contribution added after `max_span_mm` had resolved
        # would be a contribution that never applied.
        seg_kb, seg_ctx = _segment_view(kb, scope, site, sink, ctx["run"], model)
        select_node = builder.add(
            "selection", "select_model",
            payload={"run_id": run.id, "model_ref": model.ref, "source": source,
                     "options": options},
            inputs=[run_fact.id],
        )

        res = resolve_param(seg_kb, seg_ctx, "max_span_mm")
        # No rule covers it. This used to raise, which made an uncovered exposure
        # category produce no plan at all on the single most important parameter
        # in the system — a run failed over a GAP, which contract §3.2.4 forbids.
        # The run proceeds on FALLBACK_MAX_SPAN_MM and says so, twice: a `gap`
        # node here instead of a rule firing, and one warning per section naming
        # every bay laid out to it (`_report_uncovered_max_span`).
        assumed = res.winner is None
        max_span_mm: Mm = (
            FALLBACK_MAX_SPAN_MM if assumed
            else next(a.value for a in res.winner.actions if a.kind == "set_param")
        )
        # A DISAGREEING TIE inside the hard band, survivable only because one
        # contender is published (`evaluator.resolve`). Never let the alphabet
        # decide a safety limit: the tie-break that picks a winner is
        # `object_id` last, so renaming a row would otherwise flip a 1200 mm
        # maximum to 2400 mm and quote it. Take the most restrictive number every
        # contender could live with. Lower is safer HERE and the direction is not
        # general — `min_rail_separation_mm` is the opposite — which is why this
        # is at the site that knows its parameter and not in the evaluator.
        if any(c.hard for c in res.conflicts):
            max_span_mm = min(a.value for f in res.firings for a in f.actions
                              if a.kind == "set_param")
        # a manufactured bay width, if this model's line has one. Resolved under
        # the same segment scope as the rest, so a model contributes it through
        # `layout_policy` rather than through a private channel. Resolved BEFORE
        # the decision node below, because when the maximum is assumed this is an
        # input to it — a node reporting 1800 for a basis of 2400 would explain a
        # fence the run did not build.
        exact_res = resolve_param(seg_kb, seg_ctx, "exact_span_mm")
        sink.extend(exact_res.conflicts)
        exact_span = exact_span_ref = None
        if exact_res.winner is not None:
            exact_span = next(a.value for a in exact_res.winner.actions
                              if a.kind == "set_param")
            exact_span_ref = exact_res.winner.version.ref

        # A manufactured bay width beats an INVENTED maximum. If nobody stated a
        # max span and the model declares the width its line actually ships in,
        # that number is authored data and `FALLBACK_MAX_SPAN_MM` is not — so the
        # fallback yields to it rather than judging it. Without this the run laid
        # out 1800 mm bays for 2400 mm panels and reported, at ERROR severity,
        # that the panels exceeded "the 1800 mm maximum span" — a limit nobody
        # set, against a plan that could not be built. The gap still stands: no
        # rule covers the parameter, and the section is still warned.
        yielded_to_exact = bool(assumed and exact_span is not None
                                and exact_span > max_span_mm)
        if yielded_to_exact:
            max_span_mm = exact_span

        firing = builder.add(
            "gap" if assumed else "rule_firing",
            "uncovered_param" if assumed else "resolve_max_span",
            payload={"run_id": run.id, "param": "max_span_mm",
                     "value": max_span_mm,
                     # what the basis actually IS, so the explanation cannot
                     # claim a fallback the layout did not use
                     **({"basis": "manufactured_width"} if yielded_to_exact
                        else {"basis": "fallback"} if assumed else {})},
            inputs=[run_fact.id, select_node.id],
            # nothing governs an assumed value, and that IS the explanation
            governed_by=[] if assumed else [res.winner.version.ref],
            # a defeated edge cites the LOSING version (decision-model.md); the loser
            # is any firing whose defeated_by is non-empty
            defeated=[f.version.ref for f in res.firings if f.defeated_by],
            confidence="uncertain" if assumed else "deterministic",
        )
        sink.extend(res.conflicts)

        rails, rails_refs = _resolve_quantity(
            seg_kb, seg_ctx, "rails_per_span", DEFAULT_RAILS_PER_SPAN, sink)
        screws, screws_refs = _resolve_quantity(
            seg_kb, seg_ctx, "screws_per_span", DEFAULT_SCREWS_PER_SPAN, sink)

        sm = _SegmentModel(
            model=model,
            use=ModelUse(
                model_id=model.id, version=model.version,
                content_hash=content_hash(model),
                options=options,
            ),
            options=options,
            select_node_id=select_node.id,
            max_span=max_span_mm,
            max_span_ref="" if assumed else res.winner.version.ref,
            max_span_assumed=assumed,
            max_span_basis=("manufactured_width" if yielded_to_exact
                            else "fallback" if assumed else "rule"),
            firing_node_id=firing.id,
            rails_per_span=rails,
            screws_per_span=screws,
            quantity_refs=rails_refs + screws_refs,
            exact_span=exact_span, exact_span_ref=exact_span_ref,
        )
        resolved[key] = sm
        models_used.append(sm.use)
        # Recorded from the SEGMENT, not from the library: a part reached by no bay
        # of this fence was not resolved by this run, and a snapshot naming it would
        # claim the run depended on something it never read.
        # `.extend`, never `+=`: an augmented assignment inside this closure would
        # rebind the name as a LOCAL of `segment_model` and lose the run's list
        # entirely — the snapshot would come out empty on every run.
        parts_used.extend(part_uses)
        return sm

    # -- gates -----------------------------------------------------------------
    gates: list[tuple[Mm, Mm, str, str]] = []
    openings: dict[str, Mm] = {}  # event id -> the opening the USER asked for
    kit_sources: dict[str, str] = {}  # event id -> "payload" | "catalog"
    for ev in run.point_events:
        if ev.payload.kind == "gate":
            gs = anchor_station(topo, run, ev.anchor)
            opening = ev.payload.width_mm
            ge = min(gs + opening, length)
            gate_ref = f"gate@{run.id}:{gs}-{ge}"
            openings[ev.id] = opening
            if gs + opening > length:
                # the opening was CLAMPED to the section end: the drawing shows a
                # gap the gate cannot fill, and the setting-out sheet would hand
                # that contradiction to a crew
                c_node = builder.add(
                    "conflict", "gate_past_run_end",
                    payload={"element": gate_ref, "asked_mm": opening,
                             "available_mm": length - gs, "station_mm": gs},
                    scope_refs=[gate_ref],
                )
                strategy.warnings.append(
                    StrategyWarning(
                        code="gate_past_run_end", severity="error",
                        message=f"Gate at station {gs} asks for {opening} mm but only "
                                f"{length - gs} mm of the section remains — move the "
                                "gate or shorten it.",
                        element_refs=[gate_ref], decision_ref=c_node.id,
                        params={"element": gate_ref, "asked_mm": opening,
                                "available_mm": length - gs, "station_mm": gs},
                    )
                )
            # the payload's kit wins (it is the user's choice); otherwise the kit is
            # selected from the catalog BY DECLARED WIDTH — never by a SKU pattern
            kit = ev.payload.kit_sku or _kit_for_opening(catalog, opening)
            kit_sources[ev.id] = "payload" if ev.payload.kit_sku else "catalog"
            if not kit:
                strategy.warnings.append(
                    StrategyWarning(
                        code="no_gate_kit", severity="error",
                        message=f"No product in the catalog declares that it fits a "
                                f"{opening} mm gate opening; this gate cannot be priced.",
                        params={"element": gate_ref, "opening_width_mm": opening},
                        element_refs=[gate_ref],
                    )
                )
            elif kit not in catalog.products:
                strategy.warnings.append(
                    StrategyWarning(
                        code="unknown_product", severity="error",
                        message=f"Gate kit '{kit}' is not in the catalog; BOM will "
                                "price it at zero.",
                        params={"sku": kit},
                        element_refs=[gate_ref],
                    )
                )
            gates.append((gs, ge, kit, ev.id))
    gates.sort()
    gate_edges = {s for gs, ge, _, _ in gates for s in (gs, ge)}
    # gate fact nodes exist before any post so flanking-post decisions cite the
    # gate topology event (golden-scenarios S10)
    gate_fact_ids: dict[str, str] = {}
    gate_edge_facts: dict[Mm, list[str]] = {}
    for gs, ge, _, ev_id in gates:
        fact = builder.add(
            "input_fact", "gate_event",
            # `run_id` is how a run-level node names its SECTION
            # (report/section_decisions.py). A gate names no element — the posts
            # it forces do — so without it the section that the gate reshaped
            # gets the reinforced posts and never the gate that caused them.
            payload={"run_id": run.id, "event_id": ev_id,
                     "start_mm": gs, "end_mm": ge},
        )
        gate_fact_ids[ev_id] = fact.id
        for s in (gs, ge):
            gate_edge_facts.setdefault(s, []).append(fact.id)

    # -- overrides addressed to this run ---------------------------------------
    pinned_stations: dict[Mm, Override] = {}
    suppress_ovs: list[Override] = []
    for ov in overrides:
        if ov.run_id != run.id:
            continue
        d = ov.directive
        if d.kind == "pin_post" and 0 < d.station_mm < length:
            pinned_stations[d.station_mm] = ov
        elif d.kind == "suppress_post":
            suppress_ovs.append(ov)
    # `force_vertical` is collected by `_run_post_facts` below, because a POST's
    # panel facts read the mode it forces too — one list, so a bay and the post
    # beside it cannot disagree about which overrides cover them.

    corners = corner_stations(topo, run)
    transitions = base_transition_stations(topo, run)
    # base-top STEPS >= threshold force a structural boundary; the threshold is
    # knowledge, not code (K-STEP-POST) — sections-model addendum
    step_threshold, step_refs = _resolve_quantity(
        kb, ctx, "base_top_step_boundary_mm", 100, sink
    )
    base_steps = base_top_step_stations(topo, run, step_threshold)
    step_info = {station: (delta, ev_id, "base_top_step")
                 for station, delta, ev_id in base_steps}
    # vertical GROUND steps (cliffs/retaining drops) are structural boundaries too
    for station, delta in ground_step_stations(topo, run, step_threshold):
        step_info.setdefault(station, (delta, None, "ground_step"))
    step_stations = set(step_info)
    # buildability ceiling: a single step a fence can absorb (rule-editable)
    max_step, max_step_refs = _resolve_quantity(kb, ctx, "max_panel_step_mm", 600, sink)
    # optional plumb-consequence rules: only checked when a rule exists
    gap_res = resolve_param(kb, ctx, "max_panel_gap_mm")
    sink.extend(gap_res.conflicts)
    max_gap = (next(a.value for a in gap_res.winner.actions if a.kind == "set_param")
               if gap_res.winner else None)
    height_res = resolve_param(kb, ctx, "max_fence_height_mm")
    sink.extend(height_res.conflicts)
    max_height = (next(a.value for a in height_res.winner.actions if a.kind == "set_param")
                  if height_res.winner else None)
    gate_slope_res = resolve_param(kb, ctx, "gate_max_slope_permille")
    sink.extend(gate_slope_res.conflicts)
    max_gate_slope = (
        next(a.value for a in gate_slope_res.winner.actions if a.kind == "set_param")
        if gate_slope_res.winner else None)
    fixed: set[Mm] = {0, length} | set(corners) | set(transitions) | set(pinned_stations)
    fixed |= gate_edges | step_stations
    # a model change is a structural boundary for the same reason a base transition
    # is: a bay may not straddle the place where the fence becomes a different fence
    fixed |= set(fence_model_transition_stations(topo, run))
    fixed_sorted = sorted(fixed)

    reinf_sku, reinf_refs = _resolve_reinforcement(kb, scope, site, sink)

    # -- the panel facts every post of this run is matched against -------------
    # Resolved here rather than beside the `choose_vertical_mode` node below,
    # because the first post is created on the next line and a post predicate may
    # read `panel.vertical`. The node still belongs where the graph already puts
    # it; what moves is the answer, which is now asked once and used twice.
    post_facts, vert_res, vertical_refs, vertical_defeated = _run_post_facts(
        topo, run, kb, scope, site, sink, overrides, policy
    )
    vertical = post_facts.vertical

    # -- interior fixed posts --------------------------------------------------
    for station in fixed_sorted:
        if station in (0, length):
            continue  # node posts own the termini
        surface = base_surface_at(topo, run, station)
        inputs = [run_fact.id]
        kind = "line"
        pinned = False
        reinforced = False
        step_governed: list[str] = []
        if station in gate_edges:
            kind = "gate"
            reinforced = surface != "masonry_wall" and reinf_sku is not None
            inputs = inputs + gate_edge_facts.get(station, [])
        elif station in corners:
            kind = "corner"
        elif station in transitions:
            kind = "transition"
        elif station in step_stations:
            kind = "transition"
            delta, ev_id, step_kind = step_info[station]
            step_fact = builder.add(
                "input_fact", step_kind,
                payload={"event_id": ev_id, "station_mm": station, "step_mm": delta,
                         "threshold_mm": step_threshold},
            )
            inputs = inputs + [step_fact.id]
            step_governed = list(step_refs)
            if abs(delta) > max_step:
                over = builder.add(
                    "conflict", "excessive_step",
                    payload={"element": f"post@{run.id}:{station}",
                             "step_mm": abs(delta), "max_mm": max_step},
                    governed_by=max_step_refs,
                    inputs=[step_fact.id],
                )
                strategy.warnings.append(
                    StrategyWarning(
                        code="excessive_step", severity="error",
                        message=f"Step of {abs(delta)} mm at station {station} exceeds "
                                f"the buildable maximum of {max_step} mm — this needs "
                                "an engineered solution.",
                        element_refs=[f"post@{run.id}:{station}"],
                        decision_ref=over.id,
                        params={"element": f"post@{run.id}:{station}",
                                "step_mm": abs(delta), "max_mm": max_step},
                    )
                )
        override_nodes: list[str] = []
        ov = pinned_stations.get(station)
        if ov is not None:
            pinned = True
            applied.add(ov.id)
            override_nodes.append(
                builder.add(
                    "override_applied", "pin_post",
                    payload={"override_id": ov.id, "station_mm": station},
                ).id
            )
        forced_sku, forced_mounting, matched = _matched_force_overrides(
            overrides, run.id, station
        )
        for mov in matched:
            applied.add(mov.id)
            override_nodes.append(
                builder.add(
                    "override_applied", mov.directive.kind,
                    payload={"override_id": mov.id, "station_mm": station},
                ).id
            )
        tilt_deg, tilt_ev = (0, None) if kind == "gate" else _post_tilt_at(topo, run, station)
        model_post = _model_post_skus(
            library, default_model, catalog, parts,
            _post_sides(post_facts, station, length, kind), resolved_posts)
        post, cap_gap = _make_post(
            builder, kb, scope, site, sink,
            model_post=model_post.post_sku, model_post_rejected=model_post.post_rejected,
            model_cap=model_post.cap_for,
            post_id=f"post@{run.id}:{station}", run_ref=run.id,
            station=station, kind=kind, surface=surface,
            ground_z_mm=ground_z(topo, run, station),
            base_z_mm=_stand_z(topo, run, station),
            inputs=inputs,
            reinforced=reinforced,
            reinforcement_refs=(reinf_refs if reinforced else []) + step_governed,
            reinforced_sku=reinf_sku,
            pinned=pinned,
            forced_sku=forced_sku, forced_mounting=forced_mounting,
            override_nodes=override_nodes,
            tilt_deg=tilt_deg,
        )
        _cap_unsupplied(strategy, cap_gap, post.id, station)
        strategy.posts.append(post)

    # -- gate elements ---------------------------------------------------------
    for gs, ge, kit, ev_id in gates:
        gate_fact_id = gate_fact_ids[ev_id]
        gate = Gate(
            id=f"gate@{run.id}:{gs}-{ge}", run_ref=run.id,
            start_station_mm=gs, end_station_mm=ge, kit_sku=kit,
        )
        strategy.gates.append(gate)
        # The kit must fit the opening that will EXIST on site. Checking the
        # authored width instead let a clamped gate (one that runs past the end of
        # its section) keep a kit that cannot fit the remaining gap — and the
        # setting-out sheet then hands "opening 600 · GATE-KIT-1000" to a crew.
        opening = min(openings[ev_id], ge - gs)
        kit_width = _declared_opening(catalog, kit)
        if kit_width is not None and kit_width != opening:
            k_node = builder.add(
                "conflict", "gate_kit_width_mismatch",
                payload={"element": gate.id, "sku": kit,
                         "kit_width_mm": kit_width, "opening_width_mm": opening},
                scope_refs=[gate.id],
            )
            strategy.warnings.append(
                StrategyWarning(
                    code="gate_kit_width_mismatch", severity="error",
                    message=f"Gate kit {kit} fits a {kit_width} mm opening but the "
                            f"opening is {opening} mm — the BOM would price the wrong "
                            "gate.",
                    element_refs=[gate.id], decision_ref=k_node.id,
                    params={"element": gate.id, "sku": kit,
                            "kit_width_mm": kit_width, "opening_width_mm": opening},
                )
            )
        if max_gate_slope is not None and ge > gs:
            drop = abs(ground_z(topo, run, ge) - ground_z(topo, run, gs))
            gate_slope = round(drop * 1000 / (ge - gs))
            if gate_slope > max_gate_slope:
                g_node = builder.add(
                    "conflict", "gate_on_slope",
                    payload={"element": f"gate@{run.id}:{gs}-{ge}",
                             "slope_permille": gate_slope, "max_permille": max_gate_slope},
                    governed_by=[gate_slope_res.winner.version.ref],
                )
                strategy.warnings.append(
                    StrategyWarning(
                        code="gate_on_slope", severity="warning",
                        message=f"Gate opening at {gs}-{ge} sits on a "
                                f"{gate_slope / 10:.1f}% slope — the ground needs "
                                "leveling for the gate to swing.",
                        element_refs=[f"gate@{run.id}:{gs}-{ge}"], decision_ref=g_node.id,
                        params={"element": f"gate@{run.id}:{gs}-{ge}",
                                "slope_permille": gate_slope,
                                "max_permille": max_gate_slope},
                    )
                )
        placed = builder.add(
            "structural", "place_gate",
            payload={"start_mm": gs, "end_mm": ge},
            scope_refs=[gate.id],
            inputs=[gate_fact_id],
        )
        if kit:
            # provenance is the SKU's real source. A kit copied from the user's gate
            # event was never chosen by a rule: crediting K-GATE-REINF (which governs
            # POST reinforcement, not the kit) made the explanation lie — foundation
            # §15, "the decision graph is the explanation".
            builder.add(
                "selection", "select_gate_kit",
                payload={"kit_sku": kit, "source": kit_sources[ev_id],
                         "event_id": ev_id, "opening_width_mm": opening},
                scope_refs=[gate.id],
                inputs=[placed.id, gate_fact_id],
            )

    # -- vertical mode: the NODE. The answer was resolved before the first post,
    # because a post's predicate may read `panel.vertical` and a post stands
    # before any bay does; the node and its conflicts stay here, where the graph
    # already puts them.
    sink.extend(vert_res.conflicts)
    vertical_node = builder.add(
        "vertical", "choose_vertical_mode",
        # `run_id` because this node decides for the SECTION and names no
        # element. A reader asking what was decided about a section had to infer
        # it from the evidence closure otherwise, which cannot reach a node
        # emitted before that run's geometry fact — so say it.
        payload={"run_id": run.id, "mode": vertical,
                 "slope_permille": slope_permille},
        inputs=[run_fact.id],
        governed_by=vertical_refs,
        defeated=vertical_defeated,
    )

    tilt_ev_check, _, _ = _interval_at(topo, run, length // 2, "post_tilt")
    if (tilt_ev_check is not None and tilt_ev_check.payload.mode != "plumb"
            and vertical == "stepped"):
        t_node = builder.add(
            "conflict", "tilted_stepped",
            payload={"run_id": run.id, "mode": tilt_ev_check.payload.mode},
        )
        strategy.warnings.append(
            StrategyWarning(
                code="tilted_stepped", severity="warning",
                message=f"Section {run.id} combines tilted posts with stepped panels "
                        "— stepped panels sit level and normally pair with plumb "
                        "posts; check the design intent.",
                decision_ref=t_node.id,
                params={"run_id": run.id, "mode": tilt_ev_check.payload.mode},
            )
        )

    fv_nodes: dict[str, str] = {}  # override id -> decision node id

    def span_vertical(mid: Mm) -> tuple[str, str | None]:
        ov = _forced_vertical(post_facts.force_vertical, mid)
        if ov is None:
            return vertical, None
        d = ov.directive
        applied.add(ov.id)
        if ov.id not in fv_nodes:
            fv_nodes[ov.id] = builder.add(
                "override_applied", "force_vertical",
                payload={"override_id": ov.id, "mode": d.mode,
                         "interval": [d.start_station_mm, d.end_station_mm]},
            ).id
        return d.mode, fv_nodes[ov.id]

    # -- span quantities (resolved here so demand needs no knowledge access) ---
    # (rails_per_span / screws_per_span moved into segment_model: they are resolved
    # under the segment's model scope, so a rule may say "three rails on that
    # product line" — see the `series` binding there)

    # -- layout preferences: resolved, conflicts surfaced (S13) ----------------
    prefs = preference_firings(
        kb, ctx, {"prefer_equal_spans", "prefer_min_span_width", "prefer_span_width"}
    )
    prefer_equal_ref = None
    min_span: Mm | None = None
    min_span_ref = None
    width_pref: Mm | None = None
    equal_firing = None
    width_firing = None
    for f in prefs:
        for a in f.actions:
            if a.kind == "prefer_equal_spans":
                prefer_equal_ref = f.version.ref
                equal_firing = f
            elif a.kind == "prefer_min_span_width":
                min_span = a.min_mm
                min_span_ref = f.version.ref
            elif a.kind == "prefer_span_width":
                width_pref = a.width_mm
                width_firing = f

    prefer_equal = True
    layout_pref_ref = prefer_equal_ref
    if width_firing is not None and equal_firing is not None:
        res_layout = evaluator_resolve([width_firing, equal_firing], "span_layout_preference")
        sink.extend(res_layout.conflicts)
        prefer_equal = res_layout.winner is equal_firing
        layout_pref_ref = res_layout.winner.version.ref
    elif width_firing is not None:
        prefer_equal = False
        layout_pref_ref = width_firing.version.ref

    gate_intervals = [(gs, ge) for gs, ge, _, _ in gates]
    span_ids: list[str] = []
    # spans grouped by the model they were built to, so resolve_span_quantities
    # scopes to the bays its numbers actually governed
    spans_by_model: dict[tuple | None, list[str]] = {}
    # bays whose height this section's model cannot be built at, collected for
    # ONE warning per section rather than one per bay (fence-model spec
    # §warnings): a level top over a slope gives every bay a different height
    # (S06), so a discrete-height model would otherwise file a warning per bay
    # and drown every other warning in the list. Keyed by model ref because two
    # models may meet on one run and a message names the model it is about.
    unsupported_heights: dict[str, list[tuple[Mm, str]]] = {}
    # Aggregated the same way and for the same reason. A slot that declares a
    # length rule and resolves to no length in this bay is the QUIET failure:
    # a divisible product with no cut length plans no bars, so the member is
    # priced at nothing and the parts ledger reads the hole as demand covered
    # from stock. `validate_model` catches that at authoring wherever it can,
    # but a `between_frame` length depends on the bay — a knowledge param that
    # empties the rail set, refs that invert at this height — so the only place
    # left to say it is here. (model_ref, slot_key) -> span ids.
    unmeasured_slots: dict[tuple[str, str], list[str]] = {}
    # Credits that did not land cleanly on a bay, aggregated the same way again.
    # A credit makes the panel buy LESS, and a saving is invisible on the
    # finished document — the line is simply not there — so both ways of getting
    # one wrong have to be said out loud. `validate_model` has already refused
    # every credit that is wrong on PAPER (an unknown target, a mismatched role,
    # a piece crediting its own container); what is left is per-bay and only
    # answerable here. (model_ref, kind, contained path, target slot) -> [(span,
    # qty)].
    credit_notes: dict[tuple[str, str, str, str], list[tuple[str, int]]] = {}
    for seg_start, seg_end in zip(fixed_sorted, fixed_sorted[1:]):
        if any(gs <= seg_start and seg_end <= ge for gs, ge in gate_intervals):
            continue
        seg_len = seg_end - seg_start
        if seg_len <= 0:
            continue
        # model stations are boundary stations, so the whole segment is one model's
        # and its mid-point is a safe place to ask which
        choice = fence_model_at(topo, run, (seg_start + seg_end) // 2)
        sm = segment_model(choice)
        model = sm.model
        rails_per_span, screws_per_span = sm.rails_per_span, sm.screws_per_span
        layout = layout_segment(
            seg_len, sm.max_span,
            prefer_equal=prefer_equal, min_span_mm=min_span, nominal_mm=width_pref,
            exact_mm=sm.exact_span,
        )
        governed = [r for r in (sm.max_span_ref, layout_pref_ref) if r]
        if layout.exact_over_max:
            _exact_over_max(builder, strategy, run, sm)
        elif layout.remainder_mm is not None:
            _span_not_exact(builder, strategy, run, seg_start, seg_end, sm, layout)
        layout_node = builder.add(
            "structural", "layout_spans",
            payload={
                "run_id": run.id,
                "segment": [seg_start, seg_end],
                "widths": layout.widths,
                "alternatives": (
                    [{"widths": layout.rejected_alternative,
                      "rejected_because": layout_pref_ref or "policy"}]
                    if layout.rejected_alternative else []
                ),
            },
            inputs=[run_fact.id, sm.firing_node_id, vertical_node.id],
            governed_by=governed,
        )
        stations = boundaries(seg_start, layout.widths)
        # The bays this segment is about to lay out, NAMED before they exist so
        # the quantities that govern them are recorded first. `rails_per_span`
        # decides how many positions a `Distributed` frame slot has, and those
        # positions are what a `between_frame` member is measured between — so
        # the rail count sits upstream of a slat's cut length and has to reach
        # `resolve_panel` as an input EDGE. Emitted after the span loop (where
        # this node used to live) it could only ever SHARE A SCOPE with the bays
        # it decided, and a shared scope is not a chain anything can walk.
        #
        # Per segment rather than per model: a segment is the smallest stretch
        # that has one model, and these numbers were resolved under that model's
        # scope. Two segments built to one model repeat the node, which says the
        # same true thing about each set of bays — where one node covering both
        # would have to be emitted before either segment picked its model.
        segment_span_ids = [f"span@{run.id}:{s0}-{s1}"
                            for s0, s1 in zip(stations, stations[1:])]
        quantity_node = builder.add(
            "quantity", "resolve_span_quantities",
            payload={"rails_per_span": sm.rails_per_span,
                     "screws_per_span": sm.screws_per_span},
            scope_refs=segment_span_ids,
            inputs=[run_fact.id, sm.select_node_id],
            governed_by=sm.quantity_refs,
        )
        # Interior line posts, created BEFORE the bays they bound: a bay's
        # clear opening is measured to the faces of the posts at its ends, so
        # those posts have to exist — and have their product resolved — before
        # `resolve_panel` is asked how wide the opening is.
        for s in stations[1:-1]:
            suppressor = next(
                (ov for ov in suppress_ovs if _near(ov.directive.station_mm, s)), None
            )
            if suppressor is not None:
                applied.add(suppressor.id)
                builder.add(
                    "override_applied", "suppress_post",
                    payload={"override_id": suppressor.id, "station_mm": s},
                )
                continue
            surface = base_surface_at(topo, run, s)
            forced_sku, forced_mounting, matched = _matched_force_overrides(
                overrides, run.id, s
            )
            override_nodes = []
            for mov in matched:
                applied.add(mov.id)
                override_nodes.append(
                    builder.add(
                        "override_applied", mov.directive.kind,
                        payload={"override_id": mov.id, "station_mm": s},
                    ).id
                )
            tilt_deg, _tilt_ev = _post_tilt_at(topo, run, s)
            model_post = _model_post_skus(
                library, default_model, catalog, parts,
                _post_sides(post_facts, s, length, "line"), resolved_posts)
            post, cap_gap = _make_post(
                builder, kb, scope, site, sink,
                model_post=model_post.post_sku, model_post_rejected=model_post.post_rejected,
            model_cap=model_post.cap_for,
                post_id=f"post@{run.id}:{s}", run_ref=run.id,
                station=s, kind="line", surface=surface,
                ground_z_mm=ground_z(topo, run, s),
                base_z_mm=_stand_z(topo, run, s),
                inputs=[layout_node.id],
                forced_sku=forced_sku, forced_mounting=forced_mounting,
                override_nodes=override_nodes,
                tilt_deg=tilt_deg,
            )
            _cap_unsupplied(strategy, cap_gap, post.id, s)
            strategy.posts.append(post)
        for s0, s1 in zip(stations, stations[1:]):
            width = s1 - s0
            mid = (s0 + s1) // 2
            # sample 1 mm inside: a vertical ground step exactly at a boundary is
            # the POST's business, not the neighboring spans' bottoms
            gz0 = ground_z(topo, run, min(s0 + 1, mid))
            gz1 = ground_z(topo, run, max(s1 - 1, mid))
            if base_surface_at(topo, run, mid) in BUILT_BASES:
                # panel bottom rests on the base top; sample just inside the span so
                # a step boundary reads its own side (half-open step convention)
                t0 = base_top_at(topo, run, min(s0 + 1, mid))
                t1 = base_top_at(topo, run, max(s1 - 1, mid))
                if t0 is not None:
                    gz0 += t0[0]
                if t1 is not None:
                    gz1 += t1[0]
            v_mode, fv_node = span_vertical(mid)
            height, height_src, height_extra = _span_height(topo, run, mid, gz0, gz1, policy)
            # ONE calculation for one fact: the opening is measured here, from the
            # posts that bound this bay, and both the stored span and the context
            # the panel is resolved in read that single number.
            clear = clear_opening_mm(
                width,
                _post_face_width(strategy, run, s0, length, catalog),
                _post_face_width(strategy, run, s1, length, catalog),
            )
            span = Span(
                id=f"span@{run.id}:{s0}-{s1}", run_ref=run.id,
                start_station_mm=s0, end_station_mm=s1, width_mm=width,
                clear_width_mm=clear,
                slope_len_mm=slope_len_mm(width, gz1 - gz0) if v_mode == "raked" else width,
                vertical=v_mode, height_mm=height,  # type: ignore[arg-type]
                bottom_z_start_mm=gz0, bottom_z_end_mm=gz1,
                rail_count=rails_per_span,
                screws_count=screws_per_span,
                rail_cut_basis="slope" if v_mode == "raked" else "width",
            )
            panel_ctx = PanelContext(
                centre_width_mm=width,
                clear_width_mm=clear,
                height_mm=height,
                vertical=v_mode,
                length_basis=span.rail_cut_basis,
                slope_len_mm=span.slope_len_mm,
                params={"rails_per_span": rails_per_span,
                        "screws_per_span": screws_per_span},
                options=sm.options,
            )
            # per BAY, not per segment: a variant condition reads the panel's own
            # height and vertical mode, and a level top over a slope gives every
            # bay of one segment a different height (S06)
            variant = choose_variant(model, panel_ctx)
            # A spec-declared slot becomes concrete members HERE, so what the run
            # stores is the candidate set it may choose among — the same shape an
            # authored slot has always had, and the reason `catalog_hash` may be
            # narrowed to the SKUs a run actually named.
            span.panel = resolve_panel(
                match_spec(variant.spec, catalog, panel_facts(panel_ctx)), panel_ctx,
                model_ref=model.ref, variant_index=variant.index,
            )
            if not height_supported(model.height_support, height):
                unsupported_heights.setdefault(model.ref, []).append((height, span.id))
            for slot in span.panel.slots:
                if slot.length_unresolved:
                    unmeasured_slots.setdefault(
                        (model.ref, slot.slot_key), []).append(span.id)
            for note in span.panel.credit_notes:
                credit_notes.setdefault(
                    (model.ref, note.kind, note.contained_key, note.slot_key),
                    []).append((span.id, note.qty))
            strategy.spans.append(span)
            span_ids.append(span.id)
            spans_by_model.setdefault(choice.key() if choice else None, []).append(span.id)
            span_node = builder.add(
                "structural", "create_span",
                payload={
                    "width_mm": width, "vertical": v_mode, "height_mm": height,
                    "height_source": height_src,
                    "bottom_z_start_mm": gz0, "bottom_z_end_mm": gz1,
                    **({"step_mm": abs(gz1 - gz0)} if v_mode == "stepped" else {}),
                    **height_extra,
                },
                scope_refs=[span.id],
                inputs=[layout_node.id] + ([fv_node] if fv_node else []),
                governed_by=governed,
            )
            # `span_node` among them: the panel was resolved against THIS bay's
            # width and height, so every length rule that reads them
            # (`panel_height`, `centre_to_centre`) traces to the node that fixed
            # them. It reached `resolve_panel` only through the variant node
            # before, which exists only for a model that declares variants — so
            # on the plainest model the bay's own height was not upstream of the
            # panel cut to it.
            panel_inputs = [layout_node.id, sm.select_node_id, quantity_node.id,
                            span_node.id]
            if model.variants:
                # NO `defeated` edge, and that is not an omission: a variant
                # condition is evaluated outside the knowledge evaluator, so
                # there is no losing knowledge VERSION to cite — a defeated edge
                # cites the loser's ref (decision-model.md) and a variant has
                # none. This node IS the trace. Emitted only when the model
                # actually declares variants, so a run built to a single-spec
                # model keeps the explanation it has today.
                variant_node = builder.add(
                    "selection", "select_variant",
                    payload={"model_ref": model.ref,
                             "variant_index": variant.index,
                             "failed": variant.failed,
                             "not_reached": variant.not_reached,
                             "of": len(model.variants)},
                    scope_refs=[span.id], inputs=[sm.select_node_id, span_node.id],
                )
                panel_inputs.append(variant_node.id)
            for slot in span.panel.slots:
                # one node per slot an option actually GOVERNED, not per slot:
                # "why this product" is only a question where an answer changed
                # the candidates, and a node per slot per bay would bury the
                # ones that did
                if slot.option_axis is None:
                    continue
                panel_inputs.append(builder.add(
                    "selection", "select_product",
                    payload={"slot": slot.slot_key, "axis": slot.option_axis,
                             "value": slot.option_value,
                             # exactly one member survives a narrowing, by
                             # construction: it is the member the option named
                             "sku": slot.eligibility.members[0].sku},
                    scope_refs=[span.id], inputs=[sm.select_node_id, span_node.id],
                ).id)
            for slot in span.panel.slots:
                # One node per SLOT whose purchase a credit reduced — not one per
                # credit. A credit is the one thing here that makes the panel buy
                # less, and a smaller purchase leaves no trace on the BOM of its
                # own: the line is simply shorter, or gone. So the reduction gets
                # a node rather than a footnote on the panel's, because "every
                # BOM line traces through the graph" is only true of a line that
                # exists, and this is where a reader lands when they ask why the
                # panel bought two hinges and placed four.
                #
                # Per TARGET, because the sentence is a subtraction and it has to
                # add up. Two containers each supplying two of a four-hinge slot
                # used to write two nodes, each claiming "needs 4, 2 ship inside
                # X, so the panel buys 0" — false twice, and the comment right
                # here asked for the opposite. `credited_by` carries every source,
                # so one node states the whole sum: of - qty == remaining, always.
                if not slot.credited_qty:
                    continue
                panel_inputs.append(builder.add(
                    "structural", "credit_contained",
                    payload={"slot": slot.slot_key,
                             "role": slot.role,
                             # what the slot asked for, what arrived in a box, and
                             # what is left to buy. All three, because a reader
                             # given only the difference cannot check it.
                             "of": slot.qty + slot.credited_qty,
                             "qty": slot.credited_qty,
                             "remaining": slot.qty,
                             "contained": ", ".join(slot.credited_by)},
                    scope_refs=[span.id], inputs=[sm.select_node_id, span_node.id],
                ).id)
            builder.add(
                "structural", "resolve_panel",
                payload={"model_ref": model.ref,
                         "slots": _panel_slots_payload(span.panel)},
                scope_refs=[span.id], inputs=panel_inputs,
            )
            if width > sm.max_span:
                raise GenerationFailure(
                    f"span {span.id} width {width} exceeds hard max {sm.max_span}",
                    constraint_refs=[r for r in [sm.max_span_ref] if r],
                )
            if v_mode == "stepped" and max_gap is not None and 0 < abs(gz1 - gz0) <= max_step \
                    and abs(gz1 - gz0) > max_gap:
                gap_node = builder.add(
                    "conflict", "excessive_gap",
                    payload={"element": span.id, "gap_mm": abs(gz1 - gz0), "max_mm": max_gap},
                    scope_refs=[span.id],
                    governed_by=[gap_res.winner.version.ref],
                )
                strategy.warnings.append(
                    StrategyWarning(
                        code="excessive_gap", severity="warning",
                        message=f"Stepped span {span.id} leaves a {abs(gz1 - gz0)} mm gap "
                                f"underneath (limit {max_gap} mm).",
                        element_refs=[span.id], decision_ref=gap_node.id,
                        params={"element": span.id, "gap_mm": abs(gz1 - gz0), "max_mm": max_gap},
                    )
                )
            if max_height is not None:
                plumb_worst = height + (abs(gz1 - gz0) if v_mode == "stepped" else 0)
                if plumb_worst > max_height:
                    h_node = builder.add(
                        "conflict", "max_height_exceeded",
                        payload={"element": span.id, "height_mm": plumb_worst,
                                 "max_mm": max_height},
                        scope_refs=[span.id],
                        governed_by=[height_res.winner.version.ref],
                    )
                    strategy.warnings.append(
                        StrategyWarning(
                            code="max_height_exceeded", severity="error",
                            message=f"Span {span.id} reaches {plumb_worst} mm plumb height "
                                    f"at its downhill end — above the {max_height} mm limit.",
                            element_refs=[span.id], decision_ref=h_node.id,
                            params={"element": span.id, "height_mm": plumb_worst,
                                    "max_mm": max_height},
                        )
                    )
            if v_mode == "stepped" and abs(gz1 - gz0) > max_step:
                over = builder.add(
                    "conflict", "excessive_step",
                    payload={"element": span.id, "step_mm": abs(gz1 - gz0),
                             "max_mm": max_step},
                    scope_refs=[span.id],
                    governed_by=max_step_refs,
                )
                strategy.warnings.append(
                    StrategyWarning(
                        code="excessive_step", severity="error",
                        message=f"Span {span.id} steps {abs(gz1 - gz0)} mm — beyond the "
                                f"buildable maximum of {max_step} mm; the terrain here "
                                "needs an engineered solution.",
                        element_refs=[span.id], decision_ref=over.id,
                        params={"element": span.id, "step_mm": abs(gz1 - gz0),
                                "max_mm": max_step},
                    )
                )
            if min_span and width < min_span:
                conflict_node = builder.add(
                    "conflict", "sliver_span",
                    payload={"span": span.id, "width_mm": width, "min_mm": min_span},
                    scope_refs=[span.id],
                    governed_by=[min_span_ref] if min_span_ref else [],
                )
                strategy.warnings.append(
                    StrategyWarning(
                        code="sliver_span", severity="warning",
                        message=f"Span {span.id} is {width} mm, below preferred "
                                f"minimum {min_span} mm.",
                        params={"span_id": span.id, "width_mm": width, "min_mm": min_span},
                        element_refs=[span.id], decision_ref=conflict_node.id,
                    )
                )

    _report_uncovered_max_span(run, strategy, resolved, spans_by_model)

    _check_panel_safety(kb, run, scope, site, sink, strategy, builder, resolved, spans_by_model,
                        {s.id: s for s in strategy.spans}, ctx["run"])

    for model_ref, offenders in unsupported_heights.items():
        # the DISTINCT heights: the reader has to change a height or a model, and
        # "1400 mm, 1400 mm, 1400 mm" says nothing "1400 mm" does not
        heights = sorted({h for h, _ in offenders})
        spans_affected = sorted(span_id for _, span_id in offenders)
        node = builder.add(
            "conflict", "height_not_supported",
            payload={"model_ref": model_ref, "run_id": run.id,
                     "heights_mm": heights, "n": len(heights)},
            scope_refs=spans_affected,
        )
        strategy.warnings.append(
            StrategyWarning(
                code="height_not_supported", severity="warning",
                message=f"Fence model {model_ref} does not support "
                        f"{len(heights)} panel height(s) in section {run.id}: "
                        + ", ".join(f"{h} mm" for h in heights),
                element_refs=spans_affected, decision_ref=node.id,
                # the offending heights themselves, pre-joined the way
                # `contenders` and `surfaces` already are (a warning param is a
                # `str | int`). The SENTENCE renders the range instead, because
                # a joined string is the one thing `unitParams` cannot convert
                # and a list of millimetres beside a "cm" label would be a lie;
                # the decision node's payload keeps the real int list, which is
                # what `/explain` renders in the reader's unit.
                params={"model_ref": model_ref, "run_id": run.id,
                        "heights_mm": ", ".join(str(h) for h in heights),
                        "n": len(heights),
                        "min_mm": heights[0], "max_mm": heights[-1]},
            )
        )

    for (model_ref, slot_key), spans_affected in sorted(unmeasured_slots.items()):
        # `severity="error"`, and the only panel check that is. Every other
        # warning here describes a fence that will be built badly; this one
        # describes a part that will not be PRICED at all, and a quote missing a
        # line reads as cheaper rather than as incomplete.
        affected = sorted(spans_affected)
        node = builder.add(
            "conflict", "panel_length_unresolved",
            payload={"model_ref": model_ref, "slot": slot_key,
                     "run_id": run.id, "n": len(affected)},
            scope_refs=affected,
        )
        strategy.warnings.append(
            StrategyWarning(
                code="panel_length_unresolved", severity="error",
                message=f"Model {model_ref} resolves no cut length for slot "
                        f"{slot_key} in {len(affected)} bay(s) of section "
                        f"{run.id}: the frame members it is measured between "
                        f"leave nothing to measure",
                element_refs=affected, decision_ref=node.id,
                params={"model_ref": model_ref, "slot": slot_key,
                        "run_id": run.id, "n": len(affected)},
            )
        )

    for (model_ref, kind, contained, slot_key), hits in sorted(credit_notes.items()):
        # Both kinds are WARNINGS and neither is an error, and the asymmetry is
        # deliberate. Under-crediting costs a customer a spare part; the fence
        # gets built. Over-crediting would leave a fitter without one — so the
        # resolver never over-credits (it caps at what the slot wanted), and what
        # is reported here is the evidence that it capped. A refusal would stop a
        # buildable fence over a kit that ships one hinge too many.
        affected = sorted(span_id for span_id, _ in hits)
        # The largest surplus, not the sum: the reader has to change a model or a
        # kit, and "2" said once is what they act on. `unmatched` carries the
        # count that credited nothing for the same reason.
        qty = max(q for _, q in hits)
        params = {"model_ref": model_ref, "contained": contained,
                  "slot": slot_key, "qty": qty, "run_id": run.id,
                  "n": len(affected)}
        # Two branches rather than one `code=f"contained_credit_{kind}"`, and not
        # for readability: `tests/web/test_locale_bundles.py` proves every code
        # the backend can emit has a sentence in BOTH bundles by grepping for the
        # literal `code="..."`, and a code assembled from a fragment is invisible
        # to it — a raw English string inside a Hebrew sentence the first day
        # something shows it.
        if kind == "unmatched":
            warning = StrategyWarning(
                code="contained_credit_unmatched", severity="warning",
                message=f"{contained} credits slot {slot_key}, which model "
                        f"{model_ref} does not build in {len(affected)} bay(s) "
                        f"of section {run.id}: nothing is credited there",
                params=params, element_refs=affected,
            )
        else:
            warning = StrategyWarning(
                code="contained_credit_surplus", severity="warning",
                message=f"{contained} ships {qty} more than slot {slot_key} "
                        f"needs in {len(affected)} bay(s) of section {run.id}: "
                        "the surplus credits nothing",
                params=params, element_refs=affected,
            )
        warning.decision_ref = builder.add(
            "conflict", warning.code, payload=params, scope_refs=affected,
        ).id
        strategy.warnings.append(warning)


def _panel_slots_payload(panel: ResolvedPanel) -> list[dict]:
    """One `resolve_panel` payload entry per slot: what it is, how many, and —
    where resolution fixed one — the LENGTH each piece is cut to.

    Before the panel waves every cut length on a BOM line was derivable from the
    graph: `panel_height` and `centre_to_centre` are functions of `create_span`'s
    own payload, which is an input edge of this node. `between_frame`
    is not. Its length is a function of the frame slots' positions, their face
    heights and the two engagements — none of which appears anywhere else in the
    graph — so the slat that is 1665 mm instead of 1800 mm, the whole reason
    M-SLAT@v2 exists, was a number `/explain` could not say (review finding 3).

    So the terms of that subtraction travel too, under `between`:

        length = (top_position - top_thickness//2 + top_engagement)
               - (base_position + base_thickness//2 - base_engagement)

    which is `_between_frame_extent`'s arithmetic, reported rather than repeated
    — nothing here recomputes it, and `length_mm` beside it is the resolver's own
    answer. The positions are the OUTERMOST of each referenced set, because that
    is the pair the resolver measured between.

    `between` appears only where a span start was actually fixed, which is
    exactly where those positions were used: a slot whose refs inverted at this
    bay's height resolved no length, and listing the positions it failed against
    as the ones it used would be a different claim. That bay's slot is reported
    by the `panel_length_unresolved` conflict instead.
    """
    frame = {s.slot_key: s for s in panel.slots if s.slot_kind == "frame"}
    entries: list[dict] = []
    for slot in panel.slots:
        entry: dict = {"key": slot.slot_key, "role": slot.role, "qty": slot.qty}
        # Added ONLY where containment is in play, so every panel that contains
        # nothing produces the payload it always did — the graph is stored on the
        # run and a new key on every slot of every bay would read as a change to
        # fences that have not changed.
        if slot.contained_in:
            entry["contained_in"] = slot.contained_in
        if slot.credited_qty:
            entry["credited_qty"] = slot.credited_qty
            if slot.credits_slot_key:
                entry["credits"] = slot.credits_slot_key
            if slot.credited_by:
                entry["credited_by"] = list(slot.credited_by)
        if slot.length_mm is not None:
            entry["length_mm"] = slot.length_mm
        if slot.span_start_mm is not None:
            entry["span_start_mm"] = slot.span_start_mm
            between = {}
            for end, ref, engagement in (
                ("base", slot.base_ref, slot.base_engagement_mm),
                ("top", slot.top_ref, slot.top_engagement_mm),
            ):
                target = frame.get(ref or "")
                if target is None or not target.positions_mm:
                    continue
                between[end] = {
                    "slot": target.slot_key,
                    "position_mm": (min if end == "base" else max)(target.positions_mm),
                    # 0 for an undeclared face height, which is what the extent
                    # calculation contributed for it — not a nominal
                    "thickness_mm": target.thickness_mm or 0,
                    "engagement_mm": engagement,
                }
            if between:
                entry["between"] = between
        entries.append(entry)
    return entries


# The panel checks, and the ONE knowledge param each is governed by. Every gap a
# fence model introduces is regulated somewhere — the 100 mm sphere test on
# openings, the anti-ladder rule keeping a middle rail clear of the bottom one —
# and the numbers are jurisdictional, so they live in knowledge and not here.
#
# Written as records with `code="..."` spelled out rather than as a dict keyed by
# the code, because the locale-bundle guard scans these files for exactly that
# literal: a code that only ever existed as a dict key or a loop variable would
# ship untranslated with the test green, which is the failure that guard exists
# to prevent.
def _exact_over_max(builder, strategy, run, sm) -> None:
    """A model's manufactured bay width is wider than the hard maximum span.

    Two rules of different kinds, both stated, neither able to give way: the
    panel does not exist in a narrower size and the maximum is a hard constraint.
    Surfaced as a conflict citing BOTH refs, which is what S13 requires and what
    a `min()` in the layout would have hidden — bays of neither width, reported
    as the width nobody used.
    """
    params = {"element": run.id, "run_id": run.id, "model_ref": sm.model.ref,
              "exact_mm": sm.exact_span, "max_mm": sm.max_span}
    node = builder.add(
        "conflict", "exact_span_over_max", payload=dict(params),
        governed_by=[r for r in (sm.exact_span_ref, sm.max_span_ref) if r],
    )
    strategy.warnings.append(StrategyWarning(
        code="exact_span_over_max", severity="error",
        message=f"Model {sm.model.ref} is made in {sm.exact_span} mm bays, wider "
                f"than the {sm.max_span} mm maximum span — section {run.id} was "
                "laid out freely instead.",
        decision_ref=node.id, params=params,
    ))


def _span_not_exact(builder, strategy, run, seg_start, seg_end, sm, layout) -> None:
    """A manufactured-width model met a segment that is not a whole multiple.

    Reported rather than absorbed: stretching every bay to make it come out even
    would put a pre-assembled panel in a bay it does not fit, which is the exact
    failure an exact width exists to prevent. A model that cannot tolerate a
    remainder at all contributes `exact_span_mm` as a hard_constraint, and the
    span_not_exact check is then the caller's cue to fail — not this warning's.
    """
    params = {"element": run.id, "run_id": run.id, "model_ref": sm.model.ref,
              "segment_mm": seg_end - seg_start, "exact_mm": sm.exact_span,
              "remainder_mm": layout.remainder_mm}
    node = builder.add(
        "conflict", "span_not_exact", payload=dict(params),
        governed_by=[sm.exact_span_ref] if sm.exact_span_ref else [],
    )
    strategy.warnings.append(StrategyWarning(
        code="span_not_exact", severity="warning",
        message=f"Section {run.id} does not divide into {sm.exact_span} mm bays: "
                f"{layout.remainder_mm} mm is left over as an odd bay.",
        decision_ref=node.id, params=params,
    ))


@dataclass(frozen=True)
class _PanelLimit:
    code: str
    param: str


_PANEL_LIMITS = (
    _PanelLimit(code="clear_gap_exceeded", param="max_clear_gap_mm"),
    _PanelLimit(code="rail_separation_insufficient", param="min_rail_separation_mm"),
    _PanelLimit(code="pattern_residual_large", param="max_pattern_residual_mm"),
)


def _could_apply(v: KnowledgeVersion, scope: dict[str, str], series_used: set[str]) -> bool:
    """Could this rule ever fire on THIS run, ignoring its condition?

    Only a filter against dimensions the run actually bound. A rule scoped to
    another project, or to a product line this fence is not built from, cannot
    apply here — and asking the estimator to fill in a site dimension for it is
    an item they cannot clear: entering a value changes nothing, because the rule
    still will not fire. That is standing noise on the one signal this adds.

    Deliberately conservative. An unbound dimension is NOT treated as a mismatch,
    because `bind_scope` leaves a dimension unbound exactly when the fact is
    absent, and a rule scoped to something we cannot rule out has to be assumed
    reachable. Erring toward reporting is the safe direction: a false nag is
    noise, a missed one is the silence this whole warning exists to break.
    """
    for key, value in v.scope.items():
        if key == "series":
            if series_used and value not in series_used:
                return False
        elif key in scope and scope[key] != value:
            return False
    return True


def _report_missing_site_conditions(
    kb: KnowledgeBase, site_facts: dict, scope: dict[str, str],
    series_used: set[str], strategy: Strategy, builder: GraphBuilder,
) -> None:
    """Rules that asked about this site, and a site that did not answer.

    Silence is the failure mode here. A rule conditioned on an unset dimension is
    NOT APPLICABLE — correctly, and that is the behaviour the whole design leans
    on — so it simply does not fire, the fence is built to whatever unconditioned
    rule was left, and nothing tells the estimator that the one fact deciding it
    was never entered. The plan looks complete and is answering a question nobody
    asked.

    Read off the RULES rather than off a list of dimensions, so it reports what
    this snapshot actually wanted: a knowledge base that never mentions exposure
    does not nag about exposure, and the day one starts publishing exposure rows
    the warning appears without a code change.

    **Not a `Gap`.** A gap declares `closes_by: knowledge | planning`, and this is
    neither — no curator can author this and no schema change in this repo fixes
    it. It is a field on the project that a person here has to fill in, so it is
    a warning on the run and nothing else. Filing it as a gap would put an item
    in the Knowledge Platform's review queue that nobody there can action, which
    is the one property contract §1.2.1 says that queue must have.
    """
    wanted: dict[str, str] = {}   # dimension -> the strongest type that wanted it
    for v in kb.active():
        if v.type == "candidate" or v.condition is None:
            continue
        if not _could_apply(v, scope, series_used):
            continue
        for path in field_paths(v.condition):
            if not path.startswith("site."):
                continue
            dim = path.split(".", 1)[1]
            if wanted.get(dim) != "hard_constraint":
                wanted[dim] = v.type
    missing = sorted(set(wanted) - set(site_facts))
    if not missing:
        return
    # A HARD constraint that could not be evaluated is not the same event as a
    # preference that did not fire. "Hard constraint is not preference" is a
    # foundation rule, and it should reach the report rather than stopping at
    # the resolver.
    hard = any(wanted[d] == "hard_constraint" for d in missing)
    params: dict[str, str | int] = {
        "dimensions": ", ".join(missing), "n": len(missing),
    }
    message = (
        f"{len(missing)} site condition(s) decide rules in this snapshot and are "
        f"not set: {', '.join(missing)}. Rules needing them did not apply."
    )
    node = builder.add(
        "gap", "site_condition_missing",
        payload=dict(params), confidence="uncertain",
    )
    strategy.warnings.append(StrategyWarning(
        code="site_condition_missing", severity="error" if hard else "warning",
        message=message, params=params, decision_ref=node.id,
    ))


def _report_unfilled_posts(strategy: Strategy, builder: GraphBuilder) -> None:
    """Posts standing with no product, because knowledge named no default.

    Written against the POSTS rather than against the resolution site, so that a
    post left empty by any of `_make_post`'s five precedence branches is still
    seen. **The DIAGNOSIS below is not that general**, and says so honestly: it
    names `post_ground`, because that is the only branch that can currently come
    back empty. A second branch that could — a masonry mount with no mount sku —
    would be reported here under the wrong cause, and closing that means giving
    this function the reason the sku is missing rather than inferring it.

    One gap for the run, not one per post: the missing thing is a single
    `default_component` rule, so sixty posts are one work item.
    """
    unfilled = sorted(p.id for p in strategy.posts if not p.sku)
    if not unfilled:
        return
    params: dict[str, str | int] = {"role": "post_ground", "n": len(unfilled)}
    message = (
        f"Knowledge names no default ground-post product (role post_ground); "
        f"{len(unfilled)} post(s) have no product and are unfilled in the BOM."
    )
    node = builder.add(
        "gap", "missing_default",
        payload={"role": "post_ground", "n": len(unfilled)},
        scope_refs=unfilled, confidence="uncertain",
    )
    # ERROR, not warning. `04-backend.md` states the line: a warning describes a
    # fence built badly, an error describes a part not bought at all. Every post
    # here is not bought at all — supply already says so, five times, at `error`
    # (`no_eligible_item`). Reporting the CAUSE more quietly than its own
    # consequence buries the one message that names why.
    strategy.warnings.append(StrategyWarning(
        code="no_default_post", severity="error", message=message,
        element_refs=unfilled, decision_ref=node.id, params=params,
    ))
    strategy.gaps.append(Gap(
        id="gap:post_ground",
        kind="missing_value",
        # a ROLE, so `slot` ("nothing can fill this") rather than `param`
        # ("no value for this key") — the first queue that groups by subject
        # kind would otherwise file it with the parameter gaps
        subject=GapSubject(kind="slot", ref="post_ground"),
        code="no_default_post", params=params, message=message,
        would_close="a default_component rule naming the ground-post product for role post_ground",
        closes_by="knowledge", severity="warns_line",
    ))


def _report_uncovered_max_span(
    run: Run,
    strategy: Strategy,
    resolved: dict,
    spans_by_model: dict,
) -> None:
    """One gap and one warning per section whose span basis nobody stated.

    Reported HERE rather than where the parameter resolves, because a gap is only
    worth receiving if it names what it cost: the resolution site knows the
    parameter and the fallback, and this one knows the bays that were laid out to
    it. Aggregated per section like `height_not_supported`, for the same reason —
    a systemic hole on a 60-bay fence is one thing to go fix, not sixty.

    `would_close` is BINDING (contract §1.2.1) and is the field that makes this a
    work item: it names the row, the parameter and the product line, so a curator
    reads what to author rather than that something is absent.
    """
    # Grouped by the model REF, not by the segment. Two segments of one run can
    # name the same model under different version pins or options, and
    # `spans_by_model` keys on the whole choice — so a naive loop files the same
    # missing row twice under one id. It is not two work items: `max_span_mm`
    # resolves under `series: model.id` (`_segment_view`), so a row that would
    # close it for one segment closes it for both. One gap, with every bay it
    # cost listed.
    by_model: dict[str, list[str]] = {}
    for key, span_ids in spans_by_model.items():
        sm = resolved[key]
        if sm.max_span_assumed:
            by_model.setdefault(sm.model.ref, []).extend(span_ids)

    for model_ref, span_ids in sorted(by_model.items()):
        sm = next(resolved[k] for k in spans_by_model
                  if resolved[k].model.ref == model_ref and resolved[k].max_span_assumed)
        affected = sorted(span_ids)
        params: dict[str, str | int] = {
            "element": run.id, "run_id": run.id, "model_ref": sm.model.ref,
            "param": "max_span_mm", "value_mm": sm.max_span, "n": len(affected),
            "basis": sm.max_span_basis,
        }
        basis = (
            "the width its line is manufactured in"
            if sm.max_span_basis == "manufactured_width" else "a fallback"
        )
        message = (
            f"No rule states max_span_mm for {sm.model.ref} in section {run.id}; "
            f"{len(affected)} bay(s) laid out to {basis} of {sm.max_span} mm."
        )
        strategy.warnings.append(StrategyWarning(
            code="uncovered_max_span", severity="warning", message=message,
            element_refs=affected, decision_ref=sm.firing_node_id, params=params,
        ))
        strategy.gaps.append(Gap(
            # the REF, not the id: two versions of one line are two refs, and an
            # id keyed on the bare model id would collide between them
            id=f"gap:{run.id}:{model_ref}:max_span_mm",
            kind="uncovered_condition",
            subject=GapSubject(kind="param", ref="max_span_mm"),
            code="uncovered_max_span", params=params, message=message,
            # Condition-space coordinates, and deliberately NOT the run id. The
            # BINDING example in §1.2.1 is "a footing row for exposure C,
            # non-HVHZ, at 6 ft" — a parameter plus the DIMENSIONS it is missing
            # on. `series` is that dimension here (`_segment_view` scopes the
            # lookup on it). A section id would be worse than useless: it means
            # nothing in the curator's store, and §3.1.13 bans a published
            # condition naming a specific run, so it would ask for a row the
            # contract forbids them to author. The section stays in `message`,
            # which is ours to read.
            would_close=f"a max_span_mm row for series {model_ref}",
            closes_by="knowledge", severity="warns_line",
        ))


def _check_panel_safety(
    kb: KnowledgeBase,
    run: Run,
    scope: dict[str, str],
    site: dict,
    sink: ConflictSink,
    strategy: Strategy,
    builder: GraphBuilder,
    resolved: dict,
    spans_by_model: dict,
    spans: dict[str, Span],
    run_facts: dict,
) -> None:
    """Panel gaps and rail spacing, against the limits knowledge holds.

    **The tier decides the consequence, not the check.** ADR-0005 is explicit
    that a violated hard constraint is a generation failure, and that is what the
    max-span check already does. It would be incoherent for a 1801 mm span to be
    fatal while a 130 mm child-head gap is a note. So the same check raises
    `GenerationFailure` when the governing knowledge object is a
    `hard_constraint` and warns otherwise — the demo seeds these as
    `company_rule` precisely because the numbers in it are US/AU/UK and Israeli
    standards have not been researched. A jurisdiction pack seeds them as
    `hard_constraint` and they stop a job, with no code change.

    Aggregated per section like `height_not_supported`, and for the same reason:
    a systemic gap on a 60-bay fence is one thing to go fix, not sixty.
    """
    for key, span_ids in spans_by_model.items():
        sm = resolved[key]
        # the run's REAL facts, not invented zeros: a limit conditioned on run
        # length or grade would otherwise resolve against a fence that does not
        # exist — and this context can raise, when the winner is a hard constraint
        ctx = {"scope": bind_scope(scope, {"series": sm.model.id}),
               "run": dict(run_facts), "site": site}
        for limit_rule in _PANEL_LIMITS:
            code, param = limit_rule.code, limit_rule.param
            res = resolve_param(kb, ctx, param)
            sink.extend(res.conflicts)
            if res.winner is None:
                continue  # no rule, no check — a limit nobody stated is not zero
            limit = next(a.value for a in res.winner.actions if a.kind == "set_param")
            offenders = [
                (worst, sid) for sid in span_ids
                if (worst := _panel_offence(code, spans[sid], limit)) is not None
            ]
            if not offenders:
                continue
            worst = (min if code == "rail_separation_insufficient" else max)(
                value for value, _ in offenders)
            affected = sorted(sid for _, sid in offenders)
            params = {"element": run.id, "run_id": run.id, "model_ref": sm.model.ref,
                      "value_mm": worst, "limit_mm": limit, "n": len(affected)}
            if res.winner.version.type == "hard_constraint":
                raise GenerationFailure(
                    f"{code} in section {run.id}: {worst} mm against a limit of "
                    f"{limit} mm, in {len(affected)} bay(s)",
                    code=code, constraint_refs=[res.winner.version.ref], **params,
                )
            node = builder.add(
                "conflict", code, payload=dict(params), scope_refs=affected,
                governed_by=[res.winner.version.ref],
            )
            strategy.warnings.append(StrategyWarning(
                code=code, severity="warning",
                message=f"{code} in section {run.id}: {worst} mm against a limit "
                        f"of {limit} mm, in {len(affected)} bay(s).",
                element_refs=affected, decision_ref=node.id, params=params,
            ))


def _panel_offence(code: str, span: Span, limit: Mm) -> Mm | None:
    """The offending measurement for this check on this bay, or None if it passes."""
    if span.panel is None:
        return None
    if code == "clear_gap_exceeded":
        # against max(openings_mm), never one rounded average and never the
        # between-member gaps alone. A fit spreads its residual a millimetre at a
        # time, so a single rounded value would pass a limit several real
        # openings exceeded — and `center` justification puts the whole residual
        # against the POSTS, where `gaps_mm` cannot see it at all.
        openings = [o for slot in span.panel.slots if slot.fit
                    for o in slot.fit.openings_mm]
        worst = max(openings, default=0)
        return worst if worst > limit else None
    if code == "rail_separation_insufficient":
        # the anti-ladder rule: the rail above the bottom one must be far enough
        # up that a child cannot climb the two. Only meaningful with three or
        # more rails; two rails are the top and the bottom of the frame.
        for slot in span.panel.slots:
            if slot.orientation == "horizontal" and len(slot.positions_mm) >= 3:
                rungs = sorted(slot.positions_mm)
                gap = rungs[1] - rungs[0]
                if gap < limit:
                    return gap
        return None
    residuals = [slot.fit.residual_mm for slot in span.panel.slots if slot.fit]
    worst = max(residuals, default=0)
    return worst if worst > limit else None


def _check_post_lengths(
    topology: Topology,
    kb: KnowledgeBase,
    scope: dict[str, str],
    site: dict,
    sink: ConflictSink,
    catalog: Catalog,
    builder: GraphBuilder,
    strategy: Strategy,
) -> None:
    """Plumb-post consequence of sloped ground: the downhill post of a stepped
    panel is exposed (panel height + step) above ITS ground, plus embedment below.
    When the catalog knows the post's physical length, verify it suffices.

    Also the one place `post_embed_mm` becomes a fact about a post: it is recorded
    on every post here, so the elevation draws the footing the length check paid
    for and the two cannot drift apart."""
    embed, embed_refs = _resolve_quantity(
        kb, {"scope": bind_scope(scope), "site": site}, "post_embed_mm", 600, sink
    )
    # The embedment gets a node of its own, the same shape `resolve_span_quantities`
    # has one function away. It used to cite `embed_refs` ONLY in the failure
    # branch below, so in the ordinary case nothing recorded that 600 mm had been
    # decided or by which version — while this arc promoted `embed_mm` to a
    # persisted field and then to a dimension on a drawing. Two knowledge
    # versions of `post_embed_mm` then drew two different footings with no
    # `defeated` edge anywhere (review finding 6).
    #
    # Scoped to the posts that actually spend length on it: a masonry-mounted
    # post is bolted to what it stands on and embeds nothing, so putting it in
    # this node's scope would explain a depth it does not have. A fence with no
    # buried post at all gets no node, because then nothing was decided.
    buried = [p.id for p in strategy.posts if p.mounting == "ground"]
    embed_node = builder.add(
        "quantity", "resolve_post_embedment",
        payload={"embed_mm": embed, "n": len(buried)},
        scope_refs=buried,
        governed_by=embed_refs,
    ) if buried else None

    def top_of(span: Span) -> Mm:
        return max(span.bottom_z_start_mm, span.bottom_z_end_mm) + span.height_mm

    run_lengths = {run.id: run_length(topology, run) for run in topology.runs}
    for post in strategy.posts:
        # a masonry-mounted post is bolted to what it stands on; only a post set
        # INTO the ground spends length on embedment
        #
        # Recorded BEFORE the adjacency search, because embedment is a property of
        # how the post is set — resolved once for the whole topology, from a scope
        # no span narrows. The `continue` below skips posts with no bay to measure
        # against — the node post of a run whose first bay is a gate has none — and
        # those are still buried; leaving them at 0 would draw them sitting on top
        # of the ground.
        post.embed_mm = embed if post.mounting == "ground" else 0
        adjacent: list[Span] = []
        if post.run_ref.startswith("node:"):
            node_id = post.run_ref.split(":", 1)[1]
            for run in topology.runs:
                for sp in strategy.spans:
                    if sp.run_ref != run.id:
                        continue
                    if run.start_node_id == node_id and sp.start_station_mm == 0:
                        adjacent.append(sp)
                    if run.end_node_id == node_id and sp.end_station_mm == run_lengths[run.id]:
                        adjacent.append(sp)
        else:
            adjacent = [
                sp for sp in strategy.spans
                if sp.run_ref == post.run_ref
                and post.station_mm in (sp.start_station_mm, sp.end_station_mm)
            ]
        if not adjacent:
            # No bay meets this post — the node post of a run whose first bay is
            # a gate — so there is no top to carry and `exposed_mm`/`top_z_mm`
            # stay None. NOT 0: this check never measured this post, and a 0 on
            # the setting-out sheet would draw it flat to the ground.
            continue
        stand_z = post.base_z_mm if post.base_z_mm is not None else post.ground_z_mm
        top_z = max(top_of(sp) for sp in adjacent)
        exposed = top_z - stand_z
        if post.tilt_deg:
            import math

            exposed = round(exposed / math.cos(math.radians(post.tilt_deg)))
        # the two numbers this check just made, kept on the post so the drawing
        # places its top from them instead of asking the same question again in
        # another language (review finding 4). `top_z_mm` is where the top SITS
        # — the highest bay top this post carries; `exposed_mm` is how much post
        # that takes, which on a tilted post is the longer of the two.
        post.top_z_mm = top_z
        post.exposed_mm = exposed
        required = exposed + post.embed_mm
        product = catalog.products.get(post.sku)
        available = (product.capabilities.length_mm if product else None)
        if isinstance(available, int) and required > available:
            node = builder.add(
                "conflict", "insufficient_post_length",
                # the post's own embedment, not the resolved default: on a masonry
                # post required is exposed alone, and a node claiming 600 mm
                # underground would explain a sum it did not make
                payload={"element": post.id, "required_mm": required,
                         "available_mm": available, "exposed_mm": exposed,
                         "embed_mm": post.embed_mm},
                scope_refs=[post.id],
                # the embedment reaches this sum through the node that decided
                # it, so the chain from the shortfall back to the rule is an
                # edge rather than a repeated citation
                inputs=[embed_node.id] if embed_node is not None else [],
                governed_by=embed_refs,
            )
            strategy.warnings.append(
                StrategyWarning(
                    code="insufficient_post_length", severity="error",
                    message=f"Post {post.id} needs {required} mm ({exposed} exposed "
                            f"+ {post.embed_mm} embedded) but {post.sku} is only "
                            f"{available} mm long.",
                    element_refs=[post.id], decision_ref=node.id,
                    params={"element": post.id, "required_mm": required,
                            "available_mm": available, "sku": post.sku},
                )
            )


# --- span height (intents, wall profiles) -------------------------------------

def _interval_at(topo: Topology, run: Run, station: Mm, kind: str):
    for ev in run.interval_events:
        if ev.payload.kind == kind:
            s0 = anchor_station(topo, run, ev.start_anchor)
            s1 = anchor_station(topo, run, ev.end_anchor)
            if s0 <= station <= s1:
                return ev, s0, s1
    return None, 0, 0


BUILT_BASES = ("masonry_wall", "concrete")


def _span_height(
    topo: Topology, run: Run, mid: Mm, gz0: Mm, gz1: Mm, policy: dict
) -> tuple[Mm, str, dict]:
    """Panel height for a span: (height_mm, source, extra decision payload).

    Priority: confirmed top_line intent (level top) > height intent (reduced by wall
    top when the panel sits on a wall) > policy default.
    """
    top_ev, _, _ = _interval_at(topo, run, mid, "top_line")
    if top_ev is not None and top_ev.payload.mode == "level" and top_ev.payload.z_mm is not None:
        height = max(0, top_ev.payload.z_mm - max(gz0, gz1))
        return height, top_ev.id, {"top_line_z_mm": top_ev.payload.z_mm}

    height_ev, _, _ = _interval_at(topo, run, mid, "height_intent")
    height = height_ev.payload.height_mm if height_ev is not None else policy["default_height_mm"]
    source = height_ev.id if height_ev is not None else "policy_default"
    extra: dict = {}
    if base_surface_at(topo, run, mid) in BUILT_BASES:
        top = base_top_at(topo, run, mid)
        if top is not None:
            top_h, top_ev_id = top
            height = max(0, height - top_h)
            # key names kept from the wall-only era; the id may reference a
            # base_top OR wall_profile event (sections-model addendum)
            extra = {"adjusted_by_wall_profile": top_ev_id, "wall_top_mm": top_h}
    return height, source, extra


def _surface_conflicts(conflicts, builder: GraphBuilder, strategy: Strategy) -> None:
    """Surface each DISTINCT disagreement once.

    The same slot is resolved many times in a run — once per segment, once per
    run, once per post — so two published rows that tie produce one conflict per
    RESOLUTION, and a two-run fence reported the identical disagreement twice. It
    is one fact about the knowledge, not one fact per place we happened to look:
    a run claiming two disagreements where there is one is its own wrong answer,
    and the count is what a reviewer triages by.

    Keyed on the slot AND the contenders, so a slot that genuinely ties against
    different rules under two scopes is still two findings.
    """
    seen: set[tuple] = set()
    for c in conflicts:
        key = (c.param_or_action, tuple(c.contenders))
        if key in seen:
            continue
        seen.add(key)
        node = builder.add(
            "conflict", "knowledge_conflict",
            payload={"slot": c.param_or_action, "contenders": c.contenders},
        )
        strategy.warnings.append(
            StrategyWarning(
                code="knowledge_conflict", severity="error" if c.hard else "warning",
                message=c.message,
                params={"slot": c.param_or_action, "contenders": ", ".join(c.contenders)},
                decision_ref=node.id,
            )
        )
        if not c.hard:
            continue
        # A hard tie only survives because a contender was PUBLISHED, and only
        # the publisher can fix two of their own rows contradicting each other.
        # A `StrategyWarning` alone leaves that entirely inside this repo: it
        # renders on our drawing and reaches nobody who can act on it. The gap is
        # what §3.2.6 sends back.
        #
        # `disputed` is the honest kind, and `on="value"` is the honest
        # discriminator: these rows agree about WHEN they apply — that is why
        # they tied on scope — and disagree about the number. §1.2.1 is careful
        # that publish-time `disputed` is not the same event as a resolution-time
        # `Conflict`; this is the second one telling the first what it found, not
        # the two being conflated.
        strategy.gaps.append(Gap(
            id=f"gap:disputed:{c.param_or_action}:" + ",".join(sorted(c.contenders)),
            kind="disputed", on="value",
            subject=GapSubject(kind="param", ref=c.param_or_action),
            code="knowledge_conflict",
            params={"slot": c.param_or_action, "contenders": ", ".join(c.contenders)},
            message=c.message,
            would_close=(
                f"a decision on which of {', '.join(sorted(c.contenders))} states "
                f"{c.param_or_action}, or conditions that separate them"
            ),
            closes_by="knowledge", severity="warns_line",
        ))
