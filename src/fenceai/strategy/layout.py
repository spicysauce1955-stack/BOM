"""Span layout: closed-form, deterministic (ADR-0007, material-optimization.md)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from fenceai.core.units import Mm


@dataclass(frozen=True)
class LayoutResult:
    widths: list[Mm]
    rejected_alternative: list[Mm] | None  # e.g. nominal-width layout demoted by K-EQUAL
    # the odd bay an exact-width model could not tile away, in mm. None when the
    # layout is free, or when the segment divided exactly.
    remainder_mm: Mm | None = None
    # the model asked for bays wider than the hard maximum allows: unusable, so
    # the free layout stands and the caller reports the conflict
    exact_over_max: bool = False


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


def exact_layout(length_mm: Mm, exact_mm: Mm) -> tuple[list[Mm], Mm | None]:
    """Tile a segment with bays of EXACTLY this width, plus whatever is left.

    For a model that ships as a pre-assembled panel, span width is not the
    layout's to choose: an off-size bay has no panel to put in it. The segment
    rarely divides exactly, so the honest answer is `floor(L / exact)` exact bays
    and one remainder bay, with the remainder REPORTED — a layout that silently
    stretched every bay to make it come out even would put panels in bays they do
    not fit. A model that cannot tolerate a remainder says so as a
    `hard_constraint` contribution, and generation fails instead.
    """
    if length_mm <= 0 or exact_mm <= 0:
        return [], None
    n_full, rem = divmod(length_mm, exact_mm)
    if not n_full:
        # the segment is shorter than one panel: it IS the remainder, and
        # pretending otherwise would produce a zero-bay section
        return [length_mm], length_mm
    widths = [exact_mm] * n_full
    if rem:
        widths.append(rem)
    return widths, (rem or None)


def layout_segment(
    length_mm: Mm,
    max_span_mm: Mm,
    *,
    prefer_equal: bool = True,
    min_span_mm: Mm | None = None,
    nominal_mm: Mm | None = None,
    exact_mm: Mm | None = None,
) -> LayoutResult:
    """Lay out one free segment. Equal-width preferred layout, recording the nominal
    alternative when it differs (decision-graph alternatives, scenario S02).
    nominal_mm defaults to max_span_mm and is always clamped to the hard maximum.

    `exact_mm` is not a preference and does not compete with one: it says the bays
    are a manufactured size, so it wins outright and the free-layout alternative
    is recorded as what was given up."""
    if exact_mm and exact_mm > max_span_mm:
        # A manufactured width wider than the hard maximum is a CONFLICT between
        # two things of different kinds, and the caller surfaces it as one.
        # Clamping it here would silently produce bays of neither width, and then
        # report the width nobody used — S13's shape exactly, resolved by
        # arithmetic instead of by the conflict machinery.
        return LayoutResult(
            widths=equal_layout(length_mm, max_span_mm),
            rejected_alternative=None, exact_over_max=True,
        )
    if exact_mm:
        widths, remainder = exact_layout(length_mm, exact_mm)
        free = equal_layout(length_mm, max_span_mm)
        return LayoutResult(
            widths=widths,
            rejected_alternative=free if free != widths else None,
            remainder_mm=remainder,
        )
    nominal_width = min(nominal_mm or max_span_mm, max_span_mm)
    equal = equal_layout(length_mm, max_span_mm)
    nominal = nominal_layout(length_mm, nominal_width)
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


def yield_threshold(stock_mm: Mm, kerf_mm: Mm, pieces: int) -> Mm:
    """The longest PIECE that still yields `pieces` per stock length.

    `plan_cuts` charges each piece `length + kerf` against a capacity of
    `stock + kerf` — it credits back the kerf nobody cuts after the last piece —
    so `pieces` fit exactly when `pieces * (p + kerf) <= stock + kerf`. Integer
    division, because a threshold rounded up names a length that does not fit.

    **This is a threshold on the PIECE, not on the bay.** An infill piece is cut
    to the clear opening (`fencemodel/resolve.py`), which is narrower than its
    bay by one whole post face — so a caller turning this into a bay width adds
    the face back. Getting that wrong is how the first draft of this design came
    to advertise a saving 70 mm away from where it actually is, and to claim a
    cliff at 1000 mm where two pieces already fit.

    It also has a twin in `web/static/js/post-drag.js`, because the browser needs
    it to place a snap tick. `tests/web/test_post_drag_module.py` compares the
    two over a grid rather than trusting two literals to stay equal.
    """
    if pieces < 1 or stock_mm <= 0:
        return 0
    return (stock_mm + kerf_mm) // pieces - kerf_mm


def alternative_widths(
    length_mm: Mm,
    max_span_mm: Mm,
    *,
    default: list[Mm],
    exact_mm: Mm | None = None,
    min_span_mm: Mm | None = None,
    piece_stock_mm: Mm | None = None,
    kerf_mm: Mm = 3,
    piece_shorter_by_mm: Mm = 0,
) -> list[tuple[str, list[Mm]]]:
    """Width lists worth offering BESIDE the one already built.

    `default` is passed in rather than recomputed, and that is the point:
    `layout_segment` decides what is built — honouring `prefer_equal`, a nominal
    width preference, and a `min_span` rule it only WARNS about — and a second
    opinion here is how the built layout came to be missing from its own panel.

    `piece_stock_mm` and `piece_shorter_by_mm` come from the BASELINE's resolved
    infill: its product's stock length, and how much narrower a piece is than the
    bay holding it. Neither exists until a panel is resolved, which is why
    candidate generation runs after the baseline rather than at the layout site.
    With no stock known this returns no yield alternative rather than a guessed
    one.

    Every returned list already honours the resolved maximum and minimum span, so
    an offered point never needs a person to be told it was inadmissible.
    """
    out: list[tuple[str, list[Mm]]] = []
    seen = {tuple(default)}

    def offer(name: str, widths: list[Mm]) -> None:
        if not widths or tuple(widths) in seen:
            return
        if max(widths) > max_span_mm:
            return
        if min_span_mm and min(widths) < min_span_mm:
            return
        seen.add(tuple(widths))
        out.append((name, widths))

    if length_mm <= 0:
        return out
    if exact_mm:
        offer("tiling", exact_layout(length_mm, exact_mm)[0])
    if piece_stock_mm:
        # Two pieces per board is the only step worth offering: three is a bay
        # under 700 mm on 2 m stock, which is what `min_span_mm` exists to
        # refuse — and a generator that offers slivers is the one an operator
        # turns off.
        target = yield_threshold(piece_stock_mm, kerf_mm, 2) + piece_shorter_by_mm
        if 0 < target < max_span_mm:
            offer("best_yield", equal_layout(length_mm, target))
    return out
