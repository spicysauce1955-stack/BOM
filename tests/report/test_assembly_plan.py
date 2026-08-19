"""The steps of a panel, with the parts each one fits.

The property that makes this worth having rather than a rendering of prose:
every member of the panel is placed by exactly one step, or it is reported as
`unplaced`. An instruction sheet that quietly omits a part is worse than none,
because a fitter reading it believes the panel is finished.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import AssemblyStep
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.fencemodel.demo import M_SLAT
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.report.assembly import assembly_plan

PARTS = PartLibrary(parts=demo_parts())


def _panel(model):
    return preview_panel(model, PreviewRequest(height_mm=1800, width_mm=2500),
                         demo_catalog(), part_library=PARTS).panel


def _stepped(*steps: AssemblyStep):
    model = M_SLAT.model_copy(deep=True)
    model.assembly = list(steps)
    return model, _panel(model)


def test_a_model_with_no_steps_has_no_plan_rather_than_an_empty_one():
    """Different facts. The assembly film needs to tell "this line says nothing
    about its order" from "this line says it takes no steps", because only the
    first means fall back to the role-based build order."""
    assert assembly_plan(M_SLAT, _panel(M_SLAT)) is None


def test_each_step_carries_the_parts_it_fits():
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"], text_i18n={"en": "Fit the rails."}),
        AssemblyStep(key="fill", slots=["slat"]),
        AssemblyStep(key="fix", slots=["screw"]),
    )
    plan = assembly_plan(model, panel)
    assert [s.key for s in plan.steps] == ["frame", "fill", "fix"]
    assert [p.slot_key for p in plan.steps[0].parts] == ["rail"]
    assert plan.steps[0].parts[0].qty == 2
    assert plan.steps[1].parts[0].qty == 21     # the slats this bay actually fits
    assert plan.unplaced == []


def test_a_part_no_step_fits_is_REPORTED_not_dropped():
    """The governing property. A sheet that omits the fixings reads as a finished
    panel to the person holding it."""
    model, panel = _stepped(AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel)
    assert {p.slot_key for p in plan.unplaced} == {"slat", "screw"}
    assert all(p.qty for p in plan.unplaced), "an unplaced part keeps its quantity"


def test_every_member_is_placed_exactly_once_or_reported():
    """Stated as the sum, which is how `Σ(parts) ≡ BOM` is stated: the slots the
    steps fit and the slots reported unplaced partition the panel."""
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"]),
        AssemblyStep(key="fill", slots=["slat"]),
    )
    plan = assembly_plan(model, panel)
    fitted = [p.slot_key for s in plan.steps for p in s.parts]
    assert len(fitted) == len(set(fitted)), "a part fitted twice"
    assert set(fitted) | {p.slot_key for p in plan.unplaced} == \
        {s.slot_key for s in panel.slots}


def test_the_numbers_are_the_panels_own():
    """It recomputes nothing — the same rule the structure sheet follows. A step
    reporting a different cut length from the bay it is for would be a second
    arithmetic."""
    model, panel = _stepped(AssemblyStep(key="fill", slots=["slat"]))
    part = assembly_plan(model, panel).steps[0].parts[0]
    slat = next(s for s in panel.slots if s.slot_key == "slat")
    assert (part.qty, part.length_mm) == (slat.qty, slat.length_mm)


def test_an_installation_step_that_fits_nothing_still_appears():
    """It is an instruction, and dropping it because it places no part would lose
    exactly the half of the roadmap line that is about installation."""
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"]),
        AssemblyStep(key="cure", kind="installation",
                     text_i18n={"en": "Leave the footings overnight."}),
    )
    plan = assembly_plan(model, panel)
    cure = next(s for s in plan.steps if s.key == "cure")
    assert cure.parts == [] and cure.kind == "installation"
    assert cure.text_i18n["en"]


def test_a_slot_this_BAY_does_not_have_is_skipped_rather_than_invented():
    """A step may name a slot only a variant has, and a bay built to another
    variant simply does not fit it here. Not an error — `validate_model` proved
    the slot exists in some spec — and not a phantom part either."""
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"]),
        AssemblyStep(key="brace", slots=["stile"]),   # no such slot in this bay
    )
    plan = assembly_plan(model, panel)
    brace = next(s for s in plan.steps if s.key == "brace")
    assert brace.parts == []
    assert "stile" not in {p.slot_key for p in plan.unplaced}


def test_one_models_steps_are_never_laid_over_another_models_panel():
    """The guard the structure sheet has and this did not. `assembly_plan` takes
    a model AND a panel and stamped the PANEL's ref on its answer, so v2's steps
    over a v1 panel produced a plausible sheet whose slots quietly landed in
    `unplaced` under a version they never came from — the same shape as laying a
    run out over a topology it was not generated from."""
    import pytest
    from fenceai.core.errors import ReadRefused

    other = M_SLAT.model_copy(deep=True)
    other.version = 99
    other.assembly = [AssemblyStep(key="frame", slots=["rail"])]
    with pytest.raises(ReadRefused) as exc:
        assembly_plan(other, _panel(M_SLAT))
    assert exc.value.code == "model_changed"
