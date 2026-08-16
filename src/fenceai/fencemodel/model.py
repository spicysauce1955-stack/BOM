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
from fenceai.knowledge.ast import Expr, field_paths

_SWATCH = re.compile(r"^#[0-9a-fA-F]{6}$")

LengthRule = Literal[
    "clear_between_posts", "centre_to_centre", "overlap", "panel_height",
    # a member cut to fit BETWEEN two frame members, plus whatever seats into
    # them. The only rule that reads `Member.base_ref`/`top_ref`.
    "between_frame",
]

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


class Member(BaseModel):
    key: str
    width_mm: Mm
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
    return product.capabilities.length_mm is not None


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
    return errors


def _joint_errors(spec: PanelSpec) -> list[str]:
    """Joint geometry that would cut a part to the wrong length.

    Every one of these is arithmetic the resolver would otherwise perform
    faithfully on a number the author cannot have meant — and the answer would
    come out as a plain integer on a cut list, indistinguishable from a measured
    one. The failure is per BAY, so a model published with any of them is wrong
    on every panel of every job built to it until someone measures a piece.
    """
    errors: list[str] = []
    frame_by_key = {s.key: s for s in spec.frame}

    for slot in spec.frame:
        if slot.channel_depth_mm > 0 and slot.thickness_mm == 0:
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


def _predicate_errors(key: str, eligibility: Eligibility, catalog: Catalog) -> list[str]:
    """A slot that declares what it NEEDS rather than naming products.

    The import is deferred because `match.py` imports this module for
    `Eligibility`/`EligibleItem`. Validation asking the matcher "would anything
    satisfy this?" is the right direction — the alternative is a second copy of
    the covering rule here, which is how the two would eventually disagree about
    what counts as a match.
    """
    from fenceai.fencemodel.match import match_eligibility

    errors: list[str] = []
    if eligibility.members:
        errors.append(
            f"slot {key}: eligibility declares a predicate AND names members. A "
            "slot says what it needs or which products it accepts, never both — "
            "intersecting the two lists has more than one defensible reading"
        )
        return errors
    reads = field_paths(eligibility.predicate)
    if any(p.split(".", 1)[0] != "item" for p in reads):
        # The predicate asks about the bay it is being fitted to, which does not
        # exist yet. Refusing it here for failing a question nobody asked would
        # be worse than the gap: `no_eligible_item` still reports it per bay.
        return errors
    if not match_eligibility(eligibility, catalog, {}).members:
        errors.append(
            f"slot {key}: no item in the catalog covers this spec, so nothing "
            "could ever supply it. Same reason an empty member list is refused — "
            "it would publish cleanly and then report `no_eligible_item` on "
            "every bay of every job built to this model"
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
        errors += _joint_errors(spec)

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
            if req.eligibility.predicate is not None:
                errors += _predicate_errors(key, req.eligibility, catalog)
                # a predicate slot names no skus of its own; the checks below are
                # about authored ones, and the matcher only ever selects products
                # that are IN the catalog and satisfy the requirement
                continue
            if not skus:
                # A slot nothing can supply publishes cleanly and then reports
                # `no_eligible_item` on every bay of every job built to it. The
                # author is the only person who can say what belongs here, and
                # the moment they can say it is now — not when an estimator finds
                # a panel one part short in a quote.
                errors.append(
                    f"slot {key}: no eligible product, so nothing could ever "
                    f"supply it"
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
