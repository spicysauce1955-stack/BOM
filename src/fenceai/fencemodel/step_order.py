"""The step order as a PARTIAL order, and the one sequence a reader is shown.

Contract obligation 11: prerequisites are edges with a kind, not list order. The
consequence nothing else in this codebase has had to face is that **a partial
order has no single sequence**. "The order" stops being a fact the document
carries and becomes a CHOICE among valid linearisations, and a read model that
returns one without saying so has quietly reinstated exactly the flattening the
obligation exists to prevent — only now with the authority of an engine behind
it.

So this module returns a linearisation AND the shape it came from:

* `stages` — the steps grouped into layers. Everything in one stage is
  unordered with respect to everything else in it: the document says nothing
  about which comes first, and a fitter may do them in any order.
* `unique` — whether the sequence is the ONLY valid one. True exactly when every
  stage holds one step, which (because a layer is built from its predecessors)
  is the same as saying the partial order is already total.
* `basis` — `authored` when no step declares a single prerequisite. Then the
  returned sequence is the document's PRINT order, which asserts nothing at all,
  and saying `requires`-derived would be a lie about where the order came from.
  This distinction is the whole of obligation 11 in one field.

**Determinism.** Ties inside a stage break by authored position. That is a
presentation choice and it is safe precisely BECAUSE the caller is told the
stage: the tie-break decides what a list looks like and never what is true.
Sorting by anything else — role, slot count, text length — would be a second
opinion about build order competing with the document's.

**Cycles are refused at authoring**, not discovered at render. `validate_model`
calls this function and turns `conflicts` into errors an author sees while
editing. This function itself never raises: a read model laid over an invalid
draft still has to draw something, and the draft IS invalid by definition while
it is being typed.

Not every cycle is a contradiction, and collapsing the two would be the same
flattening again. `after` and `before` are STRICT; `not_before` is not. Two steps
each `not_before` the other are the document saying they happen TOGETHER — a
legitimate thing to say about pouring two footings — while any loop containing a
strict edge asserts a step comes before itself. The first is a `concurrent`
group; the second is a `conflict`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - `model.py` imports THIS module, so the
    # runtime import would be a cycle. Nothing here needs the class: it reads
    # `key` and `requires` off whatever it is handed, and the annotation is for
    # the reader and the type checker.
    from fenceai.fencemodel.model import AssemblyStep


class StepOrder(BaseModel):
    """The partial order, and the one sequence chosen out of it."""

    # `authored`: no step asserts a dependency, so this is print order and print
    # order asserts nothing. `requires`: at least one edge exists and the
    # sequence below is a linearisation of it.
    basis: str = "authored"
    # step keys, stage by stage, in the order the read model returns them
    stages: list[list[str]] = []
    # is this the only valid sequence? A reader who is not told this will assume
    # yes, which is the failure obligation 11 names.
    unique: bool = False
    # loops that assert a step precedes itself. Refused at authoring; reported
    # here so an invalid draft still renders and says why.
    conflicts: list[list[str]] = []
    # steps the document says are done together (a `not_before` loop) — unordered
    # by assertion rather than by silence, which is a different fact.
    concurrent: list[list[str]] = []
    # alternatives: a build does one of each group, never all. Constrains no
    # order, which is why a prerequisite list cannot express it.
    exclusive: list[list[str]] = []


def step_order(steps: "list[AssemblyStep]") -> StepOrder:
    """`[AssemblyStep]` -> the partial order and one linearisation of it.

    Pure, total, and never raises — `validate_model` and `report/assembly.py`
    both call it, so there is ONE ordering implementation rather than an
    authoring-time opinion and a render-time opinion free to disagree.

    Prerequisites naming an unknown step are IGNORED here and refused by
    `validate_model`. Dropping the edge is the only honest reading: an edge to a
    step that does not exist constrains nothing, and inventing a node for it
    would make the render disagree with the document.
    """
    keys = [s.key for s in steps]
    if not keys:
        return StepOrder(basis="authored", stages=[], unique=True)
    rank = {key: i for i, key in enumerate(keys)}
    known = set(keys)

    # edges: (from, to) -> strict?  A pair asserted both strictly and loosely is
    # strict; the stronger claim is the one the document made.
    edges: dict[tuple[str, str], bool] = {}
    exclusive: list[list[str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    asserted = False

    def edge(a: str, b: str, strict: bool) -> None:
        if a == b or a not in known or b not in known:
            return
        edges[(a, b)] = edges.get((a, b), False) or strict

    for step in steps:
        for req in step.requires:
            asserted = True
            if req.step not in known:
                continue
            if req.kind == "after":
                edge(req.step, step.key, True)
            elif req.kind == "not_before":
                edge(req.step, step.key, False)
            elif req.kind == "before":
                edge(step.key, req.step, True)
            elif req.kind == "exclusive_with":
                if step.key == req.step:
                    continue
                pair = tuple(sorted((step.key, req.step), key=lambda k: rank[k]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    exclusive.append(list(pair))

    groups = _strongly_connected(keys, list(edges))
    conflicts: list[list[str]] = []
    concurrent: list[list[str]] = []
    for group in groups:
        if len(group) == 1:
            continue
        inside = {(a, b): strict for (a, b), strict in edges.items()
                  if a in set(group) and b in set(group)}
        if any(inside.values()):
            conflicts.append(list(group))
        else:
            concurrent.append(list(group))

    stages = _layers(groups, edges, rank)
    return StepOrder(
        basis="requires" if asserted else "authored",
        stages=stages,
        unique=all(len(stage) == 1 for stage in stages),
        conflicts=conflicts,
        concurrent=concurrent,
        exclusive=exclusive,
    )


def _strongly_connected(
    keys: list[str], pairs: list[tuple[str, str]],
) -> list[list[str]]:
    """Tarjan, iterative, with every group in authored order.

    Iterative rather than recursive on purpose: a step list is authored by hand
    and will never be deep, but a read model that raises `RecursionError` on a
    document somebody typed is a worse failure than any it could report.
    """
    out_edges: dict[str, list[str]] = {k: [] for k in keys}
    for a, b in pairs:
        out_edges[a].append(b)
    rank = {key: i for i, key in enumerate(keys)}

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    groups: list[list[str]] = []

    for root in keys:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child = work[-1]
            if child == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            neighbours = out_edges[node]
            while child < len(neighbours):
                nxt = neighbours[child]
                child += 1
                if nxt not in index:
                    work[-1] = (node, child)
                    work.append((nxt, 0))
                    recursed = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if recursed:
                continue
            work[-1] = (node, child)
            if low[node] == index[node]:
                group: list[str] = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    group.append(top)
                    if top == node:
                        break
                groups.append(sorted(group, key=lambda k: rank[k]))
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return groups


def _layers(
    groups: list[list[str]],
    edges: dict[tuple[str, str], bool],
    rank: dict[str, int],
) -> list[list[str]]:
    """Kahn over the condensation, one stage per layer.

    Layering rather than a plain topological sort, and that is the whole design:
    a plain sort returns a sequence and destroys the evidence that other
    sequences were equally valid. A layer IS that evidence — everything in one
    stage is mutually unordered — and it is what lets the caller say so.

    A cyclic group has already been collapsed into one node by the SCC pass, so
    this loop always terminates: the condensation of any digraph is acyclic.
    """
    home = {key: i for i, group in enumerate(groups) for key in group}
    indeg = [0] * len(groups)
    succ: list[set[int]] = [set() for _ in groups]
    for (a, b) in edges:
        ga, gb = home[a], home[b]
        if ga != gb and gb not in succ[ga]:
            succ[ga].add(gb)
            indeg[gb] += 1

    order = sorted(range(len(groups)), key=lambda g: rank[groups[g][0]])
    ready = [g for g in order if indeg[g] == 0]
    stages: list[list[str]] = []
    placed = 0
    while ready:
        stage: list[str] = []
        nxt: list[int] = []
        for g in ready:
            stage.extend(groups[g])
            placed += 1
        for g in ready:
            for h in sorted(succ[g], key=lambda x: rank[groups[x][0]]):
                indeg[h] -= 1
                if indeg[h] == 0:
                    nxt.append(h)
        stages.append(sorted(stage, key=lambda k: rank[k]))
        ready = sorted(set(nxt), key=lambda g: rank[groups[g][0]])
    if placed != len(groups):  # pragma: no cover - the condensation is acyclic
        raise AssertionError("condensation was not acyclic")
    return stages
