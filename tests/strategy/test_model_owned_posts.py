"""A model's own post and cap, as a run actually experiences them.

`tests/fencemodel/test_post_slot.py` pins the schema. What is pinned here is
that a declared post REACHES the fence — and that the situational posts still
win, because a post bolted to a wall or carrying a gate is doing a different job
from the one a product line ships.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import (
    Capabilities, Catalog, IndivisibleDiscrete, Product,
)
from fenceai.demand.derive import derive_requirements
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, PostSlot,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.ast import Cmp, FieldRef
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import ForcePostSku, Override
from tests.conftest import straight_topology

MODEL_ID = "M-OWNPOST"


def _model(post_sku="POST-S-HD", cap_sku="POST-CAP") -> FenceModel:
    return FenceModel(
        id=MODEL_ID, version=1,
        post=PostSlot(
            key="post",
            requirement=PartRequirement(
                role="post",
                eligibility=Eligibility(members=[EligibleItem(sku=post_sku)])),
            cap=PartRequirement(
                role="cap",
                eligibility=Eligibility(members=[EligibleItem(sku=cap_sku)])),
        ),
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal", placement=Distributed(count=2),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])),
        )]),
    )


def _run(model=None, topo=None, catalog=None, knowledge=None, policy=None,
         overrides=None):
    return generate(
        topo or straight_topology(3000), knowledge or demo_knowledge(),
        catalog or demo_catalog(), policy=policy, overrides=overrides,
        models=FenceModelLibrary(models=[model or _model()]),
        default_model=FenceModelChoice(model_id=MODEL_ID),
    )


def test_the_model_names_the_post_the_fence_is_built_with():
    """Knowledge's `post_ground` default is POST-S; this line ships POST-S-HD."""
    posts = _run().strategy.posts
    assert posts
    assert {p.sku for p in posts} == {"POST-S-HD"}


def test_a_model_with_no_opinion_still_gets_the_company_post_and_cap():
    """`post=None` is no opinion, and knowledge answers exactly as before."""
    model = _model()
    model.post = None
    result = _run(model)
    assert {p.sku for p in result.strategy.posts} == {"POST-S"}
    caps = [line for line in derive_requirements(
        result.strategy, demo_catalog(), policy=result.run.demand_skus)
        if line.role == "cap"]
    assert caps
    assert all([m.sku for m in c.eligibility.members] == ["POST-CAP"] for c in caps)


def test_the_model_names_the_cap_too():
    """Deliberately NOT POST-CAP: that is the company default, so a cap test
    using it passes whether or not the model was ever consulted. LATCH is not a
    cap in any real sense — it is simply a product the demo catalog has that the
    default is not, which is what makes the assertion able to fail."""
    result = _run(_model(cap_sku="LATCH"))
    caps = [line for line in derive_requirements(
        result.strategy, demo_catalog(), policy=result.run.demand_skus)
        if line.role == "cap"]
    assert caps
    assert all([m.sku for m in c.eligibility.members] == ["LATCH"] for c in caps)


# --- the panel facts a post is matched against --------------------------------

def _routed_catalog(*routings: tuple[str, list[int]]) -> Catalog:
    """The demo catalog plus vinyl posts that declare where they are ROUTED.

    `routed_at_mm` is a list, and it is in the open `attrs` bag on purpose: no
    Python reads it, a predicate does. The typed `capabilities` record is for
    facts deterministic CODE consumes.
    """
    catalog = demo_catalog()
    for sku, heights in routings:
        catalog.products[sku] = Product(
            sku=sku, name=f"Routed vinyl post {sku}",
            consumption=IndivisibleDiscrete(), price_cents=9000,
            attrs={"material": "vinyl", "routed_at_mm": heights},
            capabilities=Capabilities(length_mm=2600, face_width_mm=100),
        )
    return catalog


def _routed_model(*, insets: int = 150, cap=None) -> FenceModel:
    """A post that must be routed exactly where this panel puts its rails."""
    return FenceModel(
        id=MODEL_ID, version=1,
        post=PostSlot(
            key="post",
            requirement=PartRequirement(
                role="post",
                eligibility=Eligibility(predicate=Cmp(
                    cmp="==", left=FieldRef(path="item.routed_at_mm"),
                    right=FieldRef(path="panel.rail_positions_mm")))),
            cap=cap,
        ),
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal",
            placement=Distributed(count=2, count_param="rails_per_span",
                                  bottom_inset_mm=insets, top_inset_mm=insets),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])),
        )]),
    )


def test_a_post_is_matched_against_the_rails_its_panel_will_actually_have():
    """The arc's whole reason to exist. A 1800 mm panel with two rails inset
    150 mm puts them at 150 and 1650, so the post routed at 150/1650 is the one
    that can be assembled — and the post routed at 200/1700 is a fence that
    cannot be built, not a worse buy.

    Both are in the catalog and only the panel's own geometry separates them."""
    result = _run(_routed_model(),
                  catalog=_routed_catalog(("POST-V-150", [150, 1650]),
                                          ("POST-V-200", [200, 1700])))
    assert {p.sku for p in result.strategy.posts} == {"POST-V-150"}


def test_a_taller_panel_moves_the_rails_and_therefore_the_post():
    """The same model, the same catalog, a different height — and a different
    post. This is what makes the previous test an answer rather than a lookup:
    the rails a post is matched against are computed from the bay, so a fence
    ordered 300 mm taller orders a differently routed post."""
    result = _run(_routed_model(),
                  catalog=_routed_catalog(("POST-V-150", [150, 1650]),
                                          ("POST-V-200", [150, 1950])),
                  policy={"default_height_mm": 2100})
    assert {p.sku for p in result.strategy.posts} == {"POST-V-200"}


def test_the_rail_count_a_post_sees_is_the_one_knowledge_resolved():
    """`rails_per_span` is knowledge, not structure — a company rule may say three
    rails on this line. The post has to be routed for the rails the BAY gets, so
    the count reaching the matcher must be the resolved one and never the model's
    contributed default."""
    kb = KnowledgeBase(versions=[*demo_knowledge().versions, KnowledgeVersion(
        object_id="K-THREE-RAIL", version=1, type="company_rule",
        actions=[SetParam(param="rails_per_span", value=3)],
        title="Three rails on this line", scope={"series": MODEL_ID},
    )])
    result = _run(_routed_model(),
                  catalog=_routed_catalog(("POST-V-2", [150, 1650]),
                                          ("POST-V-3", [150, 900, 1650])),
                  knowledge=kb)
    assert {p.sku for p in result.strategy.posts} == {"POST-V-3"}
    assert all(s.rail_count == 3 for s in result.strategy.spans)


def test_a_cap_is_matched_against_the_post_it_caps():
    """Ordered, not circular, and the reason `cap` NESTS inside `PostSlot`: the
    post is chosen first, so the cap may ask how wide its face is. The routed post
    is 100 mm; POST-CAP-100 fits it and POST-CAP-80 does not."""
    catalog = _routed_catalog(("POST-V-150", [150, 1650]))
    for sku, face in (("POST-CAP-80", 80), ("POST-CAP-100", 100)):
        catalog.products[sku] = Product(
            sku=sku, name=f"Cap for {face} mm post",
            consumption=IndivisibleDiscrete(), price_cents=1200,
            attrs={"material": "vinyl", "fits_face_mm": face},
        )
    cap = PartRequirement(role="cap", eligibility=Eligibility(predicate=Cmp(
        cmp="==", left=FieldRef(path="item.fits_face_mm"),
        right=FieldRef(path="post.face_width_mm"))))
    result = _run(_routed_model(cap=cap), catalog=catalog)
    caps = [line for line in derive_requirements(
        result.strategy, catalog, policy=result.run.demand_skus) if line.role == "cap"]
    assert caps
    assert all([m.sku for m in c.eligibility.members] == ["POST-CAP-100"] for c in caps)


def test_a_cap_follows_the_post_that_was_ACTUALLY_stood_there():
    """`_make_post` puts a forced sku, a masonry mount and a gate reinforcement
    ABOVE the model's post, because each of those is a post doing a different
    JOB. The cap has to follow: a cap matched against the post the model WANTED
    is a cap for a post that is not on the drawing.

    One station is patched to a 140 mm post and the rest keep the model's 100 mm
    one, so the run needs two different caps — and the wrong answer here is not a
    missing line but a wrong one, which is why it is worth a test."""
    catalog = _routed_catalog(("POST-V-150", [150, 1650]))
    catalog.products["POST-WIDE"] = Product(
        sku="POST-WIDE", name="A post the user patched in",
        consumption=IndivisibleDiscrete(), price_cents=9500,
        attrs={"material": "vinyl"},
        capabilities=Capabilities(length_mm=2600, face_width_mm=140),
    )
    for sku, face in (("POST-CAP-100", 100), ("POST-CAP-140", 140)):
        catalog.products[sku] = Product(
            sku=sku, name=f"Cap for {face} mm post",
            consumption=IndivisibleDiscrete(), price_cents=1200,
            attrs={"material": "vinyl", "fits_face_mm": face},
        )
    cap = PartRequirement(role="cap", eligibility=Eligibility(predicate=Cmp(
        cmp="==", left=FieldRef(path="item.fits_face_mm"),
        right=FieldRef(path="post.face_width_mm"))))
    result = _run(
        _routed_model(cap=cap), catalog=catalog,
        overrides=[Override(id="ov_wide", run_id="run1",
                            directive=ForcePostSku(station_mm=1500,
                                                   sku="POST-WIDE"))],
    )
    at = {p.station_mm: (p.sku, p.cap_sku) for p in result.strategy.posts}
    assert at[1500] == ("POST-WIDE", "POST-CAP-140"), \
        "the patched post is 140 mm and its cap must be the one that fits it"
    assert at[0] == ("POST-V-150", "POST-CAP-100")


def test_a_cap_nothing_fits_the_STOOD_post_is_a_warning_not_a_wrong_cap():
    """The other half, and the reason this is not merely cosmetic: when the post
    that actually stands there has no cap in the catalog, the honest answer is no
    cap and a warning. Quietly keeping the cap that fitted the model's post would
    put a part on the BOM that cannot be fitted to the post beside it."""
    catalog = _routed_catalog(("POST-V-150", [150, 1650]))
    catalog.products["POST-WIDE"] = Product(
        sku="POST-WIDE", name="A post the user patched in",
        consumption=IndivisibleDiscrete(), price_cents=9500,
        attrs={"material": "vinyl"},
        capabilities=Capabilities(length_mm=2600, face_width_mm=140),
    )
    catalog.products["POST-CAP-100"] = Product(
        sku="POST-CAP-100", name="Cap for 100 mm post",
        consumption=IndivisibleDiscrete(), price_cents=1200,
        attrs={"material": "vinyl", "fits_face_mm": 100},
    )
    cap = PartRequirement(role="cap", eligibility=Eligibility(predicate=Cmp(
        cmp="==", left=FieldRef(path="item.fits_face_mm"),
        right=FieldRef(path="post.face_width_mm"))))
    result = _run(
        _routed_model(cap=cap), catalog=catalog,
        overrides=[Override(id="ov_wide", run_id="run1",
                            directive=ForcePostSku(station_mm=1500,
                                                   sku="POST-WIDE"))],
    )
    at = {p.station_mm: (p.sku, p.cap_sku) for p in result.strategy.posts}
    assert at[1500] == ("POST-WIDE", "")
    assert at[0] == ("POST-V-150", "POST-CAP-100")
    warned = [w for w in result.strategy.warnings
              if w.code == "no_item_covers_part_spec"]
    assert warned and all(w.severity == "warning" for w in warned)
    assert any("post@run1:1500" in w.element_refs for w in warned)


def test_the_post_is_recorded_on_the_run_like_any_other_choice():
    """A model-chosen post is a product this run named, so it belongs in
    `catalog_skus` — the set `catalog_hash` narrows to. A post the run bought and
    did not record would let that product be repriced with nobody refused."""
    result = _run()
    assert "POST-S-HD" in result.run.catalog_skus
