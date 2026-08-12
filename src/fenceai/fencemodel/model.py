"""Fence models: a named product line and the structure of its normal panel.

Immutable versions, like knowledge objects (ADR-0006): a run stamps the model
versions it resolved, so editing a model cannot change what an old run meant.

The model owns product STRUCTURE. Numbers that can conflict — max span, rail
count, embedment — stay knowledge. The DESIGN for that is `LayoutPolicy`: the
model states them as knowledge-shaped contributions and the existing evaluator
resolves them with everything else. That is phase 2 — nothing reads
`layout_policy` today, so `validate_model` refuses a model that sets one rather
than accepting an ask that would go nowhere.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.catalog.model import Catalog
from fenceai.core.units import Mm
from fenceai.knowledge.ast import Expr

_SWATCH = re.compile(r"^#[0-9a-fA-F]{6}$")

LengthRule = Literal["clear_between_posts", "centre_to_centre", "overlap"]


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
    """The model's ask of the span layout — DESIGNED to be emitted as knowledge
    rather than read directly, with authority PER CONTRIBUTION: a manufacturer
    maximum span is a hard constraint, a nominal width is a preference, and one
    authority for the whole policy would make one of the two wrong.

    NOT BUILT in phase 1: nothing turns a contribution into a knowledge version
    and the evaluator never sees one. `validate_model` therefore rejects a model
    carrying a `layout_policy`, rather than accepting a max span that would be
    silently ignored by the layout it was written to constrain."""

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


# Phase 1 resolves a PanelSpec and nothing more. Several schema fields are
# already expressible — the spec designs them, phase 2 builds them — and
# `resolve_panel` silently ignores every one of them today. Accepting such a
# model at load and then ignoring the field at resolve is not a deferral, it is
# a wrong answer with a green light: the author asks for three rails below
# 1200 mm, validation says "fine", and every bay is built to `default_spec`
# with nothing reported. So a model that USES an unbuilt feature is refused
# here, by name. Deleting an entry from this table is how phase 2 turns each
# feature on — and the resolver change and the entry's removal are then the
# same commit.
_UNSUPPORTED = "not yet supported (phase 2)"

_PERMISSIVE_HEIGHT_SUPPORT = Continuous(min_mm=0, max_mm=10_000, step_mm=1)


def _unsupported_features(model: FenceModel) -> list[str]:
    """Features the schema accepts that `resolve_panel` does not honour."""
    errors: list[str] = []
    if model.variants:
        errors.append(
            f"variants are {_UNSUPPORTED}: the generator resolves default_spec "
            "directly and select_variant has no production caller, so a variant "
            "condition would never be evaluated"
        )
    if model.option_axes:
        errors.append(
            f"option_axes are {_UNSUPPORTED}: PanelContext.options is never read, "
            "so an option value could not narrow eligibility or pick a product"
        )
    if model.layout_policy:
        errors.append(
            f"layout_policy is {_UNSUPPORTED}: nothing emits its contributions "
            "into the knowledge evaluator, so the span layout would not see them"
        )
    if model.height_support != _PERMISSIVE_HEIGHT_SUPPORT:
        errors.append(
            f"a restricted height_support is {_UNSUPPORTED}: resolution never "
            "checks the panel height against it, so an unquotable height would "
            "be built silently instead of raising height_not_supported"
        )

    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
        if spec.infill and spec.infill.excess in ("trim_last", "extension_clip"):
            errors.append(
                f"excess={spec.infill.excess!r} is {_UNSUPPORTED}: fit_pattern "
                "treats it exactly as 'truncate', which is a different BOM"
            )
        for key, req in _requirements(spec):
            if req.eligibility.predicate is not None:
                errors.append(
                    f"slot {key}: Eligibility.predicate is {_UNSUPPORTED}: it is "
                    "never evaluated and never frozen into the run's snapshot, so "
                    "it would neither add nor remove a candidate"
                )
            if req.option_axis is not None or req.sku_by_option:
                errors.append(
                    f"slot {key}: option_axis/sku_by_option are {_UNSUPPORTED}: "
                    "the chosen option value is never read at resolution, so the "
                    "slot would silently keep its full eligibility set"
                )
    return errors


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
