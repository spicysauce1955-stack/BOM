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


def _drawn_two(**kw) -> Project:
    """Two runs sharing a corner — what a real job looks like, and the shape
    `run_ids` exists to disambiguate. Separate from `_drawn` because six
    assertions above key off the single-run project."""
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=5000, y_mm=0),
               Node(id="n3", x_mm=5000, y_mm=4000)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2"),
              Run(id="run2", start_node_id="n2", end_node_id="n3")],
    )
    return Project(id="p1", name="untitled", topology=topo, **kw)


def _complete_two() -> Project:
    p = _drawn_two(job=Job(customer="Dana Levy", address="Herzl 12",
                           sold_by="bob", sold_on="2026-09-04"),
                   fence_model=FenceModelChoice(model_id="M-VINYL"),
                   context=SiteContext(landmarks=[
                       Landmark(id="lm1", kind="house", closed=True,
                                points=[(0, 3000), (5000, 3000), (5000, 8000)]),
                   ]))
    for run in p.topology.runs:
        length = 5000 if run.id == "run1" else 4000
        a0 = make_anchor(p.topology, run, 0)
        a1 = make_anchor(p.topology, run, length)
        run.interval_events = [
            IntervalEvent(id=f"{run.id}-e1", start_anchor=a0, end_anchor=a1,
                          payload=HeightIntentPayload(height_mm=1500)),
            IntervalEvent(id=f"{run.id}-e2", start_anchor=a0, end_anchor=a1,
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


# -- B02 from the UI audit: existence is not coverage --------------------------
#
# `docs/visualizations/salesperson-mvp/sales-ui-audit.md`. The original checks
# asked whether a height/base/model event EXISTS on a run. A 5 m run with a
# height stated over its first metre therefore reported nothing missing, leaving
# four metres nobody had specified — and the office person receives a sheet that
# says the job is complete.
#
# Extended to the BASE as well, which the audit did not test but which has
# identical semantics: `base_surface_at` resolves per STATION, so partial base
# coverage leaves the rest on silent `soil` exactly as partial height coverage
# leaves it on 1800.

def _partial(kind_payload, from_mm: int, to_mm: int) -> Project:
    p = _complete()
    run = p.topology.runs[0]
    run.interval_events = [
        ev for ev in run.interval_events
        if ev.payload.kind != kind_payload.kind
    ] + [IntervalEvent(
        id="e-partial",
        start_anchor=make_anchor(p.topology, run, from_mm),
        end_anchor=make_anchor(p.topology, run, to_mm),
        payload=kind_payload)]
    return p


def test_a_height_covering_one_metre_of_five_does_not_count_as_stated():
    """Audit B02, first case. Four metres are left on the silent 1800 default and
    the sheet used to report nothing missing."""
    p = _partial(HeightIntentPayload(height_mm=1500), 0, 1000)
    gap = next(g for g in handover_gaps(p) if g.code == "height_assumed")
    assert gap.params["uncovered_mm"] == 4000


def test_a_base_covering_part_of_a_run_does_not_count_either():
    """Not in the audit, and the same defect: `base_surface_at` resolves per
    station, so the uncovered remainder stands on silent `soil`."""
    p = _partial(BasePayload(surface="soil"), 0, 2000)
    gap = next(g for g in handover_gaps(p) if g.code == "base_assumed")
    assert gap.params["uncovered_mm"] == 3000


def test_a_model_covering_part_of_a_run_with_no_project_default_is_reported():
    """Audit B02, second case. Four metres with no assigned model and no default
    to fall back on."""
    from fenceai.topology.model import FenceModelPayload
    p = _partial(FenceModelPayload(model_id="M-VINYL"), 0, 1000)
    p.fence_model = None
    assert "no_model_chosen" in _codes(p)


def test_a_project_default_covers_every_metre_no_event_reaches():
    """The other half, and why coverage is not checked for the model when a
    default exists: a project-level choice applies wherever no event says
    otherwise, so partial event coverage is complete coverage."""
    from fenceai.topology.model import FenceModelPayload
    p = _partial(FenceModelPayload(model_id="M-SLAT"), 0, 1000)
    assert p.fence_model is not None
    assert "no_model_chosen" not in _codes(p)


def test_two_abutting_intervals_together_cover_the_run():
    """Merged, not counted. Somebody who states 0-2000 and 2000-5000 has
    specified the whole run, and a sheet that demanded one event would be asking
    them to undo work they did correctly."""
    p = _complete()
    run = p.topology.runs[0]
    run.interval_events = [ev for ev in run.interval_events
                           if ev.payload.kind != "height_intent"] + [
        IntervalEvent(id="e-a", start_anchor=make_anchor(p.topology, run, 0),
                      end_anchor=make_anchor(p.topology, run, 2000),
                      payload=HeightIntentPayload(height_mm=1500)),
        IntervalEvent(id="e-b", start_anchor=make_anchor(p.topology, run, 2000),
                      end_anchor=make_anchor(p.topology, run, 5000),
                      payload=HeightIntentPayload(height_mm=1800)),
    ]
    assert "height_assumed" not in _codes(p)


def test_overlapping_intervals_do_not_double_count_as_over_coverage():
    """0-3000 and 2000-5000 overlap by a metre. Naive summation reports 6000 mm
    covered on a 5000 mm run, which is fine by accident here and wrong the moment
    a gap sits beside the overlap."""
    p = _complete()
    run = p.topology.runs[0]
    run.interval_events = [ev for ev in run.interval_events
                           if ev.payload.kind != "height_intent"] + [
        IntervalEvent(id="e-a", start_anchor=make_anchor(p.topology, run, 0),
                      end_anchor=make_anchor(p.topology, run, 3000),
                      payload=HeightIntentPayload(height_mm=1500)),
        IntervalEvent(id="e-b", start_anchor=make_anchor(p.topology, run, 2000),
                      end_anchor=make_anchor(p.topology, run, 4000),
                      payload=HeightIntentPayload(height_mm=1800)),
    ]
    gap = next(g for g in handover_gaps(p) if g.code == "height_assumed")
    assert gap.params["uncovered_mm"] == 1000


def test_an_assumed_gap_names_the_stretches_it_is_about():
    """The office phones about a specific stretch, and so does the salesperson
    looking for the one they missed. A count saves neither call.

    Carried, never rendered: the sentence in both bundles interpolates
    `{runs}` and `{uncovered_mm}`, and a Hebrew sentence naming
    `run3, run7` would be worse than a row you can click.
    """
    project = _complete_two()
    # two runs, neither with a height stated over its whole length
    for run in project.topology.runs:
        run.interval_events = [ev for ev in run.interval_events
                               if ev.payload.kind != "height_intent"]
    gaps = {g.code: g for g in handover_gaps(project)}

    named = gaps["height_assumed"].params["run_ids"]
    assert named == sorted(r.id for r in project.topology.runs)
    # the count and the sum stay: they are what the sentence renders
    assert gaps["height_assumed"].params["runs"] == len(named)


def test_only_the_uncovered_stretches_are_named():
    """A run whose height IS stated must not appear in the list, or clicking
    the row lands the salesperson on a stretch with nothing wrong with it."""
    project = _complete_two()
    covered = project.topology.runs[0]
    bare = project.topology.runs[1]
    bare.interval_events = [ev for ev in bare.interval_events
                            if ev.payload.kind != "height_intent"]
    gaps = {g.code: g for g in handover_gaps(project)}
    assert gaps["height_assumed"].params["run_ids"] == [bare.id]
    assert covered.id not in gaps["height_assumed"].params["run_ids"]


def test_a_base_gap_names_its_stretches_too():
    project = _complete_two()
    for run in project.topology.runs:
        run.interval_events = [ev for ev in run.interval_events
                               if ev.payload.kind != "base"]
    gaps = {g.code: g for g in handover_gaps(project)}
    assert gaps["base_assumed"].params["run_ids"] == sorted(
        r.id for r in project.topology.runs)


# -- a gate nobody has said how to open ---------------------------------------
#
# The drawing already marks such a gate with a question mark and the gates panel
# says so. The handover sheet did not — so a job whose gate nobody can hang
# reached the office looking complete, and the one fact that is visible only to
# whoever happens to open the drawing is the fact the office phones about.

def _gated(**gate_kw) -> Project:
    """A drawn fence with one gate ON the run, authored via conftest so the
    anchor is built the way the frontend builds it (`geom.anchorFor`)."""
    from fenceai.topology.model import GatePayload
    from tests.conftest import add_point_event, straight_topology
    topo = straight_topology(5000)
    add_point_event(topo, "run1", "pe1", 2500,
                    GatePayload(width_mm=1000, **gate_kw))
    return Project(id="p1", name="untitled", topology=topo)


def test_a_gate_that_says_which_way_it_opens_asks_nothing():
    assert "gate_swing_unstated" not in _codes(_gated(opens_to="left"))


def test_a_gate_that_says_nothing_is_the_question_the_office_would_phone_about():
    """`None` is NOBODY HAS SAID, deliberately — there is no default swing,
    because a leaf hung on the wrong side opens into the driveway."""
    gap = next(g for g in handover_gaps(_gated())
               if g.code == "gate_swing_unstated")
    assert gap.params["gates"] == 1


def test_an_unstated_swing_does_not_withhold_the_estimate():
    """`blocking` gates the PRICE, and the price is not in doubt here: the fence
    is priceable and the kit is chosen. What is missing is an instruction to the
    installer, and withholding the salesperson's estimate over it would punish
    the wrong person for the wrong thing."""
    gap = next(g for g in handover_gaps(_gated())
               if g.code == "gate_swing_unstated")
    assert gap.blocking is False


def test_both_kinds_of_gate_are_counted():
    """A gate authored INSIDE a run (`GatePayload`) and one standing BESIDE the
    runs (`GateSpan`) are the same four facts about the same physical object. A
    sheet that counted only the first would go quiet the day a salesperson drew
    the gate the other way."""
    from fenceai.topology.model import GateSpan, Node
    p = _gated()
    p.topology.nodes += [Node(id="g1", x_mm=6000, y_mm=0),
                         Node(id="g2", x_mm=7000, y_mm=0)]
    p.topology.gates = [GateSpan(id="gate1", start_node_id="g1",
                                 end_node_id="g2")]
    gap = next(g for g in handover_gaps(p) if g.code == "gate_swing_unstated")
    assert gap.params["gates"] == 2


def test_a_sliding_gate_is_judged_on_the_field_that_can_hold_its_answer():
    """The case a naive `opens_to is None` gets wrong.

    A sliding gate retracts toward an EDGE and swings toward no side at all —
    `check_swing_coherence` REFUSES a sliding gate that states `opens_to`, so
    the only valid shape for a fully answered one is exactly this. Testing
    `opens_to` would report every sliding gate ever drawn as unstated."""
    p = _gated(leaf="sliding", slides_to="end")
    assert p.topology.runs[0].point_events[0].payload.opens_to is None
    assert "gate_swing_unstated" not in _codes(p)


def test_a_sliding_gate_with_no_edge_stated_still_asks():
    """The other half — otherwise the sliding branch would be a way to be
    silent about a gate nobody can install either."""
    assert "gate_swing_unstated" in _codes(_gated(leaf="sliding"))


def test_the_code_is_registered():
    """Hand-maintained beside the emitting sites: a code missing from the list
    is invisible to the locale-bundle test, and reaches a screen as its own
    key."""
    from fenceai.report.handover import HANDOVER_CODES
    assert "gate_swing_unstated" in HANDOVER_CODES
