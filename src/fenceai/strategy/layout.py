"""Span layout: closed-form, deterministic (ADR-0007, material-optimization.md)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from fenceai.core.units import Mm, round_milli_to_mm


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
    """n = ceil(L/max), widths L//n with remainder spread one mm to the first spans.

    The all-millimetre form, for a maximum span with no finer precision behind it
    — an authored rule, `FALLBACK_MAX_SPAN_MM`, a yield threshold this module
    computed itself. Where the limit came from a PUBLISHED quantity, the caller
    owes it `equal_layout_milli` instead: see that function for why.
    """
    if length_mm <= 0:
        return []
    n = math.ceil(length_mm / max_span_mm)
    base, rem = divmod(length_mm, n)
    return [base + 1 if i < rem else base for i in range(n)]


def equal_layout_milli(length_milli: int, max_span_milli: int) -> list[Mm]:
    """`equal_layout`, dividing by the PUBLISHED span limit rather than by a
    limit already rounded to the nearest millimetre.

    `contract.md:112-117` is BINDING that *"any arithmetic that MULTIPLIES a
    published value — a count, a pitch, a span limit — consumes the thousandths
    and rounds only its output."* `n = ceil(L / max_span)` is that arithmetic and
    `max_span` is that published value, and the clause spells out this exact
    division as its own worked example. Five of the six span magnitudes in the
    real `footing_schedule` tables are not whole millimetres, and rounding before
    the division moves the bay count on 2318 of the first 100 000 run lengths —
    both ways, for two different harms:

    * DOWN. `1422400` thousandths becomes `1422 mm`, and a 4267 mm run divides
      into 4 bays instead of 3. The clause's own sentence: an extra post, an
      extra footing, an extra pour — and it arrives THROUGH the rounding the
      clause mandates, which is why rounding correctly at `to_mm` was never
      enough on its own.
    * UP. `2463800` becomes `2464 mm`, and a 2464 mm run becomes one bay of
      2464.000 mm against a sealed maximum of 2463.8. Cheaper, and over the
      limit a stamped engineering table set.

    **Only `n` needs the thousandths, and that is not a compromise.** `n` is a
    COUNT, so "rounds only its output" is satisfied for free — integer ceiling
    division produces an exact integer with nothing left to round. The widths it
    then splits are LENGTHS AT REST, and ADR-0002 puts those in integer
    millimetres; `divmod(length_mm, n)` runs at mm exactly as it always has, so
    `sum(widths) == length_mm` still holds by construction and every bay is still
    a whole millimetre a person can measure. Carrying the split down to
    thousandths would not be more accurate, it would be a fence dimensioned in
    a unit nobody builds in.

    `length_milli` is scaled `*1000` by every caller and that IS exact, unlike
    the divisor: a run length is the user's drawing, integer mm at rest, with no
    finer precision anywhere upstream to lose. It is rounded back once here for
    the width split — a no-op on any value a caller can actually produce, and
    written as a rounding rather than an integer division so the function cannot
    floor a length if one ever arrives with a fraction. The parameter is milli
    anyway, to match `fencemodel.fit.fit_pattern_milli` and keep one readable
    convention: a `_milli` function takes thousandths throughout.
    """
    if length_milli <= 0 or max_span_milli <= 0:
        return []
    # Integer ceiling division — never `math.ceil(a / b)`, which converts both
    # sides to float first. At thousandths a run length is a number like
    # 100_000_000 and a span limit 2_463_800; float division of those is not
    # exact, and the values that would land wrong are precisely the ones where
    # the quotient sits a hair from an integer, which is the entire case this
    # function exists for.
    n = -(-length_milli // max_span_milli)
    base, rem = divmod(round_milli_to_mm(length_milli), n)
    return [base + 1 if i < rem else base for i in range(n)]


def min_bay_count(length_mm: Mm, max_span_milli: int) -> int:
    """`n = ceil(L / max_span)` at the PUBLISHED precision — the bay count
    `equal_layout_milli` lays this length out in, named once so nothing has to
    recompute it and drift.

    It is half of `admits_widths` below, and the half that makes the other half
    honest: the ceiling a remainder spread reaches is only defensible for a
    layout that could not have been split one more time.
    """
    if length_mm <= 0 or max_span_milli <= 0:
        return 0
    return -(-length_mm * 1000 // max_span_milli)


def remainder_ceiling_mm(max_span_milli: int) -> Mm:
    """`ceil(max_span_milli / 1000)` — the widest whole millimetre the remainder
    spread of a minimum-count layout can reach.

    **This is not a bound and must never be used as one on its own.** It was, and
    the failure is worth writing down: a published limit of 1422.4 mm has this
    return 1423, and a 1423 mm bay then looks admissible to anything that
    compares against it — including a stored answer of THREE 1423 mm bays on a
    4269 mm run, which is a post and a footing removed from a stamped schedule
    with nothing to show for it. The argument that made the ceiling safe ("with
    `n = ceil(L/max)` the widest bay is `floor(L/n)+1` at most") is an argument
    about layouts THIS ENGINE computes, and a bound cannot carry a premise its
    caller does not have to satisfy.

    So the premise is now a condition. Read this only through `admits_widths`,
    which pairs it with `min_bay_count` — together they say the thing the
    argument actually said.
    """
    return -(-max_span_milli // 1000)


def earns_remainder_ceiling(
    widths: list[Mm], length_mm: Mm, max_span_milli: int,
) -> bool:
    """Is this width list the minimum-count layout whose integer-millimetre
    remainder the ceiling excuses?

    The conjunction, in one place: no bay above `ceil(limit)`, and exactly the
    bay count the true limit forces. `contract.md`:112-117 chooses the count
    computed from the published thousandths, and ADR-0002 stores the widths as
    whole millimetres; where those two disagree by a fraction, one bay carries
    it. That bay is admissible because the only alternative is an extra post,
    footing and pour bought to recover six tenths of a millimetre — an argument
    that holds for THIS layout and evaporates for a layout with a spare bay in
    it, where the same fraction could simply have been spread differently.

    `==` on the count and not `<=`. Fewer bays than the minimum means a bay
    over the limit that a split would have fixed; more bays means the fraction
    was never forced.
    """
    if not widths or max_span_milli <= 0:
        return False
    return (max(widths) <= remainder_ceiling_mm(max_span_milli)
            and len(widths) == min_bay_count(length_mm, max_span_milli))


def admits_widths(
    widths: list[Mm],
    length_mm: Mm,
    max_span_mm: Mm,
    *,
    max_span_milli: int | None = None,
) -> bool:
    """The ONE admissibility rule for a bay layout: may this segment be built
    with these widths?

    Every site that asks the question asks it here — what the generator offers
    as an alternative, what it accepts back as a person's stored answer, what it
    lets a `lock_bay` depart from, and what makes it stop the run. They were four
    comparisons before, and they disagreed in both directions: the offer side
    filtered against the rounded millimetre limit while the accept side compared
    against `ceil(published)`, so the engine would never OFFER a 1423 mm bay and
    would happily ACCEPT one.

    Three clauses:

    * the widths tile the segment exactly, and every bay is positive;
    * no bay exceeds `max_span_mm`, the resolved limit AT REST (ADR-0002) — the
      number every clamp, warning and payload in the generator is written in.
      This is the whole rule for the authored data in this repo, where the limit
      is a whole millimetre and `max_span_milli` is exactly `max_span_mm * 1000`;
    * above that, and only there, the published fraction gets its say through
      `earns_remainder_ceiling`.

    `min_span_mm` is deliberately NOT here. `layout_segment` only warns about a
    sliver and a person may want a 400 mm bay against a wall, so a selected
    sliver is built and reported through `sliver_span` rather than refused —
    refusing it would make an answered question stricter than an unanswered one.

    Admissibility rather than membership of a candidate set, for a reason worth
    keeping: what a person chose is the WIDTHS. If they are still buildable they
    are still the answer, even where a changed `max_span` means a different
    generator would now propose them. It also avoids needing the candidate set
    before a choice can be honoured, which would be circular — candidates are
    measured from the baseline the choice helps produce.
    """
    if not widths or any(w <= 0 for w in widths):
        return False
    if sum(widths) != length_mm:
        return False
    if max(widths) <= max_span_mm:
        return True
    milli = max_span_mm * 1000 if max_span_milli is None else max_span_milli
    return earns_remainder_ceiling(widths, length_mm, milli)


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
    max_span_milli: int | None = None,
) -> LayoutResult:
    """Lay out one free segment. Equal-width preferred layout, recording the nominal
    alternative when it differs (decision-graph alternatives, scenario S02).
    nominal_mm defaults to max_span_mm and is always clamped to the hard maximum.

    `exact_mm` is not a preference and does not compete with one: it says the bays
    are a manufactured size, so it wins outright and the free-layout alternative
    is recorded as what was given up.

    `max_span_milli` is the PUBLISHED thousandths of the same limit, where a
    publisher sent them (`SetParam.value_milli`). It changes nothing else about
    this function: it reaches only the bay-COUNT division, which `contract.md`
    §1.1 requires to consume the thousandths, and `max_span_mm` remains the
    limit every comparison and every clamp here is made against, because those
    are millimetre facts about millimetre widths. Omitted, it defaults to
    `max_span_mm * 1000`, which is exact for an authored rule and for the
    fallback basis — so a caller that does not know about published precision
    keeps the behaviour it had.
    """
    span_milli = max_span_mm * 1000 if max_span_milli is None else max_span_milli
    if exact_mm and exact_mm > max_span_mm:
        # A manufactured width wider than the hard maximum is a CONFLICT between
        # two things of different kinds, and the caller surfaces it as one.
        # Clamping it here would silently produce bays of neither width, and then
        # report the width nobody used — S13's shape exactly, resolved by
        # arithmetic instead of by the conflict machinery.
        return LayoutResult(
            widths=equal_layout_milli(length_mm * 1000, span_milli),
            rejected_alternative=None, exact_over_max=True,
        )
    if exact_mm:
        widths, remainder = exact_layout(length_mm, exact_mm)
        free = equal_layout_milli(length_mm * 1000, span_milli)
        return LayoutResult(
            widths=widths,
            rejected_alternative=free if free != widths else None,
            remainder_mm=remainder,
        )
    nominal_width = min(nominal_mm or max_span_mm, max_span_mm)
    equal = equal_layout_milli(length_mm * 1000, span_milli)
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
    max_span_milli: int | None = None,
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

    "Honours the resolved maximum" is `admits_widths` and nothing else, which is
    the point of `max_span_milli` reaching here: this function is the OFFER side
    of the same question the generator answers on the ACCEPT side when the answer
    comes back, and the two used to be different comparisons. Filtering here
    against the rounded millimetre while accepting against `ceil(published)` left
    one choice set with two admissibility bounds pointing opposite ways.
    """
    out: list[tuple[str, list[Mm]]] = []
    seen = {tuple(default)}

    def offer(name: str, widths: list[Mm]) -> None:
        if not widths or tuple(widths) in seen:
            return
        if not admits_widths(widths, length_mm, max_span_mm,
                             max_span_milli=max_span_milli):
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
