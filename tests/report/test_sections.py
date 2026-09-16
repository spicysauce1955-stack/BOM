"""What each stretch of fence IS, before anything is generated.

The office opens a job it did not draw. Half of what it needs to understand —
how long each stretch is, what it stands on, what the ground does, whether
anybody stated a height — exists the moment the salesperson finishes drawing,
and long before `generate()` has run. This read model is that half.

Its governing property is the one `handover.py` already paid for: **a silent
default must arrive as a visible fact**. A stretch with no base event is
standing on `soil` because that is what `base_surface_at` answers, and this
model reports `soil` rather than leaving the field blank — a blank reads as
"nobody has looked at this yet".
"""

from __future__ import annotations

import copy

from fenceai.report.sections import section_facts
from fenceai.topology.model import (
    BasePayload, BaseTopPayload, BaseTopPoint, FenceModelPayload,
    HeightIntentPayload, Node, Run, Topology, WallProfilePayload,
)
from fenceai.topology.station import base_top_at
from tests.conftest import add_interval_event, straight_topology


def _three_runs() -> Topology:
    """An L of three runs, each 8000 mm, drawn in the order A, B, C.

    Deliberately NOT in id order: `run_c` is the second run in the list, so a
    model that sorted by id would letter them differently from the drawing.
    """
    return Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=8000, y_mm=0),
            Node(id="n3", x_mm=8000, y_mm=-8000),
            Node(id="n4", x_mm=16000, y_mm=-8000),
        ],
        runs=[
            Run(id="run_a", start_node_id="n1", end_node_id="n2"),
            Run(id="run_c", start_node_id="n2", end_node_id="n3"),
            Run(id="run_b", start_node_id="n3", end_node_id="n4"),
        ],
    )


def test_one_entry_per_run_lettered_in_drawing_order():
    facts = section_facts(_three_runs())
    assert [f.run_id for f in facts] == ["run_a", "run_c", "run_b"]
    assert [f.tag for f in facts] == ["A", "B", "C"]


def test_length_is_the_run_length_as_whole_millimetres():
    facts = section_facts(_three_runs())
    assert [f.length_mm for f in facts] == [8000, 8000, 8000]
    assert all(isinstance(f.length_mm, int) for f in facts)


def test_one_surface_over_the_whole_run_reports_that_surface_once():
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "ev1", 0, 8000,
                       BasePayload(surface="masonry_wall"))
    (facts,) = section_facts(topo)
    assert facts.base_surface == "masonry_wall"
    assert len(facts.surfaces) == 1
    assert (facts.surfaces[0].start_mm, facts.surfaces[0].end_mm) == (0, 8000)
    assert facts.surfaces[0].surface == "masonry_wall"


def test_a_surface_change_reports_mixed_and_two_stretches_that_meet_exactly():
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "ev1", 0, 3000,
                       BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "ev2", 3000, 8000,
                       BasePayload(surface="concrete"))
    (facts,) = section_facts(topo)
    assert facts.base_surface == "mixed"
    assert [(s.start_mm, s.end_mm, s.surface) for s in facts.surfaces] == [
        (0, 3000, "masonry_wall"), (3000, 8000, "concrete")]
    # No gap and no overlap: the stretches tile the run exactly.
    assert facts.surfaces[0].end_mm == facts.surfaces[1].start_mm
    assert facts.surfaces[-1].end_mm == facts.length_mm


def test_no_base_event_reports_the_silent_default_rather_than_a_blank():
    """`base_surface_at` falls back to soil; this model SAYS soil.

    A blank field reads as "nobody has looked". The whole reason the handover
    sheet exists is that a silent default reaching the office looks identical
    to a measured one, and this screen is the office's first look.
    """
    (facts,) = section_facts(straight_topology(8000))
    assert facts.base_surface == "soil"
    assert [(s.start_mm, s.end_mm, s.surface) for s in facts.surfaces] == [
        (0, 8000, "soil")]


def test_a_run_nobody_stated_a_height_for_says_so_with_a_number():
    (facts,) = section_facts(straight_topology(8000))
    assert facts.height_intent_mm is None
    assert facts.height_covered_mm == 0


def test_a_height_over_half_the_run_reports_how_much_it_covers():
    """Existence is not coverage — audit finding B02, one screen further on."""
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "ev1", 0, 4000,
                       HeightIntentPayload(height_mm=1800))
    (facts,) = section_facts(topo)
    assert facts.height_intent_mm == 1800
    assert facts.height_covered_mm == 4000


def test_two_heights_that_disagree_report_no_single_height():
    """`None` here means "no single answer", which is what the card must say.

    Picking one of them — the longer, the first — would put a height on the
    screen that half the stretch is not built to.
    """
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "ev1", 0, 4000,
                       HeightIntentPayload(height_mm=1800))
    add_interval_event(topo, "run1", "ev2", 4000, 8000,
                       HeightIntentPayload(height_mm=2100))
    (facts,) = section_facts(topo)
    assert facts.height_intent_mm is None
    assert facts.height_covered_mm == 8000, "both stretches are still covered"


def test_ground_runs_from_the_start_of_the_stretch_to_its_end():
    (facts,) = section_facts(straight_topology(8000))
    assert facts.ground, "a stretch always has a ground line"
    assert facts.ground[0].station_mm == 0
    assert facts.ground[-1].station_mm == facts.length_mm


def test_a_model_stated_over_part_of_a_run_is_reported_as_that_stretch():
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "ev1", 0, 4000,
                       FenceModelPayload(model_id="M-SLAT"))
    (facts,) = section_facts(topo)
    assert [(m.start_mm, m.end_mm, m.model_id) for m in facts.models] == [
        (0, 4000, "M-SLAT")]


def test_a_run_with_no_model_stated_reports_no_stretches():
    """Empty, not a fabricated entry: the PROJECT default applies and this model
    does not know what it is. Inventing one here would make a card claim a
    per-stretch decision nobody made."""
    (facts,) = section_facts(straight_topology(8000))
    assert facts.models == []


def test_it_is_pure():
    topo = _three_runs()
    before = copy.deepcopy(topo)
    first = section_facts(topo)
    second = section_facts(topo)
    assert first == second
    assert topo == before, "reading a topology must not change it"


def test_both_read_models_answer_base_surface_the_same_way():
    """The structure report and this one must not contradict each other.

    `structure._base_surface` used to fold over the run's base EVENTS, ignoring
    coverage — the existence-is-not-coverage mistake of audit finding B02. One
    event over half an 8 m run answered `masonry_wall` for all of it, while the
    coverage-derived answer here is `mixed`. So a card read "mixed" before
    Generate and "masonry" after, for a fence nobody had touched.

    This pins the two to one implementation, on the partially-covered run that
    is the only case where they ever differed.
    """
    from fenceai.report.structure import _base_surface

    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "ev1", 0, 4000,
                       BasePayload(surface="masonry_wall"))
    (facts,) = section_facts(topo)
    assert facts.base_surface == "mixed", "half of it stands on soil"
    assert _base_surface(topo, "run1") == facts.base_surface


def test_a_fully_covered_run_still_answers_the_surface_itself():
    """The delegation must not turn every run into "mixed" — the case that
    would make the previous test pass for the wrong reason."""
    from fenceai.report.structure import _base_surface

    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "ev1", 0, 8000,
                       BasePayload(surface="concrete"))
    (facts,) = section_facts(topo)
    assert facts.base_surface == "concrete"
    assert _base_surface(topo, "run1") == "concrete"


# --- the built base's top line --------------------------------------------
#
# The shape of the wall, reported before anything is generated. A step is two
# points at ONE station, which is how `ground` has always carried a ground step
# — no `min_step_mm`, because `==` is not a threshold.


def _walled(points: list[BaseTopPoint], start_mm: int = 0,
            end_mm: int = 8000) -> Topology:
    """An 8 m stretch standing on a wall whose top is the given profile."""
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "base", start_mm, end_mm,
                       BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "top", start_mm, end_mm,
                       BaseTopPayload(points=points))
    return topo


def test_a_stepped_wall_reports_two_points_at_one_station():
    """The proving case: a 300 mm wall that jumps to 1420 mm at 4.0 m.

    The step is carried as points 2 and 3 — station 4000 twice, 1120 mm apart —
    and NOT as a flagged station, because flagging one needs `min_step_mm` and
    that number is knowledge (K-STEP-POST), not code. Whether 1120 mm is *too
    big* is `flags.py`'s answer after Generate; that it is 1120 mm is a fact
    about the drawing.
    """
    topo = _walled([
        BaseTopPoint(pos_permille=0, z_mm=300),
        BaseTopPoint(pos_permille=500, z_mm=300),
        BaseTopPoint(pos_permille=500, z_mm=1420),   # step +1120 at station 4000
        BaseTopPoint(pos_permille=1000, z_mm=1420),
    ])
    (facts,) = section_facts(topo)

    assert [(p.station_mm, p.z_mm) for p in facts.base_top] == [
        (0, 300), (4000, 300), (4000, 1420), (8000, 1420)]

    before, after = facts.base_top[1], facts.base_top[2]
    assert before.station_mm == after.station_mm == 4000, "a step is vertical"
    assert after.z_mm - before.z_mm == 1120
    assert all(isinstance(p.station_mm, int) and isinstance(p.z_mm, int)
               for p in facts.base_top), "integer millimetres (ADR-0002)"

    # The same wall the generator will read: `base_top_at` is the one
    # implementation, and the card must not draw a different one.
    run = topo.run("run1")
    assert base_top_at(topo, run, 3999)[0] == 300
    assert base_top_at(topo, run, 4000)[0] == 1420, "the right side of the step"


def test_a_run_with_no_built_base_reports_an_empty_base_top():
    """Empty, not a flat line at zero.

    A stretch standing on soil has no base top at all. Synthesising `[(0, 0),
    (8000, 0)]` would draw a wall of no height where there is no wall, which is
    a fabricated fact — the mirror image of the `soil`-is-reported rule, not an
    exception to it.
    """
    (facts,) = section_facts(straight_topology(8000))
    assert facts.base_top == []
    assert facts.ground, "the GROUND is still there — only the wall is absent"


def test_base_top_z_is_height_above_ground_not_an_elevation():
    """The two z conventions in this model are different, and this pins which.

    `ground` carries ABSOLUTE elevation; `base_top` carries height ABOVE LOCAL
    GROUND, the convention `base_top_at` and the event itself use. Here the
    ground climbs 0 → 1000 mm and the wall is a constant 300 mm above it, so
    the wall's own numbers stay 300. A model that reported elevation would end
    at 1300, and one that reported elevation while a reader assumed otherwise
    draws the wall 1000 mm underground.
    """
    topo = _walled([
        BaseTopPoint(pos_permille=0, z_mm=300),
        BaseTopPoint(pos_permille=1000, z_mm=300),
    ])
    topo.node("n2").z_mm = 1000
    (facts,) = section_facts(topo)

    assert [(g.station_mm, g.z_mm) for g in facts.ground] == [(0, 0), (8000, 1000)]
    assert [(p.station_mm, p.z_mm) for p in facts.base_top] == [
        (0, 300), (8000, 300)]
    assert facts.base_top[-1].z_mm != facts.ground[-1].z_mm + 300, (
        "1300 would mean this field had been converted to an elevation")
    assert base_top_at(topo, topo.run("run1"), 8000)[0] == 300


def test_base_top_stations_are_proportional_to_the_INTERVAL_not_the_run():
    """`pos_permille` is along the event's interval, as `BaseTopPoint` says.

    A wall over the middle 4 m of an 8 m stretch has its 250-permille point at
    station 3000, not 2000: reading permille against the run length would slide
    every wall to the start of the section it stands on.
    """
    topo = _walled([
        BaseTopPoint(pos_permille=0, z_mm=400),
        BaseTopPoint(pos_permille=250, z_mm=500),
        BaseTopPoint(pos_permille=1000, z_mm=900),
    ], start_mm=2000, end_mm=6000)
    (facts,) = section_facts(topo)
    assert [(p.station_mm, p.z_mm) for p in facts.base_top] == [
        (2000, 400), (3000, 500), (6000, 900)]


def test_a_wall_authored_as_a_wall_profile_is_still_a_built_base_top():
    """`wall_profile` is the same question authored the older way.

    `base_top_at` answers from a `base_top` profile FALLING BACK to
    `wall_profile`, and `BaseTopPoint.z_mm` documents itself as "wall_profile
    semantics" — so a two-point linear wall is a built base top. Dropping it
    would make this field answer "nothing is built" for a wall the generator
    can see, which is exactly the lie the empty case is supposed to mean.
    """
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "base", 0, 8000,
                       BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "wall", 0, 8000,
                       WallProfilePayload(top_z_start_mm=500, top_z_end_mm=900))
    (facts,) = section_facts(topo)
    assert [(p.station_mm, p.z_mm) for p in facts.base_top] == [
        (0, 500), (8000, 900)]
    assert base_top_at(topo, topo.run("run1"), 4000)[0] == 700


def test_a_point_profile_beats_a_wall_profile_over_the_same_stretch():
    """Precedence follows `base_top_at`, which tries `base_top` first.

    Without that, a stretch carrying both would be drawn twice — a zigzag from
    two overlapping polylines — and the card would disagree with the wall the
    generator builds.
    """
    topo = _walled([
        BaseTopPoint(pos_permille=0, z_mm=300),
        BaseTopPoint(pos_permille=1000, z_mm=300),
    ])
    add_interval_event(topo, "run1", "wall", 0, 8000,
                       WallProfilePayload(top_z_start_mm=9000, top_z_end_mm=9000))
    (facts,) = section_facts(topo)
    assert [(p.station_mm, p.z_mm) for p in facts.base_top] == [
        (0, 300), (8000, 300)], "the 9000 mm wall_profile must not appear"
    assert base_top_at(topo, topo.run("run1"), 4000)[0] == 300


def test_a_point_profile_with_no_points_claims_nothing():
    """An empty `base_top` event is not an answer, so the wall still draws.

    `base_top_at` skips such an event and falls through to `wall_profile`; if
    this model let it claim the stretch instead, a half-authored profile would
    silently erase a wall the generator still builds on.
    """
    topo = straight_topology(8000)
    add_interval_event(topo, "run1", "top", 0, 8000, BaseTopPayload(points=[]))
    add_interval_event(topo, "run1", "wall", 0, 8000,
                       WallProfilePayload(top_z_start_mm=600, top_z_end_mm=600))
    (facts,) = section_facts(topo)
    assert [(p.station_mm, p.z_mm) for p in facts.base_top] == [
        (0, 600), (8000, 600)]
    assert base_top_at(topo, topo.run("run1"), 4000)[0] == 600
