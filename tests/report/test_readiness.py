"""What the office still has to do — `report/readiness.py`.

The office road's SECOND source of checks (spec §8, *"Two sources of checks, and
neither is called a gap"*). `handover_gaps` answers *did the sale get captured?*
and is a pure function of the project; steps 3–7 of the office road are
run-scoped, so they come from here instead.

Most of these tests are about what this module must NOT do. It must not
re-evaluate a rule, it must not count somebody else's sentence, and it must not
be able to stop anybody generating — three failures that would each look like a
feature on the day they shipped.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from fenceai.core.warnings import DocumentWarning, WarningTarget
from fenceai.demand.derive import DemandLine
from fenceai.fulfillment.fulfill import Bom
from fenceai.fulfillment.quote import Quote
from fenceai.fulfillment.supply import SupplyResolution
from fenceai.project.model import Annotation, Project, Selection
from fenceai.report.readiness import (
    READINESS_CODES, ReadinessItem, readiness, sale_anchor,
)
from fenceai.strategy.choices import ChoiceSet
from fenceai.strategy.model import GenerationRun, Strategy, StrategyWarning


class _Office(Project):
    """A `Project` carrying the two fields the office road will put on it.

    `acknowledgements` arrives in Task 3 and `committed_run_id` with
    `commit_plan`, which this plan puts out of scope on purpose. `readiness`
    reads both through `getattr`, so it works on either side of them — but a
    test that only proved the fallback would prove nothing about the ANCHORS,
    which are the whole mechanism. Delete this subclass when both fields land
    and these tests keep passing against the real ones.
    """

    acknowledgements: list = []
    committed_run_id: str = ""


def _ack(kind: str, anchor: str = ""):
    # Duck-typed on purpose: this names the two fields `readiness` reads off an
    # acknowledgement, so Task 3's real type has to carry them.
    return SimpleNamespace(kind=kind, anchor=anchor, by="user:u_y", at="")


def _codes(project: Project, **kw) -> set[str]:
    return {i.code for i in readiness(project, **kw)}


def _strategy(*warnings: StrategyWarning) -> Strategy:
    return Strategy(id="s1", warnings=list(warnings))


def _warning(code: str = "gate_on_slope") -> StrategyWarning:
    return StrategyWarning(code=code, severity="warning", message="watch out")


def _run(run_id: str = "run_1", *, topology_revision: int = 0) -> GenerationRun:
    return GenerationRun(id=run_id, project_id="p",
                         topology_revision=topology_revision)


def _unresolved() -> SupplyResolution:
    return SupplyResolution(
        unresolved=[DemandLine(id="d1", engineering_qty=1, role="rail")],
        warnings=[_warning("no_feasible_item")])


# --- the shape of the type ---------------------------------------------------

def test_it_reads_warnings_off_the_STORED_run_and_never_re_evaluates():
    """Contract 3.2.1: re-fetch historical runs by hash, never re-resolve to
    "current". Re-running the evaluator here would also recompute a quantity in
    a read model, which foundation §15 forbids on its own.

    Pinned by signature: `readiness` takes a strategy and never a knowledge base,
    so there is nothing in scope to evaluate against.
    """
    params = inspect.signature(readiness).parameters
    assert "knowledge" not in params
    assert "snapshot" not in params
    # The two other spellings the same mistake would arrive under. A parameter
    # named `kb` or `catalog` would be the same re-resolution wearing a shorter
    # name.
    assert "kb" not in params
    assert "catalog" not in params


def test_nothing_here_is_blocking_because_nothing_here_may_stop_a_run():
    """Contract 3.2.4: never fail a run over a gap. `blocking` exists on the
    type to match `HandoverGap`'s shape, and no office item sets it — a step
    that refused to let somebody generate would be the first thing worked
    around."""
    assert all(not i.blocking for i in readiness(Project(id="p", name="x")))
    # ...and on a loaded job too, where every check this module owns has
    # something to say. A test that only drove the empty case would pass while a
    # later check quietly set the flag.
    loaded = readiness(
        Project(id="p", name="x"),
        run=_run(), strategy=_strategy(_warning()),
        choice_sets=[ChoiceSet(id="bay_layout", scope="gap:run1:0", question="?")],
        supply=_unresolved())
    assert all(not i.blocking for i in loaded), [i.code for i in loaded if i.blocking]


def test_these_are_readiness_items_and_never_gaps():
    """`Gap` is a BINDING contract type with eight closed kinds, reported
    through `POST /gaps`. `HandoverGap` already shares the English word; a third
    thing called one would be the B03 defect again — and the way that defect
    actually arrives is a subclass, not a rename."""
    from fenceai.core.gaps import Gap

    assert not issubclass(ReadinessItem, Gap)
    src = inspect.getsource(inspect.getmodule(readiness))
    assert "from fenceai.core.gaps import" not in src
    assert "GapKind" not in src


def test_every_code_it_can_emit_is_listed():
    """`HANDOVER_CODES`' rule, applied here: a code with no entry in both bundles
    reaches a screen as its own key, and that has shipped green four times in
    this repo."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "src" / "fenceai" / "report"
           / "readiness.py").read_text()
    emitted = set(re.findall(r'ReadinessItem\(code="([a-z_]+)"', src))
    assert emitted <= set(READINESS_CODES), sorted(emitted - set(READINESS_CODES))
    # ...and the other direction, which is the one that rots: a listed code with
    # no emitting site is a locale entry nobody can reach, and it hides the
    # rename that orphaned it.
    assert set(READINESS_CODES) <= emitted, sorted(set(READINESS_CODES) - emitted)


# --- the run-scoped half -----------------------------------------------------

def test_a_fresh_job_needs_a_run_before_anything_downstream_is_a_question():
    """`no_run` is the anchor of the run-scoped half. Reporting "no plan
    committed" beside it would be three ways of saying the same thing."""
    codes = {i.code for i in readiness(Project(id="p", name="x"))}
    assert "no_run" in codes
    assert "warnings_unreviewed" not in codes
    assert "supply_unresolved" not in codes
    assert "no_plan_committed" not in codes
    assert "plan_stale" not in codes
    assert "not_priced" not in codes
    assert "choices_unanswered" not in codes


def test_a_run_in_hand_answers_step_four_and_opens_every_step_after_it():
    """The inverse of the test above, and the reason it is not enough on its
    own: a module that returned `no_run` and nothing else for ever would pass
    that one, and the office would walk a road whose last four steps never had
    anything to say."""
    codes = _codes(Project(id="p", name="x"), run=_run())
    assert "no_run" not in codes
    assert "no_plan_committed" in codes
    assert "not_priced" in codes


def test_a_document_warning_is_not_an_office_to_do():
    """Contract 3.3.5: a warning quoted from a manufacturer's document goes once
    into the plan's annexe and never onto a line. Counting one here would both
    misplace it and make a liability sentence look like our finding."""
    strategy = _strategy(_warning())
    quoted = [DocumentWarning(text_raw="Do not install below 5C", lang="en",
                              severity_lexeme="CAUTION",
                              attaches_to=WarningTarget(kind="document"))]
    items = readiness(Project(id="p", name="x"), strategy=strategy,
                      quoted_warnings=quoted)
    item = next(i for i in items if i.code == "warnings_unreviewed")
    assert item.params["n"] == 1


def test_a_run_whose_warnings_are_all_quoted_asks_the_office_nothing():
    """The same rule said as a zero, because that is where an off-by-one hides:
    a count that included the quoted sentence would leave step 4 amber for ever
    on a job with nothing wrong with it, and an amber that never clears is how a
    map teaches its reader to stop looking."""
    quoted = [DocumentWarning(text_raw="Do not install below 5C", lang="en",
                              attaches_to=WarningTarget(kind="document"))]
    codes = _codes(Project(id="p", name="x"), run=_run(),
                   strategy=_strategy(), quoted_warnings=quoted)
    assert "warnings_unreviewed" not in codes


def test_reviewing_warnings_dies_with_the_run_it_was_about():
    """Anchored to `run_id`, and orphaned the way an override is when its
    station moves. A new run means new warnings nobody has read."""
    p = _Office(id="p", name="x",
                acknowledgements=[_ack("warnings_reviewed", "run_1")])
    assert "warnings_unreviewed" not in _codes(
        p, run=_run("run_1"), strategy=_strategy(_warning()))
    assert "warnings_unreviewed" in _codes(
        p, run=_run("run_2"), strategy=_strategy(_warning()))


def test_reading_the_sale_stops_being_true_when_a_note_arrives():
    """Anchored to the SET of annotation ids at the time of reading. A promise
    added after somebody read the job is a promise nobody has read."""
    p = _Office(id="p", name="x",
                annotations=[Annotation(id="a1", target_ref="project",
                                        text="leave the gate clear")])
    p.acknowledgements = [_ack("sale_read", sale_anchor(p))]
    assert "sale_unread" not in _codes(p)

    p.annotations.append(Annotation(id="a2", target_ref="project",
                                    text="and a post clear of the tree"))
    assert "sale_unread" in _codes(p)


def test_the_sale_anchor_does_not_move_when_the_notes_are_merely_reordered():
    """Sorted, because a note list is a list and its order is nobody's decision.
    An anchor that changed when two notes swapped places would unread a sale
    somebody had read, and the office person would never learn what they had
    done to deserve it."""
    p = _Office(id="p", name="x", annotations=[
        Annotation(id="a1", target_ref="project", text="one"),
        Annotation(id="a2", target_ref="project", text="two")])
    before = sale_anchor(p)
    p.annotations.reverse()
    assert sale_anchor(p) == before


def test_the_sale_is_unread_on_a_project_that_has_no_acknowledgements_field():
    """Task 3 adds `Project.acknowledgements`; this module must work on both
    sides of it. Read through `getattr`, so a project saved before that field
    existed reports "nobody has read this" rather than raising."""
    p = Project(id="p", name="x")
    assert not hasattr(p, "acknowledgements")  # remove when Task 3 lands
    assert "sale_unread" in _codes(p)


def test_an_unanswered_question_is_counted_and_an_answered_one_is_not():
    """Matched on `(id, scope)`, which is `Selection.key()` and what
    `js/choices.js` already matches on. A set-only match would let one answer
    silence a question asked about a gap it was never measured for."""
    sets = [ChoiceSet(id="bay_layout", scope="gap:run1:0", question="?"),
            ChoiceSet(id="bay_layout", scope="gap:run1:1", question="?")]
    p = Project(id="p", name="x")
    items = readiness(p, run=_run(), choice_sets=sets)
    assert next(i for i in items if i.code == "choices_unanswered").params["n"] == 2

    p.choices = [Selection(choice_set="bay_layout", scope="gap:run1:0",
                           widths=[2000])]
    items = readiness(p, run=_run(), choice_sets=sets)
    assert next(i for i in items if i.code == "choices_unanswered").params["n"] == 1


def test_a_run_whose_questions_were_not_handed_over_asks_none():
    """Choice sets are DERIVED per generation and never stored, so a caller that
    has not got them has not got them. Reporting a question nobody was asked is
    worse than reporting none: the office person opens step 3 and finds an empty
    panel under an amber step."""
    assert "choices_unanswered" not in _codes(Project(id="p", name="x"), run=_run())


def test_an_unresolved_demand_line_is_the_materials_step_and_not_a_warning():
    """Step 5 owns supply. The unresolved lines are the ones that never got a
    product, which is a different fact from the warning that accompanies each —
    counting those warnings here would double what step 4 already counted."""
    items = readiness(Project(id="p", name="x"), run=_run(),
                      strategy=_strategy(), supply=_unresolved())
    item = next(i for i in items if i.code == "supply_unresolved")
    assert item.params["n"] == 1
    assert "warnings_unreviewed" not in {i.code for i in items}


def test_a_supply_that_resolved_cleanly_says_nothing_about_materials():
    assert "supply_unresolved" not in _codes(
        Project(id="p", name="x"), run=_run(), supply=SupplyResolution())


# --- the plan and the price --------------------------------------------------

def test_a_committed_plan_whose_drawing_moved_is_stale():
    """The loop the road is built to survive: the office may edit the drawing
    (spec §8), and a plan committed against the revision before that edit
    describes a different fence."""
    p = _Office(id="p", name="x", committed_run_id="run_1")
    p.topology.revision = 4
    codes = _codes(p, run=_run("run_1", topology_revision=3),
                   committed_run=_run("run_1", topology_revision=3))
    assert "plan_stale" in codes
    assert "no_plan_committed" not in codes

    fresh = _run("run_1", topology_revision=4)
    assert "plan_stale" not in _codes(p, run=fresh, committed_run=fresh)


def test_it_claims_no_staleness_it_cannot_see():
    """A read model reads what it is handed. Told which run is committed and not
    given it, the honest answer is silence — `report/` may not import the store
    (fitness), so "go and load it" is not available, and guessing would report a
    plan nobody has touched as stale."""
    p = _Office(id="p", name="x", committed_run_id="run_1")
    p.topology.revision = 9
    codes = _codes(p, run=_run())
    assert "plan_stale" not in codes
    assert "no_plan_committed" not in codes


def test_staleness_is_judged_on_the_committed_run_and_on_no_other():
    """Handed a run that is not the committed one, it says nothing rather than
    judging the plan by a document that is not it — which is the kind of wrong
    answer that is right often enough never to be noticed."""
    p = _Office(id="p", name="x", committed_run_id="run_1")
    p.topology.revision = 4
    assert "plan_stale" not in _codes(
        p, run=_run("run_2", topology_revision=4),
        committed_run=_run("run_2", topology_revision=4))


def test_a_quote_against_the_committed_run_is_what_prices_the_job():
    """`not_priced` names the COMMITTED run, not the newest one. A quote for a
    run nobody stood behind is a number for a fence this job is not building."""
    p = _Office(id="p", name="x", committed_run_id="run_1")
    quote = Quote(id="q1", project_id="p", run_id="run_1", bom=Bom())
    assert "not_priced" not in _codes(p, run=_run("run_1"), quotes=[quote])

    p.committed_run_id = "run_2"
    assert "not_priced" in _codes(p, run=_run("run_2"), quotes=[quote])


def test_a_superseded_quote_does_not_price_anything():
    """Accepting a quote supersedes the previously accepted one (`quote.py`). A
    superseded document is kept for the record and is not the price of this
    job."""
    p = _Office(id="p", name="x", committed_run_id="run_1")
    quote = Quote(id="q1", project_id="p", run_id="run_1", bom=Bom(),
                  status="superseded")
    assert "not_priced" in _codes(p, run=_run("run_1"), quotes=[quote])


def test_the_items_come_back_in_the_order_the_road_walks_them():
    """The road renders one step at a time, but the list is also read whole (the
    queue counts open questions the way it counts handover gaps). Sale first,
    price last, so a reader seeing the list sees their own working order."""
    codes = [i.code for i in readiness(
        Project(id="p", name="x"), run=_run(), strategy=_strategy(_warning()),
        choice_sets=[ChoiceSet(id="bay_layout", scope="g", question="?")],
        supply=_unresolved())]
    assert codes == ["sale_unread", "choices_unanswered", "warnings_unreviewed",
                     "supply_unresolved", "no_plan_committed", "not_priced"]
