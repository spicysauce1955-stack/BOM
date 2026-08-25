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
from typing import TYPE_CHECKING, Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from fenceai.catalog.model import Catalog
from fenceai.core.units import Mm
from fenceai.fencemodel.bases import FIXING_BASES
from fenceai.fencemodel.lengths import LENGTH_RULES
from fenceai.knowledge.ast import Expr, field_paths
# `parts.model` is a leaf — it imports `core.units` and nothing else — so naming
# it here costs no cycle. `parts.resolve` and `parts.validate` are the modules
# that import THIS one, and their imports stay deferred below.
from fenceai.parts.model import (
    PATH_SEP, ContainedPart, contained_path, walk_contained,
)

if TYPE_CHECKING:      # `parts.resolve` imports this module; the runtime imports
    from fenceai.parts.model import PartLibrary   # are deferred into the functions

_SWATCH = re.compile(r"^#[0-9a-fA-F]{6}$")

# A plain `str` validated against the REGISTRY (`fencemodel/lengths.py`), not a
# `Literal`. That is the whole point of the seam: a new rule — `between_rails`,
# `minus_hardware` — is a registration, where before it was an edit to this type
# AND a branch in `resolve._length_for` AND a release. The vocabulary is open;
# the SIGNATURE is what stays closed. See `core/registry.py`.
#
# Validation has not been given up, only moved: `_known_length_rule` below
# refuses an unregistered name at parse time, so a typo still fails at the
# boundary and with a message naming the alternatives, which a `Literal` never
# did as well.
LengthRule = str


def _known_length_rule(v: str | None) -> str | None:
    if v is not None and v not in LENGTH_RULES:
        raise ValueError(
            f"unknown length rule {v!r}; registered: {', '.join(LENGTH_RULES.names())}"
        )
    return v


def _known_fixing_basis(v: str) -> str:
    if v not in FIXING_BASES:
        raise ValueError(
            f"unknown fixing basis {v!r}; registered: {', '.join(FIXING_BASES.names())}"
        )
    return v


# How a member meets the one it lands on. The kind is a WORD for the shop and
# the drawing; the millimetres beside it are what the cut list reads, which is
# why `validate_model` refuses a kind whose numbers are all zero — "channel"
# with no depth and no engagement is a butt joint wearing a better name.
JointKind = Literal["butt", "channel", "groove", "bracket", "overlap"]

# The two kinds whose mechanic the schema can express: a housing of some depth,
# and a member seated into it. `bracket` and `overlap` are in the vocabulary
# because the spec named them and are refused by `_unsupported_features` —
# neither has a field that could make it mean anything, and a kind with no
# numbers behind it is a butt joint wearing a better name.
_HOUSED_JOINTS = frozenset({"channel", "groove"})


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
    """Which items may satisfy a requirement — said one of two ways, never both.

    `members` NAMES products. `predicate` says what the part NEEDS, and
    `match.match_eligibility` turns it into members against the catalog, once,
    during generation. The resolved members are what a run freezes, which is why
    a new catalog product cannot change what an accepted quote meant and why
    `catalog_hash` may be narrowed to the SKUs a run actually named.
    """

    group: str | None = None
    members: list[EligibilityMember] = []
    # Cleared by the matcher on the way into a `ResolvedSlot`: members are the
    # frozen answer, and a predicate riding along would let a later reader
    # re-evaluate it against a moved catalog and get a different candidate set
    # for the same run.
    predicate: Expr | None = None


class PartRequirement(BaseModel):
    """WHERE a part goes in this panel. What it IS lives on the part.

    The line is what the piece is versus where it goes: a joint is a relationship
    between two members in a panel, not a property of a rail — the same rail seats
    into a channel in one model and butts in another. But a rail's width is the
    rail's, and keeping it here is what let a model draw 38 while buying 45.

    `part_id` is unpinned. A slot storing `rail-38@v3` would mean fixing a rail spec
    requires republishing every model naming it, which is the entire reason the part
    is a shared entity rather than a copied template. Generation resolves
    `latest_active` and the RUN stamps what it resolved.

    `eligibility` is not authored here and carries no default a person writes: it is
    filled by `parts.resolve.resolve_model_parts` and cleared by the matcher, which
    is the same lifetime it has always had downstream.

    `role` has the SAME lifetime, and for the same reason: it is not authored here
    either, it is filled by `resolve_model_parts` from the part's `type`. Role left
    AUTHORING when the part became the thing that says what a piece is — a slot
    saying "rail" beside a part_id naming a screw part would be two authorities over
    one word — but it did not leave the system: `ResolvedSlot.role` is required, and
    `demand/derive.py` and the decision graph both read it. `""` is what an
    unresolved document carries, exactly as an empty `Eligibility` is.

    `part_id` defaults to `""`, which means *this slot names no part*. That is not
    an authoring convenience: `routed_vinyl_model`'s post and cap agree with a fact
    about the BAY (`item.routed_at_mm == panel.rail_positions_mm`), and a `SpecField`
    is always `item.<key> <agree> <literal>` — a part cannot declare a fact about the
    panel it has not been placed in. Those two slots keep their authored predicate and
    `resolve_model_parts` leaves them alone. `validate_model` still refuses a slot
    that names no part AND declares no eligibility, so the empty default cannot be a
    silent way to author nothing.
    """

    part_id: str = ""
    role: str = ""
    qty: int = 1
    length_rule: LengthRule | None = None
    _check_length_rule = field_validator("length_rule")(_known_length_rule)
    overlap_mm: Mm = 0
    option_axis: str | None = None
    sku_by_option: dict[str, str] = {}
    eligibility: Eligibility = Eligibility()
    # What ships INSIDE the piece this slot holds. Filled by
    # `parts.resolve.resolve_model_parts` from the part, never authored beside a
    # `part_id` — the same lifetime `eligibility`, `role` and `Member.width_mm`
    # have, and for the same reason: a piece's contents are the part's fact, and
    # a model able to restate them is a model able to disagree with the part.
    #
    # A slot naming NO part may author this directly, exactly as such a slot
    # authors its own eligibility (M-VINYL's post and cap). That is the one shape
    # where nothing else can supply the answer.
    contained: list[ContainedPart] = []
    # ... and what those contained pieces SUPPLY in this panel. Authored here and
    # nowhere else, because it is the only fact in the pair that is about the
    # panel rather than about the piece: a hinge in a box does not know that this
    # model calls its hinge slot `gate_hinges`.
    #
    #     {"<contained path, relative to this slot>": "<slot key it supplies>"}
    #
    # A dict and not a list of pairs, so one contained piece cannot be spent
    # twice: crediting one physical hinge against two slots would remove two
    # purchases for one piece, which is the phantom saving this whole feature
    # exists to refuse. The keys are RELATIVE (`hinge`, `hinge/pin`) because a
    # part cannot know the key of the slot it happens to be placed in.
    credits: dict[str, str] = {}

    @property
    def eligibility_source(self) -> Literal[
        "part", "authored_members", "authored_predicate", "unspecified"
    ]:
        """Which of four shapes this slot is — one accessor, so the editor and the
        validator read the same answer.

        Derived, never stored, for the reason `Part.dimensions` is: a stored copy
        would be a second authority over facts these fields already encode.

        `part_id` is checked FIRST because resolution fills `predicate` on a
        part-named slot — a resolved document would otherwise report itself as
        rule-authored, and the editor would offer to edit a rule nobody wrote.

        There is a fifth shape it cannot report. M-LEGACY's rail and screw have
        their members REPLACED per run from `demand_skus`, so what a job buys there
        comes from company knowledge — but that is a generation-time behaviour with
        no trace on the authored document. Those slots report `authored_members`,
        which is what they are on paper. Claiming otherwise would be a guess dressed
        as a fact.
        """
        if self.part_id:
            return "part"
        if self.eligibility.predicate is not None:
            return "authored_predicate"
        if self.eligibility.members:
            return "authored_members"
        return "unspecified"

    @model_validator(mode="after")
    def _part_or_authored(self) -> "PartRequirement":
        """Naming a part and authoring what it is are exclusive — on the AUTHORED
        document, which is the only place the two can both be true.

        Not a style rule. `resolve_model_parts` OVERWRITES `eligibility` and `role`
        for every slot that names a part, so a document carrying both was accepted,
        validated clean, and then had the authored half deleted without a word: a
        slot naming `rail-rail-3000` beside an `EligibleItem(sku="RAIL-40",
        approval="suggest_only")` resolved to `members=[]`, and a human sign-off
        flag went with it. `_predicate_errors`' refusal of "a predicate AND members"
        could never fire on such a slot either, because resolution wiped the
        evidence before validation read it.

        Enforced HERE rather than in `validate_model` because it is a fact about the
        document, answerable with no catalog and no library — and because the
        resolver's own writes must not have to route around a check that only ever
        applies before it runs. Assignment is deliberately not validated (pydantic's
        default): `resolve_model_parts` assigns the resolved eligibility and role
        onto a copy, and that copy is the one document where both are true and
        should be.
        """
        if not self.part_id:
            return self
        said = [
            name for name, authored in (
                ("eligibility.members", bool(self.eligibility.members)),
                ("eligibility.predicate", self.eligibility.predicate is not None),
                ("role", bool(self.role)),
                # `contained` joins the list because what is in the box is the
                # PART's fact and `resolve_model_parts` overwrites whatever is
                # written here. `credits` deliberately does NOT: what a contained
                # piece is used for in this panel is placement, which is exactly
                # what this document is the authority on.
                ("contained", bool(self.contained)),
            ) if authored
        ]
        if said:
            raise ValueError(
                f"slot names part {self.part_id!r} and also authors "
                f"{', '.join(said)} — the part is the one authority on what a piece "
                "is, and resolution would overwrite what is written here"
            )
        return self


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

def _refuse_authored_dimensions(holder, keys: tuple[str, ...]):
    """A holder that names a part must author none of the dimensions the part fills.

    The other half of `PartRequirement._part_or_authored`, one level up, because
    these fields sit on the HOLDER and not on the requirement. `_apply_dimensions`
    writes `part.width_mm or 0` and `part.thickness_mm or 0` unconditionally, so a
    part declaring no thickness silently ZEROED a thickness the author had written —
    and 0 is not a neutral value here, it is what the elevation renders as
    `declared=False`. The migration only dodged it by minting
    `rail-rail-3000-40`; the next author would have lost the number with nothing
    said. Refused where it is still fixable: put the dimension on the part, which is
    the one authority that says how wide a rail is.
    """
    if not holder.requirement.part_id:
        # Nothing here is the authority on this holder's dimensions, so whatever
        # the document carries stands — the same case `_apply_dimensions` skips.
        return holder
    said = [k for k in keys if getattr(holder, k)]
    if said:
        raise ValueError(
            f"{holder.key!r} names part {holder.requirement.part_id!r} and also "
            f"authors {', '.join(said)} — declare the dimension on the part, or the "
            "panel draws one number and buys another"
        )
    return holder


class FrameSlot(BaseModel):
    key: str
    orientation: Literal["horizontal", "vertical"]
    placement: Placement
    # the member's face height as it is SEEN — its depth in elevation. 0 means
    # undeclared, and the elevation read model says so (`declared=False`) rather
    # than drawing a nominal band that reads as measured.
    thickness_mm: Mm = 0
    joint: JointKind = "butt"
    # how deep this member RECEIVES an infill member — the U of a bottom channel,
    # the groove routed into a top rail. Measured from the receiving face inwards,
    # so it is bounded by nothing here and by `thickness_mm` in the shop; the
    # refusal below is the part that has a datum: a channel inside a member of
    # undeclared depth is a dimension with nothing to measure it from.
    channel_depth_mm: Mm = 0
    # clearance left at the BOTTOM of that channel, so the member can be tipped
    # in. It shortens nothing by itself: what the member is cut to is the
    # engagement it is authored with, and the margin is what the author must
    # leave room for when choosing it.
    insertion_margin_mm: Mm = 0
    requirement: PartRequirement

    @model_validator(mode="after")
    def _dimensions_are_the_parts(self) -> "FrameSlot":
        return _refuse_authored_dimensions(self, ("thickness_mm",))


class Member(BaseModel):
    key: str
    # Undeclared (0) until `parts.resolve.resolve_model_parts` fills it from the
    # part's dimensions — the same lifetime `thickness_mm` and `eligibility` have.
    # Keeping this authored on the part rather than here is what let a model draw
    # 38 while buying 45.
    width_mm: Mm = 0
    thickness_mm: Mm = 0
    face_offset_mm: int = 0     # + front face, - back face (shadowbox)
    gap_after_mm: Mm = 0        # MAY be negative: an overlap (board-on-board)
    base_ref: str | None = None  # frame slot key this member starts at
    top_ref: str | None = None
    joint: JointKind = "butt"
    # how far this member seats INTO its base_ref / top_ref. Added back to the
    # face-to-face distance, because the cut list wants the piece that is made,
    # not the opening it fills.
    base_engagement_mm: Mm = 0
    top_engagement_mm: Mm = 0
    requirement: PartRequirement

    @model_validator(mode="after")
    def _dimensions_are_the_parts(self) -> "Member":
        return _refuse_authored_dimensions(self, ("width_mm", "thickness_mm"))


class InfillSpec(BaseModel):
    orientation: Literal["vertical", "horizontal"]
    pattern: list[Member] = []
    justification: Literal["start", "end", "center", "spread_to_fit"] = "spread_to_fit"
    excess: Literal["truncate", "space", "trim_last", "extension_clip"] = "space"
    edge_margin_mm: Mm = 0
    supply: Literal["components", "assembly"] = "components"


class FixingRule(BaseModel):
    key: str
    # registry-validated, for `LengthRule`'s reasons
    basis: str
    _check_basis = field_validator("basis")(_known_fixing_basis)
    qty_per_basis: int
    qty_param: str | None = None   # knowledge param, as Distributed.count_param
    requirement: PartRequirement


class PanelSpec(BaseModel):
    frame: list[FrameSlot] = []
    infill: InfillSpec | None = None
    fixings: list[FixingRule] = []


class PostSlot(BaseModel):
    """The post a panel is built between, and the cap that finishes it.

    A model describing the panel and saying nothing about its posts is right for
    a company with one post standard and wrong for a product LINE: a routed vinyl
    post is specific to the panel that seats into it, and that panel is not
    expressible without it.

    The cap NESTS rather than sitting beside, because a cap exists BECAUSE a post
    does and its predicate reads the post it caps — which is only answerable
    because the post is chosen first. That ordering is what keeps every relation
    in this design one-directional.
    """

    key: str = "post"
    requirement: PartRequirement
    cap: PartRequirement | None = None


# What a POST's eligibility predicate may know about the bay it stands beside.
#
# THE cycle rule. A bay's clear opening is measured to its posts' faces, so a
# post chosen BY that opening would be choosing itself. The facts below are all
# settled from the HEIGHT of the bay, before any post is known, which is what
# makes the resolution order a DAG:
#
#     height -> rail positions -> post -> clear width -> infill fit
#
# Refused at authoring rather than at generation, where the same mistake is
# either a hang or an arbitrary answer that reads as measured. Deliberately the
# same shape as SERIES_SCOPED_PARAMS: a closed set of names, a refusal, and a
# stated reason for the boundary.
#
# `match.post_panel_facts` is what SUPPLIES these, and a test pins the two equal.
# A name declared readable here and not supplied there would be the worst of both:
# the predicate matches nothing, and the post falls silently through to the
# company default — a model quietly not getting the post it asked for.
POST_PREDICATE_PANEL_FACTS = frozenset({
    "height_mm", "rail_positions_mm", "vertical", "model_id",
})


# What a POST's eligibility predicate may know about ITSELF — not about the
# product it is choosing, which is the cycle rule below, but about the STATION.
#
# `kind` is not derived from the panel at any point: it is a fact of the
# topology — this node ends a run, that one turns a corner, the rest sit mid-run
# — and it is settled before a bay is laid out, let alone resolved. So it sits
# outside the DAG above rather than inside it, and it is readable for that
# reason alone.
#
# It has to be readable because a routed post is cut at the factory and its
# position decides WHICH FACES are cut: an end post on one face, a line post on
# two opposite faces, a corner post on two adjacent ones. Without it a product
# line names ONE post SKU for a whole run, and every end and every corner is
# ordered wrong — which is precisely why a manufacturer asks for the layout
# before it will quote.
#
# `mounting` is not here, though it is settled as early: it is resolved from
# knowledge inside `_make_post` after the model's post is chosen, and a
# `force_mounting` override can move it, so reading it here would mean resolving
# it twice in two places. See `match.post_panel_facts` for the whole reason.
POST_PREDICATE_POST_FACTS = frozenset({"kind"})


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


class AssemblyStep(BaseModel):
    """One thing a person does, in the order they do it.

    The roadmap asks that a panel carry assembly AND installation instructions.
    The difference between an instruction and a doc is whether it names PARTS: a
    step that says "fit the bottom rail" and names the slot is data — the
    assembly film can drive its order from it, the parts list can be split by it,
    and a slot no step places is a gap something can report. A step that is only
    prose is a paragraph, and a fence model is not a document.

    So `assembly` steps must name slots and `installation` steps need not: "let
    the footings cure overnight" places no part and is exactly the kind of
    instruction the second half of that roadmap line is about.

    The placeable vocabulary is the PANEL's own slots — frame, infill, fixings.
    A post, its cap and its footing belong to the bay rather than to the panel,
    so no step can name one today: an installation step about posts is prose,
    which is a real limitation and not the distinction above doing its job.
    `report/assembly.py` records what closing it would take.

    `text_i18n` follows `name_i18n`'s precedent — expert-authored prose, not a UI
    string, so it is not key-checked against the locale bundles; the surface
    falls back to whichever language the author wrote.
    """

    key: str
    kind: Literal["assembly", "installation"] = "assembly"
    slots: list[str] = []
    text_i18n: dict[str, str] = {}


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
    # None is NO OPINION, not "must come from knowledge": it is what every model
    # shipped before this carried, and it is what lets a boundary post between an
    # opinionated model and a legacy one resolve to the opinionated one's spec
    # rather than to a conflict.
    post: PostSlot | None = None
    # In the order a person does them. Empty is NO OPINION, exactly as `post`
    # is: the assembly film then falls back to its role-based build order, which
    # is what every model shipped before this had.
    assembly: list[AssemblyStep] = []

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"


# --- load-time validation ----------------------------------------------------

def spec_requirements(spec: PanelSpec) -> list[tuple[str, PartRequirement]]:
    """Every requirement a single spec carries: frame, infill, fixings.

    Public because `parts.resolve.part_requirements` walks the same structure
    to fill predicates from parts, and a second copy of this walk is exactly
    the drift hazard `part_requirements`'s own docstring warns about for
    variants: one copy feeding validation and one feeding resolution, free to
    disagree about what a spec's requirements are."""
    out = [(s.key, s.requirement) for s in spec.frame]
    if spec.infill:
        out += [(m.key, m.requirement) for m in spec.infill.pattern]
    out += [(f.key, f.requirement) for f in spec.fixings]
    return out


def spec_members(spec: PanelSpec) -> list[tuple[str, str]]:
    """Every MEMBER of a panel under the key that addresses it, and its role.

    Wider than `spec_requirements` by exactly the parts that ship inside other
    parts: a slot's own key, then one path key per contained piece at every
    depth. This is the vocabulary obligation 9 counts — "every member ...
    including parts contained inside other parts" — so it is what an assembly
    step may name and what `unplaced` is measured against.

    Kept beside `spec_requirements` and expressed in terms of it, because the two
    answer different questions about one structure and a second walk of that
    structure is the drift hazard `part_requirements` already warns about:
    `spec_requirements` is "what could be BOUGHT", this is "what is PLACED", and
    containment is precisely where those two lists stop being the same.
    """
    out: list[tuple[str, str]] = []
    for key, req in spec_requirements(spec):
        out.append((key, req.role))
        out += [(path, child.role) for path, child in walk_contained(req.contained, key)]
    return out


def _can_supply_length(catalog: Catalog, sku: str) -> bool:
    from fenceai.fencemodel.match import stock_length_mm
    product = catalog.products.get(sku)
    return product is not None and stock_length_mm(product) is not None


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
#
# The joint wave (two-tier visualizer W2) added one and shrank it in the same
# change, which is the honest account: `Member.base_ref`/`top_ref` were never in
# this table although resolution had ignored them since phase 1 and the model
# editor had been offering both selects to authors since W4 — the exact defect
# the table exists to catch, missed. `between_frame` now reads them, so the
# entry that belongs here is the NARROW one: the refs under any OTHER length
# rule, where they still reach nothing.
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
SERIES_SCOPED_PARAMS = frozenset({
    "max_span_mm", "rails_per_span", "screws_per_span", "exact_span_mm",
    # resolved under the same segment scope by `_check_panel_safety`, so a
    # product line may declare its own gap tolerance and rail spacing
    "max_clear_gap_mm", "min_rail_separation_mm", "max_pattern_residual_mm",
})


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
        if spec.infill and spec.infill.excess == "trim_last":
            # NOT a phase-2 deferral, and calling it one was wrong: trimming the
            # last member means ripping it NARROWER, which is 2D cutting — the
            # standing non-goal `docs/v1-known-limitations.md` records for sheet
            # and mesh infill, and for the same reason. `cutplan.py` cuts to
            # LENGTH; nothing in the system can price a part whose width changed.
            # This refusal ends when 2D cutting arrives, not before.
            errors.append(
                "excess='trim_last' needs 2D cutting: ripping the last member "
                "narrower changes its WIDTH, and the cut planner only cuts to "
                "length. Use 'space' (widen the gaps) or 'truncate' (leave the "
                "gap) until sheet cutting exists"
            )
        if spec.infill and spec.infill.excess == "extension_clip":
            # Also not a plain deferral: the FEATURE is undesigned, not merely
            # unbuilt. `InfillSpec` has nowhere to name the clip product, and
            # where the clips go is a real question with more than one defensible
            # answer — one at the far end, or one at each end whose opening is
            # non-zero, which differ under `center` justification. Inventing a
            # reading here would ship exactly the plausible-but-wrong answer this
            # table exists to refuse.
            errors.append(
                "excess='extension_clip' is not designed yet: InfillSpec has no "
                "field naming the clip product, and how many clips a residual "
                "needs depends on the justification. Use 'space' or 'truncate'"
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
        for holder in [*spec.frame, *(spec.infill.pattern if spec.infill else [])]:
            if holder.joint in ("bracket", "overlap"):
                # Named by the spec's vocabulary and given no field to mean
                # anything with. A bracket joint's mechanic is a PRODUCT — the
                # bracket — and `FrameSlot`/`Member` have nowhere to name one;
                # an overlap's is a lap length, which is neither a channel depth
                # (the receiving member is not housed) nor an engagement (the
                # member is not seated in anything). So both would ride on the
                # model, change no number, and be drawn as a mechanic the panel
                # does not have. Refused rather than accepted-and-ignored, which
                # is what this table is for.
                errors.append(
                    f"slot {holder.key}: joint={holder.joint!r} is "
                    f"{_UNSUPPORTED}: nothing in the schema can give it a "
                    "mechanic — a bracket needs a product and an overlap needs a "
                    "lap length, and neither has a field — so the member would be "
                    "cut exactly as a butt joint cuts it while the drawing "
                    "claimed otherwise"
                )

        for member in (spec.infill.pattern if spec.infill else []):
            seats = [n for n, mm in (("base_engagement_mm", member.base_engagement_mm),
                                     ("top_engagement_mm", member.top_engagement_mm)) if mm]
            if seats and member.requirement.length_rule != "between_frame":
                # The other half of the same hole. `_length_for` adds an
                # engagement under `between_frame` and under no other rule, so
                # here the author has said how deep the member seats and the
                # member is cut as though it seated nowhere.
                errors.append(
                    f"infill member {member.key!r}: "
                    f"{' and '.join(seats)} with "
                    f"length_rule={member.requirement.length_rule!r} is "
                    f"{_UNSUPPORTED}: only 'between_frame' adds an engagement to "
                    "the cut length, so the member would be cut as if it seated "
                    "into nothing"
                )
            refs = [n for n, r in (("base_ref", member.base_ref),
                                   ("top_ref", member.top_ref)) if r]
            if refs and member.requirement.length_rule != "between_frame":
                # `_length_for` reads the refs under `between_frame` and under no
                # other rule, so here they are two carefully chosen frame slots
                # that change nothing: the member is still cut to the panel
                # height (or a bay width), and the author who said "starts at the
                # bottom rail" gets a part that runs past it to the ground.
                errors.append(
                    f"infill member {member.key!r}: {' and '.join(refs)} with "
                    f"length_rule={member.requirement.length_rule!r} is "
                    f"{_UNSUPPORTED}: only 'between_frame' measures against the "
                    "frame, so these refs would be read by nothing and the "
                    "member would still be cut to the rule it declares"
                )

        for key, req in spec_requirements(spec):
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
    return errors


def _joint_errors(spec: PanelSpec, *, dimensions_known: bool = True) -> list[str]:
    """Joint geometry that would cut a part to the wrong length.

    `dimensions_known` is False when the caller has no part library: a member's
    thickness is filled by `parts.resolve` and is 0 in the authored document, so
    the rules that read it would refuse every channelled slot in the portfolio for
    a fact that has not been looked up yet. Skipped rather than guessed — see
    `validate_model`.

    Every one of these is arithmetic the resolver would otherwise perform
    faithfully on a number the author cannot have meant — and the answer would
    come out as a plain integer on a cut list, indistinguishable from a measured
    one. The failure is per BAY, so a model published with any of them is wrong
    on every panel of every job built to it until someone measures a piece.
    """
    errors: list[str] = []
    frame_by_key = {s.key: s for s in spec.frame}

    for slot in spec.frame:
        if dimensions_known and slot.channel_depth_mm > 0 and slot.thickness_mm == 0:
            errors.append(
                f"frame slot {slot.key!r}: channel_depth_mm="
                f"{slot.channel_depth_mm} inside a member whose thickness_mm is "
                "undeclared — the depth is measured from a face this model does "
                "not have, so nothing could check it against the member it cuts "
                "into. Declare thickness_mm, or drop the channel"
            )
        if 0 < slot.channel_depth_mm <= slot.insertion_margin_mm:
            errors.append(
                f"frame slot {slot.key!r}: insertion_margin_mm="
                f"{slot.insertion_margin_mm} is not less than channel_depth_mm="
                f"{slot.channel_depth_mm}, so the clearance swallows the whole "
                "seat and the member would rest on nothing"
            )
        if 0 < slot.thickness_mm < slot.channel_depth_mm:
            errors.append(
                f"frame slot {slot.key!r}: channel_depth_mm="
                f"{slot.channel_depth_mm} is deeper than the member it is cut "
                f"into (thickness_mm={slot.thickness_mm}) — the channel would "
                "come out the far side. Refused for the same reason an "
                "engagement deeper than its channel is: both put a member "
                "somewhere it cannot go, in a number that reads as measured"
            )
        if slot.joint in _HOUSED_JOINTS and slot.channel_depth_mm == 0:
            errors.append(
                f"frame slot {slot.key!r}: joint={slot.joint!r} with "
                "channel_depth_mm=0 claims a mechanic the numbers do not have — "
                "the drawing would show a housed joint and the cut list would "
                "read as a butt one. Give the channel its depth, or call the "
                "joint 'butt'"
            )
        if slot.requirement.length_rule == "between_frame":
            errors.append(
                f"frame slot {slot.key!r}: length_rule='between_frame' measures "
                "a member against the FRAME, and a frame slot has no "
                "base_ref/top_ref to measure between, so this slot would resolve "
                "to no cut length at all"
            )

    infill_orientation = spec.infill.orientation if spec.infill else None
    for member in (spec.infill.pattern if spec.infill else []):
        rule = member.requirement.length_rule
        if rule == "between_frame" and not (member.base_ref and member.top_ref):
            errors.append(
                f"infill member {member.key!r}: length_rule='between_frame' with "
                f"base_ref={member.base_ref!r} and top_ref={member.top_ref!r} — "
                "there is nothing to measure between, so the member would resolve "
                "to no cut length and a divisible product would be bought and "
                "priced as none at all"
            )
        for name, ref, engagement in (
            ("base_ref", member.base_ref, member.base_engagement_mm),
            ("top_ref", member.top_ref, member.top_engagement_mm),
        ):
            if ref is None:
                continue
            target = frame_by_key.get(ref)
            if target is None:
                # Deliberately not "unknown slot": a fixing key or another infill
                # member is a plausible thing to type here and a placement is
                # exactly what it does not have.
                errors.append(
                    f"infill member {member.key!r}: {name}={ref!r} is not a frame "
                    "slot of this spec, so the member has no placed member to "
                    "measure from — refs name frame slots only"
                )
                continue
            if target.orientation == infill_orientation:
                # A member is measured between the two frame members it CROSSES,
                # and `placement_positions` places a horizontal slot up the
                # height while a vertical one runs across the clear width. So a
                # vertical slat referring to a vertical stile would be cut to a
                # distance measured across the bay — a width, on a part that runs
                # up it. Not in the wave's list of refusals and added anyway: the
                # arithmetic below is orientation-blind by design (it reads
                # positions, not axes), which makes this the one mistake it
                # cannot notice, and the number it produces looks like every
                # other length on the cut list.
                errors.append(
                    f"infill member {member.key!r}: {name}={ref!r} is a "
                    f"{target.orientation} frame slot and the infill runs "
                    f"{infill_orientation}, so they never cross — the member "
                    "would be cut to a distance measured along the wrong axis of "
                    "the panel. A member is measured between the frame members "
                    "it crosses"
                )
                continue
            # The seat has to fit in what is left of the channel ABOVE the
            # clearance under it. Checked against the two together rather than
            # against the depth alone: a 12 mm seat in a 12 mm channel with a
            # 3 mm margin is a member bottoming out in a channel whose whole
            # point is to keep 3 mm under it, and the depth-only check called
            # that fine.
            seat = target.channel_depth_mm - target.insertion_margin_mm
            if engagement > seat:
                errors.append(
                    f"infill member {member.key!r}: seats {engagement} mm into "
                    f"frame slot {ref!r}, which offers {seat} mm "
                    f"(channel {target.channel_depth_mm} mm less "
                    f"{target.insertion_margin_mm} mm of insertion clearance) — "
                    f"the member would be cut {engagement - seat} mm too long on "
                    "every bay and would stand proud of the frame it is meant to "
                    "sit in"
                )
        housed = any(
            frame_by_key[r].channel_depth_mm > 0
            for r in (member.base_ref, member.top_ref) if r in frame_by_key
        )
        if member.joint != "butt" and not housed and not (
                member.base_engagement_mm or member.top_engagement_mm):
            # The conjunction the spec states: zero engagement AND no channel to
            # engage. A member named `channel` that seats nothing into a slot
            # that houses nothing is cut exactly as a butt joint cuts it, and
            # would be DRAWN as a housed one.
            errors.append(
                f"infill member {member.key!r}: joint={member.joint!r} with no "
                "engagement at either end and no channel in either frame slot "
                "claims a mechanic the numbers do not have — the member is cut "
                "exactly as a butt joint would cut it. Give it a "
                "base_engagement_mm/top_engagement_mm, or call the joint 'butt'"
            )
    return errors


def _part_errors(
    model: FenceModel, catalog: Catalog, library: PartLibrary
) -> list[str]:
    """Every part this model names, checked where the specification now lives.

    This is what replaced the slot-level "no eligible product". Members are a
    MATCHING-time artifact and resolution does not populate them, so that rule
    could no longer pass for any model — it would refuse the whole portfolio for an
    empty list that is empty by design. The guardrail is not dropped, it moves one
    level down: a part no product covers is refused by `validate_part`, in the
    voice this function already used and at the same moment.

    Deduped by part_id, because one part backing four slots is one fact about the
    library and an author cannot fix it four times.
    """
    from fenceai.parts.resolve import part_requirements
    from fenceai.parts.validate import validate_part

    errors: list[str] = []
    named = {req.part_id for _, req in part_requirements(model) if req.part_id}
    for part_id in sorted(named):
        # Never None: `resolve_model_parts` raised for any part_id with no active
        # version before this function could be reached.
        errors += validate_part(library.latest_active(part_id), catalog)
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
        for _, req in spec_requirements(spec)
        for m in req.eligibility.members
        if m.sku not in catalog.products
    })


def predicate_skus(eligibility: Eligibility, catalog: Catalog) -> list[str] | None:
    """Which products a spec-declared slot could be built from, or None if unknowable.

    The import is deferred because `match.py` imports this module for
    `Eligibility`/`EligibleItem`. Asking the MATCHER rather than walking the catalog
    here is the whole point — a second copy of the covering rule is how the two
    would eventually disagree about what counts as a match — and it is the same
    reason `parts.validate.matching_skus` is expressed in terms of this function
    rather than repeating the walk a third time.

    `None`, distinct from `[]`: the predicate asks about the bay it is being fitted
    to, which does not exist yet. "Nothing is eligible" would be a false answer to a
    question nobody asked; `no_eligible_item` still reports it per bay.
    """
    from fenceai.fencemodel.match import match_eligibility

    if any(p.split(".", 1)[0] != "item" for p in field_paths(eligibility.predicate)):
        return None
    return [m.sku for m in match_eligibility(eligibility, catalog, {}).members]


def _predicate_errors(
    key: str, eligibility: Eligibility, admitted: list[str] | None
) -> list[str]:
    """A slot that declares what it NEEDS rather than naming products.

    `admitted` is `predicate_skus`' answer, passed IN rather than computed here
    because the caller needs the same list for the slot rules below it — an option
    naming a product this slot cannot buy, a length no candidate can cut. Matching
    the catalog twice for one slot would be the cost of hiding that.
    """
    errors: list[str] = []
    if eligibility.members:
        errors.append(
            f"slot {key}: eligibility declares a predicate AND names members. A "
            "slot says what it needs or which products it accepts, never both — "
            "intersecting the two lists has more than one defensible reading"
        )
        return errors
    if admitted is None:
        return errors
    if not admitted:
        errors.append(
            f"slot {key}: no item in the catalog covers this spec, so nothing "
            "could ever supply it. Same reason an empty member list is refused — "
            "it would publish cleanly and then report `no_eligible_item` on "
            "every bay of every job built to this model"
        )
    return errors


def _post_slot_errors(post: PostSlot, catalog: Catalog) -> list[str]:
    """The post and its cap, checked like any other slot — plus the cycle rule.

    A post predicate may read only HEIGHT-derived facts about the bay. The clear
    opening is measured to the post faces, so a post chosen by that opening would
    be choosing itself; the resolution order is a DAG only while this holds:

        height -> rail positions -> post -> clear width -> infill fit

    Caught here, where it is a typo an author can fix, rather than at generation,
    where the same mistake is either a hang or an arbitrary answer that comes out
    looking measured.
    """
    errors: list[str] = []
    for what, req in (("post", post.requirement), ("cap", post.cap)):
        if req is None:
            continue
        if req.eligibility.predicate is not None:
            errors += _predicate_errors(f"{post.key} ({what})", req.eligibility, catalog)
            continue
        # The emptiness rule is narrowed rather than dropped: a slot's products come
        # from the part it names, `parts.resolve` fills the predicate above, and an
        # unresolved document has an empty list for a reason that is not an authoring
        # error — `validate_part` carries that refusal one level down. A slot naming
        # NO part and declaring nothing is the old case exactly, and it is still the
        # one that would publish cleanly and then fail on every job.
        if not req.part_id and not req.eligibility.members:
            errors.append(
                f"slot {post.key} ({what}): names no part and declares no eligible "
                "product, so nothing could ever be bought for it"
            )
        for m in req.eligibility.members:
            if m.sku not in catalog.products:
                errors.append(
                    f"slot {post.key} ({what}): eligible sku {m.sku} is not in the "
                    f"catalog")

    for what, req in (("post", post.requirement), ("cap", post.cap)):
        if req is not None and req.eligibility.predicate is not None:
            errors += _post_namespace_errors(
                post.key, what, req.eligibility.predicate, may_read_post=what == "cap",
            )
    return errors


def _post_namespace_errors(
    key: str, what: str, predicate: Expr, *, may_read_post: bool
) -> list[str]:
    """What a post's — or its cap's — predicate is allowed to know.

    The generator supplies exactly three namespaces here: `item` (the candidate),
    `panel` narrowed to `POST_PREDICATE_PANEL_FACTS`, and `post` — narrowed to
    `POST_PREDICATE_POST_FACTS` for a post, and the whole item it caps for a CAP.
    Anything else evaluates to a `MissingField`, which the matcher reads as "has
    not covered the requirement" — so the predicate would match NOTHING and the
    slot would fall silently through to the company default. Refused here, where
    it is a typo an author can fix.

    A post may read where it STANDS and not what it IS, and that is the cycle
    rule in its second form: a post chosen by the post it is has no first answer,
    while a post chosen by the corner it turns has one before the fence is laid
    out. A cap reads the whole post, because the post is already chosen — which
    is the whole reason `cap` nests inside `PostSlot`.
    """
    errors: list[str] = []
    for path in sorted(field_paths(predicate)):
        head, _, field = path.partition(".")
        if head == "item" or (head == "post" and may_read_post):
            continue
        if head == "panel" and field in POST_PREDICATE_PANEL_FACTS:
            continue
        if head == "post" and field in POST_PREDICATE_POST_FACTS:
            continue
        if head == "panel":
            errors.append(
                f"slot {key} ({what}): may not read panel.{field} — the clear "
                f"opening is measured TO the post faces, so a post chosen by it "
                f"would be choosing itself. A post is resolved from the bay's "
                f"HEIGHT, before any width is known; readable: "
                + ", ".join(f"panel.{f}" for f in sorted(POST_PREDICATE_PANEL_FACTS))
            )
        elif head == "post":
            errors.append(
                f"slot {key} ({what}): a post may not be matched on post.{field} "
                f"— it would be choosing itself. A post reads only where it "
                f"STANDS ("
                + ", ".join(f"post.{f}" for f in sorted(POST_PREDICATE_POST_FACTS))
                + "), which the topology settles before any bay is laid out; "
                f"everything the post IS is read by the CAP, because the post is "
                f"chosen first"
            )
        else:
            errors.append(
                f"slot {key} ({what}): nothing supplies {path} when a post is "
                f"resolved, so this predicate would match no product at all and "
                f"the company default would answer instead. Readable: item.*"
                + (", post.*" if may_read_post else
                   ", " + ", ".join(f"post.{f}"
                                    for f in sorted(POST_PREDICATE_POST_FACTS)))
                + ", " + ", ".join(f"panel.{f}"
                                   for f in sorted(POST_PREDICATE_PANEL_FACTS))
            )
    return errors


# What a VARIANT condition may read while still being answerable at a post's own
# station: the post-time panel facts that `PanelContext.condition_ctx` also
# supplies. `panel.width_mm` is the one it excludes, and deliberately — a post
# stands between two bays that need not be the same width, so there is no width
# to answer with.
_POST_TIME_CONDITION_PATHS = frozenset({"panel.height_mm", "panel.vertical"})


def _variant_reach_errors(model: FenceModel) -> list[str]:
    """A post matched on rail positions must be matched on the RIGHT rails.

    Which spec a bay is built to is `choose_variant`'s answer, and at a post's
    station it is answered from the height and the vertical mode alone. A variant
    that turns on the bay's WIDTH cannot be evaluated there — it would come back
    "not applicable", the default spec's rails would be handed to the predicate,
    and the post would be matched against a panel the fence does not build.

    Refused only when the two features actually meet: a model may have
    width-conditioned variants, or a post predicate reading `rail_positions_mm`,
    and neither alone is a problem.
    """
    if model.post is None:
        return []
    predicate = model.post.requirement.eligibility.predicate
    if predicate is None or "panel.rail_positions_mm" not in field_paths(predicate):
        return []
    errors: list[str] = []
    for index, variant in enumerate(model.variants):
        for path in sorted(field_paths(variant.condition) - _POST_TIME_CONDITION_PATHS):
            errors.append(
                f"variant {index}: its condition reads {path}, which is not known "
                f"at a post's own station — and slot {model.post.key} is matched on "
                f"panel.rail_positions_mm, so the post would be chosen against the "
                f"DEFAULT spec's rails while the bay is built to this variant's. "
                f"Readable there: " + ", ".join(sorted(_POST_TIME_CONDITION_PATHS))
            )
    return errors


def _assembly_step_errors(model: FenceModel) -> list[str]:
    """The rules that keep an instruction from being a paragraph.

    A step names slots because that is what makes it DATA: the film can order
    itself by it, the parts of a panel can be split by it, and a slot no step
    places is a gap something can report. The checks follow from that and from
    nothing else.

    Slots are collected across the default spec AND every variant, because a
    variant's panel is still this model's panel — refusing a step for naming a
    slot the default lacks would leave a model unable to say how its own variants
    go together.
    """
    if not model.assembly:
        return []            # no opinion, exactly as an empty `post` is
    # `spec_members`, not `spec_requirements`: a contained piece is a member of
    # the panel and obligation 9 says every member is placed by exactly one step
    # or reported `unplaced`. A step that could not name one would leave the
    # hinges in a gate kit permanently unplaceable — the check green, the fitter
    # short two hinges.
    known = {key for spec in [model.default_spec, *(v.spec for v in model.variants)]
             for key, _ in spec_members(spec)}
    errors: list[str] = []
    seen_keys: set[str] = set()
    placed_by: dict[str, str] = {}
    for step in model.assembly:
        if step.key in seen_keys:
            errors.append(
                f"assembly step {step.key}: two steps share this key, so a "
                f"reference to it names both")
        seen_keys.add(step.key)
        if step.kind == "assembly" and not step.slots:
            errors.append(
                f"assembly step {step.key}: an assembly step fits parts and this "
                f"one names none. An instruction that is only text is a doc, and "
                f"a fence model is not a document — if it fits nothing, it is an "
                f"installation step and should say so")
        for slot in step.slots:
            if slot not in known:
                errors.append(
                    f"assembly step {step.key}: no slot named {slot} in this "
                    f"model, so the step would place nothing on every job built "
                    f"to it")
            elif slot in placed_by:
                errors.append(
                    f"assembly step {step.key}: slot {slot} is already fitted by "
                    f"step {placed_by[slot]}. A part is fitted once — two steps "
                    f"naming it is a contradiction, not an ordering")
            else:
                placed_by[slot] = step.key
    return errors


def _credit_errors(model: FenceModel, roles_known: bool) -> list[str]:
    """A credit that would remove a purchase, checked where it can still be fixed.

    A credit is the one construct here that makes the panel buy LESS, so every
    way of getting it wrong is a saving nobody earned — and a saving is invisible
    on a BOM, because the line simply is not there. That asymmetry is why the
    rules below refuse rather than warn: under-crediting costs a customer one
    spare hinge, over-crediting hands a fitter a gate with nothing to hang it on.

    Slot keys are collected across the default spec AND every variant, exactly as
    an assembly step's are, because a variant's panel is still this model's
    panel. A credit whose target is missing from the ONE bay being built is a
    different fact and is warned about per bay (`contained_credit_unmatched`) —
    that one is not answerable here.

    `roles_known` is False when `validate_model` was given no library: roles are
    filled from the part, so without one every role reads `""` and the agreement
    check below would refuse every credit in the portfolio for a fact nobody has
    looked up yet. Skipped rather than guessed, exactly as the width and
    thickness rules are.
    """
    errors: list[str] = []
    specs = [model.default_spec, *(v.spec for v in model.variants)]
    role_of = {key: role for spec in specs for key, role in spec_members(spec)}
    for spec in specs:
        for key, req in spec_requirements(spec):
            contained = dict(walk_contained(req.contained, key))
            for relative, target in sorted(req.credits.items()):
                path = contained_path(key, relative)
                piece = contained.get(path)
                if piece is None:
                    errors.append(
                        f"slot {key}: credits {relative!r}, which is not a piece "
                        f"contained in this slot — nothing would be credited on "
                        f"any bay of any job built to this model"
                    )
                    continue
                if target == key:
                    errors.append(
                        f"slot {key}: {relative!r} credits its own container. A "
                        "piece cannot supply the thing it arrived inside — the "
                        "panel would stop buying the container that brings it"
                    )
                    continue
                if target not in role_of:
                    errors.append(
                        f"slot {key}: {relative!r} credits slot {target}, which "
                        f"no spec of this model declares, so the credit would "
                        f"land on nothing on every bay of every job"
                    )
                    continue
                if roles_known and piece.role != role_of[target]:
                    errors.append(
                        f"slot {key}: {relative!r} is a {piece.role or '(no role)'} "
                        f"and credits slot {target}, which is a "
                        f"{role_of[target] or '(no role)'}. A credit removes a "
                        "purchase; removing a different kind of part than the one "
                        "that arrived is a fence one part short with nobody told"
                    )
    return errors


def validate_model(
    model: FenceModel, catalog: Catalog, library: PartLibrary | None = None
) -> list[str]:
    """Every reason this model cannot be used, as English strings for the author.

    Checked once at load so resolution can trust the data. These are authoring
    errors, not user-facing warnings, so they carry no code+params.

    `library` RESOLVES the model before any of it is read, because three of these
    rules ask about numbers a slot no longer carries: a member's width, a frame
    member's thickness and a slot's eligible products all arrive from the part the
    slot names. Validating the authored document for those is validating a document
    nobody builds — it refuses every model in the portfolio for facts that have not
    been looked up yet.

    `None` means the caller has no library and therefore cannot answer those three.
    They are SKIPPED, not guessed and not failed: every other rule — the option
    axes, the refs, the joint arithmetic that reads only authored numbers, the
    unbuilt features — still runs, and a caller with a library gets the lot.

    A part with no active version ends the check immediately. Nothing further is
    answerable about a document that cannot be resolved, and a page of consequential
    errors underneath the one real cause is how an author is sent to the wrong file.
    """
    errors: list[str] = []
    if library is not None:
        from fenceai.parts.resolve import resolve_model_parts
        try:
            model, _ = resolve_model_parts(model, library)
        except ValueError as e:
            return [str(e)]
        errors += _part_errors(model, catalog, library)
    axis_keys = {a.key for a in model.option_axes}
    axis_values = {a.key: {v.key for v in a.values} for a in model.option_axes}

    errors += _unsupported_features(model)
    if model.post is not None:
        errors += _post_slot_errors(model.post, catalog)
        errors += _variant_reach_errors(model)
    errors += _assembly_step_errors(model)
    errors += _credit_errors(model, roles_known=library is not None)

    for axis in model.option_axes:
        for value in axis.values:
            if value.swatch is not None and not _SWATCH.match(value.swatch):
                errors.append(
                    f"axis {axis.key} value {value.key}: swatch must be #rrggbb, "
                    f"got {value.swatch!r}"
                )

    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
        errors += _joint_errors(spec, dimensions_known=library is not None)

        # Part-derived, so unanswerable without a library: `Member.width_mm` is 0
        # in the authored document and filled by `parts.resolve`, and a width of 0
        # trips both rules below on every infill member ever authored.
        pattern = spec.infill.pattern if (spec.infill and library is not None) else []
        for member in pattern:
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

        reqs = spec_requirements(spec)
        seen: set[str] = set()
        # Over MEMBERS rather than requirements, so a contained piece's path key
        # is held to the same uniqueness a slot key always had: `slot_key` is the
        # identity `demand`, the structure sheet's `(element, slot)` map, the
        # elevation and the panel canvas all address a part by, and two members
        # answering to one key is two parts the reader cannot tell apart.
        for key, _ in spec_members(spec):
            if key in seen:
                errors.append(f"duplicate slot key {key!r}")
            seen.add(key)
        for key, _ in reqs:
            if PATH_SEP in key:
                # A path key is `<container>/<piece>`, built by `contained_path`.
                # An AUTHORED key holding the separator could spell a path some
                # container would also produce, and then one string would address
                # two different pieces — which is the identity failure this whole
                # scheme exists to avoid, arriving by the front door.
                errors.append(
                    f"slot key {key!r} contains {PATH_SEP!r}, which is reserved "
                    "for the path of a part contained inside another part"
                )
        for key, req in reqs:
            skus = [m.sku for m in req.eligibility.members]
            if req.eligibility.predicate is not None:
                # After resolution EVERY part-named slot lands here — the normal
                # path, not the rare one — so `continue`ing past the rules below
                # dropped four of them on the whole portfolio: an option_axis naming
                # an axis the model does not declare, an option naming a product the
                # slot cannot buy, and both directions of the length_rule check. All
                # four are about the SLOT and hold however its eligibility was said.
                # The narrowing in `resolve._chosen_option` cites the first two BY
                # NAME as load-time guarantees, and with them gone it fell through to
                # `unnarrowed` — the user's colour choice silently ignored.
                admitted = predicate_skus(req.eligibility, catalog)
                errors += _predicate_errors(key, req.eligibility, admitted)
                # A predicate names no skus of ITS own; the products it admits are
                # what the matcher admits. `None` (the predicate asks about a bay
                # that does not exist yet) leaves the sku-driven rules unanswerable,
                # which is not the same as failing them.
                skus = admitted if admitted is not None else []
            elif not req.part_id and not skus:
                # A slot with neither a predicate nor members is an UNRESOLVED slot,
                # not an empty one — PROVIDED it names a part, because that is where
                # its products come from. The refusal that used to live here — a slot
                # nothing can supply publishes cleanly and then reports
                # `no_eligible_item` on every bay of every job built to it — is now
                # `validate_part`'s, in the same voice and at the same moment, over
                # the object that actually says what may supply it.
                #
                # A slot that names NO part and declares nothing is still the old
                # refusal's case, and it is the one the empty `part_id` default could
                # otherwise let through silently.
                errors.append(
                    f"slot {key}: names no part and declares no eligible product, "
                    "so nothing could ever be bought for it"
                )
            for sku in skus:
                if sku not in catalog.products:
                    errors.append(f"slot {key}: eligible sku {sku} is not in the catalog")
                elif req.length_rule is not None and not _can_supply_length(catalog, sku):
                    errors.append(
                        f"slot {key}: {sku} cannot supply a length "
                        f"(not divisible, declares no capabilities.length_mm)"
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
