"""Two behaviours, one resolver.

An elevation sample belongs to its segment PROPORTIONALLY — stretch the segment
and the sample stays a third of the way along (ADR-0003). A pinned POST does
not: a post placed 800 mm from a corner stays 800 mm from that corner, because
that is what the person measured.

Rev 1 added a SECOND resolver for overrides, which put the same pin 800 mm apart
in the plan canvas and the generator. The policy belongs on the anchor.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.topology.model import Anchor, Node, Run, Topology
from fenceai.topology.station import anchor_station, make_anchor
from tests.conftest import straight_topology


def _stretched(length_mm: int):
    topo = straight_topology(length_mm)
    return topo, topo.run("run1")


def _bent(first_leg_mm: int, second_leg_mm: int):
    """A two-leg run: `first_leg_mm` east, then `second_leg_mm` north.

    Every golden scenario is single-segment, where a segment-local offset and an
    absolute station are the SAME number — so the distinction `reanchor` is about
    is invisible on a straight run and needs a corner to be tested at all.
    """
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0),
               Node(id="n2", x_mm=first_leg_mm, y_mm=second_leg_mm)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2",
                  interior_vertices=[(first_leg_mm, 0)])],
    )
    return topo, topo.run("run1")


def test_a_proportional_anchor_moves_with_its_segment():
    topo, run = _stretched(4000)
    a = make_anchor(topo, run, 1000)
    topo2, run2 = _stretched(8000)
    assert anchor_station(topo2, run2, a) == 2000


def test_a_rigid_anchor_keeps_its_offset():
    topo, run = _stretched(4000)
    a = make_anchor(topo, run, 1000).model_copy(update={"reanchor": "rigid"})
    topo2, run2 = _stretched(8000)
    assert anchor_station(topo2, run2, a) == 1000


def test_proportional_is_the_default_so_nothing_stored_changes_meaning():
    assert Anchor(segment_index=0, offset_mm=10,
                   seg_len_at_authoring_mm=100).reanchor == "proportional"


def test_a_rigid_anchor_past_the_end_of_a_shrunken_segment_clamps():
    """It does NOT return None. Orphaning is the generator's decision, made from
    the resolved station, and a resolver that sometimes returns None forces
    every caller to branch on a case only one of them cares about."""
    topo, run = _stretched(4000)
    a = make_anchor(topo, run, 3000).model_copy(update={"reanchor": "rigid"})
    topo2, run2 = _stretched(1000)
    assert anchor_station(topo2, run2, a) == 1000


# --- cases beyond the plan's four -------------------------------------------

def test_a_rigid_anchor_is_unmoved_when_its_segment_is_unchanged():
    """The branch a `reanchor` bug hides in: proportional and rigid AGREE on an
    unchanged segment, so every single-segment golden scenario would stay green
    with the two behaviours swapped. Pinned separately from the stretch cases so
    a regression says which half broke."""
    topo, run = _stretched(4000)
    a = make_anchor(topo, run, 1200).model_copy(update={"reanchor": "rigid"})
    assert anchor_station(topo, run, a) == 1200


def test_a_rigid_anchor_on_a_later_segment_keeps_its_offset_from_its_own_corner():
    """The fact a rigid anchor asserts is the offset from ITS segment's start,
    not from the run's start — a post 800 mm past the corner stays 800 mm past
    the corner when the leg BEFORE it is stretched, and its absolute station
    moves by exactly what that earlier leg gained.

    A single-segment test cannot see this: there, offset and station are the same
    number, so a resolver that rigidly preserved the ABSOLUTE station would pass
    every other test in this file.
    """
    topo, run = _bent(4000, 3000)
    a = make_anchor(topo, run, 4800)  # 800 mm into the second (3000 mm) leg
    assert a.segment_index == 1 and a.offset_mm == 800
    rigid = a.model_copy(update={"reanchor": "rigid"})

    # stretch the FIRST leg only; the second leg is untouched
    topo2, run2 = _bent(9000, 3000)
    assert anchor_station(topo2, run2, rigid) == 9800
    # ...and proportional agrees here, because only the earlier leg changed
    assert anchor_station(topo2, run2, a) == 9800


def test_a_rigid_anchor_clamps_to_the_segment_not_to_the_run():
    """The clamp is segment-local, like the anchor. On a two-leg run whose SECOND
    leg shrank, a rigid offset past its end lands on that leg's end — not at the
    end of the run, and not at the end of the first leg."""
    topo, run = _bent(4000, 3000)
    a = make_anchor(topo, run, 6500).model_copy(update={"reanchor": "rigid"})
    assert a.segment_index == 1 and a.offset_mm == 2500

    topo2, run2 = _bent(4000, 1000)  # the leg the anchor sits on shrank
    assert anchor_station(topo2, run2, a) == 5000  # 4000 + clamp(2500 -> 1000)


def test_reanchor_survives_a_json_round_trip():
    """The policy is only as durable as its serialisation: an anchor is stored
    inside a topology and read back before it is resolved, and a field that did
    not persist would make every reload proportional again."""
    a = Anchor(segment_index=1, offset_mm=800, seg_len_at_authoring_mm=3000,
               reanchor="rigid")
    assert Anchor.model_validate_json(a.model_dump_json()).reanchor == "rigid"


def test_an_unknown_reanchor_policy_is_refused():
    """A `Literal`, not a `str`: a typo like "ridgid" must not silently resolve
    proportionally on a post whose whole point is that it does not move."""
    with pytest.raises(ValidationError):
        Anchor(segment_index=0, offset_mm=10, seg_len_at_authoring_mm=100,
               reanchor="ridgid")
