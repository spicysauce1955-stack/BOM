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
from fenceai.fencemodel.match import (
    chosen_post_facts, match_eligibility, match_spec, panel_facts, post_panel_facts,
)
from fenceai.fencemodel.model import FenceModel, validate_model
from fenceai.parts.model import PartLibrary
from fenceai.parts.resolve import library_at, resolve_model_parts
from fenceai.fencemodel.resolve import (
    PanelContext, ResolvedPanel, clear_opening_mm, rail_positions_mm, resolve_panel,
    select_variant,
)
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.report.annexe import WarningPlacement, place_for_plan
from fenceai.report.assembly import (
    AssemblyPlan,
    assembly_plan,
    bay_parts_from_posts,
)
from fenceai.report.elevation import ElevationPost, PanelElevation, panel_elevation
from fenceai.strategy.model import (
    GenerationResult, PartUse, Span, Strategy, StrategyWarning,
)

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
    # How this panel goes together, when its model says. `None` is "this line
    # states no order", which the assembly film needs to tell from "it takes no
    # steps" so it knows whether to fall back to its role-based build order.
    assembly: AssemblyPlan | None = None
    # What the DOCUMENT warns, and where each of those warnings renders
    # (obligation 10, §3.3.5). A sibling of `assembly` rather than a field inside
    # it: only a fifth of a real guide's warnings are about a step, so a list
    # hanging off the plan would have nowhere to put the other four fifths.
    #
    # Beside `warnings` above, never merged into it. That list is `code + params`
    # this engine emitted and owes a sentence for in both bundles; this one is
    # somebody else's text carried verbatim and never translated. One list would
    # need a discriminator every reader had to get right — see `core/warnings.py`.
    #
    # The preview computes it because the preview is where an AUTHOR sees where
    # their warning will land — including the annexe, which is the whole reason
    # the frontend design asks for it here: a document-scoped warning previews
    # into the annexe rather than onto every line, so a curator can see that it
    # is not going to shout at a fitter fourteen times.
    quoted_warnings: WarningPlacement = WarningPlacement()
    total_cents: int = 0


def preview_panel(
    model: FenceModel,
    request: PreviewRequest,
    catalog: Catalog,
    preset: str = "least_cost",
    # `part_library`, not `parts`: this function already has a local `parts` — the
    # priced rows it returns — and one name for two things here would be silent
    # (the shadowed one is only read further down).
    part_library: PartLibrary | None = None,
    part_snapshot: list[PartUse] | None = None,
) -> PanelPreview:
    """`part_library` and `part_snapshot` are ARGUMENTS, for the same reason `catalog` and
    `preset` are: a bay of a stored run is previewed against the parts that run
    resolved, and a model-scoped preview against today's. This function stays pure
    of the store, and the route decides which question is being asked.

    `part_snapshot` pins those versions. `bay_preview_plan` already reloads the
    model document by the version the run STAMPED and never `latest_active`,
    because the drawer once marked one product chosen while the run had bought
    another; an unpinned `part_id` inside that pinned document is the same bug by a
    new door. Empty (or absent) falls back to `latest_active`, which is the only
    honest answer for a run generated before parts existed.
    """
    if part_library is not None:
        # Compiling the part references is strictly upstream of `match_spec` below
        # — the same position it holds in `generator.segment_model`, so a preview
        # and a run resolve the same document in the same order.
        part_library = library_at(part_library, part_snapshot or [])
        model, _ = resolve_model_parts(model, part_library)
    slope = request.slope_len_mm if request.slope_len_mm is not None else request.width_mm

    def _ctx(clear_width_mm: Mm) -> PanelContext:
        return PanelContext(
            centre_width_mm=request.width_mm,
            clear_width_mm=clear_width_mm,
            height_mm=request.height_mm,
            vertical=request.vertical,
            length_basis=request.length_basis,
            slope_len_mm=slope,
            params=request.params,
            options=dict(request.options),
            slot_skus=dict(request.slot_skus),
        )

    # Provisional: the clear opening is measured TO the post faces, and which
    # post stands there is not known until the spec is. That is the resolution
    # DAG, and a preview follows it rather than short-cutting it — a model-scoped
    # preview fitted at the centre-to-centre width was fitting the panel across
    # an opening that includes half a post at each end, which is the defect W1
    # closed for the fence and left open here.
    clear = request.clear_width_mm if request.clear_width_mm is not None else request.width_mm
    spec, variant_index = select_variant(model, _ctx(clear))
    post_note: StrategyWarning | None = None
    post_sku, post_face, post_panel = "", 0, {}
    if request.clear_width_mm is None and model.post is not None:
        face, post_sku, post_panel, post_note = _preview_post_face(
            model, spec, request, catalog)
        post_face = face
        clear = clear_opening_mm(request.width_mm, face, face)
        # a variant is chosen from height, width and vertical mode — none of
        # which the opening moved — so the spec above still stands
    ctx = _ctx(clear)
    # the same matcher generation runs, so a spec-declared slot previews
    # as the products it will actually be built from
    spec = match_spec(spec, catalog, panel_facts(ctx))
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
    # Computed once and spent twice, which is the point of hoisting it. The
    # drawing needs the posts as rectangles; the assembly sheet needs them as
    # PLACEABLES, so a step can say "set the posts plumb in concrete" and name
    # what it sets. Two derivations of "which posts flank this bay" is exactly
    # the drift a single call prevents.
    posts = _preview_posts(model, post_sku, post_face, clear,
                           request.height_mm, post_panel, catalog)
    return PanelPreview(
        model_ref=model.ref,
        variant_index=variant_index,
        height_mm=request.height_mm,
        width_mm=request.width_mm,
        clear_width_mm=clear,
        panel=panel,
        elevation=panel_elevation(drawn, clear, request.height_mm, posts=posts),
        parts=parts,
        unsupplied=[_part(line, None) for line in priced.unresolved],
        warnings=(priced.warnings + _credit_warnings(panel, model.ref)
                  + ([post_note] if post_note is not None else [])),
        # Already resolved above when a library was given, and `validate_model`
        # resolves again against the SAME (pinned) library — idempotent, and it
        # keeps "which document is validated" one function's business rather than
        # a contract between two.
        assembly=assembly_plan(model, panel, bay=bay_parts_from_posts(posts)),
        # The skus this PANEL buys, which is the vocabulary a product-scoped
        # warning is placed against here. `priced.requirements` are the lines
        # fulfillment resolved a moment ago, so the placement is over what this
        # panel is actually made of rather than over the whole catalog.
        quoted_warnings=place_for_plan(
            [model], skus=[line.sku for line in priced.requirements]),
        invalid=validate_model(model, catalog, part_library),
        total_cents=priced.bom.total_cents,
    )


# A cap's height is not in the catalog, so the drawing invents one and flags it —
# the same bargain `NOMINAL_THICKNESS_PERMILLE` strikes for a rail's face height.
NOMINAL_CAP_PERMILLE = 25


def _preview_posts(
    model: FenceModel, sku: str, face_mm: Mm, clear_mm: Mm, height_mm: Mm,
    panel: dict, catalog: Catalog,
) -> list[ElevationPost]:
    """The two posts this imagined bay stands between.

    Both are the SAME post, and that is what a model-scoped preview is: there is
    no run, so no station of one is an end or a corner, and `_preview_post_face`
    already chose the representative `line` post the run is mostly made of. They
    are reported at both ends anyway, because the thing an author is looking at
    is a bay, and a bay with a post at one end is not one.

    `x_mm` is in PANEL coordinates, so the start post's is negative: it occupies
    the millimetres before the opening begins.
    """
    if not sku or face_mm <= 0:
        return []      # no post matched: draw none rather than a nominal one
    cap_sku = _preview_cap_sku(model, panel, catalog, sku)
    cap_h = (height_mm * NOMINAL_CAP_PERMILLE) // 1000 if cap_sku else 0
    return [
        ElevationPost(
            side=side, kind="line", x_mm=x, w_mm=face_mm, h_mm=height_mm,
            sku=sku, declared=True,
            cap_sku=cap_sku, cap_h_mm=cap_h, cap_declared=False,
        )
        for side, x in (("start", -face_mm), ("end", clear_mm))
    ]


def _preview_cap_sku(
    model: FenceModel, panel: dict, catalog: Catalog, post_sku: str,
) -> str:
    """Which cap this post takes, matched the way generation matches it.

    A cap's predicate reads the POST it caps, which is only answerable because
    the post was chosen first — so this runs after, never beside.

    It is handed the PANEL facts as well as the post, exactly as
    `_model_post_skus` does. `_post_namespace_errors` explicitly lets a cap read
    `panel.height_mm` and its siblings, so matching over the post alone made a
    legal cap predicate match nothing HERE and match in the fence — a preview
    reporting a gap the fence does not have.
    """
    if model.post is None or model.post.cap is None:
        return ""
    product = catalog.products.get(post_sku)
    if product is None:
        return ""
    matched = match_eligibility(
        model.post.cap.eligibility, catalog,
        {**panel, **chosen_post_facts(product, panel["post"])},
    ).members
    return matched[0].sku if matched else ""


def _preview_post_face(
    model: FenceModel, spec, request: "PreviewRequest", catalog: Catalog,
) -> tuple[Mm, str, dict, StrategyWarning | None]:
    """How much of this imagined bay is post rather than opening, and which post.

    The model's own post, matched exactly as generation matches it — the same
    `post_panel_facts` over the same `rail_positions_mm`, so a routed line
    previews against the post it will actually be built with. The preview has no
    project and therefore no neighbours, so there is no intersection to take: one
    model claims both ends, which is what a model-scoped preview IS.

    That same missing project is why the post's KIND has to be named here rather
    than looked up: there is no run, so no station of one is an end or a corner.
    `"line"` is the deliberate choice, and it is a claim about what is being
    previewed — a REPRESENTATIVE bay of the line, and the posts a run is mostly
    made of are line posts. The alternatives are worse in both directions:
    passing no kind at all would make a position-aware predicate match NOTHING
    and every preview of such a model would warn that its own post is
    unsupplied, and picking `"end"` would preview the bay a run has exactly two
    of. The face this returns is the only thing the preview spends it on, and a
    line's routed variants differ in which faces are CUT rather than in how wide
    they are — so the opening drawn here is the opening at every station of the
    run, whatever position each post turns out to stand at.

    A post nothing covers contributes NO face rather than a nominal, and says so.
    Generation refuses that fence outright; a preview must not, because a draft
    being edited is half-written by definition — but a silent fall-back to the
    centre-to-centre width would be the preview lying about the bay.
    """
    facts = post_panel_facts(
        model_id=model.id, height_mm=request.height_mm, vertical=request.vertical,
        rail_positions_mm=rail_positions_mm(spec, request.height_mm, request.params),
        kind="line",
    )
    matched = match_eligibility(
        model.post.requirement.eligibility, catalog, facts,
    ).members
    if not matched:
        # Its OWN code. `no_item_covers_part_spec` is the CAP's, and its sentence
        # says the post is uncapped — so an author whose POST spec matches
        # nothing was told about a cap, and the natural repair is to delete the
        # wrong conjunct.
        return 0, "", facts, StrategyWarning(
            code="no_item_covers_post_spec", severity="warning",
            message=f"No item in the catalog covers {model.ref}'s post "
                    f"specification, so this bay is drawn at its centre-to-centre "
                    f"width rather than the opening between two posts.",
            params={"model": model.ref, "station_mm": 0,
                    "slot_key": model.post.key, "role": model.post.requirement.role},
        )
    product = catalog.products.get(matched[0].sku)
    face = (product.capabilities.face_width_mm or 0) if product else 0
    return face, matched[0].sku, facts, None


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
    """One row of the preview, from either kind of line.

    `line` is a `ResolvedSupplyLine` for a priced part and a plain `DemandLine`
    for an unsupplied one — which by definition never got a product, so it has
    no sku and no unit to report. Empty strings are the honest answer here rather
    than a placeholder: the caller renders `unsupplied` ABOVE the priced table
    precisely so a panel one part short cannot read as complete.
    """
    return PreviewPart(
        slot_key=line.slot_key, role=line.role, qty=line.engineering_qty,
        length_mm=line.cut_length_mm, unit=getattr(line, "unit", ""),
        eligible_skus=[m.sku for m in line.eligibility.members],
        sku=getattr(line, "sku", ""),
        unit_price_cents=bom_line.unit_price_cents if bom_line else 0,
        purchase_qty=bom_line.purchase_qty if bom_line else 0,
        total_cents=bom_line.total_cents if bom_line else 0,
    )


def _credit_warnings(panel: ResolvedPanel, model_ref: str) -> list[StrategyWarning]:
    """A credit that did not land, said in the ONE place an author can fix it.

    `ResolvedPanel.credit_notes` had exactly one reader — the generator — so an
    author who aimed a credit at a slot their model does not build, or shipped a
    kit with one hinge too many, saw nothing in the model editor and found out
    only after generating a real project. The preview is the surface this
    feature's mistakes are made on; it has to be the surface they show on.

    Same codes and same params as the generator's, deliberately: one sentence per
    fact, in both bundles, rather than a preview dialect of the same warning. The
    sentences carry `{n}` and no run — a bay is a bay whether it is previewed or
    built, and which bays are affected travels in `element_refs`, exactly as
    `no_eligible_item` already reports its own.
    """
    out: list[StrategyWarning] = []
    for note in panel.credit_notes:
        params = {"model_ref": model_ref, "contained": note.contained_key,
                  "slot": note.slot_key, "qty": note.qty, "n": 1}
        if note.kind == "unmatched":
            out.append(StrategyWarning(
                code="contained_credit_unmatched", severity="warning",
                message=f"{note.contained_key} credits slot {note.slot_key}, "
                        f"which model {model_ref} does not build in this bay: "
                        "nothing is credited there",
                params=params, element_refs=[PREVIEW_SPAN_ID],
            ))
        else:
            out.append(StrategyWarning(
                code="contained_credit_surplus", severity="warning",
                message=f"{note.contained_key} ships {note.qty} more than slot "
                        f"{note.slot_key} needs in this bay: the surplus credits "
                        "nothing",
                params=params, element_refs=[PREVIEW_SPAN_ID],
            ))
    return out
