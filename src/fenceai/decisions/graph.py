"""Decision graph: the persisted explanation (decision-model.md, ADR-0006).

Append-only nodes + edges per generation run; acyclic by construction (edges may only
point to earlier ordinals). Built exclusively through GraphBuilder during generation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

NodeKind = Literal[
    "input_fact", "rule_firing", "structural", "selection", "vertical", "mounting",
    "quantity", "conflict", "assumption", "override_applied", "failure",
]
EdgeType = Literal["derived_from", "governed_by", "defeated", "input_from", "assumption_of"]


class DecisionNode(BaseModel):
    id: str
    ordinal: int
    kind: NodeKind
    action: str  # short machine-readable label
    payload: dict = {}
    scope_refs: list[str] = []  # strategy element ids / topology object ids
    confidence: Literal["deterministic", "inferred", "uncertain"] = "deterministic"
    status: Literal["proposed", "accepted", "edited", "rejected", "pinned", "superseded"] = "proposed"


class DecisionEdge(BaseModel):
    from_id: str
    to_id: str
    type: EdgeType
    knowledge_ref: str | None = None  # "OBJ@vN" for governed_by / defeated


class DecisionGraph(BaseModel):
    nodes: list[DecisionNode] = []
    edges: list[DecisionEdge] = []

    def node(self, node_id: str) -> DecisionNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def nodes_for_element(self, element_id: str) -> list[DecisionNode]:
        return [n for n in self.nodes if element_id in n.scope_refs]

    def in_edges(self, node_id: str) -> list[DecisionEdge]:
        return [e for e in self.edges if e.to_id == node_id]

    def out_edges(self, node_id: str) -> list[DecisionEdge]:
        return [e for e in self.edges if e.from_id == node_id]

    def ancestors(self, node_id: str) -> list[DecisionNode]:
        """Evidence closure of a node (walk in_edges transitively)."""
        seen: dict[str, DecisionNode] = {}
        stack = [node_id]
        while stack:
            cur = stack.pop()
            for e in self.in_edges(cur):
                if e.from_id not in seen:
                    seen[e.from_id] = self.node(e.from_id)
                    stack.append(e.from_id)
        return sorted(seen.values(), key=lambda n: n.ordinal)

    def dependents_of_knowledge(self, object_id: str) -> list[DecisionNode]:
        """Which decisions depend on a knowledge object (impact analysis entry)."""
        starts = {
            e.to_id
            for e in self.edges
            if e.type == "governed_by" and e.knowledge_ref and e.knowledge_ref.split("@")[0] == object_id
        }
        result: dict[str, DecisionNode] = {nid: self.node(nid) for nid in starts}
        stack = list(starts)
        while stack:
            cur = stack.pop()
            for e in self.out_edges(cur):
                if e.to_id not in result:
                    result[e.to_id] = self.node(e.to_id)
                    stack.append(e.to_id)
        return sorted(result.values(), key=lambda n: n.ordinal)


class GraphBuilder:
    def __init__(self) -> None:
        self._graph = DecisionGraph()
        self._n = 0

    def add(
        self,
        kind: NodeKind,
        action: str,
        *,
        payload: dict | None = None,
        scope_refs: list[str] | None = None,
        confidence: str = "deterministic",
        status: str = "proposed",
        governed_by: list[str] | None = None,  # knowledge refs "OBJ@vN"
        defeated: list[str] | None = None,
        inputs: list[str] | None = None,  # earlier node ids
        assumptions: list[str] | None = None,
    ) -> DecisionNode:
        self._n += 1
        node = DecisionNode(
            id=f"d{self._n:04d}",
            ordinal=self._n,
            kind=kind,
            action=action,
            payload=payload or {},
            scope_refs=scope_refs or [],
            confidence=confidence,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
        )
        self._graph.nodes.append(node)
        known = {n.id for n in self._graph.nodes}
        for src in inputs or []:
            self._edge(src, node.id, "input_from", known)
        for ref in governed_by or []:
            self._knowledge_edge(node.id, "governed_by", ref, known)
        for ref in defeated or []:
            self._knowledge_edge(node.id, "defeated", ref, known)
        for src in assumptions or []:
            self._edge(src, node.id, "assumption_of", known)
        return node

    def _edge(self, from_id: str, to_id: str, type_: EdgeType, known: set[str]) -> None:
        if from_id not in known:
            raise ValueError(f"edge references unknown node {from_id}")
        if self._graph.node(from_id).ordinal >= self._graph.node(to_id).ordinal:
            raise ValueError("edges must point from earlier to later ordinals (acyclicity)")
        self._graph.edges.append(DecisionEdge(from_id=from_id, to_id=to_id, type=type_))

    def _knowledge_edge(self, to_id: str, type_: EdgeType, knowledge_ref: str, known: set[str]) -> None:
        # governed_by/defeated edges reference knowledge versions via a synthetic
        # input_fact node per knowledge ref (created lazily, once per graph).
        src_id = self._knowledge_node(knowledge_ref)
        self._graph.edges.append(
            DecisionEdge(from_id=src_id, to_id=to_id, type=type_, knowledge_ref=knowledge_ref)
        )

    def _knowledge_node(self, knowledge_ref: str) -> str:
        for n in self._graph.nodes:
            if n.kind == "input_fact" and n.payload.get("knowledge_ref") == knowledge_ref:
                return n.id
        self._n += 1
        node = DecisionNode(
            id=f"d{self._n:04d}",
            ordinal=self._n,
            kind="input_fact",
            action="knowledge_version",
            payload={"knowledge_ref": knowledge_ref},
        )
        # Knowledge nodes are inputs; ordering vs the consuming node is fixed up by
        # inserting before use — but ordinals must stay monotonic, so we simply allow
        # knowledge nodes to appear later in ordinal order while edges still originate
        # from them (they are sources, never targets, so acyclicity holds).
        self._graph.nodes.append(node)
        return node.id

    def build(self) -> DecisionGraph:
        return self._graph
