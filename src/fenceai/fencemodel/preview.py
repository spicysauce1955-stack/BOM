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
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.core.units import Cents, Mm
from fenceai.fencemodel.model import FenceModel, validate_model
from fenceai.fencemodel.resolve import PanelContext, ResolvedPanel, resolve_panel, select_variant
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.report.elevation import PanelElevation, panel_elevation
from fenceai.strategy.model import Span, Strategy, StrategyWarning

PREVIEW_SPAN_ID = "span@preview:0-0"


class PreviewRequest(BaseModel):
    """The bay a preview is imagined into. Millimetres at rest, like everything
    else — the display unit is the client's business (`units.js`)."""

    height_mm: Mm = 1800
    width_mm: Mm = 2500                  # centre to centre, as a span is measured
    clear_width_mm: Mm | None = None     # None = the same, until face widths land
    vertical: str = "level"
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
    ctx = PanelContext(
        centre_width_mm=request.width_mm,
        clear_width_mm=clear,
        height_mm=request.height_mm,
        vertical=request.vertical,
        length_basis="width",
        params=request.params,
        options=dict(request.options),
        slot_skus=dict(request.slot_skus),
    )
    spec, variant_index = select_variant(model, ctx)
    panel = resolve_panel(spec, ctx, model_ref=model.ref)

    span = Span(
        id=PREVIEW_SPAN_ID, run_ref="preview",
        start_station_mm=0, end_station_mm=request.width_mm,
        width_mm=request.width_mm, slope_len_mm=request.width_mm,
        vertical=request.vertical,  # type: ignore[arg-type]
        height_mm=request.height_mm,
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
