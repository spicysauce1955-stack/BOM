"""Every problem on a job, carrying where it belongs on the drawing.

This model finds nothing. It PLACES what three other models already found —
the handover sheet, the office's readiness list, and the warnings a stored run
came back with — so that a screen can draw each one at the spot it is about.

Two properties it must never lose:

* **Nothing is dropped.** A flag whose place cannot be worked out is placed on
  the job, never discarded. A screen that silently swallows a warning it could
  not draw is worse than one that lists it without a mark.
* **A quoted document warning is not a flag.** A manufacturer's sentence goes
  once into the annexe and never onto a fence (contract §3.3.5). Placing one
  would publish their liability text as our finding about this job.
"""

from __future__ import annotations

import copy
import inspect

from fenceai.core.warnings import DocumentWarning
from fenceai.report.flags import job_flags
from fenceai.report.handover import HandoverGap
from fenceai.report.readiness import ReadinessItem
from fenceai.strategy.choices import ChoiceSet
from fenceai.strategy.model import StrategyWarning


def _flag(flags, code):
    matching = [f for f in flags if f.code == code]
    assert matching, f"{code} is not in {[f.code for f in flags]}"
    return matching[0]


def test_a_gap_over_three_runs_is_placed_on_all_three():
    gap = HandoverGap(code="height_assumed", params={
        "height_mm": 1800, "runs": 3,
        "run_ids": ["run1", "run2", "run3"], "uncovered_mm": 28000})
    flag = _flag(job_flags(gaps=[gap], items=[], warnings=[], choice_sets=[]),
                 "height_assumed")
    assert [p.kind for p in flag.places] == ["run", "run", "run"]
    assert [p.run_id for p in flag.places] == ["run1", "run2", "run3"]


def test_a_gap_naming_no_runs_is_placed_on_the_job():
    """Still placed. "The whole job" is a place, not an absence of one."""
    gap = HandoverGap(code="customer_missing", params={})
    flag = _flag(job_flags(gaps=[gap], items=[], warnings=[], choice_sets=[]),
                 "customer_missing")
    assert [p.kind for p in flag.places] == ["job"]


def test_an_unanswered_choice_is_placed_at_the_station_its_scope_names():
    item = ReadinessItem(code="choices_unanswered", params={
        "n": 2, "scopes": ["gap:run2:0", "gap:run3:4000"]})
    flag = _flag(job_flags(gaps=[], items=[item], warnings=[], choice_sets=[]),
                 "choices_unanswered")
    assert [(p.kind, p.run_id, p.station_mm) for p in flag.places] == [
        ("station", "run2", 0), ("station", "run3", 4000)]


def test_a_scope_that_cannot_be_parsed_keeps_its_flag_and_lands_on_the_job():
    """A flag we cannot draw is still a flag. Dropping it would hide a real
    finding behind a formatting change nobody noticed."""
    item = ReadinessItem(code="choices_unanswered", params={
        "n": 2, "scopes": ["model:mfr/certainteed/rail", "gap:run2:0"]})
    flag = _flag(job_flags(gaps=[], items=[item], warnings=[], choice_sets=[]),
                 "choices_unanswered")
    kinds = [(p.kind, p.run_id, p.station_mm) for p in flag.places]
    assert ("job", "", None) in kinds
    assert ("station", "run2", 0) in kinds


def test_an_element_ref_is_parsed_into_its_run_and_station():
    """`post@run1:4000` must mark the STEP, not the middle of the stretch."""
    warning = StrategyWarning(
        code="excessive_step", severity="error",
        message="Step of 1120 mm at station 4000 exceeds 600 mm",
        params={"element": "post@run1:4000", "step_mm": 1120, "max_mm": 600},
        element_refs=["post@run1:4000"])
    flag = _flag(job_flags(gaps=[], items=[], warnings=[warning], choice_sets=[]),
                 "excessive_step")
    (place,) = flag.places
    assert place.kind == "element"
    assert place.element_id == "post@run1:4000"
    assert place.run_id == "run1"
    assert place.station_mm == 4000


def test_a_span_ref_carrying_a_range_is_placed_at_its_start():
    warning = StrategyWarning(
        code="something", message="x", element_refs=["span@run1:1334-2667"])
    (place,) = _flag(job_flags(gaps=[], items=[], warnings=[warning],
                               choice_sets=[]), "something").places
    assert (place.run_id, place.station_mm) == ("run1", 1334)


def test_a_ref_naming_a_node_carries_no_station():
    """`gate@gate1` names an element with no run and no station, and the place
    must say so rather than inventing a zero — station 0 of nothing is the start
    of a stretch, which is a different claim."""
    warning = StrategyWarning(
        code="gate_kit_width_mismatch", severity="error", message="x",
        element_refs=["gate@gate1"])
    (place,) = _flag(job_flags(gaps=[], items=[], warnings=[warning],
                               choice_sets=[]), "gate_kit_width_mismatch").places
    assert place.kind == "element"
    assert place.element_id == "gate@gate1"
    assert place.station_mm is None


def test_a_warning_about_a_node_is_placed_on_that_node():
    warning = StrategyWarning(
        code="node_surface_disagreement", message="x",
        params={"node_id": "n8", "surfaces": "concrete, masonry_wall"})
    (place,) = _flag(job_flags(gaps=[], items=[], warnings=[warning],
                               choice_sets=[]), "node_surface_disagreement").places
    assert (place.kind, place.node_id) == ("node", "n8")


def test_severity_comes_from_the_source_and_never_from_the_code():
    blocking_gap = HandoverGap(code="no_model_chosen", params={}, blocking=True)
    open_gap = HandoverGap(code="sold_by_missing", params={})
    err = StrategyWarning(code="excessive_step", severity="error", message="x")
    warn = StrategyWarning(code="slope_notice", severity="warning", message="x")
    info = StrategyWarning(code="fyi", severity="info", message="x")
    item = ReadinessItem(code="not_priced", params={})

    flags = job_flags(gaps=[blocking_gap, open_gap], items=[item],
                      warnings=[err, warn, info], choice_sets=[])
    by_code = {f.code: f.severity for f in flags}
    assert by_code["no_model_chosen"] == "blocking"
    assert by_code["sold_by_missing"] == "open"
    assert by_code["excessive_step"] == "blocking"
    assert by_code["slope_notice"] == "open"
    assert by_code["fyi"] == "answered"
    assert by_code["not_priced"] == "open"


def test_no_readiness_item_is_ever_blocking():
    """`readiness()` has no blocking items by design — contract 3.2.4 forbids
    failing a run over a gap. This mapping must not invent one."""
    items = [ReadinessItem(code=c, params={}) for c in
             ("sale_unread", "choices_unanswered", "no_run",
              "warnings_unreviewed", "no_plan_committed", "not_priced")]
    flags = job_flags(gaps=[], items=items, warnings=[], choice_sets=[])
    assert all(f.severity != "blocking" for f in flags)


def test_a_quoted_document_warning_cannot_even_be_offered():
    """Contract §3.3.5, enforced by the SIGNATURE rather than by a filter.

    Quoting a manufacturer's liability sentence onto a fence mark publishes
    their words as our finding about this job. A filter would be a rule somebody
    can delete; a parameter that does not exist is a rule nobody can reach —
    `job_flags` takes no argument a `DocumentWarning` could arrive through, and
    this test fails the day one is added.
    """
    accepted = set(inspect.signature(job_flags).parameters)
    assert accepted == {"gaps", "items", "warnings", "choice_sets"}, (
        "job_flags grew a parameter — if a DocumentWarning can reach it, the "
        "annexe rule (contract §3.3.5) is now a filter somebody can remove")

    # And no accepted type can CARRY one. The first version of this asserted
    # `DocumentWarning not in (HandoverGap, ReadinessItem, StrategyWarning)`,
    # which compares a class object against a tuple of class objects and is
    # true of any four unrelated classes — it would have passed with a
    # `DocumentWarning` field on every one of them.
    for model in (HandoverGap, ReadinessItem, StrategyWarning, ChoiceSet):
        for name, field in model.model_fields.items():
            rendered = str(field.annotation)
            assert "DocumentWarning" not in rendered, (
                f"{model.__name__}.{name} can carry a quoted warning into "
                f"job_flags; contract §3.3.5 says it may never reach a mark")


def test_blocking_comes_first_then_open_then_answered():
    flags = job_flags(
        gaps=[HandoverGap(code="no_model_chosen", params={}, blocking=True)],
        items=[ReadinessItem(code="not_priced", params={})],
        warnings=[StrategyWarning(code="fyi", severity="info", message="x")],
        choice_sets=[])
    assert [f.severity for f in flags] == ["blocking", "open", "answered"]


def test_it_is_stable_for_equal_inputs():
    args = dict(gaps=[HandoverGap(code="height_assumed",
                                  params={"run_ids": ["run2", "run1"]})],
                items=[], warnings=[], choice_sets=[])
    assert job_flags(**args) == job_flags(**args)


def test_a_blocking_readiness_item_stays_blocking():
    """The mapping, not the fixture.

    `test_no_readiness_item_is_ever_blocking` asserts a property of the items it
    builds — none of them sets `blocking` — so hard-coding `severity="open"`
    for every readiness item passed the whole suite. `ReadinessItem.blocking` is
    a real field, and `flags.py` reads it precisely so a future blocking item is
    not silently downgraded. This is what makes that true.
    """
    item = ReadinessItem(code="hypothetical", params={}, blocking=True)
    (flag,) = job_flags(gaps=[], items=[item], warnings=[], choice_sets=[])
    assert flag.severity == "blocking"


def test_within_a_band_the_rules_own_order_survives():
    """Sorted by severity ALONE, so equal severities keep source order — which
    is the order the rules fired in. Re-sorting by code passed every test,
    because no test ever had two flags in one band."""
    codes = ["zulu", "alpha", "mike"]
    warnings = [StrategyWarning(code=c, severity="warning", message="x")
                for c in codes]
    flags = job_flags(gaps=[], items=[], warnings=warnings, choice_sets=[])
    assert [f.code for f in flags] == codes, "not alphabetised, not shuffled"


def test_a_warnings_english_sentence_rides_along_as_a_fallback():
    """Codes are an OPEN registry, so a code with no bundle entry is expected
    rather than broken — and this is the only thing between the reader and a raw
    key on screen. Our own codes carry none: they are always registered."""
    warning = StrategyWarning(code="unregistered_yet", severity="warning",
                              message="Something specific happened at 4000 mm.")
    (flag,) = job_flags(gaps=[], items=[], warnings=[warning], choice_sets=[])
    assert flag.message == "Something specific happened at 4000 mm."

    (gap_flag,) = job_flags(gaps=[HandoverGap(code="customer_missing", params={})],
                            items=[], warnings=[], choice_sets=[])
    assert gap_flag.message == ""


def test_it_does_not_mutate_what_it_is_given():
    """The purity check the sections tests do properly. Calling twice with the
    SAME list objects cannot detect an in-place sort — both calls would agree."""
    gaps = [HandoverGap(code="height_assumed",
                        params={"run_ids": ["run2", "run1"]})]
    before = copy.deepcopy(gaps)
    job_flags(gaps=gaps, items=[], warnings=[], choice_sets=[])
    assert gaps == before, "reading a finding must not reorder it"
