"""Built-in models. M-LEGACY is the compatibility path: a run with no fence_model
event resolves to it, and it must reproduce today's behaviour exactly.

It declares centre_to_centre deliberately. golden-scenarios.md:23 says rails are
cut to "clear width" while demand/derive.py:63 cuts to span.width_mm, which is
centre-to-centre. That disagreement predates this work and CLAUDE.md forbids
reconciling it silently, so M-LEGACY preserves the CODE's behaviour and the
scenario text is settled separately through the golden-scenarios skill.

M-SLAT is the other kind: a real product line, free to be whatever the mechanism
can express, and therefore the model that says what the mechanism can express.
Both are built by a function taking their PARTS, because the structure is the
model's and what goes in each slot is the library's. They took skus before the
part library existed; the argument moved down one level and kept its reason.

M-LEGACY did NOT move, and that is the one deliberate exception. Its eligibility
is not authored — it is rebuilt at generation from the run's resolved
`demand_skus` (`generator._pick_model`), so a knowledge `DefaultComponent` still
reaches the BOM. A part_id would freeze a SKU in front of that rule and silently
outrank it, which is the failure that seam exists to prevent. It therefore also
still carries its own `role`, because nothing resolves one for it.

It has two versions, which is the third kind of built-in: v1 is what every
existing job resolved and must keep resolving, and v2 is the same line drawn
with a joint. A version is immutable (ADR-0006), so demonstrating a new feature
means adding a document, never editing v1 — a stored run stamped M-SLAT@v1 has
to come back the same panel.
"""

from __future__ import annotations

from fenceai.core.gaps import SourceRef
from fenceai.core.warnings import DocumentWarning, WarningTarget
from fenceai.fencemodel.model import (
    AssemblyStep, Distributed, Eligibility, EligibleItem, FenceModel, FixingRule,
    FrameSlot,
    FromBottom, FromTop, InfillSpec, Member, PanelSpec, PartRequirement, PostSlot,
    Prerequisite,
)
from fenceai.knowledge.ast import And, Cmp, FieldRef, In, Lit, Or


def legacy_model(rail_sku: str = "RAIL-3000", screw_sku: str = "SCREW-S10") -> FenceModel:
    """The model's eligibility is seeded from the run's resolved demand skus, so
    a knowledge DefaultComponent change still reaches the BOM.

    Hence the only two slots in the built-ins that still author `role` and
    `eligibility` directly: this document is already RESOLVED when it is built, by
    knowledge rather than by the part library. `parts.resolve` leaves a requirement
    naming no part exactly as it found it, which is what keeps that seam open."""
    return FenceModel(
        id="M-LEGACY", version=1,
        name_i18n={"en": "Legacy panel", "he": "פאנל מורשת"},
        # Two warnings, and they are here rather than only on M-VINYL for one
        # reason: this is the document nearly every run in the repo is built to,
        # so it is the only one that puts an ANNEXE on a plan that goes to site
        # and a product notice on a BOM line a buyer reads. A surface nothing
        # reaches is a surface nobody notices is wrong.
        #
        # Both are UNATTRIBUTED, and that is the honest state of a legacy
        # document: nobody traced it, and §1.1 forbids this side from minting a
        # `SourceRef` to pretend otherwise. M-VINYL carries the cited case.
        warnings=[
            DocumentWarning(
                text_raw="WARNING: This fence is not a pool barrier and must "
                         "not be relied on as one.",
                lang="en", severity_lexeme="WARNING",
                attaches_to=WarningTarget(kind="document"),
            ),
            DocumentWarning(
                text_raw="Pre-drill this rail before screwing it to the post "
                         "face; driving cold splits the end.",
                lang="en", severity_lexeme="NOTICE",
                attaches_to=WarningTarget(kind="product", ref=rail_sku),
            ),
        ],
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
    slat_part: str = "infill-slat-100",
    rail_part: str = "rail-rail-3000",
    screw_part: str = "screw-screw-s10",
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
                    part_id=rail_part, qty=1, length_rule="centre_to_centre"),
            )],
            infill=InfillSpec(
                orientation="vertical",
                justification="spread_to_fit", excess="space", edge_margin_mm=0,
                pattern=[Member(
                    key="slat", gap_after_mm=20,
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
                        part_id=slat_part, qty=1, length_rule="panel_height"),
                )],
            ),
            fixings=[FixingRule(
                key="screw", basis="per_member_crossing", qty_per_basis=2,
                requirement=PartRequirement(part_id=screw_part, qty=1),
            )],
        ),
    )


def channel_slat_model(
    slat_part: str = "infill-slat-100",
    rail_part: str = "rail-rail-3000-40",
    channel_part: str = "rail-channel-3000",
    screw_part: str = "screw-screw-s10",
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
                    # why the slot names its own part rather than reusing the
                    # rail: one SKU cannot be 40 mm tall in one panel and 60 in
                    # another, and the slats' cut length depends on which it is.
                    # The 60 mm face is no longer written here — it is the part's
                    # `thickness_mm` and `parts.resolve` fills this field from it,
                    # so the panel can no longer draw one number and buy another.
                    joint="channel",
                    channel_depth_mm=20, insertion_margin_mm=3,
                    requirement=PartRequirement(
                        part_id=channel_part, qty=1,
                        length_rule="centre_to_centre"),
                ),
                FrameSlot(
                    key="top_rail", orientation="horizontal",
                    placement=FromTop(offset_mm=50),
                    requirement=PartRequirement(
                        part_id=rail_part, qty=1,
                        length_rule="centre_to_centre"),
                ),
            ],
            infill=InfillSpec(
                orientation="vertical",
                justification="spread_to_fit", excess="space", edge_margin_mm=0,
                pattern=[Member(
                    key="slat", gap_after_mm=20,
                    base_ref="bottom_channel", top_ref="top_rail",
                    # `channel` names the BASE joint, which is the one with a
                    # mechanic; the top end butts under the rail and takes no
                    # engagement. One kind per member is what the schema has, and
                    # naming the end that changes the cut length is the honest
                    # use of it — the two engagements are separate fields, so
                    # nothing downstream has to read this kind as both ends.
                    joint="channel", base_engagement_mm=15, top_engagement_mm=0,
                    requirement=PartRequirement(
                        part_id=slat_part, qty=1, length_rule="between_frame"),
                )],
            ),
            fixings=[FixingRule(
                key="screw", basis="per_member", qty_per_basis=1,
                requirement=PartRequirement(part_id=screw_part, qty=1),
            )],
        ),
    )


def routed_vinyl_model(
    slat_part: str = "infill-slat-v-150",
    rail_part: str = "rail-rail-v-3000",
) -> FenceModel:
    """M-VINYL: the line that cannot be described without its post.

    A screwed panel is a panel between two posts, and the posts are the company's
    business. A routed vinyl fence is not: the rails do not sit ON the post, they
    go THROUGH it, into holes punched at the factory at fixed heights. So the post
    is part of the product, and it is the only part of it whose eligibility cannot
    be authored as a list of SKUs — which routing is right depends on where THIS
    bay puts its rails, and that is a number no author knows.

    Nor is it one post. The factory cuts the holes before the post ever reaches
    the site, so which FACES are cut is decided by where the post will stand: one
    face at an end, two opposite faces mid-run, two adjacent faces at a corner. A
    14-post run is 2 end + 11 line + 1 corner, not 14 of one SKU — which is why
    a manufacturer asks for the layout before it will quote. The predicate reads
    `post.kind` for exactly that, and `post.kind` is answerable without a cycle
    because it comes from the TOPOLOGY and not from the panel: a node either ends
    a run or turns a corner long before any bay is laid out over it.

    Hence the predicate, and hence the whole resolution order behind it:

        height -> rail positions -> post -> clear width -> infill fit

    A post whose routing disagrees with the panel is not a worse buy. It is a
    fence that cannot be assembled — the holes are already punched — so the
    requirement lives in the post part's SPEC and non-matching posts never become
    candidates at all.

    The cap reads the post it caps, which is answerable only because the post is
    chosen first. That is the whole reason `cap` nests inside `PostSlot`.

    **No fixings, and that is the model saying something true.** A slat held in a
    channel top and bottom is not screwed; M-SLAT's `per_member_crossing` rule
    would buy two screws per slat per rail for a joint that has none. A model that
    carried a fixing rule "for symmetry" would put real money on a real BOM.

    Both members are eligible for ONE product each, so this model demonstrates the
    post spec rather than the supply objective — S15 owns that. The POST is the
    exception and always has been: its candidate set is whatever the predicate
    admits, and it now admits a different product at each kind of station.
    """
    return FenceModel(
        id="M-VINYL", version=1,
        name_i18n={"en": "Routed vinyl privacy fence", "he": "גדר PVC מחורצת"},
        grade="residential", status="active",
        post=PostSlot(
            key="post",
            # Names NO part, and this is the vocabulary's boundary rather than an
            # omission. The predicate below agrees with a fact about the BAY —
            # `item.routed_at_mm == panel.rail_positions_mm` — while a `SpecField`
            # is always `item.<key> <agree> <literal>`. A part declares what a piece
            # IS; it cannot declare where this panel puts its rails. Expressing the
            # routing as a literal `[150, 1650]` would delete every 2100 mm fence.
            requirement=PartRequirement(
                role="post",
                eligibility=Eligibility(predicate=And(items=[
                    Cmp(cmp="==", left=FieldRef(path="item.material"),
                        right=Lit(value="vinyl")),
                    # THE term of the arc. `panel.rail_positions_mm` is
                    # `placement_positions`' answer for the frame slot below,
                    # computed at this post's own station from the bay's height.
                    Cmp(cmp="==", left=FieldRef(path="item.routed_at_mm"),
                        right=FieldRef(path="panel.rail_positions_mm")),
                    # The other half of the same fact: WHICH FACES the factory
                    # cut. Kept as its own conjunct rather than folded into the
                    # term above, because the two fail differently and the
                    # diagnostic depends on telling them apart —
                    # `sole_excluding_term` names the ONE term that excluded
                    # everybody, and "your posts are routed 300 mm from where
                    # this bay wants its rails" (post_routing_mismatch) is a
                    # different sentence from "nothing in this line is cut for a
                    # post where three runs meet".
                    #
                    # A GATE post takes the end post: one panel meets it and goes
                    # into that one routed face, and the leaf hangs off the other
                    # side on hardware rather than through a hole. A TRANSITION —
                    # a step or a change of base — is a line post: a bay each
                    # side, at 180 degrees, exactly like any other mid-run post.
                    #
                    # A JUNCTION is deliberately absent. Three runs meeting needs
                    # a post cut on three faces and this line does not make one,
                    # so the generator refuses that fence by name instead of
                    # quietly standing a two-face post where three panels have to
                    # land. That is the refusal doing its job, not a gap.
                    Or(items=[
                        And(items=[
                            In(item=FieldRef(path="post.kind"),
                               options=["end", "gate"]),
                            Cmp(cmp="==", left=FieldRef(path="item.routed_faces"),
                                right=Lit(value="single")),
                        ]),
                        And(items=[
                            In(item=FieldRef(path="post.kind"),
                               options=["line", "transition"]),
                            Cmp(cmp="==", left=FieldRef(path="item.routed_faces"),
                                right=Lit(value="opposite")),
                        ]),
                        And(items=[
                            In(item=FieldRef(path="post.kind"), options=["corner"]),
                            Cmp(cmp="==", left=FieldRef(path="item.routed_faces"),
                                right=Lit(value="adjacent")),
                        ]),
                    ]),
                ])),
            ),
            # Same boundary: `item.fits_face_mm == post.face_width_mm` reads the
            # post this cap sits on, which is answerable only because the post is
            # chosen first — and is not a fact any part can declare about itself.
            cap=PartRequirement(
                role="cap",
                eligibility=Eligibility(predicate=Cmp(
                    cmp="==", left=FieldRef(path="item.fits_face_mm"),
                    right=FieldRef(path="post.face_width_mm"))),
            ),
        ),
        # How it goes together, in the order a fitter does it. A routed vinyl
        # panel is the line where this matters most: nothing is screwed, so the
        # ORDER is the whole assembly — a board dropped in before its top rail is
        # a board that cannot be dropped in at all.
        #
        # The last step fits nothing and says so by being an `installation` step:
        # curing is an instruction about the job, not about a part.
        assembly=[
            AssemblyStep(
                key="set_posts", scope="post", bay_parts=["post", "footing"],
                text_i18n={
                    "en": "Set every post plumb in its footing, routed faces "
                          "square to the line.",
                    "he": "העמידו כל עמוד אנכית ביסוד שלו, כשהפאות המחורצות "
                          "ניצבות לקו.",
                }),
            AssemblyStep(
                key="cure", kind="installation", scope="site",
                requires=[Prerequisite(step="set_posts", kind="after")],
                text_i18n={
                    "en": "Leave the post footings to cure before loading the "
                          "panels; a routed post carries the fence from its holes.",
                    "he": "הניחו ליסודות העמודים להתקשות לפני העמסת הפאנלים; "
                          "עמוד מחורץ נושא את הגדר מהחורים שלו.",
                }),
            AssemblyStep(
                key="rails", slots=["rail"],
                requires=[Prerequisite(step="set_posts", kind="after")],
                text_i18n={
                    "en": "Slide both rails through the routed holes in the posts, "
                          "channel facing in.",
                    "he": "השחילו את שתי המסילות דרך החורים המחורצים בעמודים, "
                          "כשהתעלה פונה פנימה.",
                }),
            AssemblyStep(
                key="boards", slots=["slat"],
                # TWO different claims, and the reason `requires` has kinds. The
                # rails one is STRICT: a board dropped in before its top rail is a
                # board that cannot be dropped in at all. The cure one is a
                # MINIMUM — the boards must not go in first, but a crew filling
                # the last bay as the first footings finish is not doing anything
                # wrong. A prerequisite LIST could only have said "after both",
                # which is a stronger claim than this guide makes.
                requires=[Prerequisite(step="rails", kind="after"),
                          Prerequisite(step="cure", kind="not_before")],
                text_i18n={
                    "en": "Drop the boards in from above, one at a time, seating "
                          "each into the bottom channel before letting it fall "
                          "under the top rail.",
                    "he": "הכניסו את הלוחות מלמעלה, אחד אחד, כשכל לוח יושב תחילה "
                          "בתעלה התחתונה ורק אז מונח מתחת למסילה העליונה.",
                }),
            AssemblyStep(
                key="cap_posts", scope="post", bay_parts=["cap"],
                requires=[Prerequisite(step="boards", kind="after")],
                text_i18n={
                    "en": "Cap the posts last, once every bay beside them is "
                          "filled and nothing else has to go down a post.",
                    "he": "התקינו את הכיפות בסוף, לאחר שכל המפרשים שלצידן מלאים "
                          "ואין עוד מה להשחיל דרך העמוד.",
                }),
        ],
        # What the guide WARNS, in the words the guide uses (obligation 10).
        # M-VINYL carries these for the same reason it carries all five step
        # scopes: it is the document that exercises the feature, and a surface
        # nothing reaches is a surface nobody notices is wrong.
        #
        # Four kinds on purpose, because they render in four different places:
        # the safety box goes in the ANNEXE (once, never on a line), the cure
        # note goes on its STEP, the pool notice goes on the BOM line for the
        # sku it is about, and the warranty note goes in the annexe beside the
        # safety box. That is the whole of §3.3.5 in one document.
        #
        # `lang="en"` on every one of them, in a Hebrew-first product, and that
        # is not an omission: zero of the corpus's 81,794 elements are Hebrew,
        # a quoted warning renders verbatim in the language it was written in,
        # and offering to translate a manufacturer's liability sentence would be
        # publishing a claim they never made. The surface marks it as quoted and
        # sets the direction from `lang`.
        warnings=[
            DocumentWarning(
                text_raw="CAUTION: In freeze-thaw regions, set every post "
                         "footing below the local frost line. A footing poured "
                         "above the frost line will heave, and a routed fence "
                         "moves with its posts.",
                lang="en", severity_lexeme="CAUTION",
                attaches_to=WarningTarget(kind="document"),
                # An obviously-demo citation, in a file of obviously-demo data.
                # A real one can only come from the Discovery surface: §1.1 makes
                # `SourceRef.id` opaque and forbids building one, which is
                # exactly why `cites` is optional on this side.
                cites=SourceRef(id="DEMO-src-vinyl-1",
                                belongs_to="sha256:DEMO-vinyl-install-guide"),
            ),
            DocumentWarning(
                text_raw="WARNING: Do not load a panel onto a post whose footing "
                         "has not cured. A routed post carries the fence from "
                         "its holes, and one pulled out of plumb early cannot be "
                         "brought back.",
                lang="en", severity_lexeme="WARNING",
                attaches_to=WarningTarget(kind="step", ref="cure"),
                cites=SourceRef(id="DEMO-src-vinyl-2",
                                belongs_to="sha256:DEMO-vinyl-install-guide"),
            ),
            DocumentWarning(
                # UNATTRIBUTED, deliberately: the second rendering a surface has
                # to get right. A warning nobody can trace is still worth
                # carrying and must not look like one that can be checked.
                text_raw="This section is not rated for pool-barrier use.",
                lang="en", severity_lexeme="NOTICE",
                attaches_to=WarningTarget(kind="product", ref="SLAT-V-150"),
            ),
            DocumentWarning(
                text_raw="Warranty is void where components from another "
                         "manufacturer are substituted into this assembly.",
                lang="en", severity_lexeme="IMPORTANT",
                attaches_to=WarningTarget(kind="warranty"),
                cites=SourceRef(id="DEMO-src-vinyl-3",
                                belongs_to="sha256:DEMO-vinyl-warranty"),
            ),
        ],
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal",
                # ONE slot for both rails, insets and all, because the routing is
                # a property of the SET: a post punched at 150 and 1650 is punched
                # for a pair, and two slots placed independently could be moved
                # apart by one edit while the post kept its holes. `count_param`
                # stays, so a company rule asking for three rails is a fence that
                # needs a three-hole post — and correctly finds none rather than
                # quietly building on a two-hole one.
                placement=Distributed(count=2, count_param="rails_per_span",
                                      bottom_inset_mm=150, top_inset_mm=150),
                joint="channel",
                channel_depth_mm=18, insertion_margin_mm=3,
                requirement=PartRequirement(
                    # centre_to_centre, and for once the reason is physical
                    # rather than inherited: a routed rail does not stop at the
                    # post's face, it goes THROUGH it. Cut to the post
                    # centrelines, each end seats half a face deep into the hole
                    # it was punched for. `clear_between_posts` would cut it to
                    # the opening and leave nothing to seat.
                    part_id=rail_part, qty=1, length_rule="centre_to_centre"),
            )],
            infill=InfillSpec(
                orientation="vertical",
                # No gap and no spread. A privacy fence's boards interlock, so
                # `space` — which would widen every gap to absorb the slack — is
                # the one excess this panel must not have: eight 7 mm slots is
                # not a privacy fence. `truncate` leaves the residual whole and
                # `center` halves it into the two edges, where the post's own
                # routed channel takes it up.
                justification="center", excess="truncate", edge_margin_mm=0,
                pattern=[Member(
                    key="slat", gap_after_mm=0,
                    base_ref="rail", top_ref="rail",
                    joint="channel", base_engagement_mm=15, top_engagement_mm=15,
                    requirement=PartRequirement(
                        part_id=slat_part, qty=1, length_rule="between_frame"),
                )],
            ),
        ),
    )


M_LEGACY = legacy_model()
M_SLAT = slat_model()
M_SLAT_V2 = channel_slat_model()
M_VINYL = routed_vinyl_model()


def demo_models() -> dict[str, FenceModel]:
    """The built-in LINE: one document per id, the one an unpinned project gets.

    Keyed by id, so it can hold exactly one version each — which is the right
    shape for the question it answers ("what does choosing M-SLAT give me?") and
    the wrong one for seeding, now that a built-in has two versions."""
    return {M_LEGACY.id: M_LEGACY, M_SLAT.id: M_SLAT, M_VINYL.id: M_VINYL}


def demo_model_versions() -> list[FenceModel]:
    """Every built-in DOCUMENT, including the ones that are not the active
    version of their line — what a fresh store seeds, each with its own status.

    An id's versions in ascending order, so a seed loop that stops early leaves a
    line's history intact rather than its future."""
    return [M_LEGACY, M_SLAT, M_SLAT_V2, M_VINYL]
