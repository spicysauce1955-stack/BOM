"""Seeing a panel before there is a fence.

The governing property is that the preview is not a second implementation: it
runs the same resolve -> derive -> supply -> fulfil pipeline over a synthetic
one-bay strategy, so it cannot quietly disagree with the fence the user gets.
The last test in this file is the one that keeps that true.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.errors import RequestRefused
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT, M_VINYL
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement,
)
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from tests.conftest import straight_topology


# The library the built-in models name. A preview resolves parts exactly as
# generation does — that is the property this file exists to keep — so every call
# here hands it the same library the route does.
PARTS = PartLibrary(parts=demo_parts())


def preview(model, **kw):
    return preview_panel(model, PreviewRequest(**kw), demo_catalog(),
                         part_library=PARTS)


def by_slot(result):
    return {p.slot_key: p for p in result.parts}


# --- what a panel is made of --------------------------------------------------

def test_the_slat_panel_previews_its_slats_priced_and_cut_to_height():
    result = preview(M_SLAT, height_mm=1800, width_mm=2500)
    parts = by_slot(result)

    assert set(parts) == {"rail", "slat", "screw"}
    assert parts["rail"].qty == 2 and parts["rail"].length_mm == 2500
    assert parts["slat"].length_mm == 1800, "a slat is cut to the panel height"
    assert parts["slat"].qty == 21
    assert parts["screw"].qty == 2 * (21 * 2)
    assert all(p.sku for p in result.parts), "every part names the product chosen"
    assert result.total_cents > 0
    assert result.unsupplied == []


def test_the_legacy_panel_previews_two_rails_and_screws_and_nothing_else():
    parts = by_slot(preview(M_LEGACY, height_mm=1800, width_mm=1500))
    assert set(parts) == {"rail", "screw"}
    assert parts["rail"].qty == 2


def test_the_preview_has_no_posts_caps_or_concrete():
    """A bay's posts depend on neighbours a hypothetical bay does not have, so
    previewing them would be inventing a fence around the panel."""
    assert {p.role for p in preview(M_SLAT).parts} == {"rail", "infill", "screw"}


def test_a_wider_bay_fits_more_slats_and_costs_more():
    narrow = preview(M_SLAT, width_mm=1200)
    wide = preview(M_SLAT, width_mm=3000)
    assert by_slot(wide)["slat"].qty > by_slot(narrow)["slat"].qty
    assert wide.total_cents > narrow.total_cents


def test_a_taller_panel_does_not_change_the_slat_count_only_their_length():
    """The fit runs along the clear width; height is the members' cut length."""
    short, tall = preview(M_SLAT, height_mm=1200), preview(M_SLAT, height_mm=2000)
    assert by_slot(short)["slat"].qty == by_slot(tall)["slat"].qty
    assert by_slot(short)["slat"].length_mm == 1200
    assert by_slot(tall)["slat"].length_mm == 2000


def test_the_whole_candidate_set_is_reported_not_only_the_winner():
    """"Why that product" is what someone comparing two models is looking at."""
    part = by_slot(preview(M_SLAT))["rail"]
    assert part.eligible_skus == ["RAIL-3000"]
    assert part.sku in part.eligible_skus


def test_a_knowledge_resolved_quantity_can_be_handed_in():
    """The preview has no project, so no scope to bind and no knowledge to
    resolve. A caller that knows the numbers passes them; one that does not gets
    the model's authored defaults."""
    assert by_slot(preview(M_SLAT))["rail"].qty == 2
    assert by_slot(preview(M_SLAT, params={"rails_per_span": 3}))["rail"].qty == 3


def test_previewing_is_pure_and_deterministic():
    assert preview(M_SLAT) == preview(M_SLAT)


# --- asking for a specific product, per slot ----------------------------------
#
# The material drawer's whole question: "what does this panel cost in cedar?".
# The rule under test is that the answer NARROWS the slot, exactly as an option
# axis does — it never bypasses eligibility, an approval or a priority.

def two_candidate_model(approval: str = "auto") -> FenceModel:
    """One rail slot with two real candidates, which the built-ins deliberately
    do not have (`slat_model`: "it stays a plain panel"). Without a second
    eligible product a pin narrows nothing, so the rule would be tested against
    a set of one and every assertion would pass by accident.

    RAIL-3000 is a 3000 mm bar at 1800; SLAT-100 is a 6000 mm bar at 5400, and
    both can be cut to a 2500 mm rail — so the two really are alternatives and
    they really do cost different amounts.
    """
    return FenceModel(
        id="M-PIN", version=1,
        name_i18n={"en": "Two-candidate rail", "he": "מסילה עם שני מועמדים"},
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal",
            placement=Distributed(count=2),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(members=[
                    EligibleItem(sku="RAIL-3000", priority=1),
                    EligibleItem(sku="SLAT-100", priority=7, approval=approval),
                ]),
            ),
        )]),
    )


def test_a_pinned_sku_is_the_one_the_panel_is_priced_with():
    """Hand-derived, both ways.

    Two rails of 2500 mm, each charged its 3 mm kerf against (stock + kerf):
      * RAIL-3000 — 2503 + 2503 = 5006 does not fit 3003, so one bar per rail:
        2 x 1800 = 3600.
      * SLAT-100  — 5006 fits 6003, so both rails come off ONE bar: 5400.
    least_cost therefore buys the rail stock unasked, and pinning the slat is a
    real, checkable 1800-cent difference rather than a re-ordered list.
    """
    model = two_candidate_model()
    default = preview(model, height_mm=1800, width_mm=2500)
    pinned = preview(model, height_mm=1800, width_mm=2500,
                     slot_skus={"rail": "SLAT-100"})

    assert by_slot(default)["rail"].sku == "RAIL-3000"
    assert default.total_cents == 3600
    assert by_slot(pinned)["rail"].sku == "SLAT-100"
    assert pinned.total_cents == 5400


def test_the_pin_is_recorded_on_the_resolved_slot_and_narrows_the_candidates():
    """The drawer reads why a product is the chosen one off the slot; "cedar was
    asked for" and "cedar won anyway" are different facts, so the pin is said
    outright rather than inferred by matching the resolved sku to the request."""
    model = two_candidate_model()
    slot = preview(model, slot_skus={"rail": "SLAT-100"}).panel.slots[0]
    assert slot.pinned_sku == "SLAT-100"
    assert [m.sku for m in slot.eligibility.members] == ["SLAT-100"]
    # and with no pin, nothing claims one
    assert preview(model).panel.slots[0].pinned_sku is None
    assert len(preview(model).panel.slots[0].eligibility.members) == 2


def test_narrowing_carries_priority_and_approval_through_untouched():
    """A colour choice must not promote a product past an approval it still
    needs — the discipline `_chosen_option` states, applied to the same set."""
    model = two_candidate_model(approval="suggest_only")
    result = preview(model, height_mm=1800, width_mm=2500,
                     slot_skus={"rail": "SLAT-100"})

    member = result.panel.slots[0].eligibility.members[0]
    assert (member.sku, member.priority, member.approval) == \
        ("SLAT-100", 7, "suggest_only")
    # and the pin did NOT buy it: with no approval on the request, supply still
    # refuses to spend money on a suggest-only product
    assert [w.code for w in result.warnings] == ["substitute_needs_approval"]
    assert [p.slot_key for p in result.unsupplied] == ["rail"]
    assert result.total_cents == 0


def test_a_sku_that_slot_is_not_eligible_for_is_refused_not_ignored():
    """Ignoring it would price a panel nobody asked for and show the number as
    the answer to the question that was asked."""
    with pytest.raises(RequestRefused) as excinfo:
        preview(M_SLAT, slot_skus={"slat": "RAIL-3000"})
    assert excinfo.value.code == "sku_not_eligible"
    assert excinfo.value.params == {"slot_key": "slat", "sku": "RAIL-3000"}


def test_a_slot_this_panel_does_not_have_is_refused():
    with pytest.raises(RequestRefused) as excinfo:
        preview(M_SLAT, slot_skus={"batten": "SLAT-100"})
    assert excinfo.value.code == "sku_not_eligible"
    assert excinfo.value.params == {"slot_key": "batten", "sku": "SLAT-100"}


def test_an_empty_slot_skus_is_exactly_todays_behaviour():
    """The field's whole compatibility claim, byte for byte: a preview asked
    with `{}` must be the same document as one asked without the field at all,
    or every stored comparison and every screenshot moved for nothing."""
    assert preview(M_SLAT, slot_skus={}).model_dump_json() == \
        preview(M_SLAT).model_dump_json()


# --- the property the whole design rests on -----------------------------------

def test_the_preview_agrees_with_what_generation_actually_builds():
    """A preview computed by a simpler second code path would eventually disagree
    with the fence the user gets, and a preview that lies is worse than none. So
    it runs the real pipeline — and this is the test that keeps it honest."""
    # under the 1800 mm manufacturer maximum, so the run is a single bay and the
    # comparison is bay to bay
    result = generate(
        straight_topology(1700), demo_knowledge(), demo_catalog(),
        models=FenceModelLibrary(models=[M_SLAT]), parts=PARTS,
        default_model=FenceModelChoice(model_id="M-SLAT"),
    )
    span = result.strategy.spans[0]
    assert len(result.strategy.spans) == 1

    real = price_strategy(result.strategy, demo_catalog(),
                          demand_skus=result.run.demand_skus)
    real_panel = {
        r.slot_key: r for r in real.requirements if r.slot_key
    }

    shown = by_slot(preview(
        M_SLAT, height_mm=span.height_mm, width_mm=span.width_mm,
        # The opening, not just the width. A model-scoped preview has no posts —
        # it answers "what does this model cost at this bay size" — so a caller
        # comparing it against a REAL bay has to say how much of that size is
        # post. Supplying it is also what makes this test pin the opening: drop
        # the argument and the preview fits its slats across the full
        # centre-to-centre width and buys more screws than the run did.
        clear_width_mm=span.clear_width_mm,
        params={"rails_per_span": span.rail_count,
                "screws_per_span": span.screws_count},
    ))

    assert set(shown) == set(real_panel)
    for key, part in shown.items():
        line = real_panel[key]
        assert (part.qty, part.length_mm, part.sku, part.unit) == \
            (line.engineering_qty, line.cut_length_mm, line.sku, line.unit), \
            f"the preview and the run disagree about {key}"


def test_a_stored_bays_plan_re_resolves_the_panel_that_run_stored():
    """The same property, for a bay that already exists.

    The test above hand-assembles the context a run resolved a bay with, which
    is exactly what the drawer used to get wrong: it passed a height and a width
    and took the answer for that bay. `bay_preview_plan` reads the whole context
    back off the run, and the assertion here is the strongest available one —
    the panel it re-resolves must be the panel the run stored, field for field.
    A new `PanelContext` input in the generator that this plan does not carry
    fails here rather than in a drawer.
    """
    from fenceai.fencemodel.preview import bay_preview_plan
    from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam

    # raked (so the rails are cut on the slope) and three rails per span (so the
    # company's count differs from the model's authored default) — the two
    # inputs a height and a width cannot carry
    topo = straight_topology(1700)
    topo.nodes[1].z_mm = 200
    kb = demo_knowledge()
    kb = KnowledgeBase(versions=[
        *[v for v in kb.versions if v.object_id != "K-RAILS"],
        KnowledgeVersion(object_id="K-RAILS", version=2, type="fact",
                         title="3 rails per span",
                         actions=[SetParam(param="rails_per_span", value=3)]),
    ])
    result = generate(
        topo, kb, demo_catalog(),
        models=FenceModelLibrary(models=[M_SLAT]), parts=PARTS,
        default_model=FenceModelChoice(model_id="M-SLAT"),
    )
    span = result.strategy.spans[0]
    assert span.vertical == "raked" and span.rail_count == 3

    plan = bay_preview_plan(result, span.id)
    assert (plan.model_id, plan.version) == ("M-SLAT", M_SLAT.version)
    shown = preview_panel(M_SLAT, plan.request, demo_catalog(),
                          preset=result.run.objective_preset,
                          part_library=PARTS,
                          part_snapshot=result.run.part_snapshot)
    assert shown.panel == span.panel


def test_a_bay_of_another_run_is_not_a_bay_of_this_one():
    """`None` rather than an exception: which HTTP status "no such bay" is worth
    belongs to the route, not to the resolver."""
    from fenceai.fencemodel.preview import bay_preview_plan

    result = generate(straight_topology(1700), demo_knowledge(), demo_catalog(),
                      models=FenceModelLibrary(models=[M_SLAT]), parts=PARTS,
                      default_model=FenceModelChoice(model_id="M-SLAT"))
    assert bay_preview_plan(result, "span@elsewhere:0-1700") is None
    assert bay_preview_plan(result, result.strategy.posts[0].id) is None


def test_the_preview_carries_the_joint_details_of_the_panel_it_priced():
    """A joint detail rides on `PanelElevation`, which the preview and a stored
    run's `Bay.elevation` both hand back — one code path, so the detail beside a
    panel on the Models tab cannot say something different from the detail beside
    the bay built to it. `tests/report/test_structure.py` asserts the run side.

    M-SLAT@v2's slat seats 15 mm into a 20 mm channel with 3 mm of insertion
    clearance, and starts 65 up (50 to the channel's centre, plus half its 60 mm
    face height, less the 15 mm it disappears into) — so the buried band is
    65 -> 80, and 80 is the channel's own top face.
    """
    from fenceai.fencemodel.demo import M_SLAT_V2

    result = preview(M_SLAT_V2, height_mm=1800, width_mm=2500)
    assert result.invalid == [], "a preview of a document the loader would refuse"

    assert [d.key for d in result.elevation.details] == ["slat@bottom_channel"]
    detail = result.elevation.details[0]
    assert (detail.end, detail.kind) == ("base", "channel")
    assert (detail.channel_depth_mm, detail.engagement_mm, detail.margin_mm) == (20, 15, 3)

    slats = [m for m in result.elevation.members if m.slot_key == "slat"]
    assert slats
    for slat in slats:
        assert (slat.seat_start_mm, slat.seat_end_mm) == (65, 80)
        # the drawn piece and the priced piece are one number, and the buried
        # part of it is a sub-range of that piece rather than a second opinion
        assert slat.h_mm == by_slot(result)["slat"].length_mm == 1665
        assert slat.seat_start_mm >= slat.y_mm
        assert slat.seat_end_mm <= slat.y_mm + slat.h_mm


def test_a_model_with_no_joints_previews_no_details():
    """Every model in the repo but one, and the rule that keeps an empty section
    drawing off the screen: no engagement and no channel means nothing to draw."""
    assert preview(M_SLAT, height_mm=1800, width_mm=2500).elevation.details == []
    assert preview(M_LEGACY, height_mm=1800, width_mm=2500).elevation.details == []


def test_a_spec_declared_slot_previews_as_the_products_it_will_be_built_from():
    """The preview runs the same matcher generation runs. Without it a
    predicate slot would preview as a panel with nothing in it — and the Panel
    tab would show an empty, free panel for a model that builds perfectly well."""
    from fenceai.fencemodel.model import (
        Distributed, Eligibility, FenceModel, FrameSlot, PanelSpec, PartRequirement,
    )
    from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit

    model = FenceModel(
        id="M-PRED", version=1,
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal", placement=Distributed(count=2),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(predicate=And(items=[
                    Cmp(cmp="==", left=FieldRef(path="item.material"),
                        right=Lit(value="aluminium")),
                    Cmp(cmp="==", left=FieldRef(path="item.consumption"),
                        right=Lit(value="divisible_linear")),
                ])),
            ),
        )]),
    )
    parts = by_slot(preview(model, height_mm=1800, width_mm=2500))
    assert parts["rail"].sku == "RAIL-3000"
    assert parts["rail"].qty > 0


# --- a model that owns its post prices its own opening -------------------------

def test_a_model_that_owns_its_post_previews_the_opening_between_two_of_them():
    """The gap W1 left open here and W3 closes. The clear opening is measured TO
    the post faces, and a model-scoped preview used to have no posts to measure —
    so it fitted the panel across the full centre-to-centre width, half a post too
    wide at each end. M-VINYL's post is 90 mm, so a 1500 mm bay opens 1410."""
    shown = preview(M_VINYL, height_mm=1800, width_mm=1500)
    assert shown.clear_width_mm == 1410
    assert shown.warnings == []


def test_the_preview_and_the_fence_agree_about_a_routed_line():
    """The governing property of this module, on the model the arc exists for:
    the caller says only the height and the bay width, and the preview arrives at
    the same opening, the same slats and the same cut lengths the run does —
    without being told the opening, because the model knows its own post."""
    result = generate(
        straight_topology(1500), demo_knowledge(), demo_catalog(),
        models=FenceModelLibrary(models=[M_VINYL]), parts=PARTS,
        default_model=FenceModelChoice(model_id="M-VINYL"),
    )
    span = result.strategy.spans[0]
    shown = preview(M_VINYL, height_mm=span.height_mm, width_mm=span.width_mm,
                    params={"rails_per_span": span.rail_count})
    assert shown.clear_width_mm == span.clear_width_mm
    real = {r.slot_key: r for r in price_strategy(
        result.strategy, demo_catalog(),
        demand_skus=result.run.demand_skus).requirements if r.slot_key}
    for key, part in by_slot(shown).items():
        assert (part.qty, part.length_mm, part.sku) == (
            real[key].engineering_qty, real[key].cut_length_mm, real[key].sku), key


def test_a_post_nothing_covers_narrows_by_nothing_and_says_so():
    """A draft being edited is half-written by definition, so a preview must not
    refuse where generation does. It must not fall back silently either: an
    unmatched post contributes NO face and a warning, rather than a nominal that
    reads as measured."""
    shown = preview(M_VINYL, height_mm=1234, width_mm=1500)   # no post routed there
    assert shown.clear_width_mm == 1500
    assert [w.code for w in shown.warnings] == ["no_item_covers_post_spec"]
    assert shown.warnings[0].params["role"] == "post"


def test_a_caller_that_names_the_opening_is_still_believed():
    """`bay_preview_plan` carries a stored bay's own face allowance over rather
    than re-measuring it — imagining a wider bay does not change which posts bound
    it — so an explicit `clear_width_mm` must never be second-guessed."""
    shown = preview(M_VINYL, height_mm=1800, width_mm=1500, clear_width_mm=1300)
    assert shown.clear_width_mm == 1300


# --- the posts the previewed bay stands between -------------------------------

def test_the_preview_draws_the_post_it_measured_the_opening_to():
    """The opening is measured TO the post faces, so the preview already had to
    choose a post to know the width. Drawing it costs nothing new — and until
    now the two parts of a fence with no editor were also the two with nowhere
    on the drawing to click."""
    from fenceai.fencemodel.demo import M_VINYL

    preview = preview_panel(M_VINYL, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    posts = preview.elevation.posts
    assert [p.side for p in posts] == ["start", "end"]
    # EXACTLY the line post, not merely "some routed post". The preview names
    # `kind="line"` deliberately — a representative bay of the run — and
    # `startswith("POST-V-")` is satisfied by the end and corner variants too,
    # so it could not see that choice change under it. They are different skus
    # at different prices.
    assert [p.kind for p in posts] == ["line", "line"]
    assert {p.sku for p in posts} == {"POST-V-1800"}
    # the face it drew is the face it measured the opening with
    assert preview.clear_width_mm == 2500 - posts[0].w_mm


def test_the_start_post_is_drawn_outside_the_opening():
    """Negative x is the contract: the post occupies the millimetres BEFORE the
    panel. Clamped to zero it would sit over the first board."""
    from fenceai.fencemodel.demo import M_VINYL

    preview = preview_panel(M_VINYL, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    start, end = preview.elevation.posts
    assert start.x_mm == -start.w_mm and start.x_mm < 0
    assert end.x_mm == preview.clear_width_mm


def test_a_model_with_no_post_draws_no_post():
    """M-SLAT says nothing about its posts — the company's own standard applies,
    and inventing one on the drawing would show a part this model never asked
    for."""
    from fenceai.fencemodel.demo import M_SLAT

    preview = preview_panel(M_SLAT, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    assert preview.elevation.posts == []


def test_a_cap_is_drawn_at_a_nominal_and_says_so():
    """The catalog carries no cap height. The drawing needs one to show a cap at
    all, so it invents a proportion and flags it — exactly the bargain a rail's
    undeclared face height already strikes. The post's own face is real data and
    stays declared, which is why these are two flags and not one."""
    from fenceai.fencemodel.demo import M_VINYL

    preview = preview_panel(M_VINYL, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    post = preview.elevation.posts[0]
    assert post.cap_sku == "CAP-V-90"
    assert post.cap_h_mm > 0 and post.cap_declared is False
    assert post.declared is True, "the post face IS product data"


# --- a part that admits more than one product (fix wave, T2) ------------------

def multi_candidate_model() -> FenceModel:
    """TEST-LOCAL, deliberately. `rail-38-vinyl` is the one demo part specified by
    what it IS rather than by SKU, so it is the only one with alternatives to
    offer — and wiring it into a demo model would swap a 3000 mm aluminium rail
    for a vinyl one in every M-SLAT bay ever generated, which the compatibility
    gate forbids.

    Without a model naming it, nothing in the suite drove
    `compile_spec -> match_spec -> more than one member -> pin`: the drawer's two
    candidates came from an authored `EligibleItem` list, and the migration test
    asserted only that the fixture EXISTS.
    """
    return FenceModel(
        id="M-MULTI", version=1, name_i18n={"en": "Two vinyl rails"},
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal",
            placement=Distributed(count=2),
            requirement=PartRequirement(part_id="rail-38-vinyl", qty=1,
                                        length_rule="centre_to_centre"),
        )]),
    )


def test_a_part_specified_by_spec_offers_every_product_that_covers_it():
    """The whole chain, end to end: the part's spec compiles to a predicate, the
    matcher covers the catalog with it, and TWO products come back — which is the
    state the drawer's alternatives exist for and the state nothing reached."""
    result = preview(multi_candidate_model(), height_mm=1800, width_mm=2500)
    rail = by_slot(result)["rail"]
    assert rail.eligible_skus == ["RAIL-V-3000", "RAIL-V-3600"]
    assert rail.role == "rail", "filled from the part's type, never authored"
    assert rail.sku == "RAIL-V-3000", "least_cost picks the cheaper cut"
    assert result.total_cents == 5200


def test_pinning_the_alternative_prices_the_alternative():
    """The offer is only real if taking it changes the number. `_pinned_sku`
    narrows the matched set exactly as an option axis does — it never bypasses
    eligibility, which is why the pin has to name a member the PART admits."""
    result = preview(multi_candidate_model(), height_mm=1800, width_mm=2500,
                     slot_skus={"rail": "RAIL-V-3600"})
    rail = by_slot(result)["rail"]
    assert rail.sku == "RAIL-V-3600"
    assert result.total_cents == 6100


def test_pinning_a_product_the_part_does_not_admit_is_refused():
    """A pin that could smuggle in a product the part's spec excludes would make
    the spec advisory. RAIL-3000 is aluminium and 40 mm; the part asks for 38 mm
    vinyl."""
    with pytest.raises(RequestRefused) as e:
        preview(multi_candidate_model(), height_mm=1800, width_mm=2500,
                slot_skus={"rail": "RAIL-3000"})
    assert e.value.code == "sku_not_eligible"
