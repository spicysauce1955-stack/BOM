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
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement,
)
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from tests.conftest import straight_topology


def preview(model, **kw):
    return preview_panel(model, PreviewRequest(**kw), demo_catalog())


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
        models=FenceModelLibrary(models=[M_SLAT]),
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
        models=FenceModelLibrary(models=[M_SLAT]),
        default_model=FenceModelChoice(model_id="M-SLAT"),
    )
    span = result.strategy.spans[0]
    assert span.vertical == "raked" and span.rail_count == 3

    plan = bay_preview_plan(result, span.id)
    assert (plan.model_id, plan.version) == ("M-SLAT", M_SLAT.version)
    shown = preview_panel(M_SLAT, plan.request, demo_catalog(),
                          preset=result.run.objective_preset)
    assert shown.panel == span.panel


def test_a_bay_of_another_run_is_not_a_bay_of_this_one():
    """`None` rather than an exception: which HTTP status "no such bay" is worth
    belongs to the route, not to the resolver."""
    from fenceai.fencemodel.preview import bay_preview_plan

    result = generate(straight_topology(1700), demo_knowledge(), demo_catalog(),
                      models=FenceModelLibrary(models=[M_SLAT]),
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
