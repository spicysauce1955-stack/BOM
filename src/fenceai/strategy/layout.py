"""Span layout: closed-form, deterministic (ADR-0007, material-optimization.md)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from fenceai.core.units import Mm


@dataclass(frozen=True)
class LayoutResult:
    widths: list[Mm]
    rejected_alternative: list[Mm] | None  # e.g. nominal-width layout demoted by K-EQUAL


def equal_layout(length_mm: Mm, max_span_mm: Mm) -> list[Mm]:
    """n = ceil(L/max), widths L//n with remainder spread one mm to the first spans."""
    if length_mm <= 0:
        return []
    n = math.ceil(length_mm / max_span_mm)
    base, rem = divmod(length_mm, n)
    return [base + 1 if i < rem else base for i in range(n)]


def nominal_layout(length_mm: Mm, nominal_mm: Mm) -> list[Mm]:
    """Full nominal-width spans plus one remainder span (the rejected S02 alternative)."""
    if length_mm <= 0:
        return []
    n_full, rem = divmod(length_mm, nominal_mm)
    widths = [nominal_mm] * n_full
    if rem:
        widths.append(rem)
    return widths or [length_mm]


def layout_segment(
    length_mm: Mm,
    max_span_mm: Mm,
    *,
    prefer_equal: bool = True,
    min_span_mm: Mm | None = None,
) -> LayoutResult:
    """Lay out one free segment. Equal-width preferred layout, recording the nominal
    alternative when it differs (decision-graph alternatives, scenario S02)."""
    equal = equal_layout(length_mm, max_span_mm)
    nominal = nominal_layout(length_mm, max_span_mm)
    if prefer_equal:
        chosen, rejected = equal, (nominal if nominal != equal else None)
    else:
        chosen, rejected = nominal, (equal if equal != nominal else None)
    if min_span_mm and any(w < min_span_mm for w in chosen) and len(chosen) > 1:
        # sliver avoidance cannot fix a segment shorter than min span; otherwise the
        # equal layout only produces slivers when length/n < min — merging spans would
        # violate max_span, so the sliver stands but is reported by the caller.
        pass
    return LayoutResult(widths=chosen, rejected_alternative=rejected)


def boundaries(start_mm: Mm, widths: list[Mm]) -> list[Mm]:
    out = [start_mm]
    for w in widths:
        out.append(out[-1] + w)
    return out
