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
                self._handed_over.add(f"point:{point.id}")
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
