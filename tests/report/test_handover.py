"""What the office still needs — slice 4 of the salesperson MVP.

The MVP's whole success condition: *a sold job, captured completely enough that
the office person never has to phone the salesperson.* Completeness, not
accuracy. So the deliverable is a list of the questions the office would
otherwise have to ring up and ask.

**Reported, never enforced.** A salesperson enters this after the visit from
paper; a sheet that refused to hand over an incomplete job would just get worked
around. It says what is missing and lets a person decide — the same call
`Job` makes about blank fields.

**The two silent defaults are the point of the exercise.** A run with no height
intent is built at `default_height_mm` (1800) and a station with no base event
stands on `soil`. Neither is wrong, and neither was ever SAID — so today a fence
nobody measured the height of reaches the office indistinguishable from one that
was confirmed at 1.8 m. That is precisely the phone call this sheet exists to
prevent, and it is why the sheet reads the project rather than the run: by the
time a `Strategy` exists the assumption has already been made and looks decided.
"""

from __future__ import annotations

from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.project.model import Job, Landmark, Project, SiteContext
from fenceai.report.handover import handover_gaps
from fenceai.topology.model import (
    BasePayload, HeightIntentPayload, IntervalEvent, Node, Run, Topology,
)
from fenceai.topology.station import make_anchor


def _codes(project: Project) -> list[str]:
    return [g.code for g in handover_gaps(project)]


def _drawn(**kw) -> Project:
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=5000, y_mm=0)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2")],
    )
    return Project(id="p1", name="untitled", topology=topo, **kw)


def _complete() -> Project:
    p = _drawn(job=Job(customer="Dana Levy", address="Herzl 12",
                       sold_by="bob", sold_on="2026-09-04"),
               # what was SOLD — a complete job names it, and without it the
               # estimate is a number with nothing behind it
               fence_model=FenceModelChoice(model_id="M-VINYL"),
               context=SiteContext(landmarks=[
                   Landmark(id="lm1", kind="house", closed=True,
                            points=[(0, 3000), (5000, 3000), (5000, 8000)]),
               ]))
    run = p.topology.runs[0]
    a0 = make_anchor(p.topology, run, 0)
    a1 = make_anchor(p.topology, run, 5000)
    run.interval_events = [
        IntervalEvent(id="e1", start_anchor=a0, end_anchor=a1,
                      payload=HeightIntentPayload(height_mm=1500)),
        IntervalEvent(id="e2", start_anchor=a0, end_anchor=a1,
                      payload=BasePayload(surface="soil")),
    ]
    return p


def test_an_empty_project_says_the_first_thing_that_is_wrong():
    """Nothing drawn is the one item that makes the rest moot — an address for a
    fence that does not exist is not progress."""
    assert "no_fence_drawn" in _codes(Project(id="p1", name="untitled"))


def test_every_blank_job_field_is_its_own_question():
    """One item per field, not a single "job incomplete". The office person
    phones about a specific missing thing, and a sheet that named the category
    instead of the field would not save the call."""
    codes = _codes(_drawn())
    for c in ("customer_missing", "address_missing", "sold_by_missing",
              "sold_on_missing"):
        assert c in codes, c


def test_a_named_job_raises_none_of_those():
    codes = _codes(_drawn(job=Job(customer="Dana Levy", address="Herzl 12",
                                  sold_by="bob", sold_on="2026-09-04")))
    assert not [c for c in codes if c.endswith("_missing")]


def test_a_height_nobody_stated_is_reported_with_the_number_that_was_assumed():
    """The silent default made visible. `default_height_mm` is 1800, so a run
    with no height intent is BUILT at 1.8 m and reaches the office looking
    confirmed. The params carry the number, because "no height" and "assumed
    1800" are different sentences and only the second is actionable."""
    gap = next(g for g in handover_gaps(_drawn()) if g.code == "height_assumed")
    assert gap.params["height_mm"] == 1800
    assert gap.params["runs"] == 1


def test_a_base_nobody_stated_is_reported_as_the_soil_it_will_be_built_on():
    gap = next(g for g in handover_gaps(_drawn()) if g.code == "base_assumed")
    assert gap.params["surface"] == "soil"


def test_stating_the_height_and_the_base_silences_both():
    codes = _codes(_complete())
    assert "height_assumed" not in codes
    assert "base_assumed" not in codes


def test_a_layout_with_no_house_or_street_cannot_be_read_as_a_place():
    """The reason slice 3 exists. An office person holding a bare coordinate
    plane has to ask which side faces the road."""
    assert "no_property_context" in _codes(_drawn())
    assert "no_property_context" not in _codes(_complete())


def test_a_complete_job_has_nothing_left_to_ask():
    """The state the whole MVP is aiming at. If this list is never empty for a
    fully recorded job, the sheet is noise and will be ignored."""
    assert handover_gaps(_complete()) == []


def test_the_blocking_items_are_the_ones_the_office_cannot_start_without():
    """`blocking` is not severity theatre: it decides whether the estimate is
    shown at all. A price for a fence with no model chosen is a number with no
    meaning behind it."""
    blocking = {g.code for g in handover_gaps(Project(id="p1", name="untitled"))
                if g.blocking}
    assert "no_fence_drawn" in blocking
    assert "customer_missing" not in blocking, (
        "a missing customer name is a phone call, not a reason to withhold "
        "the estimate the salesperson needs today")


def test_the_sheet_reads_the_project_and_never_needs_a_run():
    """It must work before anything is generated — that is when a salesperson
    is filling the gaps. A sheet that required a `Strategy` would only tell them
    what was missing after the assumptions had already been made."""
    import inspect
    params = list(inspect.signature(handover_gaps).parameters)
    assert params == ["project"]


def test_naming_the_model_on_a_stretch_counts_as_naming_it():
    """A salesperson may sell two models on one job — one along the street, a
    cheaper one down the side. An interval event says so, and a sheet that only
    looked at the project-level choice would demand a model they had already
    given twice."""
    from fenceai.topology.model import FenceModelPayload, IntervalEvent
    from fenceai.topology.station import make_anchor
    p = _drawn()
    run = p.topology.runs[0]
    run.interval_events = [IntervalEvent(
        id="e9",
        start_anchor=make_anchor(p.topology, run, 0),
        end_anchor=make_anchor(p.topology, run, 5000),
        payload=FenceModelPayload(model_id="M-VINYL"))]
    assert "no_model_chosen" not in _codes(p)
