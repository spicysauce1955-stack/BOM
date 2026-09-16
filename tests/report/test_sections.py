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
    BasePayload, FenceModelPayload, HeightIntentPayload, Node, Run, Topology,
)
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
