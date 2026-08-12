"""Fitting a repeating member pattern into one dimension (fence-model spec §fit).

The same shape of problem as `strategy/layout.py`, one dimension down: given an
axis length and a repeating sequence of members and gaps, how many members fit
and what are the real gaps. Pure, no Pydantic, no other module — so the
justification x excess boundary matrix stays cheap to pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import lcm
from typing import Literal

from fenceai.core.units import Mm

Justification = Literal["start", "end", "center", "spread_to_fit"]
Excess = Literal["truncate", "space", "trim_last", "extension_clip"]


@dataclass(frozen=True)
class FitResult:
    count: int
    gaps_mm: list[Mm]            # BETWEEN members; len == max(count - 1, 0)
    edge_margin_start_mm: Mm
    edge_margin_end_mm: Mm
    residual_mm: Mm              # unallocated axis length after members+gaps+margins
    rejected_alternative: list[Mm] | None  # the gap list the other excess policy gives

    @property
    def openings_mm(self) -> list[Mm]:
        """EVERY opening across the axis, not only those between members.

        The sphere test measures a hole, and it does not care whether the hole is
        between two slats or between a slat and a post. `gaps_mm` alone misses
        both edge margins and the residual — and those are exactly where the
        slack goes: `center` justification folds the whole residual into the two
        margins and zeroes `residual_mm`, so a 2000 mm opening with 300 mm
        members and a `truncate` excess stands with two 150 mm holes against the
        posts while every between-member gap reads 50 mm.

        `start` and `spread_to_fit` leave the residual at the far end, so it
        belongs to the end margin; `end` and `center` already folded it in and
        zeroed it. Either way, adding it to the end margin is exact.
        """
        return [self.edge_margin_start_mm, *self.gaps_mm,
                self.edge_margin_end_mm + self.residual_mm]


def _cycle_advance_mm(widths: list[Mm], gaps: list[Mm]) -> Mm:
    """How far one FULL repeat of the pattern moves along the axis.

    The widths and the gaps are independent cycles, so the pattern only repeats
    after lcm(len(widths), len(gaps)) members — a two-member sequence against a
    one-member gap list advances by the sum over both members, not over one.
    """
    cycle = lcm(len(widths), len(gaps))
    return sum(widths[i % len(widths)] + gaps[i % len(gaps)] for i in range(cycle))


def _count_members(usable_mm: Mm, widths: list[Mm], gaps: list[Mm]) -> int:
    """Walk the repeating sequence, adding a member then the gap that follows it,
    while the NEXT member still fits. Gaps may be negative (an overlap)."""
    if usable_mm <= 0 or not widths or not gaps:
        return 0
    # A pattern whose full repeat does not move FORWARD places infinitely many
    # members in finite space: `used` never grows, `count` increments for ever,
    # and — because this runs inside generate() — the request thread hangs with
    # no exception ever raised. There is no defensible member count to return
    # (both 0 and "as many as we felt like" would be inventions), so say so.
    # The condition is deliberately per-CYCLE, not per-member: a pattern whose
    # individual member overlaps its neighbour to zero advance is still a real
    # board-on-board fence as long as the repeat as a whole moves on.
    # `validate_model` is the load-time gate and is stricter (per member); this
    # is the safety net for the callers that never pass through it.
    if _cycle_advance_mm(widths, gaps) <= 0:
        raise ValueError(
            f"member pattern never advances: widths {widths} with gaps {gaps} "
            f"move {_cycle_advance_mm(widths, gaps)} mm per repeat, so no finite "
            "number of members fills the axis"
        )
    used = 0
    count = 0
    while True:
        w = widths[count % len(widths)]
        if used + w > usable_mm:
            return count
        used += w
        count += 1
        used += gaps[(count - 1) % len(gaps)]


def _spread(total_mm: Mm, n: int) -> list[Mm]:
    """Remainder one mm at a time to the first gaps — the rule equal_layout uses
    (`strategy/layout.py:18`), so both spreaders behave the same way."""
    if n <= 0:
        return []
    base, rem = divmod(total_mm, n)
    return [base + 1 if i < rem else base for i in range(n)]


def fit_pattern(
    axis_len_mm: Mm,
    member_widths_mm: list[Mm],
    gaps_after_mm: list[Mm],
    *,
    justification: Justification,
    excess: Excess,
    edge_margin_mm: Mm,
) -> FitResult:
    usable = axis_len_mm - 2 * edge_margin_mm
    count = _count_members(usable, member_widths_mm, gaps_after_mm)
    if count == 0:
        # Margins alone can already claim the whole axis (or more, on a short
        # or negative one) — clamp each to half of what the axis actually has
        # rather than reporting the requested margin AND a residual that
        # double-counts the same millimetres. Deriving residual as the
        # remainder (never a separate max()) keeps the two sides equal by
        # construction, for every axis length including zero and negative.
        start = end = min(edge_margin_mm, max(axis_len_mm, 0) // 2)
        return FitResult(0, [], start, end, axis_len_mm - start - end, None)

    widths_used = sum(member_widths_mm[i % len(member_widths_mm)] for i in range(count))
    nominal = [gaps_after_mm[i % len(gaps_after_mm)] for i in range(count - 1)]
    slack = usable - widths_used - sum(nominal)

    if excess == "space" and nominal:
        gaps = [g + extra for g, extra in zip(nominal, _spread(slack, len(nominal)))]
        residual = 0
    else:
        gaps = nominal
        residual = slack

    start, end = edge_margin_mm, edge_margin_mm
    if residual and justification in ("end", "center"):
        # 'start' leaves the residual at the far end (nothing to do); 'end' pushes
        # the whole run against the far end; 'center' halves it, odd mm to the end
        # so two identical panels are identical.
        shift = residual if justification == "end" else residual // 2
        start += shift
        end += residual - shift
        residual = 0

    alternative = nominal if excess == "space" and gaps != nominal else None
    return FitResult(count, gaps, start, end, residual, alternative)
