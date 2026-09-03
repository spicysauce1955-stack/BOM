"""A hand-placed bay is built as placed, and marked when it departs.

The actor lives on `Override.author`, not on the directive — so the generator
reaches the enclosing override, and the test asserts the whole param dict rather
than one key, because `run_id` is what the surfaces need to draw the bay.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.core.errors import GenerationFailure
from fenceai.strategy.generator import generate
from fenceai.strategy.layout import LayoutResult
from fenceai.strategy.overrides import LockBay, Override, PinPost
from fenceai.topology.station import make_anchor
from tests.conftest import straight_topology


def _rigid(topo, station):
    return make_anchor(topo, topo.run("run1"), station).model_copy(
        update={"reanchor": "rigid"})


def test_an_unlocked_gap_is_still_subdivided():
    """Correct: an unlocked gap is what was left to the engine. demo max_span is
    1800, so a 3000 mm gap becomes two bays."""
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(),
                   overrides=[Override(id="o1", run_id="run1",
                                       directive=PinPost(anchor=_rigid(topo, 3000)))])
    assert [s.width_mm for s in out.strategy.spans][:2] == [1500, 1500]


def test_a_locked_bay_is_built_as_placed():
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o1", run_id="run1",
                 directive=PinPost(anchor=_rigid(topo, 3000))),
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=3000)),
    ])
    assert [s.width_mm for s in out.strategy.spans][0] == 3000


def test_a_locked_bay_over_the_maximum_warns_with_every_figure_a_surface_needs():
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o1", run_id="run1",
                 directive=PinPost(anchor=_rigid(topo, 3000))),
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=3000)),
    ])
    warn = next(w for w in out.strategy.warnings
                if w.code == "span_placed_over_maximum")
    assert warn.params == {"run_id": "run1", "placed_mm": 3000,
                           "max_mm": 1800, "over_mm": 1200, "author": "bob"}


def test_the_graph_attributes_the_placement_to_a_person():
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o1", run_id="run1",
                 directive=PinPost(anchor=_rigid(topo, 3000))),
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=3000)),
    ])
    node = next(n for n in out.graph.nodes if n.action == "lock_bay")
    assert node.payload["author"] == "bob"
    assert node.kind == "override_applied"


def test_a_narrow_lock_still_gets_sliver_span_and_not_a_second_code():
    """K-SLIVER prefers 500 mm; a 400 mm bay against a wall is a thing people
    want, so it is the EXISTING preference warning and not a new code."""
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=400)),
    ])
    assert [s.width_mm for s in out.strategy.spans][0] == 400
    slivers = [w for w in out.strategy.warnings if w.code == "sliver_span"]
    assert [w.params["width_mm"] for w in slivers] == [400]
    assert not [w for w in out.strategy.warnings
                if w.code == "span_placed_over_maximum"]


def test_the_lock_authorises_only_the_bay_it_placed():
    """A run with a lock in it is not a run with the maximum switched off: the
    bays the engine laid out beside the locked one are still under 1800, and
    exactly one bay is reported over the maximum."""
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=3000)),
    ])
    widths = [s.width_mm for s in out.strategy.spans]
    assert widths[0] == 3000
    assert all(w <= 1800 for w in widths[1:])
    assert len([w for w in out.strategy.warnings
                if w.code == "span_placed_over_maximum"]) == 1


def test_an_over_wide_bay_nobody_locked_still_fails_loudly(monkeypatch):
    """The failure this narrowing must NOT introduce.

    The danger is not the locked bay: it is that an ACCIDENTAL over-wide bay — a
    layout bug, a knowledge rule with a wrong number — stops failing loudly and
    ships as a warned line that looks deliberate. So the guard has to get
    narrower, not absent.

    Simulated as the accident itself: `layout_segment` is made to hand back the
    whole segment as one bay, which is what a layout bug looks like from here.
    The run below HAS a lock, and the over-wide bay is still fatal — because the
    authorisation is scoped to the interval the lock placed, not to the run.
    """
    from fenceai.strategy import generator as gen

    monkeypatch.setattr(
        gen, "layout_segment",
        lambda length_mm, max_span_mm, **kw: LayoutResult(
            widths=[length_mm], rejected_alternative=None),
    )
    topo = straight_topology(5000)
    with pytest.raises(GenerationFailure):
        generate(topo, demo_knowledge(), demo_catalog())
    with pytest.raises(GenerationFailure):
        generate(topo, demo_knowledge(), demo_catalog(), overrides=[
            Override(id="o2", run_id="run1", author="bob",
                     directive=LockBay(at=_rigid(topo, 0), width_mm=1500)),
        ])
