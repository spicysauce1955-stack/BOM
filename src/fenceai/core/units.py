"""Unit discipline (ADR-0002): integer millimeters and cents at rest.

Exactly two tolerances exist in the whole system. Do not add ad-hoc epsilons.
"""

from __future__ import annotations

import math

# Construction-scale tolerance: "same point", loop closure, anchor re-matching.
SNAP_TOLERANCE_MM = 25
# Numeric tolerance for comparing derived geometry after rounding back to int mm.
NUMERIC_TOLERANCE_MM = 1

Mm = int  # semantic alias: integer millimeters
Cents = int  # semantic alias: integer cents


def dist_mm(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Euclidean distance between two int-mm points, rounded once to int mm."""
    return round(math.hypot(b[0] - a[0], b[1] - a[1]))


def slope_len_mm(plan_mm: int, rise_mm: int) -> int:
    """Slope (true) length from plan-projected length and vertical rise.

    The single documented rounding point for chord->slope conversion (ADR-0002).
    """
    return round(math.hypot(plan_mm, rise_mm))
