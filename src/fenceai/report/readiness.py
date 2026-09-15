"""What the office still has to do — the run-scoped half of the office road.

`handover.py` answers *did the sale get captured?* It is a pure function of the
PROJECT, which is what lets it catch the silent 1800 mm height before a strategy
makes it look decided. Steps 1–2 of the office road read it unchanged.

Steps 3–7 are a different question — *has anybody worked this job out yet, and
does what came back still describe today's fence?* — and it cannot be answered
from the project alone, because the answers live on a run. So this is a second
read model beside the first, with the same shape, the same discipline, and its
own `readiness.*` locale namespace (spec §8, *"Two sources of checks, and
neither is called a gap"*).

**Deliberately not called a gap.** `Gap` is a BINDING contract type (§1.2.1)
with eight closed kinds and two binding fields, implemented unrenamed in
`core/gaps.py` and reported through `POST /gaps`. `HandoverGap` already shares
the English word; a third would be the B03 defect again. Nothing here is ever
routed to that endpoint, and this module imports none of it.

**It is handed everything and fetches nothing.** A read model that loaded a run
would decide WHICH run, and `report/` may not import the store (foundation §15,
and `tests/architecture/test_fitness.py` refuses it outright). The practical
consequence is that this module reports only what its caller could see: told
that a run is committed but not given that run, it says nothing about staleness
rather than guessing.

**And it re-evaluates NOTHING.** There is no knowledge base in this signature and
there must never be one. Re-running the evaluator to ask "is this still a
warning?" would re-resolve to current knowledge — exactly what contract 3.2.1
forbids ("re-fetch historical runs by hash, never re-resolve") — and would
recompute a quantity inside a read model, which foundation §15 forbids on its
own. The warnings this counts are the ones the run was stored with.

**Nothing here is blocking.** `blocking` exists on the type because
`HandoverGap` has it and the two are rendered by one row renderer, and no check
in this module sets it. Contract 3.2.4 is explicit that a gap never fails a run,
and a road step that refused to let somebody press Generate would be the first
thing in this system anybody worked around.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.warnings import DocumentWarning
from fenceai.fulfillment.quote import Quote
from fenceai.fulfillment.supply import SupplyResolution
from fenceai.project.model import (
    SALE_READ, WARNINGS_REVIEWED, Project, sale_anchor,
)
from fenceai.strategy.choices import ChoiceSet
from fenceai.strategy.model import GenerationRun, Strategy

# The two acknowledgement kinds this module asks about, spelled once. Named
# FACTS and never step keys: `Stated`'s own argument — a step key would put a
# screen's structure into the project record, and the road engine is pure and
# could not contradict it. `commands/desk.py` writes these (Task 3 of
# `docs/superpowers/plans/2026-09-15-office-road.md`) and must use `sale_anchor`
# below for the first one, so the writer and the reader cannot disagree about
# what was acknowledged.
# The two kinds, re-exported from `project/` so this module and `commands/desk.py`
# name one spelling. They live down there because an anchor is a fact about the
# PROJECT — what a person read — and putting it in a read model made a leaf
# package depend upward on a reporting one.


class ReadinessItem(BaseModel):
    """One thing the office has not done yet.

    `code` + `params`, like every other platform-emitted item in this system:
    the sentence lives in both locale bundles under `readiness.<code>` and is
    rendered there, never assembled here. English text built in Python reaches a
    Hebrew-first reader as English.

    `params` are also the row's HANDLE — `n` is rendered, and anything else is
    carried for the surface to select with (`handover.py`'s `run_ids`
    convention). A sentence naming ids would be worse than a row you can click.
    """

    code: str
    params: dict = {}
    # Always False, and kept anyway: this renders through the same row renderer
    # as `HandoverGap`, and a missing field there would be a second shape for
    # one component to branch on. See the module docstring for why no check sets
    # it.
    blocking: bool = False


def _acknowledgements(project: Project) -> list:
    """The acknowledgements on this project, on a project that may not have any.

    `Project.acknowledgements` arrives in Task 3 of the office-road plan, and
    this module is Task 2. Read through `getattr` so it works on both sides of
    that task rather than either blocking it or being blocked by it. Drop the
    fallback once the field exists — a `getattr` that can no longer miss is a
    reader hiding a typo in the field name.
    """
    return list(getattr(project, "acknowledgements", []))


def _acknowledged(project: Project, kind: str, anchor: str) -> bool:
    """Has somebody answered THIS question about THIS thing?

    Both halves are the check. A match on `kind` alone would let a review of one
    run's warnings silence the next run's, which is the whole reason an
    acknowledgement is anchored at all.
    """
    return any(a.kind == kind and a.anchor == anchor
               for a in _acknowledgements(project))


def readiness(
    project: Project,
    *,
    run: GenerationRun | None = None,
    strategy: Strategy | None = None,
    choice_sets: list[ChoiceSet] | None = None,
    supply: SupplyResolution | None = None,
    committed_run: GenerationRun | None = None,
    quotes: list[Quote] | None = None,
    quoted_warnings: list[DocumentWarning] | None = None,
) -> list[ReadinessItem]:
    """Everything the office still has to do, in the order the road walks it.

    Order is the road's own: the sale first, the price last. The road renders
    one step at a time, but the list is read whole as well — the queue counts
    open questions the way it counts handover gaps — and a reader seeing the
    list should see their own working order.

    Every argument after `project` is a document the CALLER already holds. None
    of them is fetched here (module docstring), and none of them is a knowledge
    base.
    """
    out: list[ReadinessItem] = []

    # --- step 1: the sale ---------------------------------------------------
    # Counting unread notes instead would be the wrong question: the office
    # person reads the drawing, the job fields and the promises together, and a
    # job with no notes at all still has a sale somebody has to read. The check
    # is not "is there something to read" but "has anybody said they read it".
    if not _acknowledged(project, SALE_READ, sale_anchor(project)):
        out.append(ReadinessItem(code="sale_unread"))

    # --- the run-scoped half ------------------------------------------------
    # `no_run` is its anchor and returns ALONE: with no run there is no strategy,
    # no supply resolution and no plan to commit, so listing "no plan committed"
    # and "not priced" beside it would be three ways of saying one thing — the
    # same restraint `handover_gaps` shows when it returns `no_fence_drawn` by
    # itself.
    #
    # A strategy counts as a run for this purpose. They are produced together and
    # a caller holding one holds the other; refusing to answer because only the
    # strategy was passed would make this module fussier than the fact it is
    # reporting.
    if run is None and strategy is None:
        out.append(ReadinessItem(code="no_run"))
        return out

    # --- step 3: the questions ----------------------------------------------
    # Choice sets are DERIVED per generation and never stored, so a caller that
    # has not got them has not got them, and `None` means "nobody asked" rather
    # than "nothing was asked". Reporting a question nobody was asked is worse
    # than reporting none: the office person opens the step and finds an empty
    # panel under an amber heading.
    #
    # Matched on `(id, scope)` — `Selection.key()`, and what `js/choices.js`
    # already matches on. A set-only match would let one answer silence a
    # question asked about a gap it was never measured for.
    if choice_sets:
        answered = {c.key() for c in project.choices}
        unanswered = [s for s in choice_sets if (s.id, s.scope) not in answered]
        if unanswered:
            out.append(ReadinessItem(code="choices_unanswered", params={
                "n": len(unanswered),
                # Carried, never rendered: the step selects the first open
                # question with it.
                "scopes": [s.scope for s in unanswered]}))

    # --- step 4: generate, and read what came back --------------------------
    # `StrategyWarning` ONLY. `quoted_warnings` is accepted and deliberately not
    # counted: a `DocumentWarning` is a manufacturer's own sentence, and contract
    # 3.3.5 puts it once into the plan's annexe and never onto a line. Counting
    # one here would misplace it AND make somebody else's liability notice look
    # like this engine's finding about the job. The parameter exists so that the
    # exclusion is explicit and testable rather than an omission a later caller
    # "fixes" by concatenating the two lists.
    #
    # Supply's warnings are excluded for a different reason: each one is paired
    # with an unresolved line, which step 5 counts below, so adding them here
    # would report one problem twice on two different steps.
    unreviewed = len(strategy.warnings) if strategy else 0
    if unreviewed and not _acknowledged(
            project, WARNINGS_REVIEWED, run.id if run else ""):
        # Anchored to the run id, so a new generation un-reads them. A person who
        # read the last run's warnings has not read this one's, and the map
        # saying so without anybody navigating is the loop working.
        out.append(ReadinessItem(code="warnings_unreviewed",
                                 params={"n": unreviewed}))

    # --- step 5: the materials ----------------------------------------------
    # The unresolved DEMAND lines, not the warnings that accompany them: an
    # unresolved line is one that never got a product and so cannot reach
    # `fulfill()` at all, which is a fact about the order rather than a remark
    # about it.
    if supply and supply.unresolved:
        out.append(ReadinessItem(code="supply_unresolved",
                                 params={"n": len(supply.unresolved)}))

    # --- step 6: the plan ---------------------------------------------------
    # `commit_plan` is out of scope for this plan, so `committed_run_id` does not
    # exist on `Project` yet and this reads as "nothing committed" on every job.
    # That is the honest answer and the reason it was left visible: a step that
    # reports what is genuinely undone is the road working, where a step that
    # read done because the field was missing would be the completeness lie.
    committed = getattr(project, "committed_run_id", "")
    if not committed:
        out.append(ReadinessItem(code="no_plan_committed"))
    elif (committed_run is not None and committed_run.id == committed
          and committed_run.topology_revision != project.topology.revision):
        # The office may edit the drawing (spec §8) and should: a plan committed
        # against the revision before that edit describes a different fence. `!=`
        # rather than `<` because a revision going backwards is not a plan that
        # is merely old, it is one nobody can account for.
        #
        # The id is checked because staleness is a claim about the COMMITTED run
        # and about no other. Handed the newest run by a caller that meant to
        # pass the committed one, a version without this test would judge the
        # plan by a document that is not it — and it would be right just often
        # enough not to be noticed.
        out.append(ReadinessItem(code="plan_stale", params={
            "committed_revision": committed_run.topology_revision,
            "revision": project.topology.revision}))

    # --- step 7: the price --------------------------------------------------
    # The quote has to name the run this job stands behind. A quote for some
    # other run is a number for a fence this job is not building, and a
    # superseded one is kept for the record rather than for the price
    # (`fulfillment/quote.py`).
    #
    # With nothing committed the run in hand is the best answer available, and
    # the step still reports honestly rather than reading done on a job nobody
    # has priced.
    priced_run = committed or (run.id if run else "")
    if not any(q.run_id == priced_run and q.status != "superseded"
               for q in (quotes or [])):
        out.append(ReadinessItem(code="not_priced"))

    return out


# Every code this module can emit. Hand-maintained beside the emitting sites, for
# the reason `HANDOVER_CODES` is: a code with no entry in both bundles reaches a
# screen as its own key, and that has shipped green four times in this repo.
# `tests/web/test_locale_bundles.py` checks both directions against this list.
READINESS_CODES = [
    "sale_unread",
    "choices_unanswered",
    "no_run",
    "warnings_unreviewed",
    "supply_unresolved",
    "no_plan_committed",
    "plan_stale",
    "not_priced",
]
