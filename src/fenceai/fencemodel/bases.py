"""Fixing bases — how many of a thing a panel needs, as data rather than a branch.

Was a `Literal` of six names in `model.py` plus a dict literal in `resolve.py`
that knew what each meant. Adding `per_corner` meant editing both and shipping a
release; adding a part type meant adding a row. See `core/registry.py` for why
that asymmetry was worth removing.

**The signature is the contract**: `(PanelCounts) -> int`. A basis that can be
written this way is a registration. One that cannot — a basis needing the
neighbouring bay, say, which a panel does not know — is the escalation test
saying it needs a release, and a `Gap` until then.
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from fenceai.core.registry import Registry


class PanelCounts(BaseModel):
    """What a basis may count, and nothing else.

    The three are genuinely different and conflating them over-orders, which is
    the mistake this type exists to make hard:

    * `member_count` is **parts** — a member with `qty=2` is two physical pieces
      at one position (a batten pair, a board front and back), and each takes its
      own screw and makes its own crossing.
    * `placed_count` is **positions along the axis**, which is what the fit
      produced. A gap is between two positions, not between two pieces that share
      one; with `qty=2` the two counts differ by a factor.
    * `frame_count` is the frame members the infill crosses.
    """

    member_count: int = 0
    placed_count: int = 0
    frame_count: int = 0


FixingBasisFn = Callable[[PanelCounts], int]

FIXING_BASES: Registry[FixingBasisFn] = Registry("fixing basis")


@FIXING_BASES.register("per_panel")
def _per_panel(counts: PanelCounts) -> int:
    return 1


@FIXING_BASES.register("per_frame_member")
def _per_frame_member(counts: PanelCounts) -> int:
    return counts.frame_count


@FIXING_BASES.register("per_member")
def _per_member(counts: PanelCounts) -> int:
    return counts.member_count


@FIXING_BASES.register("per_end_member")
def _per_end_member(counts: PanelCounts) -> int:
    """First and last ALONG THE AXIS — a placement question, so it counts
    positions rather than parts."""
    return min(counts.placed_count, 2)


@FIXING_BASES.register("per_gap")
def _per_gap(counts: PanelCounts) -> int:
    return max(counts.placed_count - 1, 0)


@FIXING_BASES.register("per_member_crossing")
def _per_member_crossing(counts: PanelCounts) -> int:
    """Counted ARITHMETICALLY — members x frame members — not by walking real
    intersections. `report/elevation.py` says the same thing where it draws them."""
    return counts.member_count * counts.frame_count
