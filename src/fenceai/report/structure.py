"""The structure report: how the fence is laid out, and what each piece consists of.

A READ MODEL over one generation run — pure, derived, persisted nowhere. It answers
the two questions the drawing and the BOM leave between them:

  * where does every post go, and how wide is every bay (setting out, on site);
  * what does each element consist of (its parts).

Nothing here computes quantities. The parts come from inverting pegs that already
exist — `ResolvedSupplyLine.pegs` holds strategy element ids and `BomLine.pegs` holds
requirement ids — so the sum of the per-element parts IS the BOM, grouped by element
instead of by SKU. Anything the BOM carries that no element asked for (rounding
overage, a package remainder) is reported as unassigned rather than quietly dropped.

Tags (`P1`, `B1`, `G1`, sections `A`, `B`, …) are derived here and never stored:
element ids stay the machine identity, tags are what a crew says out loud.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.core.units import Mm
from fenceai.demand.derive import DemandLine
from fenceai.fulfillment.lines import ResolvedSupplyLine
from fenceai.fulfillment.fulfill import Bom
from fenceai.report.elevation import PanelElevation, panel_elevation
from fenceai.strategy.model import Strategy, StrategyWarning
from fenceai.topology.model import Topology
from fenceai.topology.station import ground_samples, run_length


class Part(BaseModel):
    """One material line of a single element — the same numbers as the BOM, seen
    from the element that caused them."""

    sku: str
    qty: int
    unit: str  # "each" | "cut" | "application"
    role: str = ""  # post | cap | concrete | rail | screw | gate_kit (see derive.py)
    slot_key: str = ""  # sub-element identity: which part of the panel this is
    cut_length_mm: Mm | None = None
    length_basis: str | None = None  # "width" | "slope"
    from_bars: list[str] = []  # cut-plan bar provenance ("new #2", an inventory id)


class Station(BaseModel):
    """A post, as the crew meets it: a running distance from the section start and
    the centre-to-centre spacing from the post before it."""

    tag: str          # unique per ELEMENT across the whole report ("A/P3")
    # the section that owns this post, when this row is a cross-reference: a
    # corner post belongs to one section and is SET OUT by both, and it must
    # carry one tag, or the drawing and the two tables disagree about its name
    shared_from: str | None = None
    element_id: str
    station_mm: Mm
    spacing_mm: Mm | None = None  # None for the first post of a section
    kind: str
    sku: str
    mounting: str
    ground_z_mm: Mm
    base_z_mm: Mm  # what the post stands on: a built base top, or the ground
    # what the elevation needs to draw the post as it actually sits: how far below
    # ground_z_mm it is set (the strategy's own number, resolved and checked at
    # generation), and how long the post is. `post_length_mm` is None when the
    # catalog product declares no length — the drawing then omits the embed
    # dimension instead of guessing one, which on a setting-out sheet is worse
    # than saying nothing.
    embed_mm: Mm = 0
    post_length_mm: Mm | None = None
    # ... and how far it rises ABOVE that: `top_z_mm` is the elevation of the
    # post top (the highest top of the bays that meet it), `exposed_mm` the
    # length of post that reaches it — the tilt-corrected number, so on a leaning
    # post the two differ. Copied from the strategy, where `_check_post_lengths`
    # computed them; the drawing must not answer "what does this post carry" a
    # second time, or a run that warns a post is 200 mm short draws it fine.
    #
    # None means no bay meets this post — the node post of a run whose first bay
    # is a gate — so nothing measured it. A drawing must then place the top by
    # some other rule of its own and say so; 0 is not that rule, it would read as
    # a post flush with the ground.
    exposed_mm: Mm | None = None
    top_z_mm: Mm | None = None
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
    # what this bay LOOKS like, derived from the same resolved slots its parts
    # come from — so the drawing and the schedule cannot disagree. None for a run
    # generated before panels existed, which `parts` already reports on.
    elevation: PanelElevation | None = None


def _elevation_for(span, bay_tag: str, resolved_sku: dict) -> PanelElevation | None:
    """The bay drawn, from its own resolved panel.

    `resolved_sku` fills in what `ResolvedSlot.sku` never carries — supply names
    the product on the REQUIREMENT, not on the slot — so this read model says the
    same thing here as it does on the preview. One shape with two truths is how a
    client ends up branching on which endpoint it came from.

    Clear width is the centre-to-centre width until products carry a face width
    (`attrs.face_width_mm`), which is the same approximation `resolve_panel` is
    handed at generation — so the drawing and the cut lengths agree about the
    opening even while both are waiting on the same catalog field.
    """
    if span.panel is None:
        return None
    drawn = span.panel.model_copy(deep=True)
    for slot in drawn.slots:
        slot.sku = resolved_sku.get((span.id, slot.slot_key), "")
    return panel_elevation(drawn, span.width_mm, span.height_mm,
                           span_id=span.id, bay_tag=bay_tag)


class GateRow(BaseModel):
    tag: str
    element_id: str
    # the posts the gate hangs between — the one thing a hanging crew needs
    from_tag: str | None = None
    to_tag: str | None = None
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
    # The ground under this section, as (station, z) — the SAME samples the
    # generator measured slope and steps against (`topology.station.ground_samples`),
    # not one z per post.
    #
    # A client with only the stations has to interpolate between them, and
    # between two posts either side of a retaining step that is a smooth chord:
    # a picture that argues with the site, on the datum the footings and the
    # embed hatch sit on. Copied, never recomputed — the report reads the same
    # function the layout read.
    ground: list[tuple[Mm, Mm]] = []


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
    # Both directions of "the parts and the BOM agree", because the BOM omits a
    # line entirely when stock covers the demand:
    #   unassigned — purchased beyond what any element asked for (rounding, whole
    #                packages); shown, never hidden
    #   from_stock — asked for and met from inventory, so it appears on no
    #                purchase line but still has to be picked in the yard
    unassigned: list[SkuTotal] = []
    from_stock: list[SkuTotal] = []


class StructureReport(BaseModel):
    run_id: str
    sections: list[Section] = []
    totals: Totals = Totals()
    # which inventory snapshot the cut-piece provenance was read against; the
    # layout never depends on it, the `from_bars` of a part does
    inventory_hash: str = ""
    # supply-resolution warnings (no_eligible_item, substitute_needs_approval, ...),
    # stamped by the caller exactly as inventory_hash is — build_structure() itself
    # stays a pure function of (topology, strategy, requirements, bom) and does not
    # compute these; a bay with a part nothing can supply must not go silent here.
    warnings: list[StrategyWarning] = []
    # the lines resolve_supply could not name a product for — stamped alongside
    # `warnings` for the same reason: routing them out of `requirements` (so a
    # blank sku can never reach fulfill()/the ledger) must not make them
    # disappear from what this view reports.
    # DemandLines, not resolved ones: an unresolved line is precisely one
    # that never got a product, and the type is what stops it reaching
    # fulfill()
    unresolved: list[DemandLine] = []


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


class _Ledger(BaseModel):
    """What every element asked for, and how the BOM answered it."""

    per_element: dict[str, list[Part]] = {}
    per_sku: list[SkuTotal] = []
    unassigned: list[SkuTotal] = []
    from_stock: list[SkuTotal] = []


def _parts_by_element(requirements: list[ResolvedSupplyLine], bom: Bom) -> _Ledger:
    """element id -> its parts, and the two ways the BOM can differ from them.

    Everything is accounted per (sku, UNIT): one SKU can legitimately be demanded
    in two units (a tube bought as a post and cut as a rail), and summing across
    them produced nonsense — including negative "unassigned" quantities.
    """
    bars = _bars_by_requirement(bom)
    per_element: dict[str, list[Part]] = {}
    asked: dict[tuple[str, str], int] = {}
    unpegged: dict[tuple[str, str], int] = {}
    for req in requirements:
        part = Part(
            sku=req.sku, qty=req.engineering_qty, unit=req.unit, role=req.role,
            slot_key=req.slot_key,
            cut_length_mm=req.cut_length_mm, length_basis=req.length_basis,
            from_bars=bars.get(req.id, []),
        )
        key = (req.sku, req.unit)
        asked[key] = asked.get(key, 0) + req.engineering_qty
        if req.pegs:
            for element_id in req.pegs:
                per_element.setdefault(element_id, []).append(part)
        else:
            # nobody's part: it belongs in the unassigned bucket, not in a
            # phantom element that no table would ever show
            unpegged[key] = unpegged.get(key, 0) + req.engineering_qty

    purchased: dict[tuple[str, str], int] = {}
    for line in bom.lines:
        key = (line.sku, line.engineering_unit)
        purchased[key] = purchased.get(key, 0) + line.engineering_qty
    unassigned: list[SkuTotal] = []
    from_stock: list[SkuTotal] = []
    for key in sorted(set(asked) | set(purchased)):
        sku, unit = key
        extra = purchased.get(key, 0) - asked.get(key, 0)
        if extra > 0:
            unassigned.append(SkuTotal(sku=sku, qty=extra, unit=unit))
        elif extra < 0:
            # asked for but not purchased: inventory covered it (fulfilment emits
            # no line at all when stock is enough), so the yard still picks it
            from_stock.append(SkuTotal(sku=sku, qty=-extra, unit=unit))
    for key, qty in sorted(unpegged.items()):
        unassigned.append(SkuTotal(sku=key[0], qty=qty, unit=key[1]))

    return _Ledger(
        per_element=per_element,
        per_sku=[SkuTotal(sku=sku, qty=qty, unit=unit)
                 for (sku, unit), qty in sorted(asked.items())],
        unassigned=unassigned, from_stock=from_stock,
    )


def _merge_parts(parts: list[Part]) -> list[Part]:
    """One line per (sku, unit, cut length): two rails of the same cut read as 2, not 1+1."""
    merged: dict[tuple, Part] = {}
    for p in parts:
        key = (p.sku, p.unit, p.role, p.slot_key, p.cut_length_mm, p.length_basis)
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
    """The section's base surface — or "mixed" when it genuinely has more than
    one, rather than whichever event happened to be authored first."""
    run = topo.run(run_id)
    surfaces = {iv.payload.surface for iv in run.interval_events
                if iv.payload.kind == "base"}
    if not surfaces:
        return "soil"
    return surfaces.pop() if len(surfaces) == 1 else "mixed"


def _post_tilt(topo: Topology, run_id: str) -> str:
    run = topo.run(run_id)
    modes = {iv.payload.mode for iv in run.interval_events
             if iv.payload.kind == "post_tilt"}
    if not modes:
        return "plumb"
    return modes.pop() if len(modes) == 1 else "mixed"


def _declared_post_length(catalog: Catalog | None, sku: str) -> Mm | None:
    """The post product's own length, read and never derived. The `isinstance`
    guard mirrors `_check_post_lengths` exactly: a length the generator would not
    check against is a length this sheet will not draw against either."""
    product = catalog.products.get(sku) if catalog else None
    length = product.attrs.get("length_mm") if product else None
    return length if isinstance(length, int) else None


def build_structure(
    topology: Topology,
    strategy: Strategy,
    requirements: list[ResolvedSupplyLine],
    bom: Bom,
    run_id: str = "",
    catalog: Catalog | None = None,
) -> StructureReport:
    """Pure: the same inputs always produce the same report.

    The catalog is a fifth GIVEN, not a fifth computation: the only thing read
    from it is a post product's declared `length_mm`, copied onto the station.
    Without one, every station reports `post_length_mm=None` — the same answer a
    product that declares no length gets, and the same drawing.
    """
    ledger = _parts_by_element(requirements, bom)
    parts = ledger.per_element
    # (element, slot) -> the product supply chose for it. Keyed on both because a
    # slot key is only unique WITHIN a panel: every bay resolves "rail".
    resolved_sku = {
        (peg, line.slot_key): line.sku
        for line in requirements if line.slot_key
        for peg in line.pegs
    }
    report = StructureReport(run_id=run_id)
    heights: list[Mm] = []
    element_tag: dict[str, str] = {}   # element id -> its ONE tag
    tag_owner: dict[str, str] = {}     # element id -> the section that named it

    for index, run in enumerate(topology.runs):
        length = run_length(topology, run)
        section = Section(
            tag=_section_tag(index), run_id=run.id, length_mm=length,
            base_surface=_base_surface(topology, run.id),
            post_tilt=_post_tilt(topology, run.id),
            ground=ground_samples(topology, run),
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
        owned = 0
        for station, post in own:
            # a post already tagged by an earlier section keeps that tag here
            existing = element_tag.get(post.id)
            if existing:
                tag, shared_from = existing, tag_owner[post.id]
            else:
                owned += 1
                tag = f"{section.tag}/P{owned}"
                shared_from = None
                element_tag[post.id] = tag
                tag_owner[post.id] = section.tag
            station_tag.setdefault(station, tag)
            section.setting_out.append(Station(
                tag=tag, shared_from=shared_from, element_id=post.id, station_mm=station,
                spacing_mm=None if previous is None else station - previous,
                kind=post.kind, sku=post.sku, mounting=post.mounting,
                ground_z_mm=post.ground_z_mm,
                base_z_mm=post.base_z_mm if post.base_z_mm is not None else post.ground_z_mm,
                embed_mm=post.embed_mm,
                post_length_mm=_declared_post_length(catalog, post.sku),
                exposed_mm=post.exposed_mm, top_z_mm=post.top_z_mm,
                tilt_deg=post.tilt_deg, reinforced=post.reinforced, pinned=post.pinned,
                parts=_merge_parts(parts.get(post.id, [])),
            ))
            previous = station

        for n, span in enumerate(
            sorted((s for s in strategy.spans if s.run_ref == run.id),
                   key=lambda s: s.start_station_mm), start=1):
            heights.append(span.height_mm)
            section.bays.append(Bay(
                tag=f"{section.tag}/B{n}", element_id=span.id,
                from_tag=station_tag.get(span.start_station_mm),
                to_tag=station_tag.get(span.end_station_mm),
                start_station_mm=span.start_station_mm, end_station_mm=span.end_station_mm,
                width_mm=span.width_mm, slope_len_mm=span.slope_len_mm,
                height_mm=span.height_mm, vertical=span.vertical,
                bottom_z_start_mm=span.bottom_z_start_mm,
                bottom_z_end_mm=span.bottom_z_end_mm,
                parts=_merge_parts(parts.get(span.id, [])),
                elevation=_elevation_for(span, f"{section.tag}/B{n}", resolved_sku),
            ))

        for n, gate in enumerate(
            sorted((g for g in strategy.gates if g.run_ref == run.id),
                   key=lambda g: g.start_station_mm), start=1):
            section.gates.append(GateRow(
                tag=f"{section.tag}/G{n}", element_id=gate.id,
                from_tag=station_tag.get(gate.start_station_mm),
                to_tag=station_tag.get(gate.end_station_mm),
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

    # counted over ELEMENTS, not over rows: a shared corner post is set out by
    # two sections and bought once
    distinct_posts = {st.element_id for s in report.sections for st in s.setting_out}
    report.totals = Totals(
        fence_length_mm=sum(s.length_mm for s in report.sections),
        posts=len(distinct_posts),
        bays=sum(len(s.bays) for s in report.sections),
        gates=sum(len(s.gates) for s in report.sections),
        height_min_mm=min(heights) if heights else None,
        height_max_mm=max(heights) if heights else None,
        per_sku=ledger.per_sku,          # from the requirements, one basis for all totals
        unassigned=ledger.unassigned,
        from_stock=ledger.from_stock,
    )
    return report
