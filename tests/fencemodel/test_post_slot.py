"""Posts and caps as parts of the MODEL.

A fence model describes the panel between two posts and says nothing about the
posts themselves; a post's product came from a knowledge `DefaultComponent`
resolved once for the whole run. That is right for a company with one post
standard and wrong for a product LINE — a routed vinyl post is specific to the
panel that seats into it, and the panel is not expressible without it.

What is pinned here is the schema and its load-time rules. The generator wiring
lives in `tests/strategy/`.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, PostSlot, validate_model,
)
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit

POST_ITEMS = Eligibility(members=[EligibleItem(sku="POST-S")])
CAP_ITEMS = Eligibility(members=[EligibleItem(sku="POST-CAP")])


def _rail_slot() -> FrameSlot:
    return FrameSlot(
        key="rail", orientation="horizontal", placement=Distributed(count=2),
        requirement=PartRequirement(
            role="rail", qty=1, length_rule="centre_to_centre",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])),
    )


def _model(post: PostSlot | None) -> FenceModel:
    return FenceModel(id="M-POST", version=1, post=post,
                      default_spec=PanelSpec(frame=[_rail_slot()]))


def _post(requirement=None, cap=None) -> PostSlot:
    return PostSlot(
        key="post",
        requirement=requirement or PartRequirement(role="post", eligibility=POST_ITEMS),
        cap=cap,
    )


def test_a_model_may_say_nothing_about_posts():
    """`None` is NO OPINION, not "must come from knowledge" — it is what every
    shipped model carries, and it is what lets a boundary post between an
    opinionated model and a legacy one resolve to the opinionated one."""
    assert _model(None).post is None
    assert validate_model(_model(None), demo_catalog()) == []


def test_a_model_may_own_its_post_and_cap():
    model = _model(_post(cap=PartRequirement(role="cap", eligibility=CAP_ITEMS)))
    assert validate_model(model, demo_catalog()) == []
    assert model.post.requirement.role == "post"
    assert model.post.cap.role == "cap"


def test_a_post_slot_with_no_eligible_product_is_refused():
    """The same guardrail every other slot gets: a slot nothing can supply
    publishes cleanly and then fails on every job built to the model."""
    errs = validate_model(_model(_post(
        requirement=PartRequirement(role="post", eligibility=Eligibility()))),
        demo_catalog())
    assert any("post" in e for e in errs)


def test_a_post_predicate_may_read_height_derived_panel_facts():
    """A routed post has to agree with where the panel puts its rails, so it
    must be able to ask."""
    tall_enough = Cmp(cmp=">=", left=FieldRef(path="item.length_mm"),
                      right=FieldRef(path="panel.height_mm"))
    model = _model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=tall_enough))))
    assert validate_model(model, demo_catalog()) == []


def test_a_post_predicate_may_not_read_the_clear_width_it_helps_define():
    """THE cycle rule. The clear opening is measured to the post faces, so a
    post chosen BY the opening would be choosing itself. Refused by name at
    authoring, where it is a typo, rather than at generation, where it is a
    hang or an arbitrary answer."""
    circular = Cmp(cmp="<=", left=FieldRef(path="item.face_width_mm"),
                   right=FieldRef(path="panel.clear_width_mm"))
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=circular)))), demo_catalog())
    assert any("clear_width_mm" in e for e in errs)


def test_the_refusal_names_what_a_post_predicate_may_read():
    """A refusal the author cannot act on is half a refusal."""
    circular = Cmp(cmp="<=", left=FieldRef(path="item.face_width_mm"),
                   right=FieldRef(path="panel.centre_width_mm"))
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=circular)))), demo_catalog())
    assert any("rail_positions_mm" in e and "height_mm" in e for e in errs)


def test_a_cap_predicate_may_read_the_post_it_caps():
    """Ordered, not circular: the post is chosen first, so a cap may ask about
    it. That is the whole reason cap NESTS inside PostSlot."""
    fits = And(items=[
        Cmp(cmp="==", left=FieldRef(path="item.material"), right=Lit(value="aluminium")),
        Cmp(cmp="==", left=FieldRef(path="post.face_width_mm"), right=Lit(value=80)),
    ])
    model = _model(_post(cap=PartRequirement(
        role="cap", eligibility=Eligibility(predicate=fits))))
    assert validate_model(model, demo_catalog()) == []
