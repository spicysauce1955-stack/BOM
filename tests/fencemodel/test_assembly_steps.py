"""Assembly and installation instructions on a fence model (roadmap Admin 3).

*"Each fence panel has assembly rules and instructions (also support installation
rules and instructions)."* The only roadmap item that had no foundation at all:
nothing on `FenceModel` carried prose, an ordering, or a step.

The line this schema draws is the one `plan/open-work.md` drew before it: an
instruction that is only text is a DOC, while one that names slots and an order
is DATA — the assembly film can drive its order from it, the parts of a panel can
be split by it, and a slot no step places is a gap something can report. So an
`assembly` step must name parts, and an `installation` step need not: "let the
footings cure overnight" places nothing and is exactly what the second half of
that roadmap line is about.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import (
    AssemblyStep, Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot,
    InfillSpec, Member, PanelSpec, PartRequirement, Prerequisite, validate_model,
)

CATALOG = demo_catalog()


def _model(*steps: AssemblyStep) -> FenceModel:
    return FenceModel(
        id="M-STEPS", version=1, assembly=list(steps),
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal", placement=Distributed(count=2),
                requirement=PartRequirement(
                    role="rail", qty=1, length_rule="centre_to_centre",
                    eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])))],
            infill=InfillSpec(orientation="vertical", pattern=[Member(
                key="slat", width_mm=100, gap_after_mm=20,
                requirement=PartRequirement(
                    role="infill", qty=1, length_rule="panel_height",
                    eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")])))]),
        ),
    )


def test_a_model_may_say_nothing_about_how_it_is_built():
    """Empty is NO OPINION, exactly as `post` is — it is what every model shipped
    before this carried, and the film falls back to its role-based order."""
    assert validate_model(_model(), CATALOG) == []


def test_a_model_can_say_what_is_done_in_what_order():
    model = _model(
        AssemblyStep(key="frame", slots=["rail"],
                     text_i18n={"en": "Seat both rails into the posts."}),
        AssemblyStep(key="fill", slots=["slat"],
                     text_i18n={"en": "Drop the boards in from the top."}),
    )
    assert validate_model(model, CATALOG) == []
    assert [s.key for s in model.assembly] == ["frame", "fill"]


def test_a_step_naming_a_slot_the_panel_does_not_have_is_refused():
    """The whole value of naming slots is that the name means something. A typo
    would publish cleanly and then place nothing, on every job built to it."""
    errs = validate_model(_model(AssemblyStep(key="x", slots=["raill"])), CATALOG)
    assert any("raill" in e for e in errs)


def test_two_steps_cannot_both_place_the_same_part():
    """A part is fitted once. Two steps naming it is not an ordering, it is a
    contradiction — and it would make the parts-per-step split double-count."""
    errs = validate_model(_model(
        AssemblyStep(key="a", slots=["rail"]),
        AssemblyStep(key="b", slots=["rail", "slat"])), CATALOG)
    # the WHOLE sentence: every message begins "assembly step", so `"b" in e`
    # was free, and a message naming the slot where the earlier STEP belongs
    # would have passed it
    assert errs == [
        "assembly step b: slot rail is already fitted by step a. A part is "
        "fitted once — two steps naming it is a contradiction, not an ordering"]


def test_an_assembly_step_that_places_nothing_is_refused():
    """"An instruction that is only text is a doc" — and a fence model is not a
    document. If it fits no part, it is an INSTALLATION step and says so."""
    errs = validate_model(_model(
        AssemblyStep(key="tidy", text_i18n={"en": "Sweep up."})), CATALOG)
    assert any("tidy" in e for e in errs)


def test_an_installation_step_may_place_nothing():
    """Which is the second half of the roadmap line. Curing concrete, checking a
    line, waiting for an inspection — real instructions that fit no part."""
    model = _model(AssemblyStep(
        key="cure", kind="installation",
        text_i18n={"en": "Leave the footings to cure overnight before hanging."}))
    assert validate_model(model, CATALOG) == []


def test_two_steps_cannot_share_a_key():
    """A step's key is how a surface refers to it and how a reader tells two
    apart. Duplicates make "step 2" ambiguous."""
    errs = validate_model(_model(
        AssemblyStep(key="same", slots=["rail"]),
        AssemblyStep(key="same", slots=["slat"])), CATALOG)
    assert any("same" in e for e in errs)


def test_a_step_may_name_a_slot_that_only_a_VARIANT_has():
    """A variant's panel is still this model's panel. Refusing a step for naming
    a slot the default spec lacks would make a model with variants unable to
    describe how its own variants go together."""
    model = _model(AssemblyStep(key="brace", slots=["stile"]))
    variant_spec = model.default_spec.model_copy(deep=True)
    variant_spec.frame.append(FrameSlot(
        key="stile", orientation="vertical", placement=Distributed(count=2),
        requirement=PartRequirement(
            role="rail", qty=1, length_rule="panel_height",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]))))
    from fenceai.fencemodel.model import Variant
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    model.variants = [Variant(
        condition=Cmp(cmp=">", left=FieldRef(path="panel.height_mm"),
                      right=Lit(value=1000)),
        spec=variant_spec)]
    assert validate_model(model, CATALOG) == []


def test_a_post_is_not_a_SLOT_of_the_panel_even_now_that_a_step_can_name_one():
    """The two vocabularies stay two. `slots` is this document's own key space
    and a post has never been in it; naming one there is still a typo, and it
    still has to be refused, or `unplaced` starts reporting a member the panel
    does not have. `bay_parts` is the door that opened — see below."""
    model = _model(AssemblyStep(key="stand", slots=["post"]))
    model.post = None       # even a model that HAS one cannot name it HERE
    errs = validate_model(model, CATALOG)
    assert any("post" in e for e in errs)


def test_a_step_CAN_now_name_the_bays_post_its_cap_and_its_footing():
    """The gap `report/assembly.py` recorded and this closes: "set the posts
    plumb in concrete" used to be prose, because the placeable vocabulary was the
    panel's slots and a post is not one. It is now data — and, because it names
    parts, an `assembly` step rather than an `installation` one."""
    model = _model(
        AssemblyStep(key="stand", scope="post", bay_parts=["post", "footing"]),
        AssemblyStep(key="cap", scope="post", bay_parts=["cap"]),
        AssemblyStep(key="frame", slots=["rail"]))
    assert validate_model(model, CATALOG) == []


def test_a_panel_scoped_step_may_not_claim_the_bays_parts():
    """`scope` decides where an instruction is rendered, so a step scoped to the
    panel while naming the post outside it is a document disagreeing with
    itself — and the sheet would print a post instruction as a panel one."""
    errs = validate_model(_model(
        AssemblyStep(key="stand", bay_parts=["post"])), CATALOG)
    assert any("stand" in e and "scope" in e for e in errs)


def test_two_steps_cannot_both_place_the_bays_post():
    """The same rule slots have, one level out. A part is fitted once; two steps
    naming it is a contradiction rather than an ordering."""
    errs = validate_model(_model(
        AssemblyStep(key="a", scope="post", bay_parts=["post"]),
        AssemblyStep(key="b", scope="post", bay_parts=["post"])), CATALOG)
    assert any("already placed by step a" in e for e in errs)


def test_all_five_scopes_are_authorable_from_the_start():
    """Contract obligation 12. `run` and `site` are published and rendered by
    nothing until phase two — dropping them at authoring instead would lose the
    fact rather than defer its surface, and 44-51% of steps in real installation
    guides are neither panel nor bay."""
    for scope in ("panel", "bay", "post", "run", "site"):
        model = _model(AssemblyStep(
            key="s", scope=scope, kind="installation",
            text_i18n={"en": "Set the whole line out from the corner."}))
        assert validate_model(model, CATALOG) == [], scope


def test_a_prerequisite_naming_no_step_is_refused():
    """The edge would constrain nothing, which is not what stating it meant. Left
    to the read model it becomes a silently dropped dependency — the author
    believes they ordered two steps and the sheet disagrees."""
    errs = validate_model(_model(
        AssemblyStep(key="a", slots=["rail"]),
        AssemblyStep(key="b", slots=["slat"],
                     requires=[Prerequisite(step="ghost")])), CATALOG)
    assert any("ghost" in e for e in errs)


def test_a_step_that_requires_itself_is_refused():
    errs = validate_model(_model(
        AssemblyStep(key="a", slots=["rail"],
                     requires=[Prerequisite(step="a")])), CATALOG)
    assert any("requires itself" in e for e in errs)


def test_a_circle_of_prerequisites_is_refused_AT_AUTHORING():
    """Where the author is, holding the document, able to say which edge was
    wrong. Discovering it at render puts the question in front of a fitter three
    weeks later, who cannot answer it."""
    errs = validate_model(_model(
        AssemblyStep(key="a", slots=["rail"],
                     requires=[Prerequisite(step="b")]),
        AssemblyStep(key="b", slots=["slat"],
                     requires=[Prerequisite(step="a")])), CATALOG)
    assert any("circle" in e for e in errs)


def test_two_steps_the_document_says_happen_together_are_NOT_a_circle():
    """`not_before` both ways is concurrency, not contradiction. Refusing it
    would make a true statement about a real build unauthorable, which is the
    flattening obligation 11 names by another name."""
    model = _model(
        AssemblyStep(key="a", slots=["rail"],
                     requires=[Prerequisite(step="b", kind="not_before")]),
        AssemblyStep(key="b", slots=["slat"],
                     requires=[Prerequisite(step="a", kind="not_before")]))
    assert validate_model(model, CATALOG) == []


def test_alternatives_that_are_also_ordered_are_refused():
    """"Do one or the other" and "do this one after that one" cannot both be true
    of the same pair. Shipping it leaves every reader to guess which half the
    author meant."""
    errs = validate_model(_model(
        AssemblyStep(key="a", slots=["rail"],
                     requires=[Prerequisite(step="b", kind="exclusive_with"),
                               Prerequisite(step="b", kind="after")]),
        AssemblyStep(key="b", slots=["slat"])), CATALOG)
    assert any("alternatives" in e for e in errs)


def test_the_built_in_routed_model_is_valid_with_all_of_this_on_it():
    """The demo is the only document in the repo that exercises scopes, bay parts
    and two kinds of prerequisite at once, and it is what the browser suite
    renders. A schema change that invalidated it would ship a built-in model the
    app refuses."""
    from fenceai.fencemodel.demo import M_VINYL
    from fenceai.parts.demo import demo_parts
    from fenceai.parts.model import PartLibrary

    assert validate_model(M_VINYL, CATALOG, PartLibrary(parts=demo_parts())) == []
