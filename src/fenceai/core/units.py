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


def round_milli_to_mm(milli: int) -> int:
    """The ROUNDING RULE thousandths obey on their way to millimetres.

    Not the boundary itself: `knowledge.parameters.to_mm` is the one named point
    where a published `Quantity` becomes an `Mm` (contract §1.1, BINDING), and it
    is the only thing that checks the unit. This is the arithmetic that point
    applies, factored out here because `knowledge.model.SetParam` has to apply
    the SAME rule to check that a value at rest and the thousandths riding beside
    it are the same number — and it cannot import `parameters`, which imports it.

    Half-away-from-ZERO, written out because `round()` is banker's rounding and
    would send 2500 thousandths to 2 rather than 3. `-2500` gives `-3`, so the
    magnitude rounds the same in both directions and neither direction ever
    floors. A floor is the harm the clause names: `2463.8` floored to 2463 buys
    an extra post, footing and pour on a 9.8 m run.

    `fencemodel/fit.py` keeps a third copy on purpose — that module imports
    nothing but this alias — and `tests/fencemodel/test_fit.py` pins the copies
    against each other rather than trusting three literals to stay equal.
    """
    whole, rem = divmod(abs(milli), 1000)
    if rem >= 500:
        whole += 1
    return -whole if milli < 0 else whole
