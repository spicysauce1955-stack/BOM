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

**What belongs to no section, deliberately.** A `knowledge_version` node is the
SOURCE a decision cites rather than a step in the story — it is already named on
every node it governed. `resolve_demand_products` is decided once for the whole
PROJECT (the company's default rail, screw, concrete and cap), so attributing it
to each section would report one choice as several. Everything else in the graph
reaches a section: elements by their `run_ref`, run-level nodes by `run_id` in
their payload, and a topology fact by the node it names.

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
    # What each cited fact's SOURCE was worth, keyed by the same knowledge ref
    # `governed_by` / `defeated` already carry (§1.4 `admitted_by`).
    #
    # DERIVED from the graph, never stored: the verdict lives on the graph's own
    # `knowledge_version` node, and this is a projection of it for the refs this
    # section actually cites. Read models are pure functions of their inputs, and
    # a second copy of a verdict is a second copy that can disagree.
    #
    # A ref ABSENT from this map is NOT JUDGED — authored knowledge, with no
    # provenance to judge. A surface must render that differently from a judged
    # pass, or it claims a check nobody performed.
    admitted: dict[str, dict] = {}
    # Whether each cited fact was authored here or published, keyed the same way.
    # Carried because absence of a verdict has TWO meanings and a surface has to
    # tell them apart: an authored rule has no document to have checked, while a
    # published row we could not judge is used and unvouched for.
    origins: dict[str, str] = {}


def _touching(topology: Topology) -> dict[str, set[str]]:
    """topology node id -> the runs that meet there."""
    out: dict[str, set[str]] = {}
    for run in topology.runs:
        for node_id in (run.start_node_id, run.end_node_id):
            out.setdefault(node_id, set()).add(run.id)
    return out


def _sections_of_element(strategy: Strategy, topology: Topology) -> dict[str, set[str]]:
    """element id -> the sections it belongs to.

    A post shared at a node belongs to EVERY run that touches it: it is decided
    once and it stands on both, so reporting it to one section would leave the
    other's story with a post that appeared from nowhere. `Post.run_ref` says
    `node:n1` precisely because it names no single run, and the topology is what
    turns that into the runs — the same fact the setting-out sheet states by
    tagging such a post once and cross-referencing it from the other section.
    """
    touching = _touching(topology)
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
    touching = _touching(topology)
    out: list[ScopedDecision] = []
    for node in sorted(graph.nodes, key=lambda n: n.ordinal):
        if node.action == "knowledge_version":
            # A knowledge object is the SOURCE a decision cites, not a decision.
            # It is already named on every node it governed (`governed_by`), and
            # listing it again as a step would put "K-MAXSPAN exists" in the
            # story of every section that obeyed it.
            continue
        mine = [ref for ref in node.scope_refs
                if section_id in sections.get(ref, set())]
        # `run_id` in the payload is how a run-level node names its section;
        # `run_ref` is the same fact under the name a couple of nodes use.
        by_payload = section_id in (node.payload.get("run_id"),
                                    node.payload.get("run_ref"))
        # ...and a topology FACT names a node of the drawing. The surface under
        # this section's own end post was decided there, so it belongs to every
        # run that touches that node — the same rule the shared post itself
        # follows, applied to the fact that decided it.
        by_node = section_id in touching.get(node.payload.get("node_id", ""), set())
        if not mine and not by_payload and not by_node:
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
    # Only the refs this section cites, so a section's read model stays about
    # that section — the graph holds the verdict for every fact in the run.
    cited = {ref for d in out for ref in (*d.governed_by, *d.defeated)}
    admitted = {
        n.payload["knowledge_ref"]: n.payload["admitted_by"]
        for n in graph.nodes
        if n.action == "knowledge_version"
        and n.payload.get("knowledge_ref") in cited
        and n.payload.get("admitted_by")
    }
    origins = {
        n.payload["knowledge_ref"]: n.payload["origin"]
        for n in graph.nodes
        if n.action == "knowledge_version"
        and n.payload.get("knowledge_ref") in cited
        and n.payload.get("origin")
    }
    return SectionDecisions(
        section_id=section_id, decisions=out, admitted=admitted, origins=origins)
