"""Span layout boundary tests (test-review finding 5)."""

from __future__ import annotations

from fenceai.strategy.layout import (
    boundaries, equal_layout, equal_layout_milli, layout_segment, nominal_layout,
)


def test_exact_multiple_of_max_span():
    assert equal_layout(3600, 1800) == [1800, 1800]  # exactly at the hard max, 2 spans


def test_run_shorter_than_max_span():
    assert equal_layout(1000, 1800) == [1000]


def test_remainder_spread():
    assert equal_layout(4000, 1800) == [1334, 1333, 1333]
    assert sum(equal_layout(4000, 1800)) == 4000


def test_zero_and_negative_length():
    assert equal_layout(0, 1800) == []
    assert equal_layout(-5, 1800) == []


def test_all_widths_respect_hard_max():
    for length in (1, 1799, 1800, 1801, 3599, 3600, 3601, 5000, 9999):
        widths = equal_layout(length, 1800)
        assert all(w <= 1800 for w in widths), length
        assert sum(widths) == length


def test_equal_layout_milli_degenerates_the_same_way():
    """The boundary cases, at thousandths. A zero or negative divisor is refused
    rather than raising a ZeroDivisionError inside `generate()` — the mm form has
    no such guard because `max_span_mm` reaches it from a resolved rule, and this
    one can be handed a `value_milli` from a published row we did not write.

    Behaviour on real data lives in `tests/knowledge/test_published_precision.py`,
    against the published magnitudes it exists for.
    """
    assert equal_layout_milli(0, 1_800_000) == []
    assert equal_layout_milli(-5000, 1_800_000) == []
    assert equal_layout_milli(3_600_000, 0) == []
    assert equal_layout_milli(3_600_000, -1) == []
    # ...and the whole-millimetre path is the mm form exactly
    assert equal_layout_milli(4_000_000, 1_800_000) == equal_layout(4000, 1800)


def test_nominal_layout():
    assert nominal_layout(3000, 1800) == [1800, 1200]
    assert nominal_layout(3600, 1800) == [1800, 1800]
    assert nominal_layout(1000, 1800) == [1000]


def test_layout_segment_records_alternative_only_when_different():
    r = layout_segment(3000, 1800)
    assert r.widths == [1500, 1500]
    assert r.rejected_alternative == [1800, 1200]
    r2 = layout_segment(3600, 1800)
    assert r2.widths == [1800, 1800]
    assert r2.rejected_alternative is None


def test_boundaries():
    assert boundaries(2000, [1000, 1000]) == [2000, 3000, 4000]
