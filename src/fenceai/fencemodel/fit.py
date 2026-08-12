"""Fitting a repeating member pattern into one dimension (fence-model spec §fit).

The same shape of problem as `strategy/layout.py`, one dimension down: given an
axis length and a repeating sequence of members and gaps, how many members fit
and what are the real gaps. Pure, no Pydantic, no other module — so the
justification x excess boundary matrix stays cheap to pin.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _count_members(usable_mm: Mm, widths: list[Mm], gaps: list[Mm]) -> int:
    """Walk the repeating sequence, adding a member then the gap that follows it,
    while the NEXT member still fits. Gaps may be negative (an overlap)."""
    if usable_mm <= 0 or not widths:
        return 0
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
