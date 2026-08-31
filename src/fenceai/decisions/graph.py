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
    # a hole in what the run was TOLD — by the knowledge, or by the project's own
    # site conditions — and the value it proceeded on despite it.
    # Its own kind rather than an "assumption": an assumption is a value we
    # chose, a gap is a question nobody answered. Its own kind ALSO so the
    # annexe (build order item 8) can select on it — nothing in `report/` does
    # today, and the annexe does not exist yet.
    "gap",
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
            # `rsplit("@v", 1)` and not `split("@")`: a published object_id
            # contains `@` itself now that it carries its table's scope
            # (`max_span_mm@model/M-VINYL#0`), so splitting on the FIRST `@`
            # yielded the bare parameter name. Impact analysis then returned
            # nothing for the real object_id and everything under every scope for
            # `max_span_mm` — collapsing the two manufacturers' footing rows that
            # the scope was added to keep apart.
            if e.type == "governed_by" and e.knowledge_ref
            and e.knowledge_ref.rsplit("@v", 1)[0] == object_id
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
    def __init__(self, admitted: dict[str, dict] | None = None,
                 origins: dict[str, str] | None = None) -> None:
        self._graph = DecisionGraph()
        self._n = 0
        # Whether each fact was AUTHORED here or PUBLISHED by the Knowledge
        # Platform, keyed the same way. Three states have to be distinguishable
        # on a plan and only two were:
        #
        #   authored              -- our own rule. No document behind it, so
        #                            there is nothing to have checked.
        #   published + verdict   -- somebody's document, and we know what its
        #                            source was worth.
        #   published, NO verdict -- somebody's document that we could not judge,
        #                            because the task or class was outside our
        #                            policy registry. Used, and unvouched for.
        #
        # Without `origin` the first and third rendered identically: absence of a
        # verdict read as "nothing to check" when it sometimes meant "we could
        # not check". One of those is fine and the other is a warning.
        self._origins = origins or {}
        # Which source admitted each published fact, keyed `"OBJ@vN"` — §1.4's
        # `admitted_by`, computed at ingest and recorded on the RUN.
        #
        # It arrives as plain dicts rather than as `AdmittedBy`, deliberately:
        # `decisions/` must not import the knowledge package. The graph's job is
        # to carry a payload a renderer can read, and typing this field would
        # tie the explanation layer to the module that happens to produce the
        # verdict today.
        #
        # An ABSENT entry means NOT JUDGED, and never "judged and passed".
        # Authored knowledge has no provenance, so it has no entry, and a
        # surface that rendered the two the same way would claim a check that
        # nobody performed.
        self._admitted = admitted or {}

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
        # materialize knowledge input nodes FIRST so every edge points from an
        # earlier ordinal to a later one — acyclicity by construction, no exceptions
        knowledge_srcs = {
            ref: self._knowledge_node(ref) for ref in [*(governed_by or []), *(defeated or [])]
        }
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
        for src in inputs or []:
            self._edge(src, node.id, "input_from")
        for ref in governed_by or []:
            self._edge(knowledge_srcs[ref], node.id, "governed_by", knowledge_ref=ref)
        for ref in defeated or []:
            self._edge(knowledge_srcs[ref], node.id, "defeated", knowledge_ref=ref)
        for src in assumptions or []:
            self._edge(src, node.id, "assumption_of")
        return node

    def _edge(
        self, from_id: str, to_id: str, type_: EdgeType, *, knowledge_ref: str | None = None
    ) -> None:
        if self._graph.node(from_id).ordinal >= self._graph.node(to_id).ordinal:
            raise ValueError("edges must point from earlier to later ordinals (acyclicity)")
        self._graph.edges.append(
            DecisionEdge(from_id=from_id, to_id=to_id, type=type_, knowledge_ref=knowledge_ref)
        )

    def _knowledge_node(self, knowledge_ref: str) -> str:
        for n in self._graph.nodes:
            if n.kind == "input_fact" and n.payload.get("knowledge_ref") == knowledge_ref:
                return n.id
        self._n += 1
        payload: dict = {"knowledge_ref": knowledge_ref}
        # The verdict joins onto the ref that is already here. Nothing new is
        # invented in the graph: `governed_by` and `defeated` edges have always
        # carried this ref, so every decision a published fact governed can
        # already be traced to it — this adds what that fact's source was worth.
        verdict = self._admitted.get(knowledge_ref)
        if verdict is not None:
            payload["admitted_by"] = verdict
        origin = self._origins.get(knowledge_ref)
        if origin:
            payload["origin"] = origin
        node = DecisionNode(
            id=f"d{self._n:04d}",
            ordinal=self._n,
            kind="input_fact",
            action="knowledge_version",
            payload=payload,
        )
        self._graph.nodes.append(node)
        return node.id

    def build(self) -> DecisionGraph:
        return self._graph
