"""What the fence is built to once a new height has carved an older one.

The height tool now carves (static/js/intervals.js, tested in
tests/web/test_intervals_module.py). These pin the other half of the claim in
docs/superpowers/specs/2026-10-12-office-desk-without-ai-design.md: that the
carved list is what the generator builds, and that the appended list it
replaces was not.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.topology.model import HeightIntentPayload
from tests.conftest import add_interval_event, straight_topology


def _heights_by_bay(topo) -> list[tuple[int, int, int]]:
    result = generate(topo, demo_knowledge(), demo_catalog())
    return sorted((s.start_station_mm, s.end_station_mm, s.height_mm)
                  for s in result.strategy.spans)


def test_an_appended_height_over_an_older_one_is_never_built():
    """The defect the carving closes, kept as a test so the reason stays true:
    if the generator ever starts reading the LAST covering height, the carving
    is still right, and this test says the old behaviour has gone."""
    topo = straight_topology(6000, "side")
    add_interval_event(topo, "side", "dana", 0, 6000, HeightIntentPayload(height_mm=1800))
    add_interval_event(topo, "side", "yossi", 0, 6000, HeightIntentPayload(height_mm=1750))
    assert {h for _, _, h in _heights_by_bay(topo)} == {1800}


def test_a_height_that_replaced_the_whole_stretch_is_built():
    topo = straight_topology(6000, "side")
    add_interval_event(topo, "side", "yossi", 0, 6000, HeightIntentPayload(height_mm=1750))
    assert {h for _, _, h in _heights_by_bay(topo)} == {1750}


def test_a_carved_height_keeps_the_older_one_where_the_new_one_stops():
    topo = straight_topology(6000, "side")
    add_interval_event(topo, "side", "dana", 0, 3000, HeightIntentPayload(height_mm=1800))
    add_interval_event(topo, "side", "yossi", 3000, 6000, HeightIntentPayload(height_mm=1750))
    bays = _heights_by_bay(topo)
    assert bays, "a 6 m run must build bays"
    for start, end, height in bays:
        middle = (start + end) // 2
        assert height == (1800 if middle < 3000 else 1750), bays
