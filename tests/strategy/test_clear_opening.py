"""The clear opening between two posts, as a bay actually experiences it.

`PanelContext` carried `clear_width_mm=width` from phase 1 onward — the
centre-to-centre width, with a comment saying face widths would arrive later.
They never did, so `clear_between_posts` and `centre_to_centre` returned the same
number and every vertical infill was fitted across an opening that includes half a
post at each end.

What is pinned here is the difference between the two rules. The arithmetic itself
lives in `tests/fencemodel/test_clear_width.py`.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

MODEL_ID = "M-CLEAR"

# demo_catalog(): POST-S is the soil default and declares attrs.face_width_mm.
# Half of it is lost at each end of a bay, so a bay loses one whole face.
POST_S_FACE_MM = 80


def _model(length_rule: str) -> FenceModel:
    return FenceModel(
        id=MODEL_ID, version=1, name_i18n={"en": "Clear-rule test"},
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal",
            placement=Distributed(count=2),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule=length_rule,
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),
            ),
        )]),
    )


def _rail_lengths(length_rule: str) -> list[tuple[int, int]]:
    """(bay centre-to-centre width, rail cut length) for every bay."""
    result = generate(
        straight_topology(3000),
        demo_knowledge(),
        demo_catalog(),
        models=FenceModelLibrary(models=[_model(length_rule)]),
        default_model=FenceModelChoice(model_id=MODEL_ID),
    )
    assert result.strategy.spans, "no bays were laid out"
    return [
        (span.width_mm,
         next(s.length_mm for s in span.panel.slots if s.slot_key == "rail"))
        for span in result.strategy.spans
    ]


def test_a_clear_between_posts_member_is_cut_narrower_than_the_bay_is_wide():
    """Half a post face is lost at each end, so a bay loses one whole face."""
    for width_mm, cut_mm in _rail_lengths("clear_between_posts"):
        assert cut_mm == width_mm - POST_S_FACE_MM


def test_a_centre_to_centre_member_is_cut_to_the_full_bay_width():
    """The other half of the same fact: the two rules must not agree."""
    for width_mm, cut_mm in _rail_lengths("centre_to_centre"):
        assert cut_mm == width_mm


def test_a_bay_records_the_clear_opening_it_was_resolved_with():
    """Computed once, in generation, from the posts that bound the bay — and
    RECORDED, because a stored run is re-read by the panel preview and by the
    read models. Re-deriving the opening downstream is how the picture and the
    cut list end up a post-face apart."""
    result = generate(
        straight_topology(3000),
        demo_knowledge(),
        demo_catalog(),
        models=FenceModelLibrary(models=[_model("centre_to_centre")]),
        default_model=FenceModelChoice(model_id=MODEL_ID),
    )
    assert result.strategy.spans
    for span in result.strategy.spans:
        assert span.clear_width_mm == span.width_mm - POST_S_FACE_MM
