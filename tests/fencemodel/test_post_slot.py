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
    POST_PREDICATE_PANEL_FACTS, POST_PREDICATE_POST_FACTS, Distributed, Eligibility,
    EligibleItem, FenceModel, FrameSlot, PanelSpec, PartRequirement, PostSlot,
    Variant, validate_model,
)
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit
from fenceai.project.model import SITE_DIMENSIONS

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
    default with nobody told.

    All three namespaces, because all three are declared: `panel` narrowed by the
    cycle rule, `post` — where this one stands — and `site`, which the cycle rule
    does not narrow at all.

    `site` is pinned DIFFERENTLY on purpose, and the difference is the whole
    design of the namespace. `panel` and `post` are closed sets and every member
    is always supplied. A site dimension is supplied only when the PROJECT
    answered it, because that absence is what makes a condition on it *not
    applicable* instead of false — so the assertion is containment, and equality
    would be pinning the fixture's site rather than the contract. What the author
    may READ is `SITE_DIMENSIONS`; what a given run SUPPLIES is whatever was
    entered, and `site_condition_missing` reports the difference.
    """
    supplied = post_panel_facts(
        model_id="M", height_mm=1800, vertical="level", rail_positions_mm=[0, 1800],
        kind="line", site={"hvhz": True},
    )
    assert set(supplied) == {"panel", "post", "site"}
    assert set(supplied["panel"]) == POST_PREDICATE_PANEL_FACTS
    assert set(supplied["post"]) == POST_PREDICATE_POST_FACTS
    # What the author may READ is the whole vocabulary...
    assert set(supplied["site"]) <= SITE_DIMENSIONS
    # ...and what THIS call supplies is exactly what it was handed, unfiltered.
    # Containment alone let a namespace lose a dimension on the way through and
    # still pass, which is the one failure a post's site namespace can have.
    assert supplied["site"] == {"hvhz": True}

    # A caller with no site passes `{}` and SAYS so — there is no default to
    # forget, because an unbound namespace and an unanswered dimension need
    # opposite treatments (`resolve._assert_site_bound`).
    no_site = post_panel_facts(
        model_id="M", height_mm=1800, vertical="level", rail_positions_mm=[0, 1800],
        kind="line", site={},
    )
    assert no_site["site"] == {}


def test_the_site_namespace_cannot_be_forgotten_by_a_new_call_site():
    """`site` is a required keyword, so the mistake is a TypeError at the call
    site rather than a fence quietly built to the default spec.

    This is the guard that keeps the whole slice from being re-openable: the
    silent version of this failure is what `site.*` was bound to fix."""
    import pytest as _pytest
    with _pytest.raises(TypeError):
        post_panel_facts(model_id="M", height_mm=1800, vertical="level",
                         rail_positions_mm=[0, 1800], kind="line")


def test_a_post_predicate_may_read_where_it_stands():
    """The routed-post fact. WHICH FACES a post is cut on is decided by its
    position in the layout — one face at an end, two opposite mid-run, two
    adjacent at a corner — so a line whose posts are routed cannot name its post
    without reading `post.kind`.

    It is readable and `panel.clear_width_mm` is not, and the difference is not
    taste: a post's kind comes from the TOPOLOGY and is settled before any bay is
    laid out, so it sits outside the resolution DAG rather than inside it.

    Kills: removing `post.kind` from `POST_PREDICATE_POST_FACTS`, which would
    refuse the only predicate that can order an end post correctly.
    """
    reads = Cmp(cmp="==", left=FieldRef(path="post.kind"), right=Lit(value="end"))
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=reads)))), demo_catalog())
    assert errs == [], f"post.kind was refused: {errs}"


def test_every_name_declared_readable_about_the_post_is_accepted():
    """The same guard `POST_PREDICATE_PANEL_FACTS` gets, on the second set: a
    name an author is told they may read and is then refused for reading is worse
    than no set at all.

    Kills: adding a fact to `POST_PREDICATE_POST_FACTS` and to `post_panel_facts`
    without teaching `_post_namespace_errors` about it.
    """
    for field in POST_PREDICATE_POST_FACTS:
        reads = Cmp(cmp="==", left=FieldRef(path=f"post.{field}"),
                    right=Lit(value="anything"))
        errs = validate_model(_model(_post(requirement=PartRequirement(
            role="post", eligibility=Eligibility(predicate=reads)))), demo_catalog())
        assert errs == [], f"post.{field} was refused: {errs}"


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


def test_a_post_may_not_be_matched_on_the_post_it_is():
    """The cycle rule in its second form. A cap reads the post because the post
    was chosen first; a post reading one has no first answer.

    `post` being readable at all is what makes this worth pinning twice: opening
    the namespace for WHERE a post stands must not open it for WHAT it is, and
    the refusal must still name what may be read instead.

    Kills: widening the post namespace to `post.*` (e.g. by giving a post the
    cap's `may_read_post`) rather than to the declared set.
    """
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=Cmp(
            cmp="==", left=FieldRef(path="post.face_width_mm"),
            right=Lit(value=80)))))), demo_catalog())
    assert any("choosing itself" in e for e in errs)
    assert any("post.kind" in e for e in errs)


def test_a_post_predicate_reading_a_namespace_nobody_supplies_is_still_refused():
    """The `post` namespace is now partly open, and an unknown HEAD must not
    ride in on that. `MissingField` is a NO in the matcher, so this would match
    nothing and fall silently through to the company default.

    Kills: allowing any `post.*` path, and dropping the head check entirely.
    """
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=Cmp(
            cmp="==", left=FieldRef(path="station.kind"),
            right=Lit(value="end")))))), demo_catalog())
    assert any("station.kind" in e for e in errs)
    assert any("post.kind" in e for e in errs)   # and it says what to read instead


def test_a_post_may_not_be_matched_on_a_position_fact_nobody_supplies():
    """`post.mounting` is the near miss this refusal exists for: it is settled as
    early as the kind is, and it is deliberately NOT supplied (it is resolved
    from knowledge after the post is chosen, and a `force_mounting` override can
    move it — see `match.post_panel_facts`). Declared-but-unsupplied is the one
    failure mode the two-sets-pinned-equal test cannot catch on its own, so the
    boundary is asserted from the other side too.

    Kills: hand-waving `post.mounting` into `POST_PREDICATE_POST_FACTS` without
    supplying it — which would make the predicate match nothing at all.
    """
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=Cmp(
            cmp="==", left=FieldRef(path="post.mounting"),
            right=Lit(value="masonry")))))), demo_catalog())
    assert any("post.mounting" in e for e in errs)


def test_a_cap_predicate_reading_a_namespace_nobody_supplies_is_refused():
    """`MissingField` is a NO in the matcher, so an unsupplied namespace does not
    error at generation — it matches nothing, and the slot falls silently through
    to the company default. The author is told here instead."""
    errs = validate_model(_model(_post(cap=PartRequirement(
        role="cap", eligibility=Eligibility(predicate=Cmp(
            cmp="==", left=FieldRef(path="project.city"),
            right=Lit(value="חיפה")))))), demo_catalog())
    assert any("project.city" in e and "cap" in e for e in errs)


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


def test_a_site_conditioned_variant_is_fine_beside_a_routed_post():
    """The site IS known at a post's station, and unlike a width there is a right
    answer to give: a whole-site fact does not vary between the two bays a post
    stands between, so `_PostFacts.at` supplies the SAME site the bay does and
    both pick the same variant.

    Kills: adding `site` to the condition context without teaching
    `_variant_reach_errors` that it is answerable there, which would refuse a
    site-conditioned variant on every routed model — the feature declared and
    then withheld from the product line most likely to want it.
    """
    model = _model(_routed_post())
    model.variants = [_variant(Cmp(cmp="==", left=FieldRef(path="site.hvhz"),
                                   right=Lit(value=True)))]
    assert validate_model(model, demo_catalog()) == []


def test_a_post_predicate_may_read_the_site():
    """A post is a product too, and "galvanised posts in a hurricane zone" is an
    item-against-SITE relation. The cycle rule does not narrow it: a whole-site
    fact is settled before the fence is drawn, so it cannot depend on the post it
    helps choose."""
    reads = Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=True))
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=reads)))), demo_catalog())
    assert errs == [], f"site.hvhz was refused: {errs}"


def test_a_post_predicate_reading_a_site_dimension_that_does_not_exist_is_refused():
    """The namespace being open is not the dimension being open. An unknown
    dimension matches nothing, forever, and the post falls silently through to
    the company default — which is what `_post_namespace_errors` exists to stop
    for every other namespace."""
    reads = Cmp(cmp="==", left=FieldRef(path="site.hvzh"), right=Lit(value=True))
    errs = validate_model(_model(_post(requirement=PartRequirement(
        role="post", eligibility=Eligibility(predicate=reads)))), demo_catalog())
    assert any("site.hvzh is not a site condition" in e for e in errs)


def test_a_width_conditioned_variant_is_refused_beside_a_routed_CAP_too():
    """A cap's predicate is evaluated against the same post-time facts, so a cap
    matched on `panel.rail_positions_mm` takes the identical divergence — and got
    no refusal at all, because the check read only the post's own predicate.

    Same defect, same sentence, one slot along."""
    routed_cap = _post(
        requirement=PartRequirement(
            role="post",
            eligibility=Eligibility(members=[EligibleItem(sku="POST-S-HD")])),
        cap=PartRequirement(
            role="cap",
            eligibility=Eligibility(predicate=Cmp(
                cmp="==", left=FieldRef(path="item.routed_at_mm"),
                right=FieldRef(path="panel.rail_positions_mm")))),
    )
    model = _model(routed_cap)
    model.variants = [_variant(Cmp(cmp=">", left=FieldRef(path="panel.width_mm"),
                                   right=Lit(value=2000)))]
    errs = validate_model(model, demo_catalog())
    assert any("panel.width_mm" in e and "(cap)" in e for e in errs), errs


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
