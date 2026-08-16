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
from dataclasses import dataclass

from fenceai.catalog.model import CATALOG_SCHEMA_VERSION, Catalog, catalog_hash
from fenceai.core.errors import GenerationFailure
from fenceai.core.units import SNAP_TOLERANCE_MM, Mm, slope_len_mm
from fenceai.decisions.graph import GraphBuilder
from fenceai.fencemodel.demo import legacy_model
from fenceai.fencemodel.library import FenceModelLibrary, content_hash
from fenceai.fencemodel.match import match_eligibility, match_spec, panel_facts
from fenceai.fencemodel.model import FenceModel, unknown_skus, validate_model
from fenceai.fencemodel.resolve import (
    PanelContext, ResolvedPanel, choose_variant, clear_opening_mm, height_supported,
    resolve_panel,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.evaluator import (
    Resolution,
    preference_firings,
    resolve as evaluator_resolve,
    resolve_actions,
    resolve_param,
)
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.strategy.layout import boundaries, layout_segment
from fenceai.strategy.model import (
    Gate,
    GenerationResult,
    GenerationRun,
    ModelUse,
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
    run_length,
)

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
# There is deliberately NO fulfillment version here. A run's stored document is
# the strategy and its graph; the BOM is recomputed on every read and is already
# a function of mutable inventory. A fulfillment algorithm version belongs to the
# materialization identity this system does not have yet (see the backend audit
# response, §1.5) — putting it in the DESIGN digest would deepen exactly the
# conflation that finding is about.
PLANNING_BEHAVIOR_VERSION = "planning-v1"
RUN_DIGEST_VERSION = "digest-v1"

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
) -> GenerationResult:
    overrides = overrides or []
    models = models or FenceModelLibrary()
    policy = {**DEFAULT_POLICY, **(policy or {})}
    builder = GraphBuilder()
    strategy = Strategy(id="strategy")
    applied: set[str] = set()
    # dimensions known for the whole run; narrower ones (surface, context) are
    # bound where they become facts
    scope = bind_scope({"project_id": project_id})

    demand_skus, demand_refs = _resolve_demand_skus(knowledge, scope)
    builder.add(
        "quantity", "resolve_demand_products",
        payload=dict(demand_skus),
        governed_by=demand_refs,
    )

    _generate_node_posts(
        topology, knowledge, scope, catalog, overrides, builder, strategy, applied,
        models, default_model,
    )
    # every fence model actually drawn from, across all runs — part of the run id
    # (a model swap changes what the run means even though the digest's other
    # inputs are untouched)
    models_used: list[ModelUse] = []
    for run in topology.runs:
        _generate_run(
            topology, run, knowledge, scope, catalog, overrides, policy,
            builder, strategy, applied, demand_skus, models_used,
            models, default_model,
        )

    _check_post_lengths(topology, knowledge, scope, catalog, builder, strategy)

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
    # - objective_preset: which supply-resolution preset a later /bom read will use
    run_meta.model_snapshot = sorted(
        {u.sort_key(): u for u in models_used}.values(), key=ModelUse.sort_key
    )
    run_meta.catalog_skus = _skus_used(strategy, demand_skus)
    run_meta.catalog_hash = catalog_hash(catalog, run_meta.catalog_skus)
    run_meta.catalog_schema_version = CATALOG_SCHEMA_VERSION
    # `policy` was already merged with DEFAULT_POLICY above, so the key always
    # exists — a `.get(..., "least_cost")` fallback here could never fire; direct
    # indexing says so instead of implying a fallback that is dead on arrival.
    run_meta.objective_preset = policy["objective_preset"]
    run_meta.id = "run_" + hashlib.sha256(
        json.dumps(
            # project_id is BOUND AS A SCOPE DIMENSION (bind_scope, above), so a
            # project-scoped rule changes the fence without changing any other
            # digest input. Two projects with the same topology then collide, and
            # `save_run`'s INSERT OR IGNORE drops the second silently: its user
            # presses Generate, sees their own answer in the response, and every
            # later read serves the other project's fence.
            [project_id, topology.model_dump(), run_meta.knowledge_snapshot,
             [o.model_dump() for o in overrides], policy,
             [u.model_dump() for u in run_meta.model_snapshot], run_meta.catalog_hash,
             run_meta.objective_preset,
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


def _post_ctx(scope: dict[str, str], surface: str, context: str = "") -> dict:
    return {
        "scope": bind_scope(scope, {"surface": surface, "context": context}),
        "post": {"surface": surface, "context": context},
    }


def _resolve_mounting(
    kb: KnowledgeBase, scope: dict[str, str], surface: str
) -> tuple[str, str | None, list[str]]:
    """(mounting, rule sku, governed refs) for a base surface — slot-scoped so rules
    for other surfaces never compete (critic finding 5)."""
    res = resolve_actions(
        kb, _post_ctx(scope, surface), "require_mounting", match=lambda a: a.surface == surface
    )
    if res.winner:
        act = res.winner.actions[0]
        return act.mounting, act.sku, [res.winner.version.ref]
    return "ground", None, []


def _resolve_reinforcement(
    kb: KnowledgeBase, scope: dict[str, str]
) -> tuple[str | None, list[str]]:
    """(reinforced-post sku, governed refs) for gate context, or (None, [])."""
    res = resolve_actions(
        kb, _post_ctx(scope, "", context="gate"), "require_post_reinforcement",
        match=lambda a: a.context == "gate",
    )
    if res.winner:
        return res.winner.actions[0].sku, [res.winner.version.ref]
    return None, []


def _resolve_default_post(
    kb: KnowledgeBase, scope: dict[str, str], surface: str
) -> tuple[str, list[str]]:
    res = resolve_actions(
        kb, _post_ctx(scope, surface), "default_component",
        match=lambda a: a.role == "post_ground",
    )
    if res.winner:
        return res.winner.actions[0].sku, [res.winner.version.ref]
    raise GenerationFailure("no default ground-post product in knowledge (role post_ground)")


DEMAND_ROLE_DEFAULTS = {
    "rail": ("rail_sku", "RAIL-3000"),
    "screw": ("screw_sku", "SCREW-S10"),
    "concrete": ("concrete_sku", "CONC-25"),
    "cap": ("cap_sku", "POST-CAP"),
}


def _resolve_demand_skus(
    kb: KnowledgeBase, scope: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Demand product selection is knowledge (DefaultComponent roles), never a
    code literal — swapping the whole fence system (e.g. to a Barrette catalog)
    is a rule change. Falls back to the demo defaults when no rule exists."""
    skus: dict[str, str] = {}
    refs: list[str] = []
    for role, (key, fallback) in DEMAND_ROLE_DEFAULTS.items():
        res = resolve_actions(
            kb, _post_ctx(scope, ""),
            "default_component", match=lambda a, role=role: a.role == role,
        )
        if res.winner:
            skus[key] = res.winner.actions[0].sku
            refs.append(res.winner.version.ref)
        else:
            skus[key] = fallback
    return skus, refs


def _resolve_quantity(kb: KnowledgeBase, ctx: dict, param: str, default: int) -> tuple[int, list[str]]:
    res = resolve_param(kb, ctx, param)
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



def _model_post_skus(
    library: FenceModelLibrary,
    default_model: FenceModelChoice | None,
    topo: Topology,
    run: Run,
    station: Mm,
    catalog: Catalog,
) -> tuple[str | None, str | None]:
    """The post and cap the MODEL at this station asks for, if it asks.

    Sampled at the POST'S OWN station rather than gathered from the bays either
    side. A post stands at one place, and `fence_model_at` answers for that place
    with the same half-open convention every other station question uses — so the
    answer cannot depend on which neighbouring bay happened to be resolved first.

    Choosing among several matched candidates is `sorted-first`, not cost-based:
    a post is one line and the cut-plan coupling that makes `select_supply` worth
    running does not apply to an indivisible each. Recorded in the limitations
    rather than faked — a post line still carries its full eligibility into
    demand, so the choice remains explainable there.
    """
    choice = fence_model_at(topo, run, station) or default_model
    if choice is None:
        return None, None
    model = library.resolve(choice.model_id, choice.version_pin)
    if model is None or model.post is None:
        return None, None

    def first(req) -> str | None:
        if req is None:
            return None
        resolved = match_eligibility(req.eligibility, catalog, {})
        return resolved.members[0].sku if resolved.members else None

    return first(model.post.requirement), first(model.post.cap)


def _make_post(
    builder: GraphBuilder,
    kb: KnowledgeBase,
    scope: dict[str, str],
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
    model_cap: str | None = None,
) -> Post:
    """Create a post; every selection resolved from knowledge BEFORE the decision
    node is recorded — elements are never mutated afterwards (critic finding 4)."""
    mounting, mount_sku, governed = _resolve_mounting(kb, scope, surface)
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
    else:
        sku, sku_refs = _resolve_default_post(kb, scope, surface)
    post = Post(
        id=post_id, run_ref=run_ref, station_mm=station, kind=kind,  # type: ignore[arg-type]
        reinforced=reinforced, mounting=mounting, sku=sku,  # type: ignore[arg-type]
        ground_z_mm=ground_z_mm, base_z_mm=base_z_mm, tilt_deg=tilt_deg, pinned=pinned,
        cap_sku=model_cap or "",
    )
    builder.add(
        "structural", "place_post",
        payload={"station_mm": station, "kind": kind, "surface": surface,
                 "mounting": mounting, "sku": sku,
                 **({"base_z_mm": base_z_mm} if base_z_mm is not None
                    and base_z_mm != ground_z_mm else {}),
                 **({"tilt_deg": tilt_deg} if tilt_deg else {})},
        scope_refs=[post.id],
        inputs=inputs + (override_nodes or []),
        governed_by=governed + (reinforcement_refs or []) + sku_refs,
        status="pinned" if pinned else "proposed",
    )
    return post


# --- node posts ---------------------------------------------------------------

def _generate_node_posts(
    topology: Topology,
    kb: KnowledgeBase,
    scope: dict[str, str],
    catalog: Catalog,
    overrides: list[Override],
    builder: GraphBuilder,
    strategy: Strategy,
    applied: set[str],
    library: FenceModelLibrary | None = None,
    default_model: FenceModelChoice | None = None,
) -> None:
    touches_by_node: dict[str, list[tuple[Run, Mm]]] = {}
    for run in topology.runs:
        touches_by_node.setdefault(run.start_node_id, []).append((run, 0))
        touches_by_node.setdefault(run.end_node_id, []).append(
            (run, run_length(topology, run))
        )

    reinf_sku, reinf_refs = _resolve_reinforcement(kb, scope)

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
        kind = "end" if len(touches) == 1 else ("corner" if len(touches) == 2 else "junction")
        fact = builder.add(
            "input_fact", "topology_node",
            payload={"node_id": node.id, "x_mm": node.x_mm, "y_mm": node.y_mm,
                     "runs": len(touches)},
        )
        node_post_sku, node_cap_sku = (
            _model_post_skus(library, default_model, topology, run0, station0, catalog)
            if library is not None else (None, None))
        post = _make_post(
            builder, kb, scope,
            model_post=node_post_sku, model_cap=node_cap_sku,
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
        strategy.posts.append(post)


# --- per-run generation --------------------------------------------------------

def _validate_resolved_model(model: FenceModel, catalog: Catalog) -> None:
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

    Cost: O(model) — slots x eligibility members, plus axes x values, with
    catalog access by dict lookup only. It does not touch the topology, so it
    does not grow with the fence: it runs once per distinct model CHOICE on a run
    (memoised in `segment_model`), never once per segment and never once per
    span — a run built entirely to one model validates once. Measured on this machine:
    2.1 us for `M-LEGACY` against 0.85 ms for a four-bay `generate()` (0.24%),
    and 0.04% of a 60-bay one, where it is still a single call. No caching
    needed — and a cache keyed on a model that `legacy_model()` rebuilds per
    call would cost more than the check it skipped.
    """
    errors = validate_model(model, catalog)
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
    max_span_ref: str
    firing_node_id: str
    rails_per_span: int
    screws_per_span: int
    quantity_refs: list[str]
    # a manufactured bay width, when the model's line ships as pre-assembled
    # panels: not a preference, so it does not compete with one
    exact_span: Mm | None = None
    exact_span_ref: str | None = None


LEGACY_MODEL_ID = "M-LEGACY"
LEGACY_MODEL_VERSION = 1


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
        _validate_resolved_model(model, catalog)
        # `series` is the dimension a knowledge rule needs to say "spans exactly
        # 1800 on that product line" — blocked until a model id was a fact of
        # generation (plan/current-status.md, the two blocked dimensions).
        seg_ctx = {
            "scope": bind_scope(scope, {"series": model.id}),
            "run": ctx["run"],
        }
        # The model's layout policy joins the knowledge BEFORE anything under
        # this scope is resolved — a contribution added after `max_span_mm` had
        # resolved would be a contribution that never applied. The run's own
        # KnowledgeBase is never mutated (generate() does not touch its inputs):
        # this is a per-segment view of it, so one model's asks cannot survive
        # into the next segment's resolution.
        seg_kb = (KnowledgeBase(versions=[*kb.versions, *_policy_knowledge(model)])
                  if model.layout_policy else kb)
        select_node = builder.add(
            "selection", "select_model",
            payload={"model_ref": model.ref, "source": source,
                     "options": options},
            inputs=[run_fact.id],
        )

        res = resolve_param(seg_kb, seg_ctx, "max_span_mm")
        if res.winner is None:
            raise GenerationFailure(f"no max_span_mm knowledge applies to run {run.id}")
        max_span_mm: Mm = next(a.value for a in res.winner.actions if a.kind == "set_param")
        firing = builder.add(
            "rule_firing", "resolve_max_span",
            payload={"param": "max_span_mm", "value": max_span_mm},
            inputs=[run_fact.id, select_node.id],
            governed_by=[res.winner.version.ref],
            # a defeated edge cites the LOSING version (decision-model.md); the loser
            # is any firing whose defeated_by is non-empty
            defeated=[f.version.ref for f in res.firings if f.defeated_by],
        )
        _surface_conflicts(res.conflicts, builder, strategy)

        # a manufactured bay width, if this model's line has one. Resolved under
        # the same segment scope as the rest, so a model contributes it through
        # `layout_policy` rather than through a private channel.
        exact_res = resolve_param(seg_kb, seg_ctx, "exact_span_mm")
        exact_span = exact_span_ref = None
        if exact_res.winner is not None:
            exact_span = next(a.value for a in exact_res.winner.actions
                              if a.kind == "set_param")
            exact_span_ref = exact_res.winner.version.ref

        rails, rails_refs = _resolve_quantity(seg_kb, seg_ctx, "rails_per_span", 2)
        screws, screws_refs = _resolve_quantity(seg_kb, seg_ctx, "screws_per_span", 8)

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
            max_span_ref=res.winner.version.ref,
            firing_node_id=firing.id,
            rails_per_span=rails,
            screws_per_span=screws,
            quantity_refs=rails_refs + screws_refs,
            exact_span=exact_span, exact_span_ref=exact_span_ref,
        )
        resolved[key] = sm
        models_used.append(sm.use)
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
            payload={"event_id": ev_id, "start_mm": gs, "end_mm": ge},
        )
        gate_fact_ids[ev_id] = fact.id
        for s in (gs, ge):
            gate_edge_facts.setdefault(s, []).append(fact.id)

    # -- overrides addressed to this run ---------------------------------------
    pinned_stations: dict[Mm, Override] = {}
    suppress_ovs: list[Override] = []
    force_vertical_ovs: list[Override] = []
    for ov in overrides:
        if ov.run_id != run.id:
            continue
        d = ov.directive
        if d.kind == "pin_post" and 0 < d.station_mm < length:
            pinned_stations[d.station_mm] = ov
        elif d.kind == "suppress_post":
            suppress_ovs.append(ov)
        elif d.kind == "force_vertical":
            force_vertical_ovs.append(ov)

    corners = corner_stations(topo, run)
    transitions = base_transition_stations(topo, run)
    # base-top STEPS >= threshold force a structural boundary; the threshold is
    # knowledge, not code (K-STEP-POST) — sections-model addendum
    step_threshold, step_refs = _resolve_quantity(
        kb, ctx, "base_top_step_boundary_mm", 100
    )
    base_steps = base_top_step_stations(topo, run, step_threshold)
    step_info = {station: (delta, ev_id, "base_top_step")
                 for station, delta, ev_id in base_steps}
    # vertical GROUND steps (cliffs/retaining drops) are structural boundaries too
    for station, delta in ground_step_stations(topo, run, step_threshold):
        step_info.setdefault(station, (delta, None, "ground_step"))
    step_stations = set(step_info)
    # buildability ceiling: a single step a fence can absorb (rule-editable)
    max_step, max_step_refs = _resolve_quantity(kb, ctx, "max_panel_step_mm", 600)
    # optional plumb-consequence rules: only checked when a rule exists
    gap_res = resolve_param(kb, ctx, "max_panel_gap_mm")
    max_gap = (next(a.value for a in gap_res.winner.actions if a.kind == "set_param")
               if gap_res.winner else None)
    height_res = resolve_param(kb, ctx, "max_fence_height_mm")
    max_height = (next(a.value for a in height_res.winner.actions if a.kind == "set_param")
                  if height_res.winner else None)
    gate_slope_res = resolve_param(kb, ctx, "gate_max_slope_permille")
    max_gate_slope = (
        next(a.value for a in gate_slope_res.winner.actions if a.kind == "set_param")
        if gate_slope_res.winner else None)
    fixed: set[Mm] = {0, length} | set(corners) | set(transitions) | set(pinned_stations)
    fixed |= gate_edges | step_stations
    # a model change is a structural boundary for the same reason a base transition
    # is: a bay may not straddle the place where the fence becomes a different fence
    fixed |= set(fence_model_transition_stations(topo, run))
    fixed_sorted = sorted(fixed)

    reinf_sku, reinf_refs = _resolve_reinforcement(kb, scope)

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
        fixed_post_sku, fixed_cap_sku = _model_post_skus(
            library, default_model, topo, run, station, catalog)
        post = _make_post(
            builder, kb, scope,
            model_post=fixed_post_sku, model_cap=fixed_cap_sku,
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

    # -- vertical mode: slot-resolved, never loop-overwritten ------------------
    default_vertical = "level" if slope_permille == 0 else "raked"
    vert_firings = preference_firings(kb, ctx, {"prefer_vertical"})
    modes = {a.mode for f in vert_firings for a in f.actions if a.kind == "prefer_vertical"}
    vert_res: Resolution = evaluator_resolve(
        vert_firings, "vertical_mode", values_agree=len(modes) <= 1
    )
    _surface_conflicts(vert_res.conflicts, builder, strategy)
    if vert_res.winner:
        vertical = next(
            a.mode for a in vert_res.winner.actions if a.kind == "prefer_vertical"
        )
        vertical_refs = [vert_res.winner.version.ref]
        vertical_defeated = [f.version.ref for f in vert_res.firings if f.defeated_by]
    else:
        vertical = default_vertical
        vertical_refs = []
        vertical_defeated = []
    vertical_node = builder.add(
        "vertical", "choose_vertical_mode",
        payload={"mode": vertical, "slope_permille": slope_permille},
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
        for ov in force_vertical_ovs:
            d = ov.directive
            if d.start_station_mm <= mid <= d.end_station_mm:
                applied.add(ov.id)
                if ov.id not in fv_nodes:
                    fv_nodes[ov.id] = builder.add(
                        "override_applied", "force_vertical",
                        payload={"override_id": ov.id, "mode": d.mode,
                                 "interval": [d.start_station_mm, d.end_station_mm]},
                    ).id
                return d.mode, fv_nodes[ov.id]
        return vertical, None

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
        _surface_conflicts(res_layout.conflicts, builder, strategy)
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
        governed = [sm.max_span_ref] + ([layout_pref_ref] if layout_pref_ref else [])
        if layout.exact_over_max:
            _exact_over_max(builder, strategy, run, sm)
        elif layout.remainder_mm is not None:
            _span_not_exact(builder, strategy, run, seg_start, seg_end, sm, layout)
        layout_node = builder.add(
            "structural", "layout_spans",
            payload={
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
            line_post_sku, line_cap_sku = _model_post_skus(
                library, default_model, topo, run, s, catalog)
            post = _make_post(
                builder, kb, scope,
                model_post=line_post_sku, model_cap=line_cap_sku,
                post_id=f"post@{run.id}:{s}", run_ref=run.id,
                station=s, kind="line", surface=surface,
                ground_z_mm=ground_z(topo, run, s),
                base_z_mm=_stand_z(topo, run, s),
                inputs=[layout_node.id],
                forced_sku=forced_sku, forced_mounting=forced_mounting,
                override_nodes=override_nodes,
                tilt_deg=tilt_deg,
            )
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
            builder.add(
                "structural", "resolve_panel",
                payload={"model_ref": model.ref,
                         "slots": _panel_slots_payload(span.panel)},
                scope_refs=[span.id], inputs=panel_inputs,
            )
            if width > sm.max_span:
                raise GenerationFailure(
                    f"span {span.id} width {width} exceeds hard max {sm.max_span}",
                    constraint_refs=[sm.max_span_ref],
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

    _check_panel_safety(kb, run, scope, strategy, builder, resolved, spans_by_model,
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


def _check_panel_safety(
    kb: KnowledgeBase,
    run: Run,
    scope: dict[str, str],
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
               "run": dict(run_facts)}
        for limit_rule in _PANEL_LIMITS:
            code, param = limit_rule.code, limit_rule.param
            res = resolve_param(kb, ctx, param)
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
        kb, {"scope": bind_scope(scope)}, "post_embed_mm", 600
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
    for c in conflicts:
        node = builder.add(
            "conflict", "knowledge_conflict",
            payload={"slot": c.param_or_action, "contenders": c.contenders},
        )
        strategy.warnings.append(
            StrategyWarning(
                code="knowledge_conflict", severity="warning",
                message=c.message,
                params={"slot": c.param_or_action, "contenders": ", ".join(c.contenders)},
                decision_ref=node.id,
            )
        )
