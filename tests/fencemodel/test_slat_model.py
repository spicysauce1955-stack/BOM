"""M-SLAT is the first model that is not a compatibility shim: nothing about it
has to reproduce a legacy number, so it is where the panel mechanism is asked to
carry an infill — a fitted member count, a spread residual, and fixings counted
per crossing rather than per panel.

It is therefore also where the phase-1 boundary is felt rather than described,
and one test below pins the boundary instead of asserting the number we want.
"""

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import DivisibleLinear
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT, demo_models, slat_model
from fenceai.fencemodel.model import validate_model
from fenceai.fencemodel.resolve import PanelContext, resolve_panel

# One bay, stated once: 2500 c/c between post centres, 2400 clear between their
# faces, 1800 tall and level. Every count below is derived from these three
# numbers by hand in the test that uses it.
BAY = PanelContext(
    centre_width_mm=2500, clear_width_mm=2400, height_mm=1800,
    vertical="level", length_basis="width", params={"rails_per_span": 2},
)


def test_slat_model_validates_against_the_demo_catalog():
    """The load-time gate is the definition of "phase-1 buildable": M-SLAT may
    only use features `resolve_panel` actually honours, and the demo catalog must
    stock every sku it names."""
    assert validate_model(M_SLAT, demo_catalog()) == []


def test_the_model_library_keeps_both_built_ins():
    assert demo_models() == {"M-LEGACY": M_LEGACY, "M-SLAT": M_SLAT}
    assert M_SLAT.ref == "M-SLAT@v1"


def test_the_skus_are_arguments_so_a_project_catalog_can_differ():
    """Same reason `legacy_model()` takes them: the structure is the model's, the
    products are the project's."""
    spec = slat_model(slat_sku="X-SLAT", rail_sku="X-RAIL",
                      screw_sku="X-SCREW").default_spec
    holders = [*spec.frame, *spec.infill.pattern, *spec.fixings]
    assert {h.key: [m.sku for m in h.requirement.eligibility.members] for h in holders} \
        == {"rail": ["X-RAIL"], "slat": ["X-SLAT"], "screw": ["X-SCREW"]}


# ---- the bay, resolved ------------------------------------------------------

def test_a_2400_bay_resolves_two_rails_twenty_slats_and_eighty_screws():
    """2400 clear takes 20 slats: 19 x (100 + 20) + 100 = 2380 fits, a 21st does
    not. Two rails, so 40 crossings, so 80 screws — the count a per_panel rule
    (M-LEGACY's 8) cannot express, which is why this model exists.
    """
    panel = resolve_panel(M_SLAT.default_spec, BAY, M_SLAT.ref)
    by_key = {s.slot_key: s for s in panel.slots}

    assert panel.model_ref == "M-SLAT@v1"
    assert sorted(by_key) == ["rail", "screw", "slat"]
    assert (by_key["rail"].qty, by_key["rail"].role) == (2, "rail")
    assert (by_key["slat"].qty, by_key["slat"].role) == (20, "infill")
    assert (by_key["screw"].qty, by_key["screw"].role) == (80, "screw")
    assert by_key["screw"].qty == 2 * (20 * 2)


def test_the_rails_are_cut_centre_to_centre_like_the_legacy_model():
    """The doc/code disagreement `demo.py` records is about which number a rail
    is cut to, and it is unsettled; a second model quietly choosing the other
    answer would settle it by arithmetic."""
    rail = next(s for s in resolve_panel(M_SLAT.default_spec, BAY).slots
                if s.slot_key == "rail")
    assert rail.length_mm == 2500
    assert rail.length_basis == "width"


def test_a_knowledge_param_still_wins_the_rail_count_and_the_screws_follow():
    """The crossing count is derived, not authored: three rails is 60 crossings
    without anyone editing the fixing rule."""
    ctx = BAY.model_copy(update={"params": {"rails_per_span": 3}})
    by_key = {s.slot_key: s for s in resolve_panel(M_SLAT.default_spec, ctx).slots}
    assert by_key["rail"].qty == 3
    assert by_key["screw"].qty == 120


def test_the_slat_is_cut_to_the_panel_height_not_to_the_bay_width():
    """The distinction the `panel_height` rule exists to draw. Every other
    LengthRule derives from the bay's width, and one of those on a vertical
    member would stamp 2400 (or 2500) on a part the fence cuts to 1800 and put
    that number on a cut list."""
    slat = next(s for s in resolve_panel(M_SLAT.default_spec, BAY).slots
                if s.slot_key == "slat")
    assert slat.length_mm == BAY.height_mm == 1800
    assert slat.length_mm not in (BAY.clear_width_mm, BAY.centre_width_mm)


def test_a_raked_bay_does_not_stretch_the_slats():
    """The slope factor corrects a HORIZONTAL member for running along the grade.
    A raked bay's top follows the grade and its bottom follows the ground, so the
    two datums stay parallel and a full-height member keeps one length — only its
    end cuts are angled."""
    raked = BAY.model_copy(update={
        "vertical": "raked", "length_basis": "slope", "slope_len_mm": 2600})
    by_key = {s.slot_key: s for s in resolve_panel(M_SLAT.default_spec, raked).slots}
    assert by_key["slat"].length_mm == 1800
    assert by_key["rail"].length_mm == 2600, "the rail still follows the grade"


def test_resolution_is_deterministic():
    assert resolve_panel(M_SLAT.default_spec, BAY) == resolve_panel(M_SLAT.default_spec, BAY)


# ---- the fit ----------------------------------------------------------------

def test_the_residual_is_spread_into_the_gaps_and_nothing_is_left_over():
    """`excess="space"` means the axis is accounted for to the millimetre: the
    20 mm the nominal pattern leaves over is not a 20 mm hole at one end, it is
    one extra millimetre in each of 19 gaps plus one more in the first."""
    fit = next(s for s in resolve_panel(M_SLAT.default_spec, BAY).slots
               if s.slot_key == "slat").fit
    slat = M_SLAT.default_spec.infill.pattern[0]

    assert fit.count == 20
    assert len(fit.gaps_mm) == 19
    assert fit.count * slat.width_mm + sum(fit.gaps_mm) \
        + fit.edge_margin_start_mm + fit.edge_margin_end_mm == BAY.clear_width_mm
    assert fit.residual_mm == 0
    assert max(fit.gaps_mm) - min(fit.gaps_mm) <= 1
    assert sorted(fit.gaps_mm) == [21] * 18 + [22]
    # what the author asked for, kept beside what they got: the sphere test is
    # measured against max(gaps_mm), which is 22 here and not the authored 20
    assert fit.rejected_alternative == [slat.gap_after_mm] * 19


def test_the_gaps_stay_within_a_millimetre_across_every_bay_width():
    """The property, not one width: an integer spread that drifts by 2 mm would
    let a clear-gap check pass on the average while a real opening exceeds it."""
    for clear in range(600, 3001, 7):
        ctx = BAY.model_copy(update={"clear_width_mm": clear})
        slat = next((s for s in resolve_panel(M_SLAT.default_spec, ctx).slots
                     if s.slot_key == "slat"), None)
        if slat is None or len(slat.fit.gaps_mm) < 2:
            continue
        fit = slat.fit
        assert max(fit.gaps_mm) - min(fit.gaps_mm) <= 1, clear
        assert fit.count * 100 + sum(fit.gaps_mm) == clear, clear


# ---- the product the model spends -------------------------------------------

def test_the_slat_stock_length_is_chosen_for_the_height_it_is_cut_to():
    """Three 1800 mm slats per 6 m bar, and the fourth is not a rounding
    question: `plan_cuts` charges each piece its kerf against (stock + kerf), so
    3 x 1803 = 5409 fits 6003 and 4 x 1803 = 7212 does not. The leftover, 591 mm,
    clears `min_reusable_remnant_mm`, so a bar's tail is stock rather than
    scrap — the remnant path is live on this product instead of dead.
    """
    slat = demo_catalog().product("SLAT-100")
    sem = slat.consumption
    assert isinstance(sem, DivisibleLinear)

    piece, capacity = BAY.height_mm + sem.kerf_mm, sem.purchase_length_mm + sem.kerf_mm
    assert 3 * piece <= capacity < 4 * piece
    leftover = sem.purchase_length_mm - 3 * BAY.height_mm - 3 * sem.kerf_mm
    assert leftover == 591 >= sem.min_reusable_remnant_mm
