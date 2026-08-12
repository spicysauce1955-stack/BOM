"""The supply choice, as a decision-graph node.

`resolve_supply` has always recorded which product it chose, which it rejected
and under which preset — and nothing consumed it. It reached no node, so
`/explain` could not say why POLE-3000 was bought instead of POLE-2000. While
every shipped model had exactly one eligible member per slot the gap was
invisible; the moment a model ships a multi-member group, the system is making a
priced choice it cannot account for, which contradicts foundation §15 for exactly
the decision most worth explaining. (`docs/v1-known-limitations.md` records this
with the trigger that has now fired.)

The blocker was structural, and this is the way round it. Selection is coupled to
the cut plan and therefore runs in fulfillment, which has no graph builder and no
business acquiring one. So the nodes are **derived at read time** from a stored
run, exactly as `report/structure.py` derives the setting-out sheet: a pure
function of `(graph, decisions)` returning a NEW graph. The stored document is
never touched — reading a run must not change it, and a test pins that.

Ordinals continue from the stored graph's maximum, so the appended nodes are
strictly later than everything they point at and the acyclicity invariant
`GraphBuilder._edge` enforces during generation still holds here.
"""

from __future__ import annotations

from fenceai.decisions.graph import DecisionEdge, DecisionGraph, DecisionNode
from fenceai.fulfillment.supply import SupplyDecision


def with_supply_decisions(
    graph: DecisionGraph, decisions: list[SupplyDecision]
) -> DecisionGraph:
    """A copy of `graph` with one `select_supply` node per decision.

    Each node scopes to the strategy elements its requirement lines peg to, so
    clicking a bay explains the products bought for it. A decision whose lines
    peg to nothing (a run-wide demand) still gets its node — unscoped, reachable
    through the graph rather than through an element."""
    out = graph.model_copy(deep=True)
    ordinal = max((n.ordinal for n in out.nodes), default=0)

    for decision in sorted(decisions, key=lambda d: (d.slot_key, d.chosen)):
        ordinal += 1
        node = DecisionNode(
            id=f"s{ordinal:04d}",
            ordinal=ordinal,
            kind="selection",
            action="select_supply",
            payload={
                "chosen": decision.chosen,
                "preset": decision.preset,
                "slot_key": decision.slot_key,
                "role": decision.role,
                "requirement_ids": list(decision.requirement_ids),
                "candidates": [c.model_dump() for c in decision.candidates],
            },
            scope_refs=list(decision.pegs),
        )
        out.nodes.append(node)
        # the panel resolution that asked for this part is the evidence this
        # choice was made in answer to, where the run recorded one
        for source in _panel_nodes(out, decision.pegs):
            if source.ordinal < node.ordinal:
                out.edges.append(
                    DecisionEdge(from_id=source.id, to_id=node.id, type="input_from")
                )
    return out


def _panel_nodes(graph: DecisionGraph, pegs: list[str]) -> list[DecisionNode]:
    wanted = set(pegs)
    return [n for n in graph.nodes
            if n.action == "resolve_panel" and wanted.intersection(n.scope_refs)]
