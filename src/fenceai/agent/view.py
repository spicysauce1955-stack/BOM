"""What a task may look at — read-only, and it remembers what it handed over.

Broad read, narrow run (spec §4). There are no mutators here on purpose: an
adapter cannot reach for state the deterministic side owns if the object it
holds cannot write.

**Never cached across runs.** A view is constructed per task run and thrown
away. `conversation.md` T53 §1 is the worst form of the alternative — a team
telling the other side twice that a cut was blocked for a reason false when
written: "Ours was worse than a stale comment — we asserted the stale state as
a current reason." A cached view is an agent doing exactly that.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §4.
"""

from __future__ import annotations

from fenceai.agent.proposal import ViewDigest
from fenceai.project.model import Project
from fenceai.strategy.choices import ChoiceSet
from fenceai.strategy.model import GenerationResult


def point_ref(choice_set_id: str, scope: str, point_id: str) -> str:
    """The grounding reference for one design point — QUALIFIED by the set and
    the scope it belongs to.

    A point id is not an identity. `generator.py` names its points from a small
    fixed vocabulary — `default`, `displaced`, `tiling`, `best_yield` — so every
    open gap on a job carries points with the SAME ids. Recording a bare
    `point:<id>` therefore collapsed all of them into one ref, and check 2 then
    admitted a claim that quoted gap 1's widths as the reason for gap 2's
    layout: a citation that resolves, to the wrong thing. "A claim carries how
    it is known" holds only where the reference names one thing.

    NUL-separated for the reason `history.js` NUL-separates a choice key: a real
    scope contains colons (`gap:run1:0`), so joining on one lets two different
    triples spell the same ref. This is compared for equality and never parsed
    or rendered — the UI shows a claim's `text`, never its `evidence`.
    """
    return "point:" + "\0".join((choice_set_id, scope, point_id))


class AgentView:
    def __init__(self, project: Project, result: GenerationResult) -> None:
        self._project = project
        self._result = result
        self._handed_over: set[str] = set()

    # -- slices ---------------------------------------------------------------

    def open_choice_sets(self) -> list[ChoiceSet]:
        """Questions still open — a set the person has already answered is not
        one. Reading it records every point id as handed over."""
        answered = {(c.choice_set, c.scope) for c in self._project.choices}
        out = [c for c in self._result.choice_sets
               if (c.id, c.scope) not in answered]
        for choice_set in out:
            for point in choice_set.points:
                self._handed_over.add(
                    point_ref(choice_set.id, choice_set.scope, point.id))
        return out

    def point_ids(self, choice_set: str, scope: str) -> set[str]:
        return {p.id for c in self._result.choice_sets
                if c.id == choice_set and c.scope == scope for p in c.points}

    # -- accounting -----------------------------------------------------------

    def refs_handed_over(self) -> set[str]:
        """Every reference this run's view actually returned.

        The grounding check matches a claim's evidence against this set, which
        is why it is accumulated rather than recomputed: an agent may only cite
        what it was handed, so it can echo a citation and never invent one.
        """
        return set(self._handed_over)

    def has(self, slice_name: str) -> bool:
        if slice_name == "choice_sets":
            return bool(self._result.choice_sets)
        raise KeyError(f"no such view slice: {slice_name}")

    def digest(self, slices: list[str]) -> ViewDigest:
        run = self._result.run
        return ViewDigest(
            slices=list(slices),
            run_id=run.id,
            topology_revision=run.topology_revision,
            knowledge_hash=run.snapshot_hash,
        )
