"""Dispatch and the three checks. Spec §6 and §8.

Nothing a person sees has skipped a check, and a proposal that fails one is
DROPPED and counted as an agent defect — never shown. A user must never be
offered something impossible.
"""
from __future__ import annotations

from dataclasses import replace

from fenceai.agent.proposal import Claim, Declined, NoStanding, Proposal, TaskResult, proposal_id
from fenceai.agent.registry import _REGISTRY, ActionSpec, SelectChoicePoint, register
from fenceai.agent.run import run_task
from fenceai.agent.tasks import RANK_CHOICE_SET
from fenceai.agent.view import AgentView, point_ref
from fenceai.decisions.graph import DecisionGraph
from fenceai.project.model import Project, Selection
from fenceai.strategy.choices import ChoiceSet, DesignPoint
from fenceai.strategy.model import GenerationResult, GenerationRun, Strategy

# `axes` trades off (fewer posts, more offcut) so NEITHER point dominates the
# other under `strategy.choices.dominates` — both are genuinely `offered()`.
# The original fixture gave ALT strictly worse axes than DEFAULT on every
# shared axis, which `offered()` (correctly) excludes; that was never a
# reachable "good proposal" in the real system, only in a test that never
# called `offered()`.
DEFAULT = DesignPoint(id="p1", label="2 x 2500", widths=[2500, 2500],
                      axes={"posts": 3, "offcut_mm": 800}, is_default=True)
ALT = DesignPoint(id="p2", label="1800 + 1400 + 1800", widths=[1800, 1400, 1800],
                  axes={"posts": 4, "offcut_mm": 100})


def _view(*points: DesignPoint) -> AgentView:
    sets = [ChoiceSet(id="bay_layout", scope="gap:run1:0",
                      question="q", points=list(points))] if points else []
    return AgentView(Project(id="pr_1", name="t"), GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=1,
                          snapshot_hash="kh"),
        strategy=Strategy(id="st_1"), graph=DecisionGraph(), choice_sets=sets))


class _Runner:
    """A runner under test control — the point is what the CHECKS do with it."""

    interpreter_id = "fake"

    def __init__(self, *proposals: Proposal):
        self._proposals = list(proposals)

    def run(self, task, view, project_id) -> TaskResult:
        return TaskResult(task_id=task.id, evaluated=True,
                          proposals=self._proposals, produced=len(self._proposals))


class _RawRunner:
    """A runner that hands back an arbitrary `TaskResult` — for exercising
    paths `_Runner` above cannot reach: `measured`, `declined`, `no_standing`,
    and a runner's own (mis)reported `evaluated`."""

    interpreter_id = "raw"

    def __init__(self, result: TaskResult):
        self._result = result

    def run(self, task, view, project_id) -> TaskResult:
        return self._result


def _proposal(point_id="p2", kind="select_choice_point", claims=None,
              scope="gap:run1:0") -> Proposal:
    payload = {"choice_set": "bay_layout", "scope": scope, "point_id": point_id}
    return Proposal(id=proposal_id("rank_choice_set", kind, payload, scope),
                    task_id="rank_choice_set", project_id="pr_1", kind=kind,
                    payload=payload, scope=scope,
                    claims=claims if claims is not None
                    else [Claim(marker="read", text="x",
                                evidence=point_ref("bay_layout", "gap:run1:0", point_id))])


def test_a_good_proposal_survives_every_check():
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _Runner(_proposal()),
                   project_id="pr_1")
    assert out.evaluated is True
    assert len(out.proposals) == 1
    assert out.produced == 1 and out.dropped == 0


def test_an_action_the_task_may_not_emit_is_dropped():
    """Check 1. The permission list is the grammar, and this is the belt to its
    braces — a runner that emitted an unpermitted kind is broken, not creative."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(kind="pin_post")), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1
    # `produced` counts what the task EMITTED (spec §8b), not survivors — on
    # the all-dropped path it must still be 1, never 0.
    assert out.produced == 1


def test_a_claim_citing_something_the_view_never_handed_over_is_dropped():
    """Check 2, and it is the one that stops fabrication. A `ref_id` the view
    did not return is refused whether or not it would have resolved —
    conversation.md T58 §2 and T59 §2."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[
                       Claim(marker="read", text="page 17",
                             evidence="ref:sha256-nobody-handed-this-over")])),
                   project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_an_inferred_claim_needs_no_evidence_and_is_not_dropped():
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[
                       Claim(marker="inferred", text="it looks better")])),
                   project_id="pr_1")
    assert len(out.proposals) == 1


def test_a_point_that_is_not_in_the_offered_set_is_dropped():
    """Check 3. A user must never be offered something impossible."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(point_id="p9")), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_task_with_an_empty_slice_reports_that_it_did_not_look():
    """Vacuous green. "I did not look" is never "nothing to report"."""
    out = run_task(RANK_CHOICE_SET, _view(), _Runner(_proposal()), project_id="pr_1")
    assert out.evaluated is False
    assert out.proposals == []


def test_the_runner_is_not_called_when_there_is_nothing_to_look_at():
    class _Exploding:
        interpreter_id = "boom"

        def run(self, task, view, project_id):
            raise AssertionError("must not be called on an empty slice")

    assert run_task(RANK_CHOICE_SET, _view(), _Exploding(),
                    project_id="pr_1").evaluated is False


def test_more_proposals_than_the_cap_are_trimmed_not_dropped():
    """A cap is a cap. Trimming is not a defect, so it does not count as one."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(), _proposal(point_id="p1")), project_id="pr_1")
    assert len(out.proposals) == RANK_CHOICE_SET.max_proposals
    assert out.dropped == 0


def test_a_runner_that_raises_reports_not_evaluated_rather_than_nothing_found():
    class _Broken:
        interpreter_id = "broken"

        def run(self, task, view, project_id):
            raise RuntimeError("adapter exploded")

    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _Broken(), project_id="pr_1")
    assert out.evaluated is False
    assert out.proposals == []


# -- fix round 1: C1, I1-I6 -----------------------------------------------


def test_a_fabricated_citation_in_measured_is_refused_not_shown():
    """C1. `measured` reaches a person exactly as `proposals` do (spec §8);
    check 2 must not be proposal-only, or a runner fabricates a citation
    simply by not putting it in a proposal. Counted under `claims_refused`,
    not `dropped` — `dropped` is a proposal counter (N1)."""
    bad = Claim(marker="read", text="a fact",
               evidence="ref:sha256-nobody-handed-this-over")
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=True, measured=[bad])
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert out.measured == []
    assert out.claims_refused == 1
    assert out.dropped == 0


def test_a_grounded_measured_claim_survives():
    good = Claim(marker="read", text="a fact",
                 evidence=point_ref("bay_layout", "gap:run1:0", "p2"))
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=True, measured=[good])
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert out.measured == [good]
    assert out.claims_refused == 0
    assert out.dropped == 0


def test_a_fabricated_citation_in_declined_is_refused_not_shown():
    """C1. `Declined.claims` is the same `Claim` type as a proposal's."""
    bad = Claim(marker="read", text="a fact",
               evidence="ref:sha256-nobody-handed-this-over")
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=True,
                     declined=[Declined(kind="select_choice_point", claims=[bad])])
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert out.declined == []
    assert out.claims_refused == 1
    assert out.dropped == 0


def test_a_fabricated_citation_in_no_standing_is_refused_not_shown():
    """C1. `NoStanding.claims` too — every path that reaches a person."""
    bad = Claim(marker="read", text="a fact",
               evidence="ref:sha256-nobody-handed-this-over")
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=True,
                     no_standing=[NoStanding(about="x", whose="them", claims=[bad])])
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert out.no_standing == []
    assert out.claims_refused == 1
    assert out.dropped == 0


def test_produced_and_dropped_stay_a_coherent_proposal_pair():
    """N1. `produced - dropped` must stay the proposal survivor count even
    when claims are ALSO being refused elsewhere on the same result — the two
    counters must not share a denominator with `claims_refused`."""
    bad = Claim(marker="read", text="a fact",
               evidence="ref:sha256-nobody-handed-this-over")
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=True,
                     proposals=[_proposal()], produced=1, measured=[bad])
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert len(out.proposals) == 1
    assert out.produced == 1 and out.dropped == 0
    assert out.produced - out.dropped == len(out.proposals)
    assert out.claims_refused == 1


def test_a_point_from_an_already_answered_set_fails_check_3_not_check_2():
    """I1. Check 3 asks whether the point is in `offered()` of a set THIS
    run's view still considers open — a set the project already answered must
    not let its points back in through membership in the result alone.

    Uses an `inferred` claim, which needs no evidence and so always passes
    check 2 regardless of what was handed over — an answered set hands over
    no refs, so a `read`/`measured` claim here would be killed by check 2
    first and this test would pass for the wrong reason (N3). The `inferred`
    claim isolates check 3: reverting it to `point_ids()` over every set the
    result ever carried makes this test fail."""
    project = Project(id="pr_1", name="t",
                      choices=[Selection(choice_set="bay_layout", scope="gap:run1:0")])
    result = GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=1,
                          snapshot_hash="kh"),
        strategy=Strategy(id="st_1"), graph=DecisionGraph(),
        choice_sets=[ChoiceSet(id="bay_layout", scope="gap:run1:0", question="q",
                               points=[DEFAULT, ALT])])
    view = AgentView(project, result)
    proposal = _proposal(claims=[Claim(marker="inferred", text="picks p2 anyway")])
    out = run_task(RANK_CHOICE_SET, view, _Runner(proposal), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_dominated_point_is_not_offered_and_is_dropped():
    """I1. `offered()`, not raw membership: a point strictly worse than the
    default on every shared axis is dropped even though it is a real point in
    a genuinely open set."""
    strictly_worse = DesignPoint(id="d2", label="worse everywhere",
                                 widths=[1800, 1400, 1800], axes={"posts": 4})
    strictly_better_default = DesignPoint(id="d1", label="fewer everything",
                                          widths=[2500, 2500], axes={"posts": 3},
                                          is_default=True)
    view = _view(strictly_better_default, strictly_worse)
    out = run_task(RANK_CHOICE_SET, view, _Runner(_proposal(point_id="d2")),
                   project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_measured_claim_is_refused_because_this_slice_has_nothing_measurable():
    """I2. `RANK_CHOICE_SET`'s view only ever hands over choice-set refs —
    there is no local re-execution surface yet (it arrives with the Claude
    adapter in slice 2) — so a `measured` claim is refused outright, even one
    citing a ref this very run handed over, rather than passing by accident or
    failing the wrong check for the wrong reason."""
    claim = Claim(marker="measured", text="observed",
                  evidence=point_ref("bay_layout", "gap:run1:0", "p2"))
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[claim])), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_saw_is_stamped_from_the_view_actually_read_not_the_runner():
    """I4. `Proposal.saw` is the dispatcher's fact, stamped from
    `view.digest()` — the test runner never sets it, and the proposal
    fixture's default is an empty `ViewDigest`."""
    view = _view(DEFAULT, ALT)
    out = run_task(RANK_CHOICE_SET, view, _Runner(_proposal()), project_id="pr_1")
    [proposal] = out.proposals
    assert proposal.saw == view.digest(RANK_CHOICE_SET.reads)
    assert proposal.saw.run_id == "run_1"


def test_a_proposal_with_no_claims_is_not_a_proposal():
    """I5. Vacuous grounding: no claims to fail check 2 must not read as
    having passed it."""
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT),
                   _Runner(_proposal(claims=[])), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_a_runner_that_claims_it_did_not_look_is_taken_at_its_word():
    """I6. `evaluated: false` must mean nothing else on the result can be
    trusted either — a runner cannot say it did not look while still handing
    over proposals it wants believed."""
    smuggled = _proposal()
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=False,
                     proposals=[smuggled], produced=1)
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert out.evaluated is False
    assert out.proposals == []


# -- final-branch review: I1, I2 ------------------------------------------


def test_an_unevidenced_decline_is_refused_and_counted():
    """I2. `all([])` is True, so an empty `claims` list passed a check it
    never faced — while the identical case was explicitly closed for
    proposals sixty lines above. An unevidenced refusal is not a reason
    (`proposal.py`: "a rejection nobody can check is not a reason")."""
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=True,
                     declined=[Declined(kind="select_choice_point")])
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert out.declined == []
    assert out.claims_refused == 1
    assert out.dropped == 0


def test_an_unevidenced_no_standing_is_refused_and_counted():
    """I2, the other branch. Same rule, same counter."""
    raw = TaskResult(task_id=RANK_CHOICE_SET.id, evaluated=True,
                     no_standing=[NoStanding(about="x", whose="them")])
    out = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), _RawRunner(raw), project_id="pr_1")
    assert out.no_standing == []
    assert out.claims_refused == 1
    assert out.dropped == 0


def test_check_3_comes_off_the_registry_row_not_a_branch_on_kind():
    """I1. A kind the task may emit whose row's referential check refuses is
    dropped — and the dispatcher never names a kind to decide that. Registers
    a throwaway kind (a stand-in for slice 2's `pin_post`) with a check that
    denies: before this fix the dispatcher's `if kind == "select_choice_point"`
    fell through to `return True` for exactly this shape and the proposal was
    SHOWN."""
    kind = "test_only_action"
    seen: list = []

    def _never(payload, open_sets) -> bool:
        seen.append(payload)
        return False

    spec = register(ActionSpec(kind=kind, payload_model=SelectChoicePoint,
                               rung="directive", i18n_key="agent.action.test_only",
                               referential=_never))
    try:
        task = replace(RANK_CHOICE_SET, may_emit=[kind])
        out = run_task(task, _view(DEFAULT, ALT),
                       _Runner(_proposal(kind=kind)), project_id="pr_1")
        assert out.proposals == []
        assert out.dropped == 1
        assert seen, "the row's own check must be the thing that was consulted"
    finally:
        _REGISTRY.pop(kind, None)
    assert spec.kind == kind


def test_a_kind_with_no_registry_row_at_all_is_dropped_not_admitted():
    """The other half of "default to deny": nothing to look the check up on
    means the proposal does not survive."""
    task = replace(RANK_CHOICE_SET, may_emit=["never_registered"])
    out = run_task(task, _view(DEFAULT, ALT),
                   _Runner(_proposal(kind="never_registered")), project_id="pr_1")
    assert out.proposals == []
    assert out.dropped == 1


def test_the_dispatcher_stamps_every_fact_that_is_its_own_not_the_runners():
    """A runner says what it SUGGESTS. It does not get to say what is true about
    the suggesting.

    Only `saw` was stamped, and the rest passed through verbatim — so a runner
    could return `status="kept"`, which asserts that a PERSON confirmed this
    proposal, and it reached the wire that way. "AI interpretations are
    proposals until confirmed" (foundation §15) was, at that point, the stub's
    good manners rather than a property of the framework — which is precisely
    what this module's own docstring says it must not be.

    `id` matters for a second reason: content-derived is what lets a rejection
    suppress a re-proposal. A runner minting its own id defeats that silently,
    and nothing would notice until the Claude adapter re-proposed something a
    person had already thrown away.
    """
    class Rogue:
        interpreter_id = "the-real-runner"

        def run(self, task, view, project_id):
            view.open_choice_sets()
            payload = {"choice_set": "bay_layout", "scope": "gap:run1:0",
                       "point_id": "p2"}
            return TaskResult(task_id=task.id, evaluated=True, proposals=[Proposal(
                id="prop_MINTED_BY_THE_RUNNER",
                task_id="a_task_that_did_not_run",
                project_id="SOME_OTHER_PROJECT",
                kind="select_choice_point", payload=payload, scope="gap:run1:0",
                claims=[Claim(marker="read", text="4 posts",
                              evidence=point_ref("bay_layout", "gap:run1:0", "p2"))],
                agent_id="somebody-else",
                status="kept",
            )])

    res = run_task(RANK_CHOICE_SET, _view(DEFAULT, ALT), Rogue(), project_id="pr_1")
    assert len(res.proposals) == 1, "the proposal is admissible; that is the point"
    p = res.proposals[0]
    assert p.status == "proposed", "a runner claimed a person had kept it"
    assert p.project_id == "pr_1"
    assert p.task_id == RANK_CHOICE_SET.id
    assert p.agent_id == "the-real-runner", "attributed to somebody else"
    assert p.id == proposal_id(RANK_CHOICE_SET.id, "select_choice_point",
                               {"choice_set": "bay_layout", "scope": "gap:run1:0",
                                "point_id": "p2"}, "gap:run1:0")


def test_two_open_gaps_do_not_collapse_into_one_grounding_ref():
    """Check 2 is only as strong as the IDENTITY of the thing cited.

    Point ids are a small fixed vocabulary — `default`, `displaced`, `tiling`,
    `best_yield` — so every open gap on a job carries points with the same ids.
    While the view recorded a bare `point:<id>`, all of them collapsed into one
    ref: an agent citing "the point I read" produced a citation that resolved
    against whichever gap happened to match, and `agent-advice.js` would print
    one gap's widths as the stated reason for another's layout. A reference that
    names two things does not ground anything.

    What this does NOT claim: that a proposal may only cite its own gap. Citing
    a neighbouring run is legitimate advice ("same layout as the stretch beside
    it"), and forbidding it is a product decision this slice has not taken. The
    property bought here is that such a citation is now RECOGNISABLE as being
    about the other gap, rather than indistinguishable from a local one.
    """
    a = DesignPoint(id="best_yield", label="1666 · 1667 · 1667",
                    widths=[1666, 1667, 1667], axes={"posts": 4, "offcut_mm": 10})
    b = DesignPoint(id="best_yield", label="9999 · 9999", widths=[9999, 9999],
                    axes={"posts": 3, "offcut_mm": 900})
    sets = [ChoiceSet(id="bay_layout", scope="gap:run1:0", question="q", points=[DEFAULT, a]),
            ChoiceSet(id="bay_layout", scope="gap:run2:0", question="q", points=[DEFAULT, b])]
    view = AgentView(Project(id="pr_1", name="t"), GenerationResult(
        run=GenerationRun(id="run_1", project_id="pr_1", topology_revision=1,
                          snapshot_hash="kh"),
        strategy=Strategy(id="st_1"), graph=DecisionGraph(), choice_sets=sets))
    view.open_choice_sets()
    refs = view.refs_handed_over()

    # four points across two gaps are four refs, not two
    assert len(refs) == 4, refs
    assert point_ref("bay_layout", "gap:run1:0", "best_yield") in refs
    assert point_ref("bay_layout", "gap:run2:0", "best_yield") in refs
    assert "point:best_yield" not in refs, "the bare id is not an identity"
    assert "point:default" not in refs


def test_a_claim_citing_a_gap_that_was_never_read_is_refused():
    """The other side of the qualification: a ref that looks plausible and was
    never handed over must not resolve. Before, `point:best_yield` matched as
    soon as ANY open gap had a point by that name — so an invented citation
    naming a gap the view never returned was admitted on a name collision."""
    view = _view(DEFAULT, ALT)

    class Inventing:
        interpreter_id = "fake"

        def run(self, task, view, project_id):
            view.open_choice_sets()
            payload = {"choice_set": "bay_layout", "scope": "gap:run1:0",
                       "point_id": "p2"}
            return TaskResult(task_id=task.id, evaluated=True, proposals=[Proposal(
                id="x", task_id=task.id, project_id=project_id,
                kind="select_choice_point", payload=payload, scope="gap:run1:0",
                claims=[Claim(marker="read", text="4 posts",
                              evidence=point_ref("bay_layout", "gap:run9:0", "p2"))],
            )])

    res = run_task(RANK_CHOICE_SET, view, Inventing(), project_id="pr_1")
    assert res.proposals == [], "a citation to a gap nobody read"
    assert res.dropped == 1
