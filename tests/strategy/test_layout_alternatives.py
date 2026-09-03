"""The alternatives to whatever the engine just built.

Two things the first draft of this got wrong, both found by adversarial review.

The yield threshold is a threshold on the **infill piece**, and a piece is cut to
the clear opening — `clear_opening_mm` subtracts a whole post face — so a
threshold applied to a bay width is measured on a length `plan_cuts` is never
handed. With a 70 mm face the cliff is 70 mm away from where the draft put it.

And the default was regenerated here rather than passed in, so a `min_span` rule
that only WARNS inside `layout_segment` while REJECTING in candidate generation
could leave the built layout absent from its own panel.

`docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md` §5.
"""

from __future__ import annotations

from fenceai.strategy.layout import alternative_widths, yield_threshold


def test_the_yield_threshold_is_the_cliff_plan_cuts_actually_has():
    """Each piece costs `length + kerf` against a capacity of `stock + kerf`, so
    two fit at 998 and not at 1000. Checked against `plan_cuts` itself, not
    against this formula, in `tests/strategy/test_yield_against_plan_cuts.py`."""
    assert yield_threshold(2000, 3, 2) == 998
    assert yield_threshold(2000, 0, 2) == 1000
    assert yield_threshold(2000, 3, 1) == 2000


def test_a_degenerate_piece_count_returns_zero_rather_than_dividing():
    """The JS twin gives `Infinity` for the same call, so both sides guard it and
    the node test compares them over a grid that includes this row."""
    assert yield_threshold(2000, 3, 0) == 0
    assert yield_threshold(0, 3, 2) == 0


def test_the_default_is_never_returned_as_an_alternative():
    """It is already a point. Offering it twice asks the same question twice."""
    assert alternative_widths(5000, 1800, default=[1667, 1667, 1666]) == []


def test_a_manufactured_width_is_offered_beside_the_default():
    got = dict(alternative_widths(5000, 2000, default=[1667, 1667, 1666],
                                   exact_mm=2000))
    assert got["tiling"] == [2000, 2000, 1000]


def test_the_yield_alternative_converts_through_the_post_face():
    """The threshold is on the PIECE. A bay is wider than the piece it holds by
    one post face, so the bay-width target is the piece threshold plus the face
    — and the first draft's 998 was 70 mm off on a 70 mm post."""
    got = dict(alternative_widths(
        5000, 2000, default=[1667, 1667, 1666],
        piece_stock_mm=2000, kerf_mm=3, piece_shorter_by_mm=70))
    # piece threshold 998 -> bay target 1068 -> ceil(5000 / 1068) = 5 bays
    assert got["best_yield"] == [1000, 1000, 1000, 1000, 1000]


def test_no_stock_means_no_yield_alternative_rather_than_a_guessed_one():
    """Before the baseline resolves a panel there is no stock length. The engine
    does not invent one in order to have something to offer."""
    assert "best_yield" not in dict(
        alternative_widths(5000, 2000, default=[1667, 1667, 1666]))


def test_an_alternative_below_the_minimum_span_is_not_offered():
    """A sliver is not an option. `prefer_min_span_width` is a knowledge rule, so
    the caller passes the floor in rather than this module inventing one."""
    got = dict(alternative_widths(
        5000, 2000, default=[1667, 1667, 1666], min_span_mm=1200,
        piece_stock_mm=2000, kerf_mm=3, piece_shorter_by_mm=0))
    assert "best_yield" not in got


def test_an_alternative_over_the_maximum_span_is_not_offered():
    """`exact_span` wider than the RESOLVED maximum is a conflict the generator
    already reports through its own machinery; it is not an option to put on a
    panel."""
    assert alternative_widths(5000, 1800, default=[1667, 1667, 1666],
                               exact_mm=2000) == []


def test_a_zero_length_gap_offers_nothing():
    assert alternative_widths(0, 2000, default=[]) == []


def test_a_yield_target_at_or_over_the_maximum_offers_nothing_new():
    """A threshold at or above the maximum span reproduces the layout the first
    generator already produced, and a duplicate row is a question asked twice."""
    got = alternative_widths(5000, 900, default=[1667, 1667, 1666],
                              piece_stock_mm=2000, kerf_mm=3)
    assert [name for name, _ in got] == []
