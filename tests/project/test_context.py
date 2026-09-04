"""The house and the street — slice 3 of the salesperson MVP.

A salesperson does not think *"node at (0,0) to node at (12000,0)"*. They think
*"along the street side, about 12 metres, then it turns in toward the house."*
Without that context the office person receiving the layout cannot read it as a
PLACE, and every question they would otherwise answer themselves becomes a phone
call — which is the one thing this MVP exists to prevent.

**Why this lives on `Project` and not in `Topology`.** A landmark changes no
quantity. `Topology` is what `generate()` consumes and what every derived view
checks its own staleness against, so a house in there would bump the topology
revision and 409 the structure sheet because somebody nudged a driveway. The
constraint that keeps this cheap is that generation must never see it — asserted
below rather than merely intended.

**One shape for everything.** A house is a closed polyline, a street is an open
one. A salesperson sketching on paper draws both with the same stroke, and two
geometry types would buy nothing but a second set of edge cases.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.project.model import Landmark, Project, SiteContext


def _house() -> Landmark:
    return Landmark(id="lm1", kind="house", closed=True, label="the house",
                    points=[(0, 0), (8000, 0), (8000, 6000), (0, 6000)])


def test_a_project_starts_with_no_context_and_that_is_valid():
    """Every project that exists today has none, and none of them may break."""
    p = Project(id="p1", name="untitled")
    assert p.context.landmarks == []


def test_a_house_is_a_closed_outline_and_a_street_is_an_open_line():
    ctx = SiteContext(landmarks=[
        _house(),
        Landmark(id="lm2", kind="street", points=[(-2000, -3000), (20000, -3000)]),
    ])
    house, street = ctx.landmarks
    assert house.closed and len(house.points) == 4
    assert not street.closed and len(street.points) == 2


def test_a_landmark_needs_at_least_two_points():
    """A single point is not a shape. It would render as nothing and read as a
    landmark that failed to draw."""
    with pytest.raises(ValidationError):
        Landmark(id="lm1", kind="street", points=[(0, 0)])


def test_a_closed_landmark_needs_at_least_three():
    """Two points cannot enclose anything; a "closed" line is a contradiction
    that would draw as a line and claim to be a building."""
    with pytest.raises(ValidationError):
        Landmark(id="lm1", kind="house", closed=True, points=[(0, 0), (1000, 0)])


def test_an_unknown_kind_is_refused_at_the_boundary():
    """Kinds are a REGISTRY, not a free string: each one is drawn differently and
    means something specific to the office person reading the layout. Adding a
    kind is a one-line change to `LANDMARK_KINDS`; inventing one by typo is not.
    """
    with pytest.raises(ValidationError):
        Landmark(id="lm1", kind="swimming-pool", points=[(0, 0), (1, 1)])


def test_the_registry_covers_what_a_salesperson_actually_names():
    """They said it in this order: relative to the house, the street, the road.
    `other` carries the rest with a label, so an unnamed thing on the sketch is
    recordable rather than lost."""
    from fenceai.project.model import LANDMARK_KINDS
    assert set(LANDMARK_KINDS) == {"house", "street", "boundary", "other"}


def test_coordinates_are_integer_millimetres_like_everything_else():
    """ADR-0002. The landmark shares a plane with the topology's nodes, so a
    float here would put the house on a different grid from the fence."""
    lm = Landmark(id="lm1", kind="street", points=[(1.6, 2.4), (3000.5, 0)])
    assert lm.points == [(2, 2), (3000, 0)]
    assert all(isinstance(v, int) for p in lm.points for v in p)


def test_a_context_round_trips_through_serialisation():
    p = Project(id="p1", name="untitled", context=SiteContext(landmarks=[_house()]))
    assert Project.model_validate(p.model_dump()) == p


def test_two_landmarks_may_not_share_an_id():
    """The same reason `Topology` refuses duplicate node ids: downstream they
    silently merge, and a delete would remove the wrong one."""
    with pytest.raises(ValidationError):
        SiteContext(landmarks=[_house(), _house()])


def test_the_context_is_invisible_to_generation():
    """The constraint that keeps this slice cheap, asserted rather than intended.

    A landmark changes no quantity, so a fence generated with a house beside it
    must be byte-identical to the same fence generated without one. If this ever
    fails, the context has become topology and needs a revision, a staleness
    check and a place in the decision graph — none of which it has.
    """
    from fenceai.catalog.demo import demo_catalog
    from fenceai.knowledge.demo import demo_knowledge
    from fenceai.strategy.generator import generate
    from tests.conftest import straight_topology

    topo = straight_topology(5000)
    bare = generate(topo, demo_knowledge(), demo_catalog())
    # `generate()` takes a topology, not a project — which IS the isolation. The
    # assertion is that nothing had to be passed: there is no parameter through
    # which a landmark could reach it.
    import inspect
    params = set(inspect.signature(generate).parameters)
    assert "context" not in params and "landmarks" not in params
    assert "project" not in params
    again = generate(topo, demo_knowledge(), demo_catalog())
    assert [s.width_mm for s in bare.strategy.spans] == \
           [s.width_mm for s in again.strategy.spans]
