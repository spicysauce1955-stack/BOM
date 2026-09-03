"""Where a directive applies, resolved the way every other anchor is.

`override_station` is a two-line wrapper over `anchor_station` ON PURPOSE. Rev 1
reimplemented the resolution and its three tests all avoided the one case where
the two implementations differ — a segment that changed length with the anchor
still inside it.
"""

from __future__ import annotations

import typing

import pytest
from pydantic import ValidationError

from fenceai.strategy.overrides import (
    Directive,
    LockBay,
    Override,
    PinPost,
    SuppressPost,
    override_station,
)
from fenceai.topology.station import anchor_station, make_anchor
from tests.conftest import straight_topology


def _rigid(topo, run, station):
    return make_anchor(topo, run, station).model_copy(update={"reanchor": "rigid"})


def test_a_pin_resolves_exactly_as_anchor_station_does():
    """The equivalence rev 1's tests could not see. If these two ever disagree,
    the plan canvas and the generator draw the same post in two places."""
    topo = straight_topology(4000)
    run = topo.run("run1")
    pin = PinPost(anchor=_rigid(topo, run, 1200))
    bigger = straight_topology(9000)
    assert override_station(bigger, bigger.run("run1"), pin) \
        == anchor_station(bigger, bigger.run("run1"), pin.anchor)


def test_a_pinned_post_keeps_its_distance_when_the_run_grows():
    topo = straight_topology(4000)
    pin = PinPost(anchor=_rigid(topo, topo.run("run1"), 1200))
    bigger = straight_topology(9000)
    assert override_station(bigger, bigger.run("run1"), pin) == 1200


def test_a_stored_pin_with_no_anchor_still_resolves():
    """Every stored override carries `station_mm` and nothing else, and every
    golden scenario is single-segment, where both readings agree exactly."""
    topo = straight_topology(4000)
    assert override_station(topo, topo.run("run1"), PinPost(station_mm=1200)) == 1200


def test_a_directive_carrying_neither_is_orphaned_not_pinned_at_zero():
    """`station_mm` gains a default so the anchor can be the only field, and
    `0 < station < length` would silently discard a bare PinPost with no report."""
    topo = straight_topology(4000)
    assert override_station(topo, topo.run("run1"), PinPost()) is None


def test_a_locked_bay_is_one_anchor_and_a_width():
    """NOT two anchors. Two anchors can half-orphan, can swallow a corner when
    a leg grows, and silently redefine which bay was locked — all three found by
    review."""
    topo = straight_topology(5000)
    lock = LockBay(at=_rigid(topo, topo.run("run1"), 2000), width_mm=1000)
    assert override_station(topo, topo.run("run1"), lock) == 2000
    assert lock.width_mm == 1000


# --- cases beyond the plan's five -------------------------------------------

def test_an_anchor_beats_a_stale_station_on_the_same_directive():
    """A directive can carry BOTH — `station_mm` is what the browser has always
    sent, and an anchored pin picks up an anchor without the old field being
    cleared. The anchor is the one that survives a geometry edit, so it wins;
    reading `station_mm` first would freeze the pin at the number it had when
    the run was a different length."""
    topo = straight_topology(4000)
    pin = PinPost(station_mm=1200, anchor=_rigid(topo, topo.run("run1"), 1200))
    bigger = straight_topology(9000)
    # both readings say 1200 on the authoring geometry...
    assert override_station(topo, topo.run("run1"), pin) == 1200
    # ...and on the stretched run the anchor is what answered
    assert override_station(bigger, bigger.run("run1"), pin) == 1200


def test_a_proportional_pin_anchor_stretches_and_a_rigid_one_does_not():
    """The wrapper adds no policy of its own: which of the two behaviours a pin
    gets is a fact about its ANCHOR, resolved by the one resolver. Two pins on
    the same station and the same run answer differently, and the difference
    comes entirely from `Anchor.reanchor`."""
    topo = straight_topology(4000)
    run = topo.run("run1")
    rigid = PinPost(anchor=_rigid(topo, run, 1000))
    proportional = PinPost(anchor=make_anchor(topo, run, 1000))
    bigger = straight_topology(8000)
    assert override_station(bigger, bigger.run("run1"), rigid) == 1000
    assert override_station(bigger, bigger.run("run1"), proportional) == 2000


def test_a_suppress_post_is_anchored_the_same_way():
    """`anchor` went onto both directives, not just the one the demo drags. A
    suppression that stayed station-only would drift off the post it suppresses
    the first time the run was edited, and the post would silently come back."""
    topo = straight_topology(4000)
    kill = SuppressPost(anchor=_rigid(topo, topo.run("run1"), 2000))
    bigger = straight_topology(9000)
    assert override_station(bigger, bigger.run("run1"), kill) == 2000
    assert override_station(topo, topo.run("run1"),
                            SuppressPost(station_mm=2000)) == 2000


def test_a_lock_bay_needs_its_anchor_and_its_width():
    """No defaults on either: a `LockBay` that fell back to station 0 or width 0
    would be a directive to build a bay nobody described, and it is built AS
    PLACED — there is no later step that would notice."""
    topo = straight_topology(5000)
    with pytest.raises(ValidationError):
        LockBay(width_mm=1000)
    with pytest.raises(ValidationError):
        LockBay(at=make_anchor(topo, topo.run("run1"), 2000))


def test_lock_bay_round_trips_through_the_discriminated_union():
    """`Override.directive` is discriminated on `kind`, so a `lock_bay` that was
    not added to the union parses as nothing and a stored override raises on
    load — the failure appears at read time, far from this change."""
    topo = straight_topology(5000)
    lock = LockBay(at=_rigid(topo, topo.run("run1"), 2000), width_mm=1000)
    ov = Override(id="ov1", run_id="run1", directive=lock)
    back = Override.model_validate_json(ov.model_dump_json())
    assert isinstance(back.directive, LockBay)
    assert back.directive.kind == "lock_bay"
    assert override_station(topo, topo.run("run1"), back.directive) == 2000


def test_every_directive_kind_resolves_to_somewhere_or_to_none():
    """`override_station` is called with whatever the union admits, so a kind
    added later must not raise here. Enumerated FROM the union rather than
    listed, so a new directive fails this test instead of failing at runtime the
    first time somebody stores one."""
    topo = straight_topology(6000)
    run = topo.run("run1")
    kinds = typing.get_args(typing.get_args(Directive)[0])
    assert len(kinds) >= 6, kinds  # the five that existed, plus lock_bay
    for model in kinds:
        fields = model.model_fields
        kwargs = {}
        if "at" in fields:
            kwargs["at"] = _rigid(topo, run, 2000)
        if "width_mm" in fields:
            kwargs["width_mm"] = 1000
        if "station_mm" in fields:
            kwargs["station_mm"] = 2000
        if "start_station_mm" in fields:
            kwargs["start_station_mm"] = 1000
            kwargs["end_station_mm"] = 3000
        if "sku" in fields:
            kwargs["sku"] = "POST-S"
        if "mounting" in fields:
            kwargs["mounting"] = "ground"
        if "mode" in fields:
            kwargs["mode"] = "level"
        station = override_station(topo, run, model(**kwargs))
        assert station is None or isinstance(station, int), (model, station)
