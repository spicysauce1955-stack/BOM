"""Fence models: a named product line and the structure of its normal panel.

Immutable versions, like knowledge objects (ADR-0006): a run stamps the model
versions it resolved, so editing a model cannot change what an old run meant.

The model owns product STRUCTURE. Numbers that can conflict — max span, rail
count, embedment — stay knowledge. `LayoutPolicy` is how the two meet: the model
states them as knowledge-shaped contributions scoped to `series=<model_id>` and
the existing evaluator resolves them with everything else, at each
contribution's OWN authority. The model gets no private channel into the
generator, and `validate_model` still refuses a contribution to a param that
generation resolves before any model is chosen (`SERIES_SCOPED_PARAMS`), because
that one really would go nowhere.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.catalog.model import Catalog
from fenceai.core.units import Mm
from fenceai.knowledge.ast import Expr

_SWATCH = re.compile(r"^#[0-9a-fA-F]{6}$")

LengthRule = Literal["clear_between_posts", "centre_to_centre", "overlap", "panel_height"]


# --- what a part IS, and which items may supply it ---------------------------

class EligibleItem(BaseModel):
    """One way to satisfy a requirement. Ordered by `priority`, which is the
    company's stated preference — never a probability (SAP's usage probability
    splits demand across alternates for forecasting; we compute one exact job).

    Deliberately no `supply` and no `conversion`: how a SKU is consumed already
    lives on the product, and a ratio is the nominal division that kerf
    disproves."""

    kind: Literal["catalog_item"] = "catalog_item"
    sku: str
    priority: int = 1
    approval: Literal["auto", "suggest_only"] = "auto"


# A discriminated union with one variant today. The workshop seam depends on
# this staying a union: a future `FabricatedRoute` carries operations instead of
# a SKU, and nothing outside the resolver may read `.sku` directly.
EligibilityMember = Annotated[Union[EligibleItem,], Field(discriminator="kind")]


class Eligibility(BaseModel):
    group: str | None = None
    members: list[EligibilityMember] = []
    # DESIGNED to be resolved once and frozen into the run's snapshot, so a new
    # catalog product cannot change what an accepted quote meant. NOT BUILT:
    # nothing evaluates it and nothing freezes it, so `validate_model` rejects a
    # model that sets one instead of letting it read as a working filter.
    predicate: Expr | None = None


class PartRequirement(BaseModel):
    role: str                       # post | cap | concrete | rail | screw | infill | spacer
    qty: int = 1
    length_rule: LengthRule | None = None
    overlap_mm: Mm = 0              # only for length_rule == "overlap"
    option_axis: str | None = None
    sku_by_option: dict[str, str] = {}
    eligibility: Eligibility = Eligibility()


# --- placement ---------------------------------------------------------------

class FromBottom(BaseModel):
    kind: Literal["from_bottom"] = "from_bottom"
    offset_mm: Mm


class FromTop(BaseModel):
    kind: Literal["from_top"] = "from_top"
    offset_mm: Mm


class Fraction(BaseModel):
    kind: Literal["fraction"] = "fraction"
    permille: int


class Distributed(BaseModel):
    """N members spread over the panel height. `count_param` names a KNOWLEDGE
    param so a company rule can still win the count (see the spec: rail count is
    a number, not structure); `count` is the model's contributed default."""

    kind: Literal["distributed"] = "distributed"
    count: int
    count_param: str | None = None
    bottom_inset_mm: Mm = 0
    top_inset_mm: Mm = 0


Placement = Annotated[
    Union[FromBottom, FromTop, Fraction, Distributed], Field(discriminator="kind")
]


# --- the panel ---------------------------------------------------------------

class FrameSlot(BaseModel):
    key: str
    orientation: Literal["horizontal", "vertical"]
    placement: Placement
    requirement: PartRequirement


class Member(BaseModel):
    key: str
    width_mm: Mm
    thickness_mm: Mm = 0
    face_offset_mm: int = 0     # + front face, - back face (shadowbox)
    gap_after_mm: Mm = 0        # MAY be negative: an overlap (board-on-board)
    base_ref: str | None = None  # frame slot key this member starts at
    top_ref: str | None = None
    requirement: PartRequirement


class InfillSpec(BaseModel):
    orientation: Literal["vertical", "horizontal"]
    pattern: list[Member] = []
    justification: Literal["start", "end", "center", "spread_to_fit"] = "spread_to_fit"
    excess: Literal["truncate", "space", "trim_last", "extension_clip"] = "space"
    edge_margin_mm: Mm = 0
    supply: Literal["components", "assembly"] = "components"


class FixingRule(BaseModel):
    key: str
    basis: Literal[
        "per_member_crossing", "per_member", "per_end_member",
        "per_gap", "per_frame_member", "per_panel",
    ]
    qty_per_basis: int
    qty_param: str | None = None   # knowledge param, as Distributed.count_param
    requirement: PartRequirement


class PanelSpec(BaseModel):
    frame: list[FrameSlot] = []
    infill: InfillSpec | None = None
    fixings: list[FixingRule] = []


# --- the model ---------------------------------------------------------------

class OptionValue(BaseModel):
    key: str
    label_i18n: dict[str, str] = {}
    swatch: str | None = None   # validated at load: plain hex only


class Axis(BaseModel):
    key: str
    label_i18n: dict[str, str] = {}
    kind: Literal["enum", "numeric"]
    values: list[OptionValue] = []
    available_when: Expr | None = None


class PolicyContribution(BaseModel):
    """The model's ask of the span layout, emitted as knowledge rather than read
    directly (`strategy/generator.py::_policy_knowledge`), with authority PER
    CONTRIBUTION: a manufacturer maximum span is a hard constraint, a nominal
    width is a preference, and one authority for the whole policy would make one
    of the two wrong — an unbeatable preference, or a beatable safety limit.

    `param` is limited to `SERIES_SCOPED_PARAMS`: the params generation resolves
    under the model's own scope, and therefore the ones a contribution can
    actually reach."""

    param: str
    value: int
    knowledge_type: Literal["hard_constraint", "company_rule", "fact", "preference"]
    authority: int | None = None


class Variant(BaseModel):
    condition: Expr
    spec: PanelSpec


class Continuous(BaseModel):
    kind: Literal["continuous"] = "continuous"
    min_mm: Mm
    max_mm: Mm
    step_mm: Mm = 1


class Discrete(BaseModel):
    kind: Literal["discrete"] = "discrete"
    heights_mm: list[Mm] = []


HeightSupport = Annotated[Union[Continuous, Discrete], Field(discriminator="kind")]


class FenceModel(BaseModel):
    id: str
    version: int
    name_i18n: dict[str, str] = {}
    grade: Literal["residential", "commercial", "industrial"] = "residential"
    status: Literal["draft", "active", "retired"] = "active"
    height_support: HeightSupport = Continuous(min_mm=0, max_mm=10_000)
    layout_policy: list[PolicyContribution] = []
    option_axes: list[Axis] = []
    default_spec: PanelSpec = PanelSpec()
    variants: list[Variant] = []   # authored order; first satisfied condition wins

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"


# --- load-time validation ----------------------------------------------------

def _requirements(spec: PanelSpec) -> list[tuple[str, PartRequirement]]:
    out = [(s.key, s.requirement) for s in spec.frame]
    if spec.infill:
        out += [(m.key, m.requirement) for m in spec.infill.pattern]
    out += [(f.key, f.requirement) for f in spec.fixings]
    return out


def _can_supply_length(catalog: Catalog, sku: str) -> bool:
    product = catalog.products.get(sku)
    if product is None:
        return False
    if product.consumption.kind == "divisible_linear":
        return True
    return isinstance(product.attrs.get("length_mm"), int)


# Several schema fields are expressible ahead of the resolver that reads them —
# the spec designs them, a later wave builds them — and resolution silently
# ignores every one of them until it does. Accepting such a model at load and
# then ignoring the field is not a deferral, it is a wrong answer with a green
# light: the author asks for the infill to be BOUGHT as one pre-made unit,
# validation says "fine", and the panel is bought as its parts with nothing
# reported. So a model that USES an unbuilt feature is refused here, by name.
# Deleting an entry from this table is how a wave turns each feature on — and
# the resolver change and the entry's removal are then the same commit.
#
# W3 emptied four of these entries (variants, option axes, height support,
# layout policy) and kept two NARROWED ones, because narrowing an entry to the
# part that is genuinely unbuilt is the same discipline as deleting it: an
# `Axis.available_when`, and a `layout_policy` contribution to a param no model
# scope reaches. What is left after that is real: `Eligibility.group` and
# `.predicate`, `excess=trim_last|extension_clip`, and `infill supply=assembly`.
#
# W4 ADDED one, `Axis.kind != "enum"` — the table works in both directions. A
# field can sit here unnoticed while only demo data writes it and become a
# wrong answer the moment an editor puts it in front of an author, which is
# exactly what an authoring wave is for finding.
_UNSUPPORTED = "not yet supported (phase 2)"

# The params a `layout_policy` contribution may name, because these are the ones
# generation resolves under the model's own `series` scope — inside the segment
# loop, AFTER the model is known (`strategy/generator.py::segment_model`).
# Everything else in the fence is resolved once for the whole topology, before
# any model has been chosen: `post_embed_mm` is resolved in `_check_post_lengths`
# and `max_panel_step_mm`, `max_panel_gap_mm` and friends per RUN, all of them
# from a scope with no `series` bound. A contribution naming one of those would
# be accepted, emitted, and matched by nothing — a model asking for a deeper
# footing and getting the company's, silently. Widening this set means moving
# the corresponding resolution inside the segment loop, in the same change;
# `tests/strategy/test_panel_features.py` pins each member by contributing it
# and watching the fence move.
SERIES_SCOPED_PARAMS = frozenset({"max_span_mm", "rails_per_span", "screws_per_span"})


def _unsupported_features(model: FenceModel) -> list[str]:
    """Features the schema accepts that `resolve_panel` does not honour."""
    errors: list[str] = []
    for axis in model.option_axes:
        if axis.kind != "enum":
            # Nothing reads `Axis.kind`. `_chosen_option` narrows by looking the
            # answer up in `sku_by_option` — `str(ctx.options[axis])` against the
            # keys of the axis's own `values` — so a `numeric` axis is answered
            # out of a hand-listed enumeration, and only the numbers someone
            # thought to list can be given. "1000, 1200 or 1800" is a different
            # question from "a height", and the field says the second while the
            # resolver asks the first. Harmless while only demo data declared
            # axes; W4 puts it in front of an author.
            errors.append(
                f"axis {axis.key}: kind={axis.kind!r} is {_UNSUPPORTED}: nothing "
                "reads Axis.kind and resolution answers every axis from its "
                "declared `values`, so this would behave as an enum of whatever "
                "values were listed"
            )
        if axis.available_when is not None:
            # The one part of the axis feature W3 left unbuilt, and narrowed to
            # the field rather than left on the whole feature: an axis is
            # answered by whoever chose the model — a project default or an
            # interval event — long before a bay exists, so `available_when`
            # cannot be evaluated at resolution against the panel it would need
            # to read, and there is no surface yet that could hide the question.
            # An accepted-but-ignored one would let a model declare "this axis
            # only applies below 1200" and then narrow a 1800 mm bay by it.
            errors.append(
                f"axis {axis.key}: available_when is {_UNSUPPORTED}: nothing "
                "evaluates it, so the axis would stay answerable — and its "
                "answer would still narrow a slot — where the model says it "
                "does not apply"
            )
    for contribution in model.layout_policy:
        if contribution.param not in SERIES_SCOPED_PARAMS:
            errors.append(
                f"layout_policy param {contribution.param!r} is {_UNSUPPORTED}: "
                "generation resolves it before any model is chosen, from a scope "
                "with no `series` bound, so this contribution would enter the "
                "evaluator and match nothing. Supported today: "
                + ", ".join(sorted(SERIES_SCOPED_PARAMS))
            )

    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
        if spec.infill and spec.infill.excess in ("trim_last", "extension_clip"):
            errors.append(
                f"excess={spec.infill.excess!r} is {_UNSUPPORTED}: fit_pattern "
                "treats it exactly as 'truncate', which is a different BOM"
            )
        if spec.infill and spec.infill.supply != "components":
            # Classified as geometry-only in the first pass and therefore left
            # out of this table. It is not geometry: "assembly" means the infill
            # is BOUGHT as one pre-made unit rather than as N members, and
            # `resolve_panel` unconditionally emits a component slot per member.
            # Nothing reads the field, so authoring it passes validation and
            # silently produces a different set of purchased SKUs — the exact
            # defect class this table exists to close.
            errors.append(
                f"infill supply={spec.infill.supply!r} is {_UNSUPPORTED}: "
                "resolve_panel always emits per-member component slots, so the "
                "panel would be bought as its parts rather than as one unit"
            )
        for key, req in _requirements(spec):
            if req.eligibility.group is not None:
                # Never read: `resolve_supply` groups by the (sku, priority,
                # approval) SIGNATURE of the usable members and by nothing else.
                # This is not cosmetic — grouping decides which lines are costed
                # together, and cut planning is not additive, so it decides the
                # answer. Measured: two lines (1500 mm and 1000 mm) over BIG
                # (3000 mm @ 1000c) and SMALL (1600 mm @ 600c) resolve to BIG as
                # one group (one bar, 1000c, beating two SMALL bars at 1200c) and
                # to SMALL as two groups (600c each). An honoured `group` would
                # have picked the other product.
                errors.append(
                    f"slot {key}: Eligibility.group is {_UNSUPPORTED}: supply "
                    "resolution groups by the members' (sku, priority, approval) "
                    "signature and never reads this, so a named group would "
                    "neither join nor separate the lines it names — and grouping "
                    "decides which product is chosen"
                )
            if req.eligibility.predicate is not None:
                errors.append(
                    f"slot {key}: Eligibility.predicate is {_UNSUPPORTED}: it is "
                    "never evaluated and never frozen into the run's snapshot, so "
                    "it would neither add nor remove a candidate"
                )
    return errors


def unknown_skus(model: FenceModel, catalog: Catalog) -> list[str]:
    """Eligible SKUs this catalog does not stock — the ONE validation failure a
    user can cause without authoring a model.

    `legacy_model()` seeds its eligibility from the run's resolved `demand_skus`,
    which come from a knowledge `DefaultComponent` whose sku is a free-text
    field in the editor. So this is the failure that needs a `code + params` a
    Hebrew reader can act on; the rest of `validate_model`'s errors are English
    authoring text for someone editing a model, and no route exists to do that
    yet. Computed structurally, never by parsing those strings."""
    return sorted({
        m.sku
        for spec in [model.default_spec, *(v.spec for v in model.variants)]
        for _, req in _requirements(spec)
        for m in req.eligibility.members
        if m.sku not in catalog.products
    })


def validate_model(model: FenceModel, catalog: Catalog) -> list[str]:
    """Every reason this model cannot be used, as English strings for the author.

    Checked once at load so resolution can trust the data. These are authoring
    errors, not user-facing warnings, so they carry no code+params."""
    errors: list[str] = []
    axis_keys = {a.key for a in model.option_axes}
    axis_values = {a.key: {v.key for v in a.values} for a in model.option_axes}

    errors += _unsupported_features(model)

    for axis in model.option_axes:
        for value in axis.values:
            if value.swatch is not None and not _SWATCH.match(value.swatch):
                errors.append(
                    f"axis {axis.key} value {value.key}: swatch must be #rrggbb, "
                    f"got {value.swatch!r}"
                )

    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
        for member in (spec.infill.pattern if spec.infill else []):
            # `fit_pattern` walks the sequence adding a member then its gap. A
            # member that occupies no space, or one whose overlap swallows it
            # whole, makes that walk stand still — infinitely many members in a
            # finite bay. `gap_after_mm` may legitimately be NEGATIVE (an
            # overlap, which is what board-on-board is), so the bound is on the
            # member's net advance, not on the gap.
            if member.width_mm <= 0:
                errors.append(
                    f"infill member {member.key!r}: width_mm must be positive, "
                    f"got {member.width_mm}"
                )
            elif member.width_mm + member.gap_after_mm <= 0:
                errors.append(
                    f"infill member {member.key!r}: width_mm + gap_after_mm must be "
                    f"positive, got {member.width_mm} + {member.gap_after_mm} = "
                    f"{member.width_mm + member.gap_after_mm}; the pattern would "
                    "never advance"
                )

        reqs = _requirements(spec)
        seen: set[str] = set()
        for key, _ in reqs:
            if key in seen:
                errors.append(f"duplicate slot key {key!r}")
            seen.add(key)
        for key, req in reqs:
            skus = [m.sku for m in req.eligibility.members]
            for sku in skus:
                if sku not in catalog.products:
                    errors.append(f"slot {key}: eligible sku {sku} is not in the catalog")
                elif req.length_rule is not None and not _can_supply_length(catalog, sku):
                    errors.append(
                        f"slot {key}: {sku} cannot supply a length "
                        f"(not divisible, no attrs.length_mm)"
                    )
                elif (req.length_rule is None
                      and catalog.products[sku].consumption.kind == "divisible_linear"):
                    # The inverse of the check above, and it fails FAR more
                    # quietly. A divisible product asked for with no cut length
                    # plans no bars, so the BOM carries no line for it at all and
                    # the parts ledger reads the gap as demand covered from stock
                    # — a panel that silently costs nothing rather than a panel
                    # that visibly costs the wrong amount. Caught at authoring,
                    # where the author can still say what length they meant.
                    errors.append(
                        f"slot {key}: {sku} is bought by the length but the slot "
                        f"declares no length_rule, so nothing would be cut or priced"
                    )
            if req.option_axis and req.option_axis not in axis_keys:
                errors.append(f"slot {key}: option_axis {req.option_axis} is not declared")
            for value, sku in req.sku_by_option.items():
                if sku not in skus:
                    errors.append(
                        f"slot {key}: option {req.option_axis}={value} names {sku}, "
                        f"which is not an eligible member"
                    )
                # Only checked once the axis itself resolves: an unknown
                # option_axis is already reported above, and flagging every
                # one of its values on top of that would be cascading noise,
                # not a new fact.
                if req.option_axis in axis_keys and value not in axis_values[req.option_axis]:
                    errors.append(
                        f"slot {key}: sku_by_option key {value!r} is not a "
                        f"declared value of axis {req.option_axis}"
                    )
    return errors
