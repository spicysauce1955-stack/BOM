"""Dispatch: task + view + runner -> a checked TaskResult.

Three checks stand between a runner's output and a person, and anything that
fails one is DROPPED and counted as an agent defect rather than shown. A user
must never be offered something impossible.

**The checks apply to everything a `TaskResult` can hand to a person, not just
`proposals`.** `declined[].claims`, `no_standing[].claims` and `measured` are
`Claim`s exactly as a proposal's are, and a runner that put a fabricated
citation in one of those instead of a proposal would otherwise slip it past
check 2 entirely — the stub's restraint is not the framework's guarantee.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §6, §8, §8b.
"""

from __future__ import annotations

from pydantic import ValidationError

from fenceai.agent.proposal import Claim, Declined, NoStanding, Proposal, TaskResult
from fenceai.agent.registry import spec_for
from fenceai.agent.tasks import TaskSpec
from fenceai.agent.view import AgentView
from fenceai.strategy.choices import ChoiceSet


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
    # asked to ground anything in it, and so THIS dispatch — not the runner —
    # holds the authoritative list of sets still open. `has()` above is a
    # peek, not a read: only `open_choice_sets()` records refs, and both check
    # 2 and check 3 below can only ever match what this call returned.
    open_sets: list[ChoiceSet] = view.open_choice_sets() if "choice_sets" in task.reads else []

    try:
        raw = runner.run(task, view, project_id)
    except Exception:  # an adapter failure is not a finding about the fence
        return TaskResult(task_id=task.id, evaluated=False)

    # `evaluated` is the dispatcher's fact, not a claim to inherit uncritically.
    # A runner cannot say "I did not look" and still hand over proposals it
    # wants believed — if it is not standing behind having looked, nothing it
    # attached is trustworthy either, so none of it reaches the checks below.
    if not raw.evaluated:
        return TaskResult(task_id=task.id, evaluated=False)

    handed_over = view.refs_handed_over()
    digest = view.digest(task.reads)

    kept: list[Proposal] = []
    dropped = 0
    for proposal in raw.proposals:
        if _admissible(proposal, task, open_sets, handed_over):
            # `saw` is stamped here, from what THIS run's view actually
            # resolved against — never trusted from the runner, for the same
            # reason `evaluated` above is not: it is the dispatcher's fact.
            kept.append(proposal.model_copy(update={"saw": digest}))
        else:
            dropped += 1

    # `claims_refused` is a SEPARATE counter from `dropped` on purpose.
    # `produced`/`dropped` are proposal counters — §8b's table is proposal-
    # shaped throughout (`shown`, `kept / reversed`, `never rendered`), so
    # `produced - dropped` must stay the proposal survivor count. A claim
    # refused here is a real agent defect too (the same guard, not analytics),
    # but it is not a proposal, so it is counted under its own name instead of
    # eroding that pairing.
    claims_refused = 0

    measured: list[Claim] = []
    for claim in raw.measured:
        if _claim_grounded(claim, handed_over):
            measured.append(claim)
        else:
            claims_refused += 1

    declined: list[Declined] = []
    for entry in raw.declined:
        if _claims_grounded(entry.claims, handed_over):
            declined.append(entry)
        else:
            claims_refused += 1

    no_standing: list[NoStanding] = []
    for entry in raw.no_standing:
        if _claims_grounded(entry.claims, handed_over):
            no_standing.append(entry)
        else:
            claims_refused += 1

    return raw.model_copy(update={
        # `produced` is what the task EMITTED, before any check ran — §8b's
        # table, not the survivor count. Counting `len(kept)` instead made the
        # all-dropped path report 0 produced for something the task plainly
        # did emit, which is the exact "agent whose output nobody can see
        # still looks idle" failure §8b exists to prevent.
        "proposals": kept[: task.max_proposals],
        "measured": measured,
        "declined": declined,
        "no_standing": no_standing,
        "produced": len(raw.proposals),
        "dropped": dropped,
        "claims_refused": claims_refused,
    })


def _claim_grounded(claim: Claim, handed_over: set[str]) -> bool:
    """Check 2, for one claim. Each marker is grounded differently.

    `inferred` carries no evidence and needs none — `proposal.py`'s validator
    already forbids one. `read` cites something FOREIGN: a ref this run's view
    actually returned, and it is admissible only if it is in `handed_over` — an
    agent can echo a citation, never invent one (conversation.md T58 §2,
    accepted at T59 §2).

    `measured` is the marker for LOCAL evidence, re-executed against the view
    and compared (spec §6) — and this slice has no re-execution surface to run
    it against: `RANK_CHOICE_SET` reads only `choice_sets`, and
    `open_choice_sets()` hands over choice-set refs, never a measured fact.
    Rather than let a `measured` claim fall into the foreign-ref check it was
    never trying to pass — which would refuse it for the wrong reason, and by
    accident stop doing so the day a `point:` ref happened to match — it is
    refused here, explicitly, with its own honest reason. Re-execution arrives
    with the Claude adapter in slice 2.
    """
    if claim.marker == "inferred":
        return True
    if claim.marker == "measured":
        return False
    return claim.evidence in handed_over


def _claims_grounded(claims: list[Claim], handed_over: set[str]) -> bool:
    """Check 2 for a whole list, and the vacuous case FIRST.

    `all([])` is True, so an empty list would pass a check it never faced: no
    claims means nothing for this check to fail, which must not read as passing
    it. An unevidenced proposal is not a proposal, and `proposal.py` makes the
    identical commitment for the other two — "a rejection nobody can check is
    not a reason". One function so the three callers cannot drift apart again;
    they did, and the difference was two words.
    """
    return bool(claims) and all(_claim_grounded(c, handed_over) for c in claims)


def _admissible(proposal: Proposal, task: TaskSpec,
                open_sets: list[ChoiceSet], handed_over: set[str]) -> bool:
    # 1 — the permission list. Belt to the grammar's braces: a runner that
    # emitted an unpermitted kind is broken, not creative.
    if proposal.kind not in task.may_emit:
        return False

    # 2 — grounding, vacuous case included (see `_claims_grounded`).
    if not _claims_grounded(proposal.claims, handed_over):
        return False

    # 3 — referential. The payload must parse into its typed model, and the
    # thing it names must actually exist. Both halves come off the REGISTRY
    # ROW: `ActionSpec.referential` is required, so every registered kind has
    # a check and a kind added tomorrow cannot quietly skip one. Asking
    # `if proposal.kind == ...` here is what made this fail open — check 3 is
    # not optional per kind, and an unknown kind denies rather than passes.
    try:
        spec = spec_for(proposal.kind)
        payload = spec.payload_model.model_validate(proposal.payload)
    except (ValidationError, KeyError):
        return False
    return spec.referential(payload, open_sets)
