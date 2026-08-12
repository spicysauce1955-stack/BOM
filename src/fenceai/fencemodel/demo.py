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
"""

from __future__ import annotations

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FixingRule, FrameSlot,
    InfillSpec, Member, PanelSpec, PartRequirement,
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


M_LEGACY = legacy_model()
M_SLAT = slat_model()


def demo_models() -> dict[str, FenceModel]:
    return {M_LEGACY.id: M_LEGACY, M_SLAT.id: M_SLAT}
