"""Strategy generation: pure, deterministic pipeline (ADR-0004, foundation §7).

generate(topology, knowledge, catalog, overrides, policy) -> GenerationResult.
Every structural/selection output is created through the GraphBuilder with its
evidence edges — the decision graph is not reconstructed afterwards.
"""

from __future__ import annotations

import hashlib
import json

from fenceai.catalog.model import Catalog
from fenceai.core.errors import GenerationFailure
from fenceai.core.units import Mm, slope_len_mm
from fenceai.decisions.graph import GraphBuilder
from fenceai.knowledge.evaluator import preference_firings, resolve_actions, resolve_param
from fenceai.knowledge.model import KnowledgeBase
from fenceai.strategy.layout import boundaries, layout_segment
from fenceai.strategy.model import (
    Gate,
    GenerationResult,
    GenerationRun,
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
    base_transition_stations,
    corner_stations,
    ground_z,
    run_length,
)

DEFAULT_POLICY: dict = {"default_height_mm": 1800, "objective_preset": "fewest_new_stock"}
GATE_REINFORCEMENT_REACH_MM = 1  # flanking post exactly at gate edge


def _height_at(topo: Topology, run: Run, station: Mm, policy: dict) -> tuple[Mm, str | None]:
    """Height intent at a station: (height, source event id or None for policy default)."""
    for ev in run.interval_events:
        if ev.payload.kind == "height_intent":
            s0 = anchor_station(topo, run, ev.start_anchor)
            s1 = anchor_station(topo, run, ev.end_anchor)
            if s0 <= station <= s1:
                return ev.payload.height_mm, ev.id
    return policy["default_height_mm"], None


def generate(
    topology: Topology,
    knowledge: KnowledgeBase,
    catalog: Catalog,
    overrides: list[Override] | None = None,
    policy: dict | None = None,
    project_id: str = "",
) -> GenerationResult:
    overrides = overrides or []
    policy = {**DEFAULT_POLICY, **(policy or {})}
    builder = GraphBuilder()
    strategy = Strategy(id="strategy")
    applied_overrides: list[str] = []

    # --- shared node posts (S03: one physical post per node) -----------------
    node_degree: dict[str, list[tuple[Run, str]]] = {}
    for run in topology.runs:
        node_degree.setdefault(run.start_node_id, []).append((run, "start"))
        node_degree.setdefault(run.end_node_id, []).append((run, "end"))

    node_post_ids: dict[str, str] = {}
    for node in topology.nodes:
        touches = node_degree.get(node.id, [])
        if not touches:
            continue
        run, end = touches[0]
        station = 0 if end == "start" else run_length(topology, run)
        surface = base_surface_at(topology, run, station)
        kind = "end" if len(touches) == 1 else ("corner" if len(touches) == 2 else "junction")
        fact = builder.add(
            "input_fact", "topology_node",
            payload={"node_id": node.id, "x_mm": node.x_mm, "y_mm": node.y_mm, "runs": len(touches)},
        )
        post, decision = _make_post(
            builder, topology, knowledge, run, station,
            post_id=f"post@node:{node.id}", run_ref=f"node:{node.id}",
            kind=kind, surface=surface, inputs=[fact.id], strategy=strategy,
        )
        node_post_ids[node.id] = post.id
        strategy.posts.append(post)

    # --- per-run generation ---------------------------------------------------
    for run in topology.runs:
        _generate_run(
            topology, run, knowledge, catalog, overrides, policy,
            builder, strategy, applied_overrides,
        )

    # --- orphaned overrides ---------------------------------------------------
    for ov in overrides:
        if ov.id not in applied_overrides:
            ov.status = "orphaned"
            strategy.warnings.append(
                StrategyWarning(
                    code="orphaned_override", severity="warning",
                    message=f"Override {ov.id} ({ov.directive.kind}) no longer matches the topology and was not applied.",
                )
            )

    graph = builder.build()
    run_meta = GenerationRun(
        id="run",
        project_id=project_id,
        topology_revision=topology.revision,
        knowledge_snapshot=knowledge.snapshot_set(),
        snapshot_hash=knowledge.snapshot_hash(),
        overrides_applied=applied_overrides,
        policy=policy,
    )
    run_meta.id = "run_" + hashlib.sha256(
        json.dumps(
            [topology.model_dump(), run_meta.knowledge_snapshot, [o.model_dump() for o in overrides], policy],
            sort_keys=True, default=str,
        ).encode()
    ).hexdigest()[:12]
    return GenerationResult(run=run_meta, strategy=strategy, graph=graph)


def _make_post(
    builder: GraphBuilder,
    topo: Topology,
    kb: KnowledgeBase,
    run: Run,
    station: Mm,
    *,
    post_id: str,
    run_ref: str,
    kind: str,
    surface: str,
    inputs: list[str],
    strategy: Strategy,
    reinforced: bool = False,
    reinforcement_refs: list[str] | None = None,
    pinned: bool = False,
    forced_sku: str | None = None,
    forced_mounting: str | None = None,
) -> tuple[Post, object]:
    """Create a post with mounting + product selection decisions."""
    ctx = {"scope": {}, "post": {"surface": surface, "context": "gate" if kind == "gate" else ""}}
    mounting = "ground"
    governed: list[str] = []
    res = resolve_actions(kb, ctx, "require_mounting")
    mount_sku: str | None = None
    if res.winner:
        for act in res.winner.actions:
            if act.kind == "require_mounting" and act.surface == surface:
                mounting = act.mounting
                mount_sku = act.sku
                governed.append(res.winner.version.ref)
    if forced_mounting:
        mounting = forced_mounting
    if mounting == "masonry":
        sku = mount_sku or "POST-M"
    elif reinforced:
        sku = "POST-S-HD"
    else:
        sku = "POST-S"
    if forced_sku:
        sku = forced_sku
    post = Post(
        id=post_id, run_ref=run_ref, station_mm=station, kind=kind,  # type: ignore[arg-type]
        reinforced=reinforced, mounting=mounting, sku=sku,  # type: ignore[arg-type]
        ground_z_mm=ground_z(topo, run, station), pinned=pinned,
    )
    decision = builder.add(
        "structural", "place_post",
        payload={"station_mm": station, "kind": kind, "surface": surface,
                 "mounting": mounting, "sku": sku},
        scope_refs=[post.id],
        inputs=inputs,
        governed_by=governed + (reinforcement_refs or []),
        status="pinned" if pinned else "proposed",
    )
    return post, decision


def _generate_run(
    topo: Topology,
    run: Run,
    kb: KnowledgeBase,
    catalog: Catalog,
    overrides: list[Override],
    policy: dict,
    builder: GraphBuilder,
    strategy: Strategy,
    applied_overrides: list[str],
) -> None:
    length = run_length(topo, run)
    z0, z1 = ground_z(topo, run, 0), ground_z(topo, run, length)
    slope_pct = abs(z1 - z0) / length * 100 if length else 0.0
    run_fact = builder.add(
        "input_fact", "run_geometry",
        payload={"run_id": run.id, "length_mm": length, "slope_pct": round(slope_pct, 2)},
    )
    ctx = {"scope": {}, "run": {"length_mm": length, "slope_pct": slope_pct}}

    # -- resolve hard span parameter ------------------------------------------
    res = resolve_param(kb, ctx, "max_span_mm")
    if res.winner is None:
        raise GenerationFailure(f"no max_span_mm knowledge applies to run {run.id}")
    max_span: Mm = next(a.value for a in res.winner.actions if a.kind == "set_param")
    max_span_ref = res.winner.version.ref
    firing_node = builder.add(
        "rule_firing", "resolve_max_span",
        payload={"param": "max_span_mm", "value": max_span},
        inputs=[run_fact.id],
        governed_by=[max_span_ref],
        defeated=[ref for f in res.firings for ref in f.defeated_by],
    )
    _surface_conflicts(res.conflicts, builder, strategy)

    # -- fixed stations & gate openings ---------------------------------------
    gates: list[tuple[Mm, Mm, str, str]] = []  # (start, end, kit_sku, event_id)
    for ev in run.point_events:
        if ev.payload.kind == "gate":
            gs = anchor_station(topo, run, ev.anchor)
            ge = min(gs + ev.payload.width_mm, length)
            kit = ev.payload.kit_sku or f"GATE-KIT-{ev.payload.width_mm}"
            gates.append((gs, ge, kit, ev.id))
    gates.sort()

    pinned_stations: dict[Mm, Override] = {}
    suppressed: dict[Mm, Override] = {}
    for ov in overrides:
        if ov.run_id != run.id:
            continue
        d = ov.directive
        if d.kind == "pin_post" and 0 < d.station_mm < length:
            pinned_stations[d.station_mm] = ov
        elif d.kind == "suppress_post":
            suppressed[d.station_mm] = ov

    corners = corner_stations(topo, run)
    transitions = base_transition_stations(topo, run)
    fixed: set[Mm] = {0, length} | set(corners) | set(transitions) | set(pinned_stations)
    for gs, ge, _, _ in gates:
        fixed |= {gs, ge}
    fixed_sorted = sorted(fixed)

    # -- interior fixed posts (corners, transitions, gate edges, pins) --------
    gate_edges = {s for gs, ge, _, _ in gates for s in (gs, ge)}
    reinf_res = resolve_actions(kb, {"scope": {}, "post": {"context": "gate", "surface": ""}},
                                "require_post_reinforcement")
    reinf_ref = reinf_res.winner.version.ref if reinf_res.winner else None
    reinf_sku = None
    if reinf_res.winner:
        reinf_sku = next(
            (a.sku for a in reinf_res.winner.actions if a.kind == "require_post_reinforcement"), None
        )

    for station in fixed_sorted:
        if station in (0, length):
            continue  # node posts already exist
        surface = base_surface_at(topo, run, station)
        inputs = [run_fact.id]
        kind = "line"
        pinned = False
        reinforced = False
        reinforcement_refs: list[str] = []
        if station in gate_edges:
            kind = "gate"
            if reinf_ref:
                reinforced = True
                reinforcement_refs = [reinf_ref]
        elif station in corners:
            kind = "corner"
        elif station in transitions:
            kind = "transition"
        ov = pinned_stations.get(station)
        if ov is not None:
            pinned = True
            applied_overrides.append(ov.id)
            ov_node = builder.add(
                "override_applied", "pin_post",
                payload={"override_id": ov.id, "station_mm": station},
            )
            inputs = inputs + [ov_node.id]
        forced_sku = None
        forced_mounting = None
        for o in overrides:
            if o.run_id == run.id and o.directive.kind == "force_post_sku" and o.directive.station_mm == station:
                forced_sku = o.directive.sku
                applied_overrides.append(o.id)
            if o.run_id == run.id and o.directive.kind == "force_mounting" and o.directive.station_mm == station:
                forced_mounting = o.directive.mounting
                applied_overrides.append(o.id)
        post, _ = _make_post(
            builder, topo, kb, run, station,
            post_id=f"post@{run.id}:{station}", run_ref=run.id, kind=kind,
            surface=surface, inputs=inputs, strategy=strategy,
            reinforced=reinforced and surface != "masonry_wall",
            reinforcement_refs=reinforcement_refs, pinned=pinned,
            forced_sku=forced_sku, forced_mounting=forced_mounting,
        )
        if reinf_sku and reinforced and post.mounting == "ground":
            post.sku = reinf_sku
        strategy.posts.append(post)

    # -- gate elements ---------------------------------------------------------
    for gs, ge, kit, ev_id in gates:
        gate_fact = builder.add(
            "input_fact", "gate_event",
            payload={"event_id": ev_id, "start_mm": gs, "end_mm": ge},
        )
        gate = Gate(
            id=f"gate@{run.id}:{gs}-{ge}", run_ref=run.id,
            start_station_mm=gs, end_station_mm=ge, kit_sku=kit,
        )
        strategy.gates.append(gate)
        builder.add(
            "selection", "select_gate_kit",
            payload={"kit_sku": kit},
            scope_refs=[gate.id],
            inputs=[gate_fact.id],
            governed_by=[reinf_ref] if reinf_ref else [],
        )

    # -- vertical mode ---------------------------------------------------------
    vertical = "level" if slope_pct == 0 else "raked"
    vertical_refs: list[str] = []
    for f in preference_firings(kb, ctx, {"prefer_vertical"}):
        for a in f.actions:
            if a.kind == "prefer_vertical":
                vertical = a.mode
                vertical_refs.append(f.version.ref)
    for ov in overrides:
        if ov.run_id == run.id and ov.directive.kind == "force_vertical":
            vertical = ov.directive.mode
            applied_overrides.append(ov.id)
            ov_node = builder.add(
                "override_applied", "force_vertical",
                payload={"override_id": ov.id, "mode": vertical},
            )
            vertical_refs = []
            break
    vertical_node = builder.add(
        "vertical", "choose_vertical_mode",
        payload={"mode": vertical, "slope_pct": round(slope_pct, 2)},
        inputs=[run_fact.id],
        governed_by=vertical_refs,
    )

    # -- span layout per free segment -----------------------------------------
    prefs = preference_firings(kb, ctx, {"prefer_equal_spans", "prefer_min_span_width"})
    prefer_equal_ref = None
    min_span: Mm | None = None
    min_span_ref = None
    for f in prefs:
        for a in f.actions:
            if a.kind == "prefer_equal_spans":
                prefer_equal_ref = f.version.ref
            elif a.kind == "prefer_min_span_width":
                min_span = a.min_mm
                min_span_ref = f.version.ref

    gate_intervals = [(gs, ge) for gs, ge, _, _ in gates]
    for seg_start, seg_end in zip(fixed_sorted, fixed_sorted[1:]):
        if any(gs <= seg_start and seg_end <= ge for gs, ge in gate_intervals):
            continue  # inside a gate opening: no fence spans
        seg_len = seg_end - seg_start
        if seg_len <= 0:
            continue
        layout = layout_segment(seg_len, max_span, prefer_equal=True, min_span_mm=min_span)
        governed = [max_span_ref] + ([prefer_equal_ref] if prefer_equal_ref else [])
        layout_node = builder.add(
            "structural", "layout_spans",
            payload={
                "segment": [seg_start, seg_end],
                "widths": layout.widths,
                "alternatives": (
                    [{"widths": layout.rejected_alternative,
                      "rejected_because": prefer_equal_ref or "policy"}]
                    if layout.rejected_alternative else []
                ),
            },
            inputs=[run_fact.id, firing_node.id, vertical_node.id],
            governed_by=governed,
        )
        stations = boundaries(seg_start, layout.widths)
        for s0, s1 in zip(stations, stations[1:]):
            width = s1 - s0
            gz0, gz1 = ground_z(topo, run, s0), ground_z(topo, run, s1)
            height, height_src = _height_at(topo, run, (s0 + s1) // 2, policy)
            span = Span(
                id=f"span@{run.id}:{s0}-{s1}", run_ref=run.id,
                start_station_mm=s0, end_station_mm=s1, width_mm=width,
                slope_len_mm=slope_len_mm(width, gz1 - gz0) if vertical == "raked" else width,
                vertical=vertical, height_mm=height,  # type: ignore[arg-type]
                bottom_z_start_mm=gz0, bottom_z_end_mm=gz1,
                rail_count=_rails_per_span(kb, ctx),
                rail_cut_basis="slope" if vertical == "raked" else "width",
            )
            strategy.spans.append(span)
            builder.add(
                "structural", "create_span",
                payload={"width_mm": width, "vertical": vertical, "height_mm": height,
                         "height_source": height_src or "policy_default"},
                scope_refs=[span.id],
                inputs=[layout_node.id],
                governed_by=governed,
            )
            if width > max_span:
                raise GenerationFailure(
                    f"span {span.id} width {width} exceeds hard max {max_span}",
                    constraint_refs=[max_span_ref],
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
                        message=f"Span {span.id} is {width} mm, below preferred minimum {min_span} mm.",
                        element_refs=[span.id], decision_ref=conflict_node.id,
                    )
                )
        # interior line posts for this segment
        for s in stations[1:-1]:
            if s in suppressed:
                ov = suppressed[s]
                applied_overrides.append(ov.id)
                builder.add(
                    "override_applied", "suppress_post",
                    payload={"override_id": ov.id, "station_mm": s},
                )
                continue
            surface = base_surface_at(topo, run, s)
            post, _ = _make_post(
                builder, topo, kb, run, s,
                post_id=f"post@{run.id}:{s}", run_ref=run.id, kind="line",
                surface=surface, inputs=[layout_node.id], strategy=strategy,
            )
            strategy.posts.append(post)


def _rails_per_span(kb: KnowledgeBase, ctx: dict) -> int:
    res = resolve_param(kb, ctx, "rails_per_span")
    if res.winner:
        return next(a.value for a in res.winner.actions if a.kind == "set_param")
    return 2


def _surface_conflicts(conflicts, builder: GraphBuilder, strategy: Strategy) -> None:
    for c in conflicts:
        node = builder.add(
            "conflict", "knowledge_conflict",
            payload={"slot": c.param_or_action, "contenders": c.contenders},
        )
        strategy.warnings.append(
            StrategyWarning(
                code="knowledge_conflict", severity="warning",
                message=c.message, decision_ref=node.id,
            )
        )
