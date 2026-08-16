"""What one panel of a model is made of, before any fence has been drawn.

The question a model picker has to answer to be a picker rather than a dropdown:
*if I build this model at this height and this bay width, what is in one panel
and what does it cost?* Until this existed a `PanelSpec` reached a human only
after generation, as two numbers on a BOM line.

It is emphatically **not** a run: no id, not stored, not quotable, and no
inventory. What it is instead is the SAME pipeline — `resolve_panel` ->
`derive_requirements` -> `resolve_supply` -> `fulfill` — driven over a synthetic
one-bay strategy. That is the whole design: a preview computed by a second,
simpler code path would eventually disagree with the fence the user then gets,
and a preview that lies is worse than no preview. Every number here is produced
by the function that will produce it for real.

The synthetic strategy carries one span and no posts, so `derive_requirements`
emits the panel's lines and nothing else — the posts, caps and concrete of a real
bay depend on neighbours this bay does not have.

A bay of a STORED run is the same question asked about a fence that exists, and
`bay_preview_plan` below is how it stays the same question: it rebuilds the
`PanelContext` the run resolved that bay with — its vertical mode, its rail cut
basis, its knowledge-resolved quantities, its option values — and hands it to the
one `preview_panel` above. A drawer that asked the model-scoped route instead was
previewing a DIFFERENT bay of the same model: level rails on a raked span, the
model's authored rail count over the company's, and whatever objective preset
that route happened to default to.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.core.errors import ReadRefused
from fenceai.core.units import Cents, Mm, slope_len_mm
from fenceai.fencemodel.model import FenceModel, validate_model
from fenceai.fencemodel.resolve import PanelContext, ResolvedPanel, resolve_panel, select_variant
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.report.elevation import PanelElevation, panel_elevation
from fenceai.strategy.model import GenerationResult, Span, Strategy, StrategyWarning

PREVIEW_SPAN_ID = "span@preview:0-0"


class PreviewRequest(BaseModel):
    """The bay a preview is imagined into. Millimetres at rest, like everything
    else — the display unit is the client's business (`units.js`)."""

    height_mm: Mm = 1800
    width_mm: Mm = 2500                  # centre to centre, as a span is measured
    clear_width_mm: Mm | None = None     # None = the same, until face widths land
    vertical: str = "level"
    # How a member that crosses the bay is measured, exactly as `Span` records
    # it: a raked bay's rails are cut on the SLOPE, and a preview that assumed
    # "width" drew and priced shorter rails than the fence is built from (S04,
    # S06). Not expressible before, so the drawer could not ask for it at all.
    length_basis: Literal["width", "slope"] = "width"   # the span's own basis
    slope_len_mm: Mm | None = None       # true length along grade; None = width
    options: dict[str, str | int] = {}
    # knowledge-resolved quantities a real bay would arrive with. The preview
    # cannot resolve knowledge itself (it has no project, so no scope to bind),
    # so a caller that knows them passes them and a caller that does not gets the
    # model's own authored defaults.
    params: dict[str, int] = {}
    # "price this panel with THAT product in this slot" — the material drawer.
    # Preview-scoped by design (spec §1): it re-prices what is being imagined and
    # patches no stored run; making a choice stick is authoring the model or an
    # override anchored to (run_id, station, kind), both of which already exist.
    slot_skus: dict[str, str] = {}


class PreviewPart(BaseModel):
    """One slot of the panel, priced. `eligible_skus` is the whole candidate set
    and `sku` the one the preset chose, because "why that product" is exactly
    what a person comparing two models is trying to see."""

    slot_key: str
    role: str
    qty: int
    length_mm: Mm | None = None
    unit: str = ""
    eligible_skus: list[str] = []
    sku: str = ""
    # the other slots this product is bought for, if any. `purchase_qty` and the
    # unit price sit on the first of them only — half a bar bought is not a
    # thing, and the money is apportioned across the rows so they still total.
    shares_sku_with: list[str] = []
    unit_price_cents: int = 0
    purchase_qty: int = 0
    total_cents: int = 0


class PanelPreview(BaseModel):
    model_ref: str
    variant_index: int | None = None
    height_mm: Mm
    width_mm: Mm
    clear_width_mm: Mm
    panel: ResolvedPanel
    # the panel drawn — rectangles in the panel's own frame, so the client
    # positions them and never computes them
    elevation: PanelElevation = PanelElevation()
    parts: list[PreviewPart] = []
    # lines nothing eligible could supply — reported, never dropped, exactly as
    # /bom reports them; a panel one part short must not preview as complete
    unsupplied: list[PreviewPart] = []
    warnings: list[StrategyWarning] = []
    # what `validate_model` says about this document. NOT a refusal — a draft
    # being edited is invalid by definition and still worth looking at — but a
    # model using an unbuilt feature previews as though the feature worked, which
    # is precisely what `_unsupported_features` exists to prevent. Reported, so
    # the surface that shows the panel can say the panel is not the whole story.
    invalid: list[str] = []
    total_cents: int = 0


def preview_panel(
    model: FenceModel,
    request: PreviewRequest,
    catalog: Catalog,
    preset: str = "least_cost",
) -> PanelPreview:
    clear = request.clear_width_mm if request.clear_width_mm is not None else request.width_mm
    slope = request.slope_len_mm if request.slope_len_mm is not None else request.width_mm
    ctx = PanelContext(
        centre_width_mm=request.width_mm,
        clear_width_mm=clear,
        height_mm=request.height_mm,
        vertical=request.vertical,
        length_basis=request.length_basis,
        slope_len_mm=slope,
        params=request.params,
        options=dict(request.options),
        slot_skus=dict(request.slot_skus),
    )
    spec, variant_index = select_variant(model, ctx)
    # the variant is recorded on the panel as well as on the preview, because a
    # bay of a stored run previews into a `ResolvedPanel` that must be the one
    # the run stored — down to which variant it was built to
    panel = resolve_panel(spec, ctx, model_ref=model.ref, variant_index=variant_index)

    span = Span(
        id=PREVIEW_SPAN_ID, run_ref="preview",
        start_station_mm=0, end_station_mm=request.width_mm,
        width_mm=request.width_mm, slope_len_mm=slope,
        vertical=request.vertical,  # type: ignore[arg-type]
        height_mm=request.height_mm,
        rail_cut_basis=request.length_basis,
        panel=panel,
    )
    # no inventory: a preview answers "what does this model cost to build", and
    # stock on hand is a property of a project, not of a model
    priced = price_strategy(Strategy(id="preview", spans=[span]), catalog, preset=preset)

    parts = _priced_parts(priced)
    # the drawing names the products the preview resolved, so a colour swatch and
    # a price belong to the same rectangle
    resolved_sku = {line.slot_key: line.sku for line in priced.requirements}
    drawn = panel.model_copy(deep=True)
    for slot in drawn.slots:
        slot.sku = resolved_sku.get(slot.slot_key, "")
    return PanelPreview(
        model_ref=model.ref,
        variant_index=variant_index,
        height_mm=request.height_mm,
        width_mm=request.width_mm,
        clear_width_mm=clear,
        panel=panel,
        elevation=panel_elevation(drawn, clear, request.height_mm),
        parts=parts,
        unsupplied=[_part(line, None) for line in priced.unresolved],
        warnings=priced.warnings,
        invalid=validate_model(model, catalog),
        total_cents=priced.bom.total_cents,
    )


# -- a bay of a stored run ----------------------------------------------------

class BayPreviewRequest(BaseModel):
    """What a caller may vary about a bay that already exists.

    Every field is optional and every default is the bay's own, so an empty body
    means "price this bay exactly as the run resolved it". Deliberately NOT a
    `PreviewRequest`: a client that could send `params`, `options` or a length
    basis for a bay of a stored fence could ask for a preview of a bay that run
    never built and be answered without a word. What the run resolved is read
    off the run; what a person is imagining — a taller bay, a wider one, a
    different product in one slot — is what is left here.
    """

    height_mm: Mm | None = None
    width_mm: Mm | None = None
    slot_skus: dict[str, str] = {}


class BayPreviewPlan(BaseModel):
    """The bay, ready to be previewed: which model document to resolve it
    against, and the request that reproduces it."""

    model_id: str
    version: int
    request: PreviewRequest


def bay_preview_plan(
    result: GenerationResult, element_id: str, ask: BayPreviewRequest | None = None,
) -> BayPreviewPlan | None:
    """Rebuild the context one stored bay was generated with.

    The generator resolves a bay from a `PanelContext` carrying far more than a
    height and a width (`strategy/generator.py`), and every part of it changes
    what the panel is made of: the vertical mode picks the variant, the rail cut
    basis decides whether a rail is cut on the chord or the slope, the params
    carry the company's rails- and screws-per-span, and the options narrow half
    the eligibility sets. A preview that defaulted them was not a preview of
    this bay.

    So they are read back rather than re-derived: the quantities from the span
    (which is where the generator recorded them), the options from the run's own
    explanation. `None` when the element is not a bay of this run — the caller
    turns that into a 404, since this module knows nothing about HTTP.
    """
    ask = ask or BayPreviewRequest()
    span = next((s for s in result.strategy.spans if s.id == element_id), None)
    if span is None:
        return None
    if span.panel is None or not span.panel.model_ref:
        # the same refusal `derive_requirements` raises for such a run, and for
        # the same reason: there IS structure, it just cannot be read without
        # regenerating — a preview must not invent a model for it
        raise ReadRefused(
            code="run_predates_fence_model",
            message=f"span {span.id} has no panel — regenerate the run",
            span_id=span.id,
        )
    model_id, version = _ref_parts(span.panel.model_ref)
    width = ask.width_mm if ask.width_mm is not None else span.width_mm
    return BayPreviewPlan(
        model_id=model_id, version=version,
        request=PreviewRequest(
            height_mm=ask.height_mm if ask.height_mm is not None else span.height_mm,
            width_mm=width,
            vertical=span.vertical,
            length_basis=span.rail_cut_basis,
            slope_len_mm=_slope_for(span, width),
            # The face allowance this bay was actually built with, carried over
            # rather than recomputed: imagining a different bay WIDTH does not
            # change which posts bound it, so the same two half-faces are lost.
            # A run generated before the opening was recorded allows nothing,
            # which is what those runs were built to.
            clear_width_mm=width - _face_allowance(span),
            # what the generator put in `ctx.params`, from where it put it: the
            # span carries the resolved quantities precisely so a later reader
            # never has to re-run the knowledge evaluator to learn them
            params={"rails_per_span": span.rail_count,
                    "screws_per_span": span.screws_count},
            options=_bay_options(result, span),
            slot_skus=dict(ask.slot_skus),
        ),
    )


def _ref_parts(model_ref: str) -> tuple[str, int]:
    model_id, _, version = model_ref.rpartition("@v")
    if not model_id or not version.isdigit():
        raise ReadRefused(
            code="run_predates_fence_model",
            message=f"unreadable model ref {model_ref!r}",
            model_ref=model_ref,
        )
    return model_id, int(version)


def _face_allowance(span: Span) -> Mm:
    """How much of this bay's centre-to-centre width is post rather than opening.

    Read back off the span rather than re-measured from the posts: the generator
    already resolved which products bound this bay and wrote the answer down, and
    a second measurement here could disagree with the panel the run stored.

    `None` is a run generated before the opening was recorded. Those bays were
    genuinely fitted at centre-to-centre, so their allowance is zero — the
    preview reproduces the fence that exists, not the one today's generator would
    build.
    """
    if span.clear_width_mm is None:
        return 0
    return span.width_mm - span.clear_width_mm


def _slope_for(span: Span, width: Mm) -> Mm:
    """The bay's true length along the grade, at the width being asked about.

    At the bay's own width this is the number the generator stored. It is
    recomputed rather than copied because a what-if may change the width, and a
    slope length carried over from a different width describes neither bay — so
    it comes from the span's own rise through the one chord->slope rounding
    point (`core.units.slope_len_mm`), the function the generator used.
    """
    if span.vertical != "raked":
        return width
    return slope_len_mm(width, span.bottom_z_end_mm - span.bottom_z_start_mm)


def _bay_options(result: GenerationResult, span: Span) -> dict[str, str | int]:
    """Which option values this bay was built with.

    Read from the decision graph, because the graph is where the run says it:
    `select_model` records the effective choice's options, and the bay's
    `resolve_panel` node takes that node as an input — so the attribution is the
    run's own, per bay. The run's `model_snapshot` cannot answer it alone: two
    stretches of one fence may be built to the SAME model version with different
    options, and then `(model_id, version)` names two entries with no way to tell
    which bay belongs to which.

    The snapshot is still the fallback, for a run stored before those nodes
    existed and for the case it does answer unambiguously — one entry for this
    model, one set of options.
    """
    graph = result.graph
    for node in graph.nodes_for_element(span.id):
        if node.action != "resolve_panel":
            continue
        for edge in graph.in_edges(node.id):
            source = graph.node(edge.from_id)
            if source.action == "select_model":
                return dict(source.payload.get("options") or {})
    uses = [u for u in result.run.model_snapshot
            if f"{u.model_id}@v{u.version}" == span.panel.model_ref]
    return dict(uses[0].options) if len(uses) == 1 else {}


def _priced_parts(priced) -> list[PreviewPart]:
    """Rows that SUM to the panel total.

    `fulfill()` emits one BOM line per SKU, so a frame with named top and bottom
    rail slots produces two requirements answered by one line. Handing that line
    to both rows made the visible column add up to twice the total shown beneath
    it — on the one surface built so a person can compare what two models cost,
    and against this phase's own stated property that the parts and the BOM agree
    in both directions.

    The line is apportioned across its requirements by engineering quantity, with
    the remainder on the first row so the rows still total exactly (integer
    cents, one rounding, no drift). `purchase_qty` and `unit_price_cents` stay on
    the FIRST row only: half a bar bought is not a thing, and repeating the whole
    count on every row is the same double-count in another column.
    """
    lines = {line.sku: line for line in priced.bom.lines}
    per_sku: dict[str, list] = {}
    for line in priced.requirements:
        per_sku.setdefault(line.sku, []).append(line)

    out: list[PreviewPart] = []
    for line in priced.requirements:
        siblings = per_sku[line.sku]
        bom_line = lines.get(line.sku)
        first = siblings[0] is line
        share = _apportion(bom_line.total_cents if bom_line else 0,
                           [s.engineering_qty for s in siblings])
        out.append(PreviewPart(
            slot_key=line.slot_key, role=line.role, qty=line.engineering_qty,
            length_mm=line.cut_length_mm, unit=line.unit,
            eligible_skus=[m.sku for m in line.eligibility.members],
            sku=line.sku,
            shares_sku_with=[s.slot_key for s in siblings if s is not line],
            unit_price_cents=(bom_line.unit_price_cents if bom_line and first else 0),
            purchase_qty=(bom_line.purchase_qty if bom_line and first else 0),
            total_cents=share[siblings.index(line)],
        ))
    return out


def _apportion(total: Cents, weights: list[int]) -> list[Cents]:
    """Split an integer total by weight, remainder to the first — so the parts
    sum to the whole exactly, for every input including a zero total."""
    if not weights or sum(weights) <= 0:
        return [total if i == 0 else 0 for i in range(len(weights))]
    denominator = sum(weights)
    shares = [(total * w) // denominator for w in weights]
    shares[0] += total - sum(shares)
    return shares


def _part(line, bom_line) -> PreviewPart:
    return PreviewPart(
        slot_key=line.slot_key, role=line.role, qty=line.engineering_qty,
        length_mm=line.cut_length_mm, unit=line.unit,
        eligible_skus=[m.sku for m in line.eligibility.members],
        sku=line.sku,
        unit_price_cents=bom_line.unit_price_cents if bom_line else 0,
        purchase_qty=bom_line.purchase_qty if bom_line else 0,
        total_cents=bom_line.total_cents if bom_line else 0,
    )
