"""Resolving a PanelSpec against one span (fence-model spec §resolve_panel).

Pure and deterministic, and it takes NO knowledge access: every param it needs
was resolved during generation and arrives on the context, exactly as
Span.rail_count does today.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.errors import RequestRefused
from fenceai.core.units import Mm
from fenceai.fencemodel.bases import FIXING_BASES, PanelCounts
from fenceai.fencemodel.lengths import LENGTH_RULES
from fenceai.fencemodel.fit import FitResult, fit_pattern
from fenceai.fencemodel.model import (
    Distributed, Eligibility, FenceModel, Fraction, FromBottom, FromTop,
    HeightSupport, Member, PanelSpec, PartRequirement, spec_requirements,
)
from fenceai.knowledge.ast import MissingField, evaluate_expr
from fenceai.parts.model import PATH_SEP, contained_path, walk_contained_qty


class PanelContext(BaseModel):
    """Everything a panel needs to know about the bay it is being laid into."""

    centre_width_mm: Mm
    clear_width_mm: Mm
    height_mm: Mm
    vertical: str = "level"
    length_basis: str = "width"      # "width" | "slope" — from the span
    slope_len_mm: Mm | None = None
    params: dict[str, int] = {}      # knowledge-resolved: rails_per_span, ...
    options: dict[str, str | int] = {}
    # A product the CALLER named for a slot — the material drawer's "build this
    # panel in cedar instead". It narrows that slot's eligibility exactly as an
    # option axis does and never bypasses it (`_pinned_sku`). Empty in every
    # generated run: a stored fence is built to its model and its overrides, not
    # to whatever a preview was last asked to imagine.
    slot_skus: dict[str, str] = {}
    # What KIND of site this fence is being built on — `SiteConditions.facts()`,
    # bound here for the same reason it is bound into every knowledge evaluation
    # context: site conditions exist precisely so that a fence can be conditioned
    # on the site, and a variant asking `site.hvhz` on a context that never
    # carried it came back "not applicable" and fell through to the DEFAULT spec
    # with nothing said. That is the worst of the three available behaviours —
    # worse than refusing the condition at authoring, because the model looks
    # authored and the fence is built to the wrong panel.
    #
    # A dict of facts and not a `SiteConditions`: this is the evaluation
    # namespace, and an UNSET dimension has to be ABSENT rather than None or the
    # `MissingField` hook that makes a condition not-applicable stops working.
    # `.facts()` is the one place that omission is decided.
    #
    # Empty is "nobody said", which is every preview with no project behind it
    # and every run generated before this existed — so a model with no site
    # condition resolves exactly as it did, and the compatibility gate does not
    # move.
    site: dict[str, str | int | bool] = {}

    def condition_ctx(self) -> dict:
        return {
            "panel": {
                "width_mm": self.centre_width_mm, "height_mm": self.height_mm,
                "vertical": self.vertical,
            },
            "site": self.site,
        }


def clear_opening_mm(centre_width_mm: Mm, face_start_mm: Mm, face_end_mm: Mm) -> Mm:
    """The opening between two post FACES, from their centre-to-centre distance.

    Half of each post stands inside the bay, so a bay loses one whole face across
    its two ends whenever both posts are the same product.

    THE rounding point for the opening (ADR-0002): the two halves are summed and
    divided ONCE, so a pair of odd faces cannot lose a millimetre twice — 75 and
    75 give 75, not 37 + 37.

    A post product declaring no `face_width_mm` contributes 0 rather than a
    nominal. The opening is then the centre-to-centre width, which is exactly
    what this system computed for every bay before this function existed: a
    guessed face would be a number that reads as measured.
    """
    return centre_width_mm - (face_start_mm + face_end_mm) // 2


class ResolvedSlot(BaseModel):
    slot_key: str
    role: str
    qty: int
    length_mm: Mm | None = None
    length_basis: str | None = None
    # This slot declares a length rule and the rule produced no length in THIS
    # bay. Recorded rather than left as a bare `length_mm is None`, which a
    # fixing and a cap share and mean nothing by: a divisible product asked for
    # with no cut length plans no bars, so the panel would price that member at
    # zero and the parts ledger would read the gap as demand covered from stock —
    # a panel that silently costs nothing rather than one that visibly costs the
    # wrong amount. `validate_model` closes that at authoring for the rules it
    # can; `between_frame` depends on the bay, so the generator warns instead.
    length_unresolved: bool = False
    # Where this member starts along its OWN axis, in panel coordinates — set
    # only by the one rule that fixes it (`between_frame`), None everywhere else,
    # where a member spans the whole opening and 0 is the answer. It travels with
    # the length because they are one calculation: the elevation draws the
    # rectangle the cut list buys, or the picture starts lying about the panel it
    # is derived from.
    span_start_mm: Mm | None = None
    sku: str = ""                    # resolved by fulfillment, never here
    eligibility: Eligibility = Eligibility()
    fit: FitResult | None = None
    # --- geometry PARAMETERS, never rectangles -------------------------------
    # The elevation is a pure function of these (foundation §15: read models are
    # derived, never stored). Storing a list of rectangles would freeze one
    # drawing into the run and make the panel's picture a thing that could
    # disagree with the panel's numbers.
    # frame | infill | fixing. On the wire a vertical FRAME slot and a vertical
    # INFILL slot are the same shape, so a client had to guess which one a
    # `gaps_mm` list belonged to — the elevation renderer confirmed its gap
    # dimension geometrically rather than by indexing, which is guesswork
    # dressed as arithmetic. Said outright instead.
    slot_kind: str = ""
    orientation: str = ""            # horizontal | vertical, in the panel's frame
    positions_mm: list[Mm] = []      # frame slots: where along the cross axis
    member_width_mm: Mm | None = None   # infill: the member's own width
    thickness_mm: Mm | None = None   # face height in elevation; None = undeclared
    face_offset_mm: int = 0          # + front / - back, for shadowbox
    pattern_index: int = 0           # which member of the repeating cycle
    # every member of the cycle, in order. A slot knows its own width, but a
    # position depends on everything BEFORE it — a two-member pattern's second
    # member sits where it does because of the first one's width and gap — so the
    # whole cycle has to travel with each slot or the walk cannot be exact.
    cycle_widths_mm: list[Mm] = []
    cycle_gaps_mm: list[Mm] = []     # the AUTHORED gaps; the fitted ones are on `fit`
    # fixing slots: which basis put this count where it is, and how many
    # fasteners each occurrence of that basis takes. Geometry PARAMETERS exactly
    # like `orientation` above — the elevation derives the fastener PLACES from
    # them, and a read model obliged to guess a basis from a count would put
    # screws where the fence has none.
    #
    # `qty_per_basis` is here because `qty` alone cannot be divided back into
    # "how many places" and "how many at each": it is the product, and a read
    # model that apportioned `qty` across whatever places it happened to find
    # would report a per-place count nothing decided — plausible, and invented.
    # It is the RESOLVED figure (a `qty_param` may have won it), because that is
    # the one this bay was built to.
    #
    # "" / 0 is a run stored before these existed, and draws nothing rather than
    # a guess.
    basis: str = ""
    qty_per_basis: int = 0
    # --- the joint, carried for the same reason the geometry above is --------
    # A section through a joint is drawn from numbers that live on the SPEC
    # (`FrameSlot.channel_depth_mm`, `Member.base_engagement_mm`), and the read
    # model that draws it is handed a `ResolvedPanel`. They travel here rather
    # than being passed beside the panel, because a read model taking both a
    # panel and the spec it came from has two sources that can disagree — and
    # only one of the two is what a stored run keeps.
    #
    # Carrying them costs the read model nothing it could get wrong:
    # `_between_frame_extent` has ALREADY spent these numbers on `span_start_mm`
    # and `length_mm`, so the drawing reports what resolution decided and
    # recomputes no length from them (foundation §15).
    joint: str = "butt"              # this slot's own JointKind
    # WHICH rule produced `length_mm`, recorded rather than inferred from the
    # number. Continuity across an intermediate post combines per-bay lengths,
    # and how they combine depends on what was measured (`CONTINUITY_JOINS`); a
    # deriver that guessed the rule back from "length == width" would be reading
    # a coincidence. "" is a run stored before this existed, and derives nothing.
    length_rule: str = ""
    # The AUTHORED override on continuity, carried from the spec so the derived
    # answer and the authored one can be compared in ONE place (`strategy/
    # continuity.py`) and their disagreement reported. Never the answer itself.
    continuity: str = "derived"
    # unstated | lands | through — the authored CAPABILITY (see `PostJoint`).
    # Only frame slots have one; an infill member's value is always "unstated"
    # because continuity is refused on infill at authoring.
    post_joint: str = "unstated"
    channel_depth_mm: Mm = 0         # frame slots: how deep this member receives
    insertion_margin_mm: Mm = 0      # ... and the clearance left at its bottom
    base_ref: str | None = None      # infill: the frame slot it starts at
    top_ref: str | None = None       # ... and the one it stops at
    base_engagement_mm: Mm = 0       # ... and how far it seats into each of them
    top_engagement_mm: Mm = 0
    # which option answer narrowed this slot's eligibility, if one did. Recorded
    # rather than re-derived: the generator writes the `select_product` node from
    # it, and a second pass matching skus back to axes would be a second, quietly
    # divergent implementation of the narrowing rule.
    option_axis: str | None = None
    option_value: str | None = None
    # --- containment ---------------------------------------------------------
    # The slot this piece ships INSIDE, as a path key; "" for a piece bought on
    # its own, which is every slot resolved before containment existed.
    #
    # A contained slot is a MEMBER of the panel and not a PURCHASE: it is
    # addressable (`slot_key` is its path), countable (`qty`), placeable by an
    # assembly step and reported `unplaced` if none names it — which is exactly
    # what obligation 9 asks of "parts contained inside other parts". It carries
    # no eligibility, because nothing chooses it: the container was chosen, and
    # the piece came in the box. `demand.derive` therefore emits no line for it,
    # and the identity still closes — what supplies this member is the BOM line
    # that bought its container.
    contained_in: str = ""
    # The two ends of ONE credit, recorded on both slots it relates.
    #
    # On the CONTAINED slot: `credits_slot_key` is the panel slot this piece
    # supplies and `credited_qty` is how many of its own `qty` were actually
    # applied — capped by what that slot wanted, so a kit shipping four hinges
    # into a panel that wants two records 2, not 4. The remainder credits nothing
    # and is reported (`contained_credit_surplus`), because a saving nobody asked
    # for is the failure this feature has to refuse.
    #
    # On the DEMANDING slot: `credited_qty` is how many of its requirement
    # arrived inside a container and `credited_by` names the path keys that
    # brought them — a LIST, because two different containers in one panel may
    # each contribute, and a single field would silently keep whichever was
    # applied last. `qty` is what is LEFT to buy. Both are here so that the
    # smaller purchase is a fact with a source rather than a quantity that
    # quietly shrank — a reduced count nobody can trace back is the thing these
    # fields exist instead of.
    #
    # `qty + credited_qty` is the original requirement; `credited_qty` is NOT a
    # member count on this slot, because those members are the contained ones and
    # counting them at both ends would place every credited hinge twice.
    credits_slot_key: str = ""
    credited_qty: int = 0
    credited_by: list[str] = []
    # and which product a caller PINNED this slot to, if one did. Recorded for
    # exactly the reason the axis above is: the narrowing rule has one
    # implementation, and a reader that matched the resolved sku back to the
    # request to decide whether it was asked for or merely chosen would be a
    # second one — it cannot tell "cedar was requested" from "cedar won anyway".
    pinned_sku: str | None = None


class CreditNote(BaseModel):
    """A credit that did not land cleanly on THIS bay.

    Carried out of resolution rather than warned about here, because
    `resolve_panel` is pure over `(spec, ctx)` and a warning needs the span, the
    run and a decision node — all of which are the generator's. The same shape
    `length_unresolved` already uses: the resolver records the fact, the
    generator aggregates it into one sentence per model and slot instead of one
    per bay of a sixty-bay fence.

    Both kinds exist so that over-crediting cannot be silent:

    * `unmatched` — this bay's panel has no such slot (a variant that does not
      declare it). Nothing is credited. `validate_model` has already refused a
      target no spec declares at all, so what reaches here is genuinely per-bay.
    * `surplus` — the container ships more of the piece than the panel wanted.
      The credit is capped at what was wanted and `qty` is what was left over,
      which buys nothing and saves nothing.
    """

    kind: Literal["unmatched", "surplus"]
    contained_key: str
    slot_key: str
    qty: int = 0


class ResolvedPanel(BaseModel):
    model_ref: str = ""
    variant_index: int | None = None
    slots: list[ResolvedSlot] = []
    # Empty on every panel that credits nothing, which is every panel resolved
    # before this existed.
    credit_notes: list[CreditNote] = []


class VariantChoice(BaseModel):
    """Which variant a bay is built to, and what was tried on the way there.

    `failed` and `not_reached` are separate because they are different facts and
    the decision node says both: a condition that was evaluated and not satisfied
    lost the contest, while a variant AFTER the winner was never asked at all
    (first satisfied condition wins). Recording the second group as failures
    would put a claim in the graph that nothing ever checked.
    """

    spec: PanelSpec
    index: int | None = None
    failed: list[int] = []        # evaluated: False, or MissingField
    not_reached: list[int] = []   # authored after the winner, never evaluated


def choose_variant(model: FenceModel, ctx: PanelContext) -> VariantChoice:
    """Which variant this BAY is built to. See `choose_variant_by` for the rule."""
    return choose_variant_by(model, ctx.condition_ctx())


def choose_variant_by(model: FenceModel, cond_ctx: dict) -> VariantChoice:
    """Authored order, first satisfied condition wins — deliberately not
    'specificity', which is undefined for a bare Expr and would have two
    implementers counting different things.

    This evaluation happens OUTSIDE the knowledge evaluator: a variant is
    product structure, not a defeasible rule, so it produces no firing and no
    `defeated` edge. Its own decision node is the whole trace (fence-model spec
    §"The shape of the thing"), which is why the losers are reported here rather
    than left to be reconstructed by a second evaluation somewhere else.

    It takes the condition CONTEXT rather than a `PanelContext` because a post is
    resolved at its own station, where the bay's width does not exist yet — and a
    caller obliged to invent one would be inventing the answer. A condition
    naming a fact the context does not carry is "not applicable" (below), and
    `validate_model` refuses the one combination where that would silently give a
    post the wrong panel's rails.
    """
    failed: list[int] = []
    for index, variant in enumerate(model.variants):
        try:
            satisfied = evaluate_expr(variant.condition, cond_ctx)
        except MissingField:
            # a condition naming a field this context never supplies is "not
            # applicable", exactly as it is in the knowledge evaluator
            satisfied = False
        if satisfied:
            return VariantChoice(
                spec=variant.spec, index=index, failed=failed,
                not_reached=list(range(index + 1, len(model.variants))),
            )
        failed.append(index)
    return VariantChoice(spec=model.default_spec, index=None, failed=failed)


def select_variant(model: FenceModel, ctx: PanelContext) -> tuple[PanelSpec, int | None]:
    """The two-value view of `choose_variant`, for callers with no graph to
    write to (the panel preview)."""
    choice = choose_variant(model, ctx)
    return choice.spec, choice.index


def height_supported(support: HeightSupport, height_mm: Mm) -> bool:
    """Can this model be built at this panel height?

    Pure and per-BAY, because a height is a property of a bay; the aggregation
    that turns several unsupported bays into ONE warning per section belongs to
    the caller that knows what a section is (fence-model spec §warnings).
    """
    if support.kind == "discrete":
        return height_mm in support.heights_mm
    if not support.min_mm <= height_mm <= support.max_mm:
        return False
    # step 0 (or 1) states no ladder — every millimetre inside the band is a
    # height you can order, which is what the permissive default means
    if support.step_mm <= 1:
        return True
    return (height_mm - support.min_mm) % support.step_mm == 0


def _between_frame_extent(
    member: Member, frame: dict[str, "ResolvedSlot"]
) -> tuple[Mm, Mm] | None:
    """(where this member starts in panel coordinates, how long it is cut).

    Both from one calculation, because they are one fact and two of them would
    drift: the elevation draws the rectangle the cut list buys, or the picture
    starts lying about the panel it is derived from — which is the property
    `report/elevation.py` opens by claiming.

    A member cut to fit between two frame members, plus what disappears into
    them:

        (top_position - base_position)
        - (top_thickness//2 + base_thickness//2)   # centreline to facing faces
        + base_engagement + top_engagement          # what the joint swallows

    The positions are READ off the frame slots this same panel already resolved,
    never re-derived: `placement_positions` is THE rounding point for placement
    (ADR-0002), and a second call here — over a span this function would have to
    reconstruct from the orientation — is exactly how two implementations end up
    a millimetre apart and move a rail out from under its own slats.

    A placement gives a member's CENTRELINE, so half of each frame member's face
    height is what stands between the two centrelines and the opening. An
    undeclared thickness contributes 0 rather than a nominal: the elevation
    already reports such a member as `declared=False`, and inventing a face
    height here would put a measured-looking number on a cut list.

    A frame slot with several positions is a rail SET (a `Distributed` ladder),
    and "between the rails" means between the outermost two: the bottom rail is
    the lowest position and the top rail the highest, which is what an author
    naming one slot at both ends is asking for. Picking a middle rail would cut
    every slat short by a bay's worth of ladder.
    """
    base_slot = frame.get(member.base_ref or "")
    top_slot = frame.get(member.top_ref or "")
    if base_slot is None or top_slot is None:
        return None
    if not base_slot.positions_mm or not top_slot.positions_mm:
        # A `count_param` resolved the referenced set to nothing, so in THIS bay
        # there is no member to seat into. Substituting the panel height would
        # hand the cut list a length measured between things that are not there.
        return None
    # the member's own ends: the facing face of the base member, less however far
    # it reaches past that face into the housing
    start = (min(base_slot.positions_mm) + (base_slot.thickness_mm or 0) // 2
             - member.base_engagement_mm)
    end = (max(top_slot.positions_mm) - (top_slot.thickness_mm or 0) // 2
           + member.top_engagement_mm)
    length = end - start
    if length <= 0:
        # NOT clamped, and not returned. Two ways to arrive here and neither is
        # decidable when the model is authored: refs the wrong way round (the
        # editor offers both selects and which member is higher depends on the
        # BAY's height), and a knowledge param collapsing a `Distributed` set to
        # one position, where both ends become the same member and the face
        # correction eats what is left. A negative number is not a shorter piece
        # — `plan_cuts` packs it into a bar and certifies the plan optimal — so
        # this bay has no resolvable length, and the caller says so.
        return None
    return (start, length)


def _length_for(req: PartRequirement, ctx: PanelContext) -> Mm | None:
    """Every rule that can be answered from the BAY alone.

    The rules themselves live in `fencemodel/lengths.py` as a registry, so a new
    one is a registration rather than a branch here plus a `Literal` edit
    (`core/registry.py`). `None` — from an unset rule, or from `between_frame`,
    which measures against the panel's own frame — means *not answerable from the
    bay*, and `resolve_panel` answers `between_frame` separately with the frame
    it just placed passed IN, never reached for, so resolution stays a pure
    function of its arguments.
    """
    if req.length_rule is None:
        return None
    return LENGTH_RULES.get(req.length_rule)(req, ctx)


def _qty(count: int, param: str | None, params: dict[str, int]) -> int:
    """A model's contributed default, or the knowledge param that beat it.

    Takes the params MAPPING rather than the whole context because a post is
    resolved before any bay exists, and `rail_positions_mm` needs this same
    arithmetic there — a second `params.get(...)` written out at that call site
    would be a second place for the count to come from.
    """
    return params.get(param, count) if param else count


def rail_positions_mm(spec: PanelSpec, height_mm: Mm, params: dict[str, int]) -> list[Mm]:
    """Where this panel's HORIZONTAL frame members sit, in panel coordinates.

    Defined once, here: the placement positions of the panel's horizontal frame
    slots (y = 0 at the bottom of the opening), sorted ascending, with a
    `Distributed` slot contributing every one of its positions. It is
    `placement_positions`' answer and never a second derivation of it.

    This is what a routed post's predicate is matched against, and it is settled
    by the bay's HEIGHT alone — which is what keeps the resolution order a DAG:

        height -> rail positions -> post -> clear width -> infill fit
    """
    out: list[Mm] = []
    for slot in spec.frame:
        if slot.orientation != "horizontal":
            continue
        count = (_qty(slot.placement.count, slot.placement.count_param, params)
                 if isinstance(slot.placement, Distributed) else 1)
        out += placement_positions(slot.placement, count, height_mm)
    return sorted(out)


def placement_positions(placement, count: int, span_mm: Mm) -> list[Mm]:
    """Where a frame slot's members sit along the axis it crosses.

    `span_mm` is the panel height for a horizontal member and the clear width for
    a vertical one. THE one rounding point for placement (ADR-0002): integer
    division here, and nothing upstream or downstream rounds again — two
    implementations differing by a millimetre would move a rail, and the fixing
    count that depends on crossings with it.

    `distributed` spreads INCLUSIVE of both ends, which is what a fence frame is:
    two rails means a top rail and a bottom rail, not two rails floating in the
    middle. A single distributed member centres, because there is no pair of ends
    for it to be one of.
    """
    if isinstance(placement, FromBottom):
        return [placement.offset_mm]
    if isinstance(placement, FromTop):
        return [span_mm - placement.offset_mm]
    if isinstance(placement, Fraction):
        return [(span_mm * placement.permille) // 1000]
    low = placement.bottom_inset_mm
    high = span_mm - placement.top_inset_mm
    if count <= 0:
        return []
    if count == 1:
        return [(low + high) // 2]
    return [low + ((high - low) * i) // (count - 1) for i in range(count)]


def _chosen_option(
    req: PartRequirement, ctx: PanelContext
) -> tuple[Eligibility, str | None, str | None]:
    """(eligibility for this slot, the axis that narrowed it, the value it took).

    The axis comes back rather than being read off the requirement by the caller
    because "bound to an axis" and "narrowed by one" are different states, and a
    slot bound to an unanswered axis must not read as governed by it.

    An enum axis NARROWS eligibility; it never bypasses it. `sku_by_option`
    names a member of the slot's OWN set — a value naming a non-member is a
    load-time model error (`validate_model`), so by the time resolution runs the
    named sku is guaranteed to be one of the candidates and narrowing can only
    ever remove alternatives. Everything the slot said about that member — its
    priority, its `suggest_only` approval — is carried through untouched, so a
    colour choice cannot promote a product past an approval it still needs.

    Three ways to narrow nothing, all of them ordinary: the slot binds no axis,
    the axis was not answered, or the answer names no sku for THIS slot (one
    axis may govern the rails and say nothing about the screws).
    """
    unnarrowed = (req.eligibility, None, None)
    if req.option_axis is None or req.option_axis not in ctx.options:
        return unnarrowed
    # options are `str | int` (a numeric axis answers with a number) while
    # sku_by_option is keyed by the axis value's key, which is a string
    value = str(ctx.options[req.option_axis])
    sku = req.sku_by_option.get(value)
    if sku is None:
        return unnarrowed
    members = [m for m in req.eligibility.members if m.sku == sku]
    if not members:
        # unreachable through a validated model; a resolver that silently
        # emptied the slot here would turn an authoring error into a panel with
        # a part nothing can supply
        return unnarrowed
    return (req.eligibility.model_copy(update={"members": members}),
            req.option_axis, value)


def _pinned_sku(
    slot_key: str, eligibility: Eligibility, ctx: PanelContext
) -> tuple[Eligibility, str | None]:
    """The caller named a product for this slot: narrow to it, or refuse.

    The same discipline as `_chosen_option`, for the same reason and applied
    AFTER it — an answer narrows a slot's eligibility, it never bypasses it. The
    surviving member keeps its own `priority` and its own `approval`, so picking
    a colour cannot promote a product past an approval it still needs, and a pin
    naming a product the axis already ruled out is out of the running because
    the axis put it there.

    A sku that is not a member of that eligibility is REFUSED, not dropped:
    ignoring it would price a panel nobody asked for and present the number as
    the answer to the question that was asked.
    """
    sku = ctx.slot_skus.get(slot_key)
    if sku is None:
        return eligibility, None
    members = [m for m in eligibility.members if m.sku == sku]
    if not members:
        raise RequestRefused(
            code="sku_not_eligible",
            message=f"slot {slot_key} cannot be supplied by {sku}",
            slot_key=slot_key, sku=sku,
        )
    return eligibility.model_copy(update={"members": members}), sku


def _refuse_unknown_slots(slots: list[ResolvedSlot], ctx: PanelContext) -> None:
    """A pin on a slot this panel does not have is refused for the same reason a
    pin on an ineligible product is: it is a question about a different panel,
    and answering it with this one's price would be answering something else.

    Checked against the slots RESOLVED rather than against the spec, because a
    slot the fit placed none of (an infill member with no room, a fixing basis
    that came out zero) is a slot this bay genuinely does not have.
    """
    resolved = {slot.slot_key for slot in slots}
    inside = {slot.slot_key for slot in slots if slot.slot_kind == "contained"}
    for slot_key, sku in ctx.slot_skus.items():
        if slot_key not in resolved:
            raise RequestRefused(
                code="sku_not_eligible",
                message=f"this panel has no slot called {slot_key}",
                slot_key=slot_key, sku=sku,
            )
        if slot_key in inside:
            # A contained piece is not chosen — it arrives inside whatever
            # supplies its container — so there is no eligibility for a pin to
            # narrow and nothing here would ever read the answer. Refused rather
            # than accepted and ignored, for the reason the refusals above are: a
            # pin that quietly does nothing prices a panel nobody asked for and
            # presents the number as the answer to the question that was asked.
            # Its OWN code, not `sku_not_eligible`. That one's sentence ends
            # "choose one of the products offered for that part", and no product
            # is ever offered for a contained piece — advice impossible to
            # follow, on a refusal the user causes by clicking. A new code is a
            # registry addition, not an amendment (CLAUDE.md), so there is no
            # cost to saying the true thing.
            raise RequestRefused(
                code="slot_not_purchasable",
                message=f"slot {slot_key} is a part contained inside another "
                        "part, so no product is chosen for it",
                slot_key=slot_key, sku=sku,
            )


def resolve_panel(
    spec: PanelSpec,
    ctx: PanelContext,
    model_ref: str = "",
    variant_index: int | None = None,
) -> ResolvedPanel:
    """`variant_index` is recorded, never chosen here: which spec applies is
    `choose_variant`'s answer, and a resolver that re-derived it from `spec`
    would be a second implementation of the precedence rule."""
    slots: list[ResolvedSlot] = []
    # The frame loop runs first and the infill loop reads its answer, because a
    # `between_frame` member is measured against frame members that are already
    # placed. Keyed by slot key, which is unique within a spec (`validate_model`).
    frame: dict[str, ResolvedSlot] = {}

    for frame_slot in spec.frame:
        req = frame_slot.requirement
        count = (_qty(frame_slot.placement.count, frame_slot.placement.count_param, ctx.params)
                 if isinstance(frame_slot.placement, Distributed) else 1)
        eligibility, option_axis, option_value = _chosen_option(req, ctx)
        eligibility, pinned = _pinned_sku(frame_slot.key, eligibility, ctx)
        # a horizontal member is placed up the HEIGHT; a vertical one across the
        # clear width
        span = (ctx.height_mm if frame_slot.orientation == "horizontal"
                else ctx.clear_width_mm)
        resolved = ResolvedSlot(
            slot_key=frame_slot.key, role=req.role, qty=count * req.qty,
            slot_kind="frame",
            length_mm=_length_for(req, ctx), length_basis=ctx.length_basis,
            length_rule=req.length_rule or "", continuity=frame_slot.continuity,
            post_joint=frame_slot.post_joint,
            eligibility=eligibility,
            option_axis=option_axis, option_value=option_value, pinned_sku=pinned,
            orientation=frame_slot.orientation,
            thickness_mm=frame_slot.thickness_mm or None,
            joint=frame_slot.joint,
            channel_depth_mm=frame_slot.channel_depth_mm,
            insertion_margin_mm=frame_slot.insertion_margin_mm,
            positions_mm=placement_positions(frame_slot.placement, count, span),
        )
        slots.append(resolved)
        frame[frame_slot.key] = resolved

    if spec.infill and spec.infill.pattern:
        axis = (ctx.clear_width_mm if spec.infill.orientation == "vertical"
                else ctx.height_mm)
        fit = fit_pattern(
            axis,
            [m.width_mm for m in spec.infill.pattern],
            [m.gap_after_mm for m in spec.infill.pattern],
            justification=spec.infill.justification,
            excess=spec.infill.excess,
            edge_margin_mm=spec.infill.edge_margin_mm,
        )
        for offset, member in enumerate(spec.infill.pattern):
            # how many of THIS member of the repeating sequence were placed
            n = sum(1 for i in range(fit.count) if i % len(spec.infill.pattern) == offset)
            if not n:
                continue
            eligibility, option_axis, option_value = _chosen_option(
                member.requirement, ctx)
            eligibility, pinned = _pinned_sku(member.key, eligibility, ctx)
            rule = member.requirement.length_rule
            if rule == "between_frame":
                extent = _between_frame_extent(member, frame)
                span_start, length = extent if extent else (None, None)
            else:
                span_start, length = None, _length_for(member.requirement, ctx)
            slots.append(ResolvedSlot(
                slot_key=member.key, role=member.requirement.role,
                slot_kind="infill", qty=n * member.requirement.qty,
                length_mm=length, span_start_mm=span_start,
                length_unresolved=rule is not None and length is None,
                # `between_frame` measures a distance INSIDE the panel, between
                # two frame members that slope together, so the slope factor
                # never applied to it — and stamping "slope" beside a number
                # that ignores the slope says the opposite to every reader of
                # the structure sheet.
                length_basis="width" if rule == "between_frame" else ctx.length_basis,
                length_rule=rule or "", continuity=member.continuity,
                eligibility=eligibility, fit=fit,
                option_axis=option_axis, option_value=option_value, pinned_sku=pinned,
                orientation=spec.infill.orientation,
                member_width_mm=member.width_mm,
                cycle_widths_mm=[m.width_mm for m in spec.infill.pattern],
                cycle_gaps_mm=[m.gap_after_mm for m in spec.infill.pattern],
                thickness_mm=member.thickness_mm or None,
                face_offset_mm=member.face_offset_mm,
                joint=member.joint,
                base_ref=member.base_ref, top_ref=member.top_ref,
                base_engagement_mm=member.base_engagement_mm,
                top_engagement_mm=member.top_engagement_mm,
                pattern_index=offset,
            ))

    frame_count = sum(s.qty for s in slots if s.fit is None)
    # Two different counts, and conflating them over-orders. `member_count` is
    # PARTS: a member with `qty=2` is two physical pieces at one position (a
    # batten pair, a board front and back), and each of them takes its own screw
    # and makes its own crossing. `placed_count` is POSITIONS along the axis,
    # which is what the fit produced — and a gap is between two positions, not
    # between two pieces that share one. With `qty=2` the two differ by a factor.
    member_count = sum(s.qty for s in slots if s.fit is not None)
    placed_count = next((s.fit.count for s in slots if s.fit is not None), 0)
    for rule in spec.fixings:
        per = _qty(rule.qty_per_basis, rule.qty_param, ctx.params)
        basis = FIXING_BASES.get(rule.basis)(PanelCounts(
            member_count=member_count, placed_count=placed_count,
            frame_count=frame_count,
        ))
        if not basis:
            continue
        eligibility, option_axis, option_value = _chosen_option(rule.requirement, ctx)
        eligibility, pinned = _pinned_sku(rule.key, eligibility, ctx)
        slots.append(ResolvedSlot(
            slot_key=rule.key, role=rule.requirement.role, slot_kind="fixing",
            qty=per * basis, basis=rule.basis, qty_per_basis=per,
            eligibility=eligibility,
            option_axis=option_axis, option_value=option_value, pinned_sku=pinned,
        ))

    # Containment runs LAST, over the finished slot list: a contained piece's
    # count is a multiple of its container's, and a container's count is not
    # known until the fit and the fixing bases have run.
    #
    # CREDITS SETTLE FIRST, and that order is the correction of a real defect
    # rather than a preference. A credited slot may itself hold contents — a
    # hinge that ships a washer — and those contents are a multiple of how many
    # of that piece the panel actually buys. Expanding them before the credit
    # reduced the count expanded them from the number the panel WOULD have
    # bought: with a kit supplying 2 of 4 hinges, the panel listed 8 washers
    # under `hinges` plus 4 under `kit/hinge` — twelve washers for four hinges
    # that hold eight. Nothing downstream could have caught it, because a
    # contained member is not a purchase and never reaches the BOM.
    notes, credited = _plan_credits(slots, spec)
    slots += _contained_slots(slots, spec, credited)

    _refuse_unknown_slots(slots, ctx)
    return ResolvedPanel(model_ref=model_ref, variant_index=variant_index,
                         slots=slots, credit_notes=notes)


def _contained_slots(
    slots: list[ResolvedSlot], spec: PanelSpec, credited: dict[str, tuple[str, int]]
) -> list[ResolvedSlot]:
    """Every part inside another part, as a member of the panel in its own right.

    The path key is the identity, and it is built by `parts.model.contained_path`
    from the container's OWN slot key — which is already unique within a panel
    and already the handle `demand`, the structure sheet, the elevation and the
    canvas address a part by. So a contained piece needs no new kind of id and
    inherits every guarantee the slot key has: `validate_model` refuses a
    duplicate path exactly as it refuses a duplicate slot key, and refuses an
    authored key containing the separator so a path can never be forged.

    `qty` MULTIPLIES, through `walk_contained_qty` — the one place that
    arithmetic lives, shared with the credit that is sized from it.

    Runs AFTER `_plan_credits`, so `slot.qty` here is already what the panel
    BUYS for that slot. That is what a credited slot's own contents must be a
    multiple of: the hinges that arrive inside a kit bring their washers under
    the kit's path, and counting them again under the slot they credit is twelve
    washers for four hinges.
    """
    by_key = {slot.slot_key: slot for slot in slots}
    out: list[ResolvedSlot] = []
    for key, req in spec_requirements(spec):
        slot = by_key.get(key)
        if slot is None or slot.qty <= 0 or not req.contained:
            # A slot this bay placed none of — an infill member with no room, a
            # fixing basis that came out zero, a slot every piece of which came
            # in somebody else's box — contains nothing here either. Emitting its
            # contents anyway would put members in the panel that arrived in a
            # box nobody bought.
            continue
        out += _flatten(req.contained, key, slot.qty, credited)
    return out


def _flatten(
    contained, container_key: str, factor: int, credited: dict[str, tuple[str, int]]
) -> list[ResolvedSlot]:
    out: list[ResolvedSlot] = []
    for path, piece, qty in walk_contained_qty(contained, container_key, factor):
        target, applied = credited.get(path, ("", 0))
        out.append(ResolvedSlot(
            slot_key=path, role=piece.role, qty=qty, slot_kind="contained",
            # `contained_in` names the IMMEDIATE container, not the root: the
            # question a reader asks of a nested piece is which box it came out
            # of, and the root is one split away from the path either way.
            contained_in=path.rsplit(PATH_SEP, 1)[0],
            credits_slot_key=target, credited_qty=applied,
        ))
    return out


def _plan_credits(
    slots: list[ResolvedSlot], spec: PanelSpec
) -> tuple[list[CreditNote], dict[str, tuple[str, int]]]:
    """Spend what arrived in the box against what the panel would have bought.

    A credit is NOT a negative demand line and NOT a silently smaller number. It
    is a SUPPLY ROUTE recorded on both slots it relates: the contained piece says
    which slot it supplies, the demanding slot says how many of its requirement
    came that way and from where, and what remains on the demanding slot is what
    the panel still buys. A purchaser reads one honest positive line; a reader
    asking why it is smaller is answered by the slot itself and by the
    `credit_contained` decision node the generator writes from these numbers.

    Runs BEFORE the contained members are materialised, which is why the source
    quantity is computed from the spec (`walk_contained_qty`) rather than read
    off a slot: the slots do not exist yet, deliberately, because their counts
    depend on the answer this function produces.

    Over-crediting is refused four ways, because it is the only failure here that
    is invisible on the finished document — a saving is a line that is not there:

    1. `validate_model` has already refused a credit whose target no spec
       declares, whose target is a different ROLE, whose target is the container
       itself or another contained piece, and whose target is drawn at a position
       (a contained piece has an identity but no PLACE).
    2. It has also refused a chain — a credit whose container is itself credited
       — so every source's container has its final quantity here and one pass in
       spec order is exact rather than order-dependent.
    3. A target this BAY does not have credits nothing and is reported.
    4. What is applied is capped at what the target actually wanted, and the
       surplus is reported. A kit shipping four hinges into a two-hinge panel
       saves two hinges, never four.
    """
    by_key = {slot.slot_key: slot for slot in slots}
    notes: list[CreditNote] = []
    credited: dict[str, tuple[str, int]] = {}
    for key, req in spec_requirements(spec):
        container = by_key.get(key)
        if container is None or container.qty <= 0:
            continue          # a slot this bay placed none of brings no box
        available = {path: qty for path, _, qty
                     in walk_contained_qty(req.contained, key, container.qty)}
        for relative, target_key in sorted(req.credits.items()):
            path = contained_path(key, relative)
            have = available.get(path, 0)
            if have <= 0:
                continue
            target = by_key.get(target_key)
            if target is None:
                notes.append(CreditNote(kind="unmatched", contained_key=path,
                                        slot_key=target_key, qty=have))
                continue
            applied = min(have, target.qty)
            if applied > 0:
                target.qty -= applied
                target.credited_qty += applied
                target.credited_by.append(path)
                credited[path] = (target_key, applied)
            if have - applied > 0:
                notes.append(CreditNote(kind="surplus", contained_key=path,
                                        slot_key=target_key, qty=have - applied))
    return notes, credited
