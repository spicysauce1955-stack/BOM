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
from fenceai.fencemodel.match import post_panel_facts
from fenceai.fencemodel.model import (
    POST_PREDICATE_PANEL_FACTS, Distributed, Eligibility, EligibleItem, FenceModel,
    FrameSlot, PanelSpec, PartRequirement, PostSlot, Variant, validate_model,
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


def test_a_post_predicate_may_read_the_height_derived_panel_facts():
    """`POST_PREDICATE_PANEL_FACTS` is the set, and the generator now supplies it
    at the post's own station (`tests/strategy/test_model_owned_posts.py`). Every
    name in it must therefore be accepted here — a set the author is told they may
    read and is then refused for reading is worse than no set at all."""
    for field in POST_PREDICATE_PANEL_FACTS:
        reads = Cmp(cmp=">=", left=FieldRef(path="item.length_mm"),
                    right=FieldRef(path=f"panel.{field}"))
        errs = validate_model(_model(_post(requirement=PartRequirement(
            role="post", eligibility=Eligibility(predicate=reads)))), demo_catalog())
        assert errs == [], f"panel.{field} was refused: {errs}"


def test_the_readable_set_is_exactly_what_the_generator_supplies():
    """Two statements of one set drift the moment either moves — and the drift is
    silent in the worst direction: a fact declared readable but never supplied
    makes a predicate match NOTHING, and the post falls through to the company
    default with nobody told."""
    supplied = post_panel_facts(
        model_id="M", height_mm=1800, vertical="level", rail_positions_mm=[0, 1800],
    )["panel"]
    assert set(supplied) == POST_PREDICATE_PANEL_FACTS


def test_a_post_predicate_on_the_item_alone_is_fine():
    """Which is the whole usable case today: a product line identifying its own
    post by what that post IS."""
    vinyl = Cmp(cmp="==", left=FieldRef(path="item.material"),
                right=Lit(value="galvanised_steel"))
    model = _model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=vinyl))))
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


def _routed_post() -> PostSlot:
    """A post matched on where the panel puts its rails — the routed-vinyl case."""
    return _post(requirement=PartRequirement(
        role="post",
        eligibility=Eligibility(predicate=Cmp(
            cmp="==", left=FieldRef(path="item.routed_at_mm"),
            right=FieldRef(path="panel.rail_positions_mm")))))


def _variant(condition) -> Variant:
    return Variant(condition=condition, spec=PanelSpec(frame=[_rail_slot()]))


def test_a_width_conditioned_variant_is_refused_beside_a_routed_post():
    """A post is resolved at its OWN station, where the bay's width does not
    exist — a post stands between two bays that need not be the same width. A
    variant turning on the width is therefore "not applicable" there, the DEFAULT
    spec's rails are handed to the predicate, and the post is matched against a
    panel the fence does not build. Refused where it is a typo."""
    model = _model(_routed_post())
    model.variants = [_variant(Cmp(cmp=">", left=FieldRef(path="panel.width_mm"),
                                   right=Lit(value=2000)))]
    errs = validate_model(model, demo_catalog())
    assert any("panel.width_mm" in e and "rail_positions_mm" in e for e in errs)


def test_a_height_conditioned_variant_is_fine_beside_a_routed_post():
    """The height IS known at a post's station — it is what the rail positions are
    derived from. Refusing every variant would refuse the feature."""
    model = _model(_routed_post())
    model.variants = [_variant(Cmp(cmp=">", left=FieldRef(path="panel.height_mm"),
                                   right=Lit(value=2000)))]
    assert validate_model(model, demo_catalog()) == []


def test_a_width_conditioned_variant_is_fine_when_no_post_reads_the_rails():
    """Neither feature is a problem alone, and the refusal fires only where they
    meet — a model whose posts are named or matched on `item.*` may condition its
    variants on anything a bay knows."""
    model = _model(_post())
    model.variants = [_variant(Cmp(cmp=">", left=FieldRef(path="panel.width_mm"),
                                   right=Lit(value=2000)))]
    assert validate_model(model, demo_catalog()) == []


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
