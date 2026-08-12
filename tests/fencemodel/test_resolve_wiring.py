"""Every field `resolve_panel` threads from a spec into a resolved slot.

The test review mutated nine of these one at a time and the suite stayed green:
each is a single-line pass-through, and each is an equivalent mutant against the
demo models, which happen to use the default for all of them. The authoring API
accepts every one of them today, so an author using any gets no protection at
all. This file is one panel that uses none of the defaults.
"""

from __future__ import annotations

import pytest

from fenceai.fencemodel.model import (
    Distributed,
    Eligibility,
    EligibleItem,
    FixingRule,
    FrameSlot,
    InfillSpec,
    Member,
    PanelSpec,
    PartRequirement,
)
from fenceai.fencemodel.resolve import PanelContext, resolve_panel
from fenceai.report.elevation import panel_elevation

RAIL = Eligibility(members=[EligibleItem(sku="RAIL-3000")])
SLAT = Eligibility(members=[EligibleItem(sku="SLAT-100")])
SCREW = Eligibility(members=[EligibleItem(sku="SCREW-S10")])


def spec() -> PanelSpec:
    """A panel that uses the non-default value of everything under test."""
    return PanelSpec(
        frame=[
            FrameSlot(
                key="rail", orientation="horizontal", thickness_mm=40,
                placement=Distributed(count=2),
                requirement=PartRequirement(role="rail", qty=1,
                                            length_rule="centre_to_centre",
                                            eligibility=RAIL),
            ),
            FrameSlot(
                key="stile", orientation="vertical",
                placement=Distributed(count=2),
                requirement=PartRequirement(role="rail", qty=1,
                                            length_rule="panel_height",
                                            eligibility=RAIL),
            ),
        ],
        infill=InfillSpec(
            orientation="vertical", justification="end", excess="truncate",
            edge_margin_mm=75,
            pattern=[
                Member(key="wide", width_mm=200, gap_after_mm=30, thickness_mm=20,
                       requirement=PartRequirement(role="infill", qty=2,
                                                   length_rule="panel_height",
                                                   eligibility=SLAT)),
                Member(key="narrow", width_mm=50, gap_after_mm=30,
                       face_offset_mm=-15,
                       requirement=PartRequirement(role="infill", qty=1,
                                                   length_rule="panel_height",
                                                   eligibility=SLAT)),
            ],
        ),
        fixings=[
            FixingRule(key="endclip", basis="per_end_member", qty_per_basis=1,
                       requirement=PartRequirement(role="screw", eligibility=SCREW)),
            FixingRule(key="spacer", basis="per_gap", qty_per_basis=1,
                       requirement=PartRequirement(role="screw", eligibility=SCREW)),
        ],
    )


BAY = PanelContext(centre_width_mm=2000, clear_width_mm=2000, height_mm=1800)


@pytest.fixture()
def slots():
    return {s.slot_key: s for s in resolve_panel(spec(), BAY).slots}


# --- the infill spec's own fields ---------------------------------------------

def test_the_edge_margin_reaches_the_fit(slots):
    """A model with an edge margin must not butt its members against the posts."""
    assert slots["wide"].fit.edge_margin_start_mm >= 75


def test_the_justification_reaches_the_fit(slots):
    """`end` pushes the run against the far end, so the residual lands at the
    START. Defaulting to `start` would put it at the wrong end silently."""
    fit = slots["wide"].fit
    assert fit.edge_margin_start_mm > fit.edge_margin_end_mm
    assert fit.residual_mm == 0


def test_a_members_own_quantity_multiplies_its_count(slots):
    """`qty=2` on a member means two parts per placed member — a batten pair, a
    front and a back board. Dropping it buys half the panel."""
    fit = slots["wide"].fit
    placed_wide = sum(1 for i in range(fit.count) if i % 2 == 0)
    assert slots["wide"].qty == 2 * placed_wide
    assert slots["narrow"].qty == fit.count - placed_wide


def test_a_negative_face_offset_puts_a_member_on_the_back_face(slots):
    """This is what makes shadowbox a pattern rather than a special case."""
    assert slots["narrow"].face_offset_mm == -15
    elevation = panel_elevation(resolve_panel(spec(), BAY), 2000, 1800)
    backs = {m.slot_key for m in elevation.members if m.face == "back"}
    assert backs == {"narrow"}


# --- frame placement -----------------------------------------------------------

def test_a_vertical_frame_slot_is_placed_across_the_width_not_up_the_height(slots):
    """`orientation="vertical"` is a first-class value with no test anywhere.
    Placing a stile up the height puts both of them on top of each other."""
    assert slots["stile"].positions_mm == [0, 2000]
    assert slots["rail"].positions_mm == [0, 1800]


def test_a_declared_face_height_is_reported_as_declared(slots):
    """The flag has to mean something in BOTH directions, or asserting it is
    vacuous: `declared` defaults to True, so only a False case tested anything."""
    assert slots["rail"].thickness_mm == 40
    assert slots["stile"].thickness_mm is None
    elevation = panel_elevation(resolve_panel(spec(), BAY), 2000, 1800)
    by_slot = {m.slot_key: m for m in elevation.members}
    assert by_slot["rail"].declared is True and by_slot["rail"].h_mm == 40
    assert by_slot["stile"].declared is False


# --- fixing bases --------------------------------------------------------------

def test_per_end_member_is_two_not_every_member(slots):
    """An end clip goes on the first and last member. Counting every member
    over-orders by roughly twentyfold."""
    assert slots["endclip"].qty == 2


def test_per_gap_counts_positions_not_pieces(slots):
    """A gap is between two POSITIONS along the axis. A member with `qty=2` is
    two pieces at ONE position — a batten pair — and it makes no extra gap. This
    test found the code counting pieces: a panel of 12 positions ordered 17
    spacers instead of 11, an error nobody notices until the van is loaded."""
    placed = slots["wide"].fit.count
    assert slots["wide"].qty == 2 * (placed - placed // 2), "the fixture needs qty=2"
    assert slots["spacer"].qty == placed - 1


def test_the_whole_panel_is_deterministic():
    assert resolve_panel(spec(), BAY) == resolve_panel(spec(), BAY)
