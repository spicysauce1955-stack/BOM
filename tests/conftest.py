"""Shared fixtures: demo catalog/knowledge and topology builders."""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.topology.model import (
    IntervalEvent,
    Node,
    PointEvent,
    Run,
    Topology,
)
from fenceai.topology.station import make_anchor


@pytest.fixture
def catalog():
    return demo_catalog()


@pytest.fixture
def knowledge():
    return demo_knowledge()


def straight_topology(length_mm: int, run_id: str = "run1") -> Topology:
    """A single straight run of the given length along the x axis."""
    return Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=length_mm, y_mm=0),
        ],
        runs=[Run(id=run_id, start_node_id="n1", end_node_id="n2")],
    )


def add_point_event(topo: Topology, run_id: str, event_id: str, station_mm: int, payload) -> None:
    run = topo.run(run_id)
    run.point_events.append(
        PointEvent(id=event_id, anchor=make_anchor(topo, run, station_mm), payload=payload)
    )


def add_interval_event(
    topo: Topology, run_id: str, event_id: str, start_mm: int, end_mm: int, payload
) -> None:
    run = topo.run(run_id)
    run.interval_events.append(
        IntervalEvent(
            id=event_id,
            start_anchor=make_anchor(topo, run, start_mm),
            end_anchor=make_anchor(topo, run, end_mm),
            payload=payload,
        )
    )
