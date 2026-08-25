"""The S18 through-rail fence, as a fixture two suites share.

Not a test module. It exists because obligation 14's shape — a demand line pegged
to TWO bays, and a 4800 mm piece cut from a 4877 mm bar — has to reach the
cross-scenario invariant battery and the compatibility gate, and neither can
build it from the shared demo catalog.

**Its own catalog, deliberately, exactly as S15 records for its own two-stock
fixture.** Adding a 16 ft and a 12 ft rail to `demo_catalog()` would put two new
divisible-linear rails in front of every predicate eligibility in the portfolio —
which is how S07's "RAIL-3000 is the only rail stock" answer moves, and how a
change meant to pin new behaviour quietly repriced every existing job.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import (
    Capabilities, DivisibleLinear, LinearPrice, Product,
)
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Axis, Distributed, Eligibility, EligibleItem, FenceModel, FixingRule,
    FrameSlot, OptionValue, PanelSpec, PartRequirement, PolicyContribution,
)
from fenceai.fencemodel.selection import FenceModelChoice

# 97 in, and the two stock lengths obligation 14 names, converted once.
MAX_SPAN_MM = 2464
STOCK_16FT_MM = 4877
STOCK_12FT_MM = 3658
RUN_MM = 9600            # four bays at 2400


def rail_product(sku: str, stock_mm: int) -> Product:
    return Product(
        sku=sku, name=f"Rail {stock_mm} mm",
        consumption=DivisibleLinear(
            purchase_length_mm=stock_mm, kerf_mm=3, min_reusable_remnant_mm=300),
        pricing=LinearPrice(cents_per_m=1000),
        capabilities=Capabilities(face_width_mm=40),
    )


def catalog_with_two_colours():
    catalog = demo_catalog()
    catalog.products["RAIL-16FT-WHITE"] = rail_product("RAIL-16FT-WHITE", STOCK_16FT_MM)
    catalog.products["RAIL-12FT-BLEND"] = rail_product("RAIL-12FT-BLEND", STOCK_12FT_MM)
    return catalog


def board_model(*, post_joint: str = "through", continuity: str = "derived") -> FenceModel:
    """One panel, two colours, and NOT ONE WORD about continuity.

    `post_joint="through"` is the authored CAPABILITY — this rail is detailed to
    pass the post rather than stop at it. It is not the answer: the same joint
    gives two bays per piece in White and one in Blend, which is the whole point.
    """
    return FenceModel(
        id="M-BOARD", version=1,
        name_i18n={"en": "Through-rail board fence", "he": "גדר קרש עם מסילה עוברת"},
        option_axes=[Axis(key="colour", kind="enum", values=[
            OptionValue(key="white"), OptionValue(key="blend")])],
        layout_policy=[PolicyContribution(
            param="max_span_mm", value=MAX_SPAN_MM, knowledge_type="hard_constraint")],
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal", post_joint=post_joint,
                continuity=continuity,
                placement=Distributed(count=2, count_param="rails_per_span"),
                requirement=PartRequirement(
                    role="rail", qty=1, length_rule="centre_to_centre",
                    option_axis="colour",
                    sku_by_option={"white": "RAIL-16FT-WHITE",
                                   "blend": "RAIL-12FT-BLEND"},
                    eligibility=Eligibility(members=[
                        EligibleItem(sku="RAIL-16FT-WHITE", priority=1),
                        EligibleItem(sku="RAIL-12FT-BLEND", priority=2)]),
                ),
            )],
            fixings=[FixingRule(
                key="screw", basis="per_panel", qty_per_basis=8,
                requirement=PartRequirement(
                    role="screw", qty=1,
                    eligibility=Eligibility(
                        members=[EligibleItem(sku="SCREW-S10", priority=1)]),
                ),
            )],
        ),
    )


def board_library() -> FenceModelLibrary:
    return FenceModelLibrary(models=[board_model()])


def white_choice() -> FenceModelChoice:
    return FenceModelChoice(model_id="M-BOARD", options={"colour": "white"})
