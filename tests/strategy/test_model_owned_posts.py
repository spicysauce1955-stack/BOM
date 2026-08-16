"""A model's own post and cap, as a run actually experiences them.

`tests/fencemodel/test_post_slot.py` pins the schema. What is pinned here is
that a declared post REACHES the fence — and that the situational posts still
win, because a post bolted to a wall or carrying a gate is doing a different job
from the one a product line ships.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, PostSlot,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
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


def _run(model=None, topo=None):
    return generate(
        topo or straight_topology(3000), demo_knowledge(), demo_catalog(),
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


def test_the_post_is_recorded_on_the_run_like_any_other_choice():
    """A model-chosen post is a product this run named, so it belongs in
    `catalog_skus` — the set `catalog_hash` narrows to. A post the run bought and
    did not record would let that product be repriced with nobody refused."""
    result = _run()
    assert "POST-S-HD" in result.run.catalog_skus
