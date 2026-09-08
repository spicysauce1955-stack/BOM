"""Dispatch: task + view + runner -> a checked TaskResult.

Three checks stand between a runner's output and a person, and a proposal that
fails one is DROPPED and counted as an agent defect rather than shown. A user
must never be offered something impossible.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §6, §8, §8b.
"""

from __future__ import annotations

from pydantic import ValidationError

from fenceai.agent.proposal import Proposal, TaskResult
from fenceai.agent.registry import parse_payload
from fenceai.agent.tasks import TaskSpec
from fenceai.agent.view import AgentView


def run_task(task: TaskSpec, view: AgentView, runner, project_id: str) -> TaskResult:
    """Run one task and return only what survived the checks.

    A task whose slices are all empty, or whose runner raises, reports
    `evaluated=False` — never an empty result that reads as "nothing to
    report". That distinction is the vacuous-green rule: a check with nothing
    to check must not report success.
    """
    if not any(view.has(name) for name in task.reads):
        return TaskResult(task_id=task.id, evaluated=False)

    # Broad read: actually walk the declared slices so the view accumulates
    # what it handed over (`view.py`'s `_handed_over`) BEFORE the runner is
    # asked to ground anything in it. `has()` above is a peek, not a read —
    # only `open_choice_sets()` records refs, and check 2 below can only ever
    # match what this call handed over on THIS run.
    if "choice_sets" in task.reads:
        view.open_choice_sets()

    try:
        raw = runner.run(task, view, project_id)
    except Exception:  # an adapter failure is not a finding about the fence
        return TaskResult(task_id=task.id, evaluated=False)

    kept, dropped = [], 0
    for proposal in raw.proposals:
        if _admissible(proposal, task, view):
            kept.append(proposal)
        else:
            dropped += 1

    return raw.model_copy(update={
        "proposals": kept[: task.max_proposals],
        "produced": len(kept),
        "dropped": dropped,
    })


def _admissible(proposal: Proposal, task: TaskSpec, view: AgentView) -> bool:
    # 1 — the permission list. Belt to the grammar's braces: a runner that
    # emitted an unpermitted kind is broken, not creative.
    if proposal.kind not in task.may_emit:
        return False

    # 2 — grounding. Every non-inferred claim must cite something THIS run's
    # view handed over. Not "does it resolve" — a real ref the agent produced
    # from nowhere would resolve. The property is that a citation can only ever
    # be echoed (conversation.md T58 §2, accepted at T59 §2).
    handed_over = view.refs_handed_over()
    for claim in proposal.claims:
        if claim.marker != "inferred" and claim.evidence not in handed_over:
            return False

    # 3 — referential. The payload must parse into its typed model and name
    # something that exists.
    try:
        payload = parse_payload(proposal.kind, proposal.payload)
    except (ValidationError, KeyError):
        return False
    if proposal.kind == "select_choice_point":
        if payload.point_id not in view.point_ids(payload.choice_set, payload.scope):
            return False
    return True
