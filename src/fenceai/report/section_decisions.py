"""The decisions of one SECTION, in the order they were made.

`/explain/{element}` answers *why is this post here*, and the roadmap asks a
different question: *"focus on specific sections of the fence and get only the
decisions related to the selected section."* Nothing answered it, because a
section is a TOPOLOGY object and the decision graph indexes by strategy element.

Derived, never stored, and it computes no decision of its own: every sentence is
`explain_node`'s, rendered from the graph the run already carries, in the
reader's language and display unit. A view that returned node kinds and left the
client to phrase them would be a second explanation, free to disagree with the
first.

**A summary, not a deeper trail.** The per-element view walks ancestors and
prints them under `←`; doing that per section would repeat one rule firing under
every bay it governed and bury the sequence this view exists to show. A node
appears once, in ordinal order — which IS causal order, because the builder
materialises every edge from a lower ordinal to a higher one.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.decisions.explain import explain_node
from fenceai.decisions.graph import DecisionGraph
from fenceai.strategy.model import Strategy
from fenceai.topology.model import Topology


class ScopedDecision(BaseModel):
    node_id: str
    ordinal: int
    kind: str
    action: str
    # the elements OF THIS SECTION the decision is about. A shared corner post
    # reaches both sections; neither is told it owns the other's bays.
    elements: list[str] = []
    sentence: str = ""
    governed_by: list[str] = []
    defeated: list[str] = []


class SectionDecisions(BaseModel):
    section_id: str
    decisions: list[ScopedDecision] = []


def _sections_of_element(strategy: Strategy, topology: Topology) -> dict[str, set[str]]:
    """element id -> the sections it belongs to.

    A post shared at a node belongs to EVERY run that touches it: it is decided
    once and it stands on both, so reporting it to one section would leave the
    other's story with a post that appeared from nowhere. `Post.run_ref` says
    `node:n1` precisely because it names no single run, and the topology is what
    turns that into the runs — the same fact the setting-out sheet states by
    tagging such a post once and cross-referencing it from the other section.
    """
    touching: dict[str, set[str]] = {}
    for run in topology.runs:
        for node_id in (run.start_node_id, run.end_node_id):
            touching.setdefault(node_id, set()).add(run.id)

    out: dict[str, set[str]] = {}
    for element in [*strategy.posts, *strategy.spans, *strategy.gates]:
        ref = element.run_ref
        if ref.startswith("node:"):
            out[element.id] = set(touching.get(ref.split(":", 1)[1], set()))
        else:
            out[element.id] = {ref}
    return out


def decisions_for_section(
    graph: DecisionGraph,
    strategy: Strategy,
    topology: Topology,
    section_id: str,
    lang: str = "en",
    units: str = "mm",
) -> SectionDecisions:
    """Every decision that settled something about `section_id`.

    Two ways a node can belong, and both are needed. Most name their elements in
    `scope_refs`. The rest decided something for the SECTION and name it in the
    payload instead — the run's own geometry, its vertical mode, a tilt conflict
    — and those are the decisions a person asking about a section wants first,
    so a scope-refs-only reading would drop exactly the wrong ones.
    """
    sections = _sections_of_element(strategy, topology)
    out: list[ScopedDecision] = []
    for node in sorted(graph.nodes, key=lambda n: n.ordinal):
        mine = [ref for ref in node.scope_refs
                if section_id in sections.get(ref, set())]
        # `run_id` in the payload is how a run-level node names its section;
        # `run_ref` is the same fact under the name a couple of nodes use.
        by_payload = section_id in (node.payload.get("run_id"),
                                    node.payload.get("run_ref"))
        # ...and some name neither. `choose_vertical_mode` carries a mode and a
        # slope and nothing else, yet it is decided for one run and is among the
        # first things a person asking about a section wants. It is reachable
        # anyway: every node of a run descends from that run's `run_geometry`
        # fact, because the builder materialises evidence edges before the node
        # that cites them. Asked ONLY as a fallback — a node that names its
        # elements or its run has already answered, and walking the closure for
        # those would pull in every fact they happen to share.
        if not mine and not by_payload and not node.scope_refs:
            by_payload = any(
                a.action == "run_geometry" and a.payload.get("run_id") == section_id
                for a in graph.ancestors(node.id))
        if not mine and not by_payload:
            continue
        out.append(ScopedDecision(
            node_id=node.id, ordinal=node.ordinal, kind=node.kind,
            action=node.action, elements=mine,
            sentence=explain_node(graph, node, lang, units),
            governed_by=[e.knowledge_ref for e in graph.in_edges(node.id)
                         if e.type == "governed_by" and e.knowledge_ref],
            defeated=[e.knowledge_ref for e in graph.in_edges(node.id)
                      if e.type == "defeated" and e.knowledge_ref],
        ))
    return SectionDecisions(section_id=section_id, decisions=out)
