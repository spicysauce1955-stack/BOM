"""The structure report: how the fence is laid out, and what each piece consists of.

A READ MODEL over one generation run — pure, derived, persisted nowhere. It answers
the two questions the drawing and the BOM leave between them:

  * where does every post go, and how wide is every bay (setting out, on site);
  * what does each element consist of (its parts).

Nothing here computes quantities. The parts come from inverting pegs that already
exist — `RequirementLine.pegs` holds strategy element ids and `BomLine.pegs` holds
requirement ids — so the sum of the per-element parts IS the BOM, grouped by element
instead of by SKU. Anything the BOM carries that no element asked for (rounding
overage, a package remainder) is reported as unassigned rather than quietly dropped.

Tags (`P1`, `B1`, `G1`, sections `A`, `B`, …) are derived here and never stored:
element ids stay the machine identity, tags are what a crew says out loud.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.demand.derive import RequirementLine
from fenceai.fulfillment.fulfill import Bom
from fenceai.strategy.model import Strategy
from fenceai.topology.model import Topology
from fenceai.topology.station import run_length


class Part(BaseModel):
    """One material line of a single element — the same numbers as the BOM, seen
    from the element that caused them."""

    sku: str
    qty: int
    unit: str  # "each" | "cut" | "application"
    role: str = ""  # post | cap | concrete | rail | screw | gate_kit (see derive.py)
    cut_length_mm: Mm | None = None
    length_basis: str | None = None  # "width" | "slope"
    from_bars: list[str] = []  # cut-plan bar provenance ("new #2", an inventory id)


class Station(BaseModel):
    """A post, as the crew meets it: a running distance from the section start and
    the centre-to-centre spacing from the post before it."""

    tag: str
    element_id: str
    station_mm: Mm
    spacing_mm: Mm | None = None  # None for the first post of a section
    kind: str
    sku: str
    mounting: str
    ground_z_mm: Mm
    base_z_mm: Mm  # what the post stands on: a built base top, or the ground
    tilt_deg: int = 0
    reinforced: bool = False
    pinned: bool = False
    parts: list[Part] = []


class Bay(BaseModel):
    tag: str
    element_id: str
    from_tag: str | None = None
    to_tag: str | None = None
    start_station_mm: Mm
    end_station_mm: Mm
    width_mm: Mm
    slope_len_mm: Mm
    height_mm: Mm
    vertical: str
    bottom_z_start_mm: Mm
    bottom_z_end_mm: Mm
    parts: list[Part] = []


class GateRow(BaseModel):
    tag: str
    element_id: str
    start_station_mm: Mm
    end_station_mm: Mm
    opening_mm: Mm
    kit_sku: str | None = None
    parts: list[Part] = []


class Section(BaseModel):
    tag: str
    run_id: str
    length_mm: Mm
    base_surface: str
    post_tilt: str = "plumb"
    height_mm: Mm | None = None  # single height, when the section has just one
    setting_out: list[Station] = []
    bays: list[Bay] = []
    gates: list[GateRow] = []


class SkuTotal(BaseModel):
    sku: str
    qty: int
    unit: str


class Totals(BaseModel):
    fence_length_mm: Mm = 0
    posts: int = 0
    bays: int = 0
    gates: int = 0
    height_min_mm: Mm | None = None
    height_max_mm: Mm | None = None
    per_sku: list[SkuTotal] = []
    # BOM demand that pegs to no element (overage, package remainders): shown, never hidden
    unassigned: list[SkuTotal] = []


class StructureReport(BaseModel):
    run_id: str
    sections: list[Section] = []
    totals: Totals = Totals()
    # which inventory snapshot the cut-piece provenance was read against; the
    # layout never depends on it, the `from_bars` of a part does
    inventory_hash: str = ""


# --- parts, by inverting the pegs -------------------------------------------

def _bars_by_requirement(bom: Bom) -> dict[str, list[str]]:
    """Which bar each cut piece came from, keyed by requirement id."""
    out: dict[str, list[str]] = {}
    for plan in bom.cut_plans.values():
        for i, bar in enumerate(plan.bars, start=1):
            label = f"{plan.sku} #{i}" if bar.source == "new" else f"{plan.sku} ⟲{bar.source}"
            for piece in bar.pieces:
                out.setdefault(piece.requirement_id, []).append(label)
    return out


def _parts_by_element(
    requirements: list[RequirementLine], bom: Bom
) -> tuple[dict[str, list[Part]], list[SkuTotal]]:
    """element id -> its parts, plus whatever the BOM carries for no element."""
    bars = _bars_by_requirement(bom)
    per_element: dict[str, list[Part]] = {}
    pegged: dict[tuple[str, str], int] = {}
    for req in requirements:
        part = Part(
            sku=req.sku, qty=req.engineering_qty, unit=req.unit, role=req.role,
            cut_length_mm=req.cut_length_mm, length_basis=req.length_basis,
            from_bars=bars.get(req.id, []),
        )
        for element_id in req.pegs or ["—"]:
            per_element.setdefault(element_id, []).append(part)
        pegged[(req.sku, req.unit)] = pegged.get((req.sku, req.unit), 0) + req.engineering_qty

    # what the BOM demands beyond what elements asked for
    unassigned: list[SkuTotal] = []
    for line in bom.lines:
        asked = sum(q for (sku, _u), q in pegged.items() if sku == line.sku)
        extra = line.engineering_qty - asked
        if extra:
            unassigned.append(SkuTotal(sku=line.sku, qty=extra, unit=line.engineering_unit))
    return per_element, unassigned


def _merge_parts(parts: list[Part]) -> list[Part]:
    """One line per (sku, unit, cut length): two rails of the same cut read as 2, not 1+1."""
    merged: dict[tuple, Part] = {}
    for p in parts:
        key = (p.sku, p.unit, p.role, p.cut_length_mm, p.length_basis)
        if key in merged:
            merged[key].qty += p.qty
            merged[key].from_bars = merged[key].from_bars + p.from_bars
        else:
            merged[key] = p.model_copy(deep=True)
    return sorted(merged.values(), key=lambda p: (p.sku, p.cut_length_mm or 0))


# --- the report --------------------------------------------------------------

_SECTION_TAGS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _section_tag(index: int) -> str:
    """A, B, … Z, AA, AB … — sections are named, not numbered, so a bay tag (B3)
    never reads like a section tag."""
    tag = ""
    n = index
    while True:
        tag = _SECTION_TAGS[n % 26] + tag
        n = n // 26 - 1
        if n < 0:
            return tag


def _base_surface(topo: Topology, run_id: str) -> str:
    run = topo.run(run_id)
    for iv in run.interval_events:
        if iv.payload.kind == "base":
            return iv.payload.surface
    return "soil"


def _post_tilt(topo: Topology, run_id: str) -> str:
    run = topo.run(run_id)
    for iv in run.interval_events:
        if iv.payload.kind == "post_tilt":
            return iv.payload.mode
    return "plumb"


def build_structure(
    topology: Topology,
    strategy: Strategy,
    requirements: list[RequirementLine],
    bom: Bom,
    run_id: str = "",
) -> StructureReport:
    """Pure: the same inputs always produce the same report."""
    parts, unassigned = _parts_by_element(requirements, bom)
    report = StructureReport(run_id=run_id)
    heights: list[Mm] = []
    per_sku: dict[tuple[str, str], int] = {}

    for index, run in enumerate(topology.runs):
        length = run_length(topology, run)
        section = Section(
            tag=_section_tag(index), run_id=run.id, length_mm=length,
            base_surface=_base_surface(topology, run.id),
            post_tilt=_post_tilt(topology, run.id),
        )

        # posts: this run's own, plus the shared node posts at either end
        own = [(p.station_mm, p) for p in strategy.posts if p.run_ref == run.id]
        for post in strategy.posts:
            if post.run_ref == f"node:{run.start_node_id}":
                own.append((0, post))
            elif post.run_ref == f"node:{run.end_node_id}":
                own.append((length, post))
        own.sort(key=lambda pair: (pair[0], pair[1].id))

        station_tag: dict[Mm, str] = {}
        previous: Mm | None = None
        for n, (station, post) in enumerate(own, start=1):
            tag = f"P{n}"
            station_tag[station] = tag
            section.setting_out.append(Station(
                tag=tag, element_id=post.id, station_mm=station,
                spacing_mm=None if previous is None else station - previous,
                kind=post.kind, sku=post.sku, mounting=post.mounting,
                ground_z_mm=post.ground_z_mm,
                base_z_mm=post.base_z_mm if post.base_z_mm is not None else post.ground_z_mm,
                tilt_deg=post.tilt_deg, reinforced=post.reinforced, pinned=post.pinned,
                parts=_merge_parts(parts.get(post.id, [])),
            ))
            previous = station

        for n, span in enumerate(
            sorted((s for s in strategy.spans if s.run_ref == run.id),
                   key=lambda s: s.start_station_mm), start=1):
            heights.append(span.height_mm)
            section.bays.append(Bay(
                tag=f"B{n}", element_id=span.id,
                from_tag=station_tag.get(span.start_station_mm),
                to_tag=station_tag.get(span.end_station_mm),
                start_station_mm=span.start_station_mm, end_station_mm=span.end_station_mm,
                width_mm=span.width_mm, slope_len_mm=span.slope_len_mm,
                height_mm=span.height_mm, vertical=span.vertical,
                bottom_z_start_mm=span.bottom_z_start_mm,
                bottom_z_end_mm=span.bottom_z_end_mm,
                parts=_merge_parts(parts.get(span.id, [])),
            ))

        for n, gate in enumerate(
            sorted((g for g in strategy.gates if g.run_ref == run.id),
                   key=lambda g: g.start_station_mm), start=1):
            section.gates.append(GateRow(
                tag=f"G{n}", element_id=gate.id,
                start_station_mm=gate.start_station_mm,
                end_station_mm=gate.end_station_mm,
                opening_mm=gate.end_station_mm - gate.start_station_mm,
                kit_sku=gate.kit_sku,
                parts=_merge_parts(parts.get(gate.id, [])),
            ))

        section_heights = {b.height_mm for b in section.bays}
        if len(section_heights) == 1:
            section.height_mm = section_heights.pop()
        report.sections.append(section)

    for element_parts in parts.values():
        for part in element_parts:
            per_sku[(part.sku, part.unit)] = per_sku.get((part.sku, part.unit), 0) + part.qty

    report.totals = Totals(
        fence_length_mm=sum(s.length_mm for s in report.sections),
        posts=sum(len(s.setting_out) for s in report.sections),
        bays=sum(len(s.bays) for s in report.sections),
        gates=sum(len(s.gates) for s in report.sections),
        height_min_mm=min(heights) if heights else None,
        height_max_mm=max(heights) if heights else None,
        per_sku=[SkuTotal(sku=sku, qty=qty, unit=unit)
                 for (sku, unit), qty in sorted(per_sku.items())],
        unassigned=unassigned,
    )
    return report
