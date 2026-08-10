"""Derived stationing and profiles over runs (ADR-0003).

All station math is exact integer arithmetic over straight segments; float64 appears
only transiently inside interpolation and is rounded once at the boundary (ADR-0002).
"""

from __future__ import annotations

import math

from fenceai.core.errors import InvalidTopology
from fenceai.core.units import NUMERIC_TOLERANCE_MM, Mm, dist_mm
from fenceai.topology.model import Anchor, Run, Topology

CORNER_ANGLE_DEG = 15.0  # turn angle above which a vertex is a structural corner


def run_points(topo: Topology, run: Run) -> list[tuple[Mm, Mm]]:
    start = topo.node(run.start_node_id)
    end = topo.node(run.end_node_id)
    return [(start.x_mm, start.y_mm), *run.interior_vertices, (end.x_mm, end.y_mm)]


def segment_lengths(points: list[tuple[Mm, Mm]]) -> list[Mm]:
    lens = [dist_mm(points[i], points[i + 1]) for i in range(len(points) - 1)]
    if any(l == 0 for l in lens):
        raise InvalidTopology("zero-length segment in run")
    return lens


def run_length(topo: Topology, run: Run) -> Mm:
    return sum(segment_lengths(run_points(topo, run)))


def cumulative_stations(points: list[tuple[Mm, Mm]]) -> list[Mm]:
    """Station of each vertex: [0, s1, s1+s2, ...]."""
    stations = [0]
    for length in segment_lengths(points):
        stations.append(stations[-1] + length)
    return stations


def anchor_station(topo: Topology, run: Run, anchor: Anchor) -> Mm:
    """Resolve an anchor to a current station, re-anchoring proportionally within its
    originating segment if that segment's length changed (ADR-0003 anchoring rule)."""
    points = run_points(topo, run)
    lens = segment_lengths(points)
    if not 0 <= anchor.segment_index < len(lens):
        raise InvalidTopology(f"anchor segment {anchor.segment_index} out of range")
    seg_len = lens[anchor.segment_index]
    if anchor.seg_len_at_authoring_mm == seg_len:
        offset = min(anchor.offset_mm, seg_len)
    else:
        offset = round(anchor.offset_mm * seg_len / anchor.seg_len_at_authoring_mm)
    return sum(lens[: anchor.segment_index]) + offset


def make_anchor(topo: Topology, run: Run, station_mm: Mm) -> Anchor:
    """Author an anchor at an absolute station on the current geometry."""
    points = run_points(topo, run)
    lens = segment_lengths(points)
    total = sum(lens)
    station = max(0, min(station_mm, total))
    acc = 0
    for i, seg_len in enumerate(lens):
        if station <= acc + seg_len or i == len(lens) - 1:
            return Anchor(
                segment_index=i,
                offset_mm=station - acc,
                seg_len_at_authoring_mm=seg_len,
            )
        acc += seg_len
    raise AssertionError("unreachable")


def point_at_station(topo: Topology, run: Run, station_mm: Mm) -> tuple[Mm, Mm]:
    points = run_points(topo, run)
    lens = segment_lengths(points)
    station = max(0, min(station_mm, sum(lens)))
    acc = 0
    for i, seg_len in enumerate(lens):
        if station <= acc + seg_len:
            t = (station - acc) / seg_len
            (x0, y0), (x1, y1) = points[i], points[i + 1]
            return (round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t))
        acc += seg_len
    return points[-1]


def corner_stations(topo: Topology, run: Run) -> list[Mm]:
    """Stations of interior vertices classified as structural corners (turn angle
    > CORNER_ANGLE_DEG), honoring corner_override point events."""
    points = run_points(topo, run)
    stations = cumulative_stations(points)
    overrides: dict[Mm, bool] = {}
    for ev in run.point_events:
        if ev.payload.kind == "corner_override":
            overrides[anchor_station(topo, run, ev.anchor)] = ev.payload.is_corner

    corners: list[Mm] = []
    for i in range(1, len(points) - 1):
        a, b, c = points[i - 1], points[i], points[i + 1]
        ang1 = math.atan2(b[1] - a[1], b[0] - a[0])
        ang2 = math.atan2(c[1] - b[1], c[0] - b[0])
        turn = abs(math.degrees((ang2 - ang1 + math.pi) % (2 * math.pi) - math.pi))
        is_corner = turn > CORNER_ANGLE_DEG
        for ov_station, ov_value in overrides.items():
            # tolerance match: re-anchoring rounding must not detach the override
            if abs(ov_station - stations[i]) <= NUMERIC_TOLERANCE_MM:
                is_corner = ov_value
        if is_corner:
            corners.append(stations[i])
    return corners


def max_slope_permille(topo: Topology, run: Run) -> int:
    """Steepest grade (permille, int) across consecutive ground samples (node
    elevations + events — endpoint-only slope would read an up-then-down run as
    flat, critic finding 16)."""
    samples = ground_samples(topo, run)
    steepest = 0
    for (s0, z0), (s1, z1) in zip(samples, samples[1:]):
        if s1 > s0:
            steepest = max(steepest, round(abs(z1 - z0) * 1000 / (s1 - s0)))
    return steepest


def ground_samples(topo: Topology, run: Run) -> list[tuple[Mm, Mm]]:
    """(station, z) ground samples for a run: the two node elevations anchor the
    endpoints (shared corners are single-valued fence-wide) plus any interior
    elevation_sample events. An explicit event within NUMERIC_TOLERANCE_MM of an
    endpoint overrides the node value (backwards compatible with event-only runs).
    """
    total = run_length(topo, run)
    events: list[tuple[Mm, Mm]] = []
    for ev in run.point_events:
        if ev.payload.kind == "elevation_sample":
            events.append((anchor_station(topo, run, ev.anchor), ev.payload.z_mm))
    events.sort()
    samples = list(events)
    if not any(abs(s) <= NUMERIC_TOLERANCE_MM for s, _ in events):
        samples.insert(0, (0, topo.node(run.start_node_id).z_mm))
    if not any(abs(s - total) <= NUMERIC_TOLERANCE_MM for s, _ in events):
        samples.append((total, topo.node(run.end_node_id).z_mm))
    samples.sort()
    return samples


def ground_z(topo: Topology, run: Run, station_mm: Mm) -> Mm:
    """Piecewise-linear ground elevation from node elevations + sample events."""
    samples = ground_samples(topo, run)
    total = run_length(topo, run)
    s = max(0, min(station_mm, total))
    for (s0, z0), (s1, z1) in zip(samples, samples[1:]):
        if s0 <= s <= s1:
            if s1 == s0:
                return z0
            return round(z0 + (z1 - z0) * (s - s0) / (s1 - s0))
    if s <= samples[0][0]:
        return samples[0][1]
    return samples[-1][1]


def base_surface_at(topo: Topology, run: Run, station_mm: Mm) -> str:
    """Base surface at a station; base interval events override the default 'soil'.

    Intervals are half-open [start, end) so the surface at a transition station is
    the RIGHT side's surface — except an interval ending at the run end includes its
    end (a boundary post at the very end still stands on that base). This makes the
    result independent of event authoring order (critic finding 8).
    """
    total = run_length(topo, run)
    for ev in run.interval_events:
        if ev.payload.kind == "base":
            s0 = anchor_station(topo, run, ev.start_anchor)
            s1 = anchor_station(topo, run, ev.end_anchor)
            end_inclusive = s1 >= total
            if s0 <= station_mm < s1 or (end_inclusive and station_mm == s1):
                return ev.payload.surface
    return "soil"


def base_transition_stations(topo: Topology, run: Run) -> list[Mm]:
    """Interior stations where the base surface changes (candidate structural boundaries)."""
    bounds: set[Mm] = set()
    total = run_length(topo, run)
    for ev in run.interval_events:
        if ev.payload.kind == "base":
            for s in (
                anchor_station(topo, run, ev.start_anchor),
                anchor_station(topo, run, ev.end_anchor),
            ):
                if 0 < s < total:
                    bounds.add(s)
    return sorted(s for s in bounds if base_surface_at(topo, run, s - 1) != base_surface_at(topo, run, s + 1))
