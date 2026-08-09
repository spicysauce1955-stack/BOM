"""Tier-1 explanations: deterministic templates rendered FROM the decision graph
(decision-model.md). Zero hallucination risk; works offline; the optional LLM polish
tier (ADR-0009) rewrites these fragments and is validated against node ids.
"""

from __future__ import annotations

from fenceai.decisions.graph import DecisionGraph, DecisionNode


def _refs(graph: DecisionGraph, node: DecisionNode, edge_type: str) -> list[str]:
    return sorted(
        e.knowledge_ref for e in graph.in_edges(node.id) if e.type == edge_type and e.knowledge_ref
    )


def explain_node(graph: DecisionGraph, node: DecisionNode) -> str:
    governed = _refs(graph, node, "governed_by")
    defeated = _refs(graph, node, "defeated")
    p = node.payload
    match node.action:
        case "place_post":
            base = (
                f"Post at station {p.get('station_mm')} mm ({p.get('kind')}, "
                f"{p.get('mounting')} mount, {p.get('sku')}) on {p.get('surface')} base."
            )
        case "layout_spans":
            alt = p.get("alternatives") or []
            base = f"Segment {p.get('segment')} divided into spans {p.get('widths')}."
            if alt:
                base += (
                    f" Alternative {alt[0]['widths']} was rejected because of "
                    f"{alt[0]['rejected_because']}."
                )
        case "create_span":
            base = (
                f"Span of {p.get('width_mm')} mm, height {p.get('height_mm')} mm, "
                f"vertical mode '{p.get('vertical')}' (height source: {p.get('height_source')})."
            )
            if "adjusted_by_wall_profile" in p:
                base += (
                    f" Height reduced by the wall top ({p.get('wall_top_mm')} mm, "
                    f"event {p['adjusted_by_wall_profile']})."
                )
            if "step_mm" in p:
                base += f" Steps {p['step_mm']} mm against the grade."
        case "choose_vertical_mode":
            base = (
                f"Vertical mode '{p.get('mode')}' chosen at {p.get('slope_permille')}"
                "‰ grade."
            )
        case "resolve_max_span":
            base = f"Maximum span resolved to {p.get('value')} mm."
        case "resolve_span_quantities":
            base = (
                f"Quantities per span: {p.get('rails_per_span')} rails, "
                f"{p.get('screws_per_span')} screws."
            )
        case "place_gate":
            base = f"Gate opening from {p.get('start_mm')} to {p.get('end_mm')} mm."
        case "select_gate_kit":
            base = f"Gate kit {p.get('kit_sku')} selected."
        case "knowledge_conflict":
            base = (
                f"Conflict on '{p.get('slot')}' between {', '.join(p.get('contenders', []))} "
                "— surfaced for review."
            )
        case "node_surface_disagreement":
            base = (
                f"Runs meeting at node {p.get('node_id')} disagree on base surface "
                f"({', '.join(p.get('surfaces', []))}); '{p.get('chosen')}' was used."
            )
        case "sliver_span":
            base = (
                f"Span {p.get('span')} is {p.get('width_mm')} mm — below the preferred "
                f"minimum of {p.get('min_mm')} mm."
            )
        case "pin_post" | "suppress_post" | "force_post_sku" | "force_mounting" | "force_vertical":
            base = f"User override {p.get('override_id')} applied ({node.action})."
        case "topology_node" | "run_geometry" | "gate_event" | "knowledge_version":
            base = f"Input fact: {node.action} {p}."
        case _:
            base = f"{node.action}: {p}"
    if governed:
        base += f" Governed by {', '.join(governed)}."
    if defeated:
        base += f" Defeated alternatives from {', '.join(defeated)}."
    if node.status == "pinned":
        base += " This decision is pinned by a user override."
    return base


def explain_element(graph: DecisionGraph, element_id: str) -> list[str]:
    """Why does this element exist / look the way it does? Rendered from the graph."""
    out: list[str] = []
    for node in graph.nodes_for_element(element_id):
        out.append(explain_node(graph, node))
        for anc in graph.ancestors(node.id):
            if anc.kind in ("input_fact", "rule_firing", "override_applied", "conflict"):
                out.append("  ← " + explain_node(graph, anc))
    return out
