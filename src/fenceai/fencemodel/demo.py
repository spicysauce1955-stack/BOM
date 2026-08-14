"""Built-in models. M-LEGACY is the compatibility path: a run with no fence_model
event resolves to it, and it must reproduce today's behaviour exactly.

It declares centre_to_centre deliberately. golden-scenarios.md:23 says rails are
cut to "clear width" while demand/derive.py:63 cuts to span.width_mm, which is
centre-to-centre. That disagreement predates this work and CLAUDE.md forbids
reconciling it silently, so M-LEGACY preserves the CODE's behaviour and the
scenario text is settled separately through the golden-scenarios skill.

M-SLAT is the other kind: a real product line, free to be whatever the mechanism
can express, and therefore the model that says what the mechanism can express.
Both are built by a function taking their skus, because the structure is the
model's and the products are the project's.

It has two versions, which is the third kind of built-in: v1 is what every
existing job resolved and must keep resolving, and v2 is the same line drawn
with a joint. A version is immutable (ADR-0006), so demonstrating a new feature
means adding a document, never editing v1 — a stored run stamped M-SLAT@v1 has
to come back the same panel.
"""

from __future__ import annotations

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FixingRule, FrameSlot,
    FromBottom, FromTop, InfillSpec, Member, PanelSpec, PartRequirement,
)


def legacy_model(rail_sku: str = "RAIL-3000", screw_sku: str = "SCREW-S10") -> FenceModel:
    """The model's eligibility is seeded from the run's resolved demand skus, so
    a knowledge DefaultComponent change still reaches the BOM."""
    return FenceModel(
        id="M-LEGACY", version=1,
        name_i18n={"en": "Legacy panel", "he": "פאנל מורשת"},
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal",
                placement=Distributed(count=2, count_param="rails_per_span"),
                requirement=PartRequirement(
                    role="rail", qty=1, length_rule="centre_to_centre",
                    eligibility=Eligibility(
                        members=[EligibleItem(sku=rail_sku, priority=1)]),
                ),
            )],
            fixings=[FixingRule(
                key="screw", basis="per_panel", qty_per_basis=8,
                qty_param="screws_per_span",
                requirement=PartRequirement(
                    role="screw", qty=1,
                    eligibility=Eligibility(
                        members=[EligibleItem(sku=screw_sku, priority=1)]),
                ),
            )],
        ),
    )


def slat_model(
    slat_sku: str = "SLAT-100",
    rail_sku: str = "RAIL-3000",
    screw_sku: str = "SCREW-S10",
) -> FenceModel:
    """A screwed slat panel: two rails spread up the height, slats fitted across
    the clear width, two screws wherever a slat crosses a rail.

    The fixing basis is the reason the frame and the infill run at right angles
    to each other. `per_member_crossing` counts members x frame members, which is
    a real crossing only when the two are perpendicular — distributed rails are
    horizontal (`Distributed`: "spread over the panel height"), so the slats are
    the vertical run, and 20 slats over two rails is 40 crossings and 80 screws.
    Parallel members would still multiply to a number, and the number would be a
    fiction.

    It stays a plain panel — no variant by height, no colour axis, no max-span
    contribution — even though the resolver now honours all three. That is a
    choice about the DEMO, not a limit: this is the built-in a fresh database
    seeds and the compatibility fixtures compare against, so it should stay the
    simplest thing that exercises the infill path end to end. A model that shows
    off variants and axes is one an author builds, which is the point.
    """
    return FenceModel(
        id="M-SLAT", version=1,
        name_i18n={"en": "Slat panel", "he": "פאנל שלבים"},
        grade="residential", status="active",
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal",
                # The count stays knowledge's, because rails ladder with height
                # and that is a number a company rule may own. centre_to_centre
                # is not a fresh judgement either: while golden-scenarios.md and
                # derive.py disagree about which width a rail is cut to, a second
                # model answering the other way would settle that disagreement by
                # arithmetic instead of through the skill that owns it.
                placement=Distributed(count=2, count_param="rails_per_span"),
                requirement=PartRequirement(
                    role="rail", qty=1, length_rule="centre_to_centre",
                    eligibility=Eligibility(
                        members=[EligibleItem(sku=rail_sku, priority=1)]),
                ),
            )],
            infill=InfillSpec(
                orientation="vertical",
                justification="spread_to_fit", excess="space", edge_margin_mm=0,
                pattern=[Member(
                    key="slat", width_mm=100, gap_after_mm=20,
                    requirement=PartRequirement(
                        # `panel_height`, not a width rule: a slat is cut to the
                        # panel's height. Every other LengthRule derives from the
                        # bay's width, and one of those on a vertical member would
                        # put 2400 on a cut list for a part the fence cuts to
                        # 1800. Leaving it off is not the safe alternative either
                        # — a divisible product asked for with no cut length
                        # plans no bars, so the panel would price no slats at all
                        # and the ledger would report every one of them as
                        # covered from stock.
                        role="infill", qty=1, length_rule="panel_height",
                        eligibility=Eligibility(
                            members=[EligibleItem(sku=slat_sku, priority=1)]),
                    ),
                )],
            ),
            fixings=[FixingRule(
                key="screw", basis="per_member_crossing", qty_per_basis=2,
                requirement=PartRequirement(
                    role="screw", qty=1,
                    eligibility=Eligibility(
                        members=[EligibleItem(sku=screw_sku, priority=1)]),
                ),
            )],
        ),
    )


def channel_slat_model(
    slat_sku: str = "SLAT-100",
    rail_sku: str = "RAIL-3000",
    channel_sku: str = "CHANNEL-3000",
    screw_sku: str = "SCREW-S10",
) -> FenceModel:
    """M-SLAT v2: the same product line, built with a joint.

    The slats sit in a 20 mm U-channel at the bottom and run up under a top
    rail, so the cut length is the opening between the two members plus the
    15 mm that disappears into the channel — 1665 mm in an 1800 mm bay, where
    v1's `panel_height` slat is 1800. That difference is the whole point of the
    version: the two panels draw the same and are cut 135 mm apart.

    The 3 mm `insertion_margin_mm` is the clearance a fitter needs to tip a slat
    into the channel before dropping it in. It shortens nothing on its own — what
    the slat is cut to is the 15 mm engagement — but it is why the engagement is
    15 and not 20, and the model is where that reason can be written down.

    The fixings change with the joint rather than beside it: a slat held by a
    channel is not screwed at the bottom, so `per_member_crossing` (v1's rule,
    which counts every slat against every rail) would buy screws for a joint that
    has none. One screw per slat, at the top rail.

    Authored as a DRAFT, and that is a claim about publishing rather than about
    the document. `latest_active` is what an unpinned project resolves, so
    seeding this active would move every existing M-SLAT job onto a different cut
    list at the next generation, silently — the exact change `preview_model_impact`
    exists to put in front of someone first. A draft is selectable by pin,
    previewable, and editable, which is everything a demonstration needs.
    """
    return FenceModel(
        id="M-SLAT", version=2, status="draft",
        name_i18n={"en": "Slat panel (channel)", "he": "פאנל שלבים (תעלה)"},
        grade="residential",
        default_spec=PanelSpec(
            frame=[
                FrameSlot(
                    key="bottom_channel", orientation="horizontal",
                    # A fixed height off the bay's bottom, not a distributed
                    # position: the channel is where the slats land, so its
                    # height is structure, and a knowledge param that moved it
                    # would move every slat's cut length with it.
                    placement=FromBottom(offset_mm=50),
                    # the face height and the housing are the CHANNEL's, which is
                    # why the slot names its own product rather than reusing the
                    # rail: one SKU cannot be 40 mm tall in one panel and 60 in
                    # another, and the slats' cut length depends on which it is.
                    thickness_mm=60, joint="channel",
                    channel_depth_mm=20, insertion_margin_mm=3,
                    requirement=PartRequirement(
                        role="rail", qty=1, length_rule="centre_to_centre",
                        eligibility=Eligibility(
                            members=[EligibleItem(sku=channel_sku, priority=1)]),
                    ),
                ),
                FrameSlot(
                    key="top_rail", orientation="horizontal",
                    placement=FromTop(offset_mm=50),
                    thickness_mm=40,
                    requirement=PartRequirement(
                        role="rail", qty=1, length_rule="centre_to_centre",
                        eligibility=Eligibility(
                            members=[EligibleItem(sku=rail_sku, priority=1)]),
                    ),
                ),
            ],
            infill=InfillSpec(
                orientation="vertical",
                justification="spread_to_fit", excess="space", edge_margin_mm=0,
                pattern=[Member(
                    key="slat", width_mm=100, gap_after_mm=20,
                    base_ref="bottom_channel", top_ref="top_rail",
                    # `channel` names the BASE joint, which is the one with a
                    # mechanic; the top end butts under the rail and takes no
                    # engagement. One kind per member is what the schema has, and
                    # naming the end that changes the cut length is the honest
                    # use of it — the elevation reports each end's engagement
                    # separately, so nothing downstream has to read this as both.
                    joint="channel", base_engagement_mm=15, top_engagement_mm=0,
                    requirement=PartRequirement(
                        role="infill", qty=1, length_rule="between_frame",
                        eligibility=Eligibility(
                            members=[EligibleItem(sku=slat_sku, priority=1)]),
                    ),
                )],
            ),
            fixings=[FixingRule(
                key="screw", basis="per_member", qty_per_basis=1,
                requirement=PartRequirement(
                    role="screw", qty=1,
                    eligibility=Eligibility(
                        members=[EligibleItem(sku=screw_sku, priority=1)]),
                ),
            )],
        ),
    )


M_LEGACY = legacy_model()
M_SLAT = slat_model()
M_SLAT_V2 = channel_slat_model()


def demo_models() -> dict[str, FenceModel]:
    """The built-in LINE: one document per id, the one an unpinned project gets.

    Keyed by id, so it can hold exactly one version each — which is the right
    shape for the question it answers ("what does choosing M-SLAT give me?") and
    the wrong one for seeding, now that a built-in has two versions."""
    return {M_LEGACY.id: M_LEGACY, M_SLAT.id: M_SLAT}


def demo_model_versions() -> list[FenceModel]:
    """Every built-in DOCUMENT, including the ones that are not the active
    version of their line — what a fresh store seeds, each with its own status.

    An id's versions in ascending order, so a seed loop that stops early leaves a
    line's history intact rather than its future."""
    return [M_LEGACY, M_SLAT, M_SLAT_V2]
