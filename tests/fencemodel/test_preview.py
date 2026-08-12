"""Seeing a panel before there is a fence.

The governing property is that the preview is not a second implementation: it
runs the same resolve -> derive -> supply -> fulfil pipeline over a synthetic
one-bay strategy, so it cannot quietly disagree with the fence the user gets.
The last test in this file is the one that keeps that true.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT
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
