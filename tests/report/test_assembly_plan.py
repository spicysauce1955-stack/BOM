"""The steps of a panel, with the parts each one fits.

The property that makes this worth having rather than a rendering of prose:
every member of the panel is placed by exactly one step, or it is reported as
`unplaced`. An instruction sheet that quietly omits a part is worse than none,
because a fitter reading it believes the panel is finished.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import AssemblyStep, Prerequisite
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.fencemodel.demo import M_SLAT
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.report.assembly import (
    StepPart, assembly_plan, bay_parts_from_posts,
)
from fenceai.report.elevation import ElevationPost

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
    # field by field: an unplaced part that lost its role or its length would be
    # a row a fitter cannot act on, and only `slot_key` was ever asserted
    assert [(p.slot_key, p.role, p.qty, p.length_mm) for p in plan.unplaced] == [
        ("slat", "infill", 21, 1800), ("screw", "screw", 84, None)]
    assert plan.model_ref == panel.model_ref == "M-SLAT@v1"


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


def test_a_slot_only_a_VARIANT_has_is_skipped_rather_than_invented():
    """A step may name a slot only a variant has, and a bay built to another
    variant simply does not fit it here.

    The first version of this test built NO variant — so it exercised "an unknown
    key is skipped" on a model `validate_model` rejects, which is a different
    claim entirely. The model below is one the validator accepts, which is what
    makes the skip legitimate rather than a swallowed typo."""
    from fenceai.fencemodel.model import Distributed, FrameSlot, PartRequirement, Variant
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    from fenceai.fencemodel.model import validate_model

    model = M_SLAT.model_copy(deep=True)
    model.assembly = [AssemblyStep(key="frame", slots=["rail"]),
                      AssemblyStep(key="brace", slots=["stile"])]
    tall = model.default_spec.model_copy(deep=True)
    tall.frame.append(FrameSlot(
        key="stile", orientation="vertical", placement=Distributed(count=2),
        requirement=PartRequirement(part_id="rail-rail-3000", qty=1,
                                    length_rule="panel_height")))
    model.variants = [Variant(
        condition=Cmp(cmp=">", left=FieldRef(path="panel.height_mm"),
                      right=Lit(value=9000)),      # this bay is 1800: default spec
        spec=tall)]
    assert validate_model(model, demo_catalog(), PARTS) == [], \
        "the model must be VALID, or the skip below is a swallowed typo"

    plan = assembly_plan(model, _panel(model))
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
    # the params are what the reader's sentence is rendered from
    assert exc.value.params == {"model_ref": "M-SLAT@v99",
                                "panel_model_ref": "M-SLAT@v1"}

    # a panel that names no model cannot contradict one, so it is not refused
    from fenceai.fencemodel.resolve import ResolvedPanel
    assert assembly_plan(other, ResolvedPanel(model_ref="", slots=[])) is not None


def test_the_preview_carries_the_plan_for_the_panel_it_resolved():
    """The wiring, which nothing tested: blanking `PanelPreview.assembly` left
    the entire suite green while the feature vanished from the API payload and
    the Panel tab. Only the browser suite would have noticed."""
    from fenceai.fencemodel.demo import M_LEGACY, M_VINYL
    from fenceai.fencemodel.preview import PreviewRequest, preview_panel

    p = preview_panel(M_VINYL, PreviewRequest(height_mm=1800, width_mm=1500),
                      demo_catalog(), part_library=PARTS)
    # the order the model's own PREREQUISITES imply, which is not its print
    # order: `cure` is authored second and lands beside `rails` because both wait
    # only on `set_posts`
    assert [s.key for s in p.assembly.steps] == \
        ["set_posts", "cure", "rails", "boards", "cap_posts"]
    boards = next(s for s in p.assembly.steps if s.key == "boards")
    assert [(x.slot_key, x.qty, x.length_mm) for x in boards.parts] \
        == [("slat", 9, 1470)]
    assert p.assembly.unplaced == []
    assert p.assembly.unplaced_bay == []
    assert p.assembly.model_ref == "M-VINYL@v1"
    # and the sequence above is one of several, which the plan says rather than
    # leaving the reader to assume
    assert p.assembly.order.basis == "requires"
    assert p.assembly.order.unique is False
    assert p.assembly.order.stages == [
        ["set_posts"], ["cure", "rails"], ["boards"], ["cap_posts"]]

    # ...and a model that states no order carries no plan, not an empty one
    legacy = preview_panel(M_LEGACY, PreviewRequest(height_mm=1800, width_mm=1500),
                           demo_catalog(), part_library=PARTS)
    assert legacy.assembly is None


def test_an_installation_step_that_DOES_name_a_slot_still_fits_it():
    """The schema permits it — only `assembly` steps are required to name parts —
    so the plan must place them rather than silently skipping the slot into
    `unplaced`, which would make the sheet contradict itself."""
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"]),
        AssemblyStep(key="site", kind="installation", slots=["screw"]),
    )
    plan = assembly_plan(model, panel)
    site = next(s for s in plan.steps if s.key == "site")
    assert [p.slot_key for p in site.parts] == ["screw"]
    assert "screw" not in {p.slot_key for p in plan.unplaced}


def test_unplaced_is_read_in_the_panels_own_slot_order():
    """The list above pins the FIELDS of each unplaced part; nothing pinned their
    ORDER, so a comprehension rebuilt over a `set`, or sorted by slot key to look
    tidy, was invisible to the suite.

    The order is the panel's own — frame, then infill, then fixings, exactly as
    `resolve_panel` builds `panel.slots` — because "the parts no step fits" is
    read beside the sheet by someone holding the panel, and every other list
    about this panel (the slots, the structure sheet's rows) is in that order.
    Alphabetical would put the screws before the boards for no reason a fitter
    could see."""
    model, panel = _stepped(AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel)
    assert [p.slot_key for p in plan.unplaced] == ["slat", "screw"]
    assert [s.slot_key for s in panel.slots] == ["rail", "slat", "screw"], \
        "the expectation above IS the panel's order, not a coincidence of names"
    # stated as a negative too, so a `sorted(...)` rebuild cannot pass by luck
    assert [p.slot_key for p in plan.unplaced] != \
        sorted(p.slot_key for p in plan.unplaced)


# --- the bay's own placeables (build-order item 11's gap) --------------------
#
# The note in `report/assembly.py` said it in full: the placeable vocabulary was
# the PANEL's slots, so no step could name a post, its cap or its footing, and an
# installation instruction about posts was prose. Closing it meant giving the read
# model the bay's posts — a different input, and the tests below are about what
# that input may and may not be used for.

def _posts(cap: bool = True) -> list[ElevationPost]:
    """The two posts a bay stands between, as the drawing already has them."""
    return [ElevationPost(side=side, kind="line", x_mm=x, w_mm=90, h_mm=1800,
                          sku="POST-90", cap_sku="CAP-90" if cap else "")
            for side, x in (("start", -90), ("end", 2410))]


def test_a_step_can_now_place_the_bays_post_and_says_which_bay_part_it_is():
    model, panel = _stepped(
        AssemblyStep(key="stand", scope="post", bay_parts=["post"]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel, bay=bay_parts_from_posts(_posts()))
    stand = next(s for s in plan.steps if s.key == "stand")
    assert [(p.slot_key, p.qty, p.belongs_to) for p in stand.parts] \
        == [("post", 2, "bay")]
    assert stand.scope == "post"


def test_the_post_count_is_READ_from_the_bay_and_never_worked_out():
    """The same discipline the structure sheet keeps with pegs. A read model that
    decided for itself how many posts a bay has would be a second opinion
    competing with the run's — and the first one to disagree with the BOM."""
    one = [_posts()[0]]
    assert bay_parts_from_posts(one)[0].qty == 1
    assert bay_parts_from_posts([])[0:1] == []


def test_a_footing_is_NAMED_but_not_invented():
    """An `ElevationPost` is a rectangle and carries no mounting, so nothing here
    knows whether a footing exists. A step may say so; against this input it
    places nothing, exactly as a step naming a slot only a variant has does.
    Inventing a footing row to make the step look answered is the move contract
    obligation 9 forbids by name."""
    model, panel = _stepped(
        AssemblyStep(key="stand", scope="post", bay_parts=["post", "footing"]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel, bay=bay_parts_from_posts(_posts()))
    stand = next(s for s in plan.steps if s.key == "stand")
    assert [p.slot_key for p in stand.parts] == ["post"]
    assert "footing" not in {p.slot_key for p in plan.unplaced_bay}


def test_a_bay_part_no_step_places_is_reported_once_the_model_names_any():
    """The bay's half of obligation 9. A model that places the post and forgets
    the cap has an incomplete procedure, and a fitter reading it would believe
    the bay finished."""
    model, panel = _stepped(
        AssemblyStep(key="stand", scope="post", bay_parts=["post"]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel, bay=bay_parts_from_posts(_posts()))
    assert [(p.slot_key, p.qty) for p in plan.unplaced_bay] == [("cap", 2)]


def test_a_model_that_says_nothing_about_the_bay_is_not_reported_as_incomplete():
    """The scope of the claim, and the reason `unplaced_bay` is opt-in. Every
    model shipped before this names no bay part; reporting their posts as
    unplaced would turn silence into a defect on every sheet in the app and bury
    the one case above. Silence is "the run's business", not "forgotten"."""
    model, panel = _stepped(AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel, bay=bay_parts_from_posts(_posts()))
    assert plan.unplaced_bay == []


def test_the_panels_own_invariant_is_untouched_by_the_bay():
    """`unplaced` is obligation 9 as written — the PANEL's members — and a post
    has never been one. Folding the bay into it would change what a number that
    already has a meaning means."""
    model, panel = _stepped(
        AssemblyStep(key="stand", scope="post", bay_parts=["post", "cap"]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel, bay=bay_parts_from_posts(_posts()))
    assert [p.slot_key for p in plan.unplaced] == ["slat", "screw"]
    assert all(p.belongs_to == "panel" for p in plan.unplaced)


def test_a_caller_that_knows_no_posts_leaves_the_step_placing_nothing():
    """A model-scoped preview whose post matched nothing draws no posts, and a
    plan is still wanted. It must not stand a phantom post up to fill the step."""
    model, panel = _stepped(
        AssemblyStep(key="stand", scope="post", bay_parts=["post"]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel)
    assert next(s for s in plan.steps if s.key == "stand").parts == []
    assert plan.unplaced_bay == []


# --- what the read model returns for a PARTIAL order ------------------------

def test_the_returned_sequence_is_a_linearisation_and_not_the_print_order():
    """Obligation 11 reaching the read model. `boards` is printed first and
    requires `frame`, so the plan returns frame first — and a reader who trusted
    the printed list would have built the panel in the order the guide denies."""
    model, panel = _stepped(
        AssemblyStep(key="boards", slots=["slat"],
                     requires=[Prerequisite(step="frame", kind="after")]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel)
    assert [s.key for s in plan.steps] == ["frame", "boards"]
    assert [s.stage for s in plan.steps] == [0, 1]
    assert plan.order.unique is True


def test_a_sequence_that_is_one_of_several_SAYS_SO():
    """The decision this slice had to make. A partial order has no single
    sequence, so the plan returns one AND the shape it came from: two steps in
    one stage are unordered with respect to each other, and `unique` is the field
    that stops a reader assuming otherwise."""
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"]),
        AssemblyStep(key="boards", slots=["slat"],
                     requires=[Prerequisite(step="frame", kind="after")]),
        AssemblyStep(key="fix", slots=["screw"],
                     requires=[Prerequisite(step="frame", kind="after")]))
    plan = assembly_plan(model, panel)
    assert plan.order.unique is False
    assert plan.order.stages == [["frame"], ["boards", "fix"]]
    assert [s.stage for s in plan.steps] == [0, 1, 1]


def test_print_order_is_reported_as_print_order():
    """A model with no `requires` is not asserting an order, and a plan that
    called this sequence `requires`-derived would be claiming a dependency the
    document never stated — the exact failure obligation 11 describes."""
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"]),
        AssemblyStep(key="fill", slots=["slat"]))
    plan = assembly_plan(model, panel)
    assert plan.order.basis == "authored"
    assert plan.order.stages == [["frame", "fill"]]
    assert [s.key for s in plan.steps] == ["frame", "fill"]


def test_a_run_or_site_scoped_step_is_PRESENT_in_the_payload():
    """Contract obligation 12: published, and left for the renderer to withhold
    from a sheet about one bay. Dropping it here would lose the fact rather than
    defer its surface, and phase two would have nothing to render."""
    model, panel = _stepped(
        AssemblyStep(key="frame", slots=["rail"]),
        AssemblyStep(key="setout", kind="installation", scope="run",
                     text_i18n={"en": "Set the line out from the corner."}),
        AssemblyStep(key="tidy", kind="installation", scope="site",
                     text_i18n={"en": "Clean down."}))
    plan = assembly_plan(model, panel)
    assert {s.key: s.scope for s in plan.steps} == \
        {"frame": "panel", "setout": "run", "tidy": "site"}


def test_a_cyclic_draft_still_renders_and_names_the_circle():
    """Refused at AUTHORING, reported here. A document being typed is invalid by
    definition and the author is looking at it, so the preview that shows them
    what they typed must not be the thing that breaks."""
    model, panel = _stepped(
        AssemblyStep(key="a", slots=["rail"],
                     requires=[Prerequisite(step="b", kind="after")]),
        AssemblyStep(key="b", slots=["slat"],
                     requires=[Prerequisite(step="a", kind="after")]))
    plan = assembly_plan(model, panel)
    assert plan.order.conflicts == [["a", "b"]]
    assert {s.key for s in plan.steps} == {"a", "b"}      # neither is dropped
    fitted = [p.slot_key for s in plan.steps for p in s.parts]
    assert sorted(fitted) == ["rail", "slat"]


def test_every_member_is_still_placed_exactly_once_under_a_reordering():
    """The governing property has to survive the sequence changing. It is stated
    over the SET, so a linearisation that dropped or duplicated a step would
    break it — which a test reading `steps[0]` positionally would not."""
    model, panel = _stepped(
        AssemblyStep(key="fix", slots=["screw"],
                     requires=[Prerequisite(step="fill", kind="after")]),
        AssemblyStep(key="fill", slots=["slat"],
                     requires=[Prerequisite(step="frame", kind="after")]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel)
    assert [s.key for s in plan.steps] == ["frame", "fill", "fix"]
    fitted = [p.slot_key for s in plan.steps for p in s.parts]
    assert len(fitted) == len(set(fitted))
    assert set(fitted) | {p.slot_key for p in plan.unplaced} == \
        {s.slot_key for s in panel.slots}


def test_a_bay_part_row_is_a_copy_and_not_the_callers_object():
    """The read model hands the same list to every step that names it. Returning
    the caller's row would let one consumer's edit reach another's, and the plan
    is a value."""
    bay = bay_parts_from_posts(_posts())
    model, panel = _stepped(
        AssemblyStep(key="stand", scope="post", bay_parts=["post"]),
        AssemblyStep(key="frame", slots=["rail"]))
    plan = assembly_plan(model, panel, bay=bay)
    placed = next(s for s in plan.steps if s.key == "stand").parts[0]
    assert placed is not bay[0] and placed == bay[0]
    assert isinstance(placed, StepPart)
