"""Fence models: a named product line and the structure of its normal panel.

Immutable versions, like knowledge objects (ADR-0006): a run stamps the model
versions it resolved, so editing a model cannot change what an old run meant.

The model owns product STRUCTURE. Numbers that can conflict — max span, rail
count, embedment — stay knowledge, and the model contributes them through
LayoutPolicy so the existing evaluator resolves them with everything else.
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
    predicate: Expr | None = None  # resolved and FROZEN into the run's snapshot


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
    directly. Authority is PER CONTRIBUTION: a manufacturer maximum span is a
    hard constraint, a nominal width is a preference. One authority for the whole
    policy would make one of the two wrong."""

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


def validate_model(model: FenceModel, catalog: Catalog) -> list[str]:
    """Every reason this model cannot be used, as English strings for the author.

    Checked once at load so resolution can trust the data. These are authoring
    errors, not user-facing warnings, so they carry no code+params."""
    errors: list[str] = []
    axis_keys = {a.key for a in model.option_axes}

    for axis in model.option_axes:
        for value in axis.values:
            if value.swatch is not None and not _SWATCH.match(value.swatch):
                errors.append(
                    f"axis {axis.key} value {value.key}: swatch must be #rrggbb, "
                    f"got {value.swatch!r}"
                )

    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
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
    return errors
