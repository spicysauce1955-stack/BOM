"""The 1-D fit that turns a panel width into a member count.

The gap list is the point: integer millimetres cannot express "23.5 mm each",
and a single rounded gap would hide openings that exceed a safety limit.
"""

import pytest

from fenceai.fencemodel.fit import _round_milli, fit_pattern, fit_pattern_milli


def _assert_accounts_for_axis(r, axis_len_mm, member_widths_mm):
    """Every millimetre of the axis must land in exactly one bucket: margins,
    members, gaps, or residual. This is the invariant FitResult.residual_mm's
    own docstring claims ("unallocated axis length after members+gaps+margins")
    — assert it directly rather than trusting each test's ad-hoc arithmetic."""
    widths_used = sum(member_widths_mm[i % len(member_widths_mm)] for i in range(r.count))
    assert r.edge_margin_start_mm + r.edge_margin_end_mm + sum(r.gaps_mm) \
        + widths_used + r.residual_mm == axis_len_mm


def test_exact_fit_leaves_no_residual():
    # 5 members of 100 with 4 gaps of 20 and no edge margin = 580; axis 580.
    r = fit_pattern(580, [100], [20], justification="spread_to_fit",
                    excess="space", edge_margin_mm=0)
    assert r.count == 5
    assert r.gaps_mm == [20, 20, 20, 20]
    assert r.residual_mm == 0
    _assert_accounts_for_axis(r, 580, [100])


def test_residual_is_spread_one_mm_at_a_time_like_equal_layout():
    """2000 wide, 100 members, 20 nominal gap, margins at each end.

    16 members fit (16*100 + 15*20 = 1900); 100 mm is left over and 'space'
    widens the 15 gaps by 100/15 = 6.67 mm each, which int mm cannot do. The
    remainder goes one mm at a time to the first gaps, mirroring equal_layout.
    """
    r = fit_pattern(2000, [100], [20], justification="spread_to_fit",
                    excess="space", edge_margin_mm=0)
    assert r.count == 16
    assert len(r.gaps_mm) == 15  # gaps BETWEEN members; margins are separate
    assert sum(r.gaps_mm) + r.count * 100 + r.edge_margin_start_mm \
        + r.edge_margin_end_mm == 2000
    assert max(r.gaps_mm) - min(r.gaps_mm) <= 1  # spread, never lumped
    assert r.gaps_mm == sorted(r.gaps_mm, reverse=True)  # the +1s come first
    _assert_accounts_for_axis(r, 2000, [100])


def test_truncate_leaves_the_residual_as_a_gap_and_does_not_widen():
    r = fit_pattern(2000, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert set(r.gaps_mm) == {20}
    assert r.residual_mm == 2000 - (r.count * 100 + sum(r.gaps_mm))
    assert r.residual_mm > 0
    _assert_accounts_for_axis(r, 2000, [100])


def test_negative_gap_is_an_overlap_and_fits_more_members():
    """Board-on-board: the second member of the pattern overlaps the first."""
    plain = fit_pattern(1000, [100], [0], justification="start",
                        excess="truncate", edge_margin_mm=0)
    lapped = fit_pattern(1000, [100], [-25], justification="start",
                         excess="truncate", edge_margin_mm=0)
    assert lapped.count > plain.count
    _assert_accounts_for_axis(plain, 1000, [100])
    _assert_accounts_for_axis(lapped, 1000, [100])


def test_two_member_pattern_alternates_widths_and_gaps():
    """Shadowbox: pattern [wide, narrow] repeats; the fit walks the sequence."""
    r = fit_pattern(1000, [100, 50], [10, 10], justification="start",
                    excess="truncate", edge_margin_mm=0)
    # 5 full repeats (100+10+50+10=170 each -> 850, 10 members) plus one more
    # 100-wide member (850+100=950 <= 1000); a further 50 would need 1010.
    assert r.count == 11
    assert r.gaps_mm[0] == 10
    _assert_accounts_for_axis(r, 1000, [100, 50])


def test_zero_length_axis_yields_nothing_rather_than_raising():
    r = fit_pattern(0, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert r.count == 0 and r.gaps_mm == []
    _assert_accounts_for_axis(r, 0, [100])


def test_axis_narrower_than_one_member_yields_nothing():
    r = fit_pattern(50, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert r.count == 0
    _assert_accounts_for_axis(r, 50, [100])


def test_edge_margins_are_taken_off_the_axis_before_fitting():
    bare = fit_pattern(1000, [100], [20], justification="start",
                       excess="truncate", edge_margin_mm=0)
    inset = fit_pattern(1000, [100], [20], justification="start",
                        excess="truncate", edge_margin_mm=60)
    assert inset.count < bare.count
    assert inset.edge_margin_start_mm == 60 and inset.edge_margin_end_mm == 60
    _assert_accounts_for_axis(bare, 1000, [100])
    _assert_accounts_for_axis(inset, 1000, [100])


def test_margins_alone_exhausting_the_axis_do_not_double_count_residual():
    """Regression: with edge_margin_mm=60 on a 120 mm axis, margins alone (120 mm)
    used to be reported ALONGSIDE a residual of the full 120 mm — 240 mm accounted
    for on a 120 mm axis. Margins must be clamped to what the axis actually holds,
    and residual must be the true remainder, not a separate max(axis, 0)."""
    r = fit_pattern(120, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=60)
    assert r.count == 0
    assert r.edge_margin_start_mm == 60 and r.edge_margin_end_mm == 60
    assert r.residual_mm == 0
    _assert_accounts_for_axis(r, 120, [100])


def test_zero_count_axis_accounting_holds_for_a_zero_length_axis():
    """A count==0 test that checks the sum identity directly, not just count==0
    — the double-counting bug above would sail through a count-only assertion."""
    r = fit_pattern(0, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert r.edge_margin_start_mm + r.edge_margin_end_mm + r.residual_mm == 0
    _assert_accounts_for_axis(r, 0, [100])


def test_spread_records_the_truncate_layout_as_the_rejected_alternative():
    r = fit_pattern(2000, [100], [20], justification="spread_to_fit",
                    excess="space", edge_margin_mm=0)
    assert r.rejected_alternative is not None
    assert set(r.rejected_alternative) == {20}
    _assert_accounts_for_axis(r, 2000, [100])


def test_is_deterministic():
    a = fit_pattern(1737, [90, 40], [15, 15], justification="spread_to_fit",
                    excess="space", edge_margin_mm=12)
    b = fit_pattern(1737, [90, 40], [15, 15], justification="spread_to_fit",
                    excess="space", edge_margin_mm=12)
    assert a == b
    _assert_accounts_for_axis(a, 1737, [90, 40])


# ---- the pattern that never advances (fix wave, finding A) -------------------

def test_a_pattern_that_never_advances_raises_instead_of_hanging():
    """`gap_after_mm` may be negative (an overlap), and nothing bounded how
    negative. A member whose overlap swallows it whole leaves `used` where it
    was, so `_count_members` incremented `count` for ever — inside generate(),
    which meant a hung request thread and no exception ever raised.

    There is no honest member count for "infinitely many fit", so it is an
    error, not a number.
    """
    with pytest.raises(ValueError, match="never advances"):
        fit_pattern(2000, [100], [-100], justification="start",
                    excess="space", edge_margin_mm=0)


def test_a_pattern_that_walks_backwards_also_raises():
    with pytest.raises(ValueError, match="never advances"):
        fit_pattern(2000, [100], [-150], justification="start",
                    excess="truncate", edge_margin_mm=0)


def test_the_guard_is_per_cycle_so_a_zero_advance_member_is_still_allowed():
    """Board-on-board: the narrow member is fully lapped by its neighbour (100
    wide, -100 gap → zero advance), but the repeat as a whole still moves on by
    150 mm. That is a real fence and must still fit."""
    r = fit_pattern(1000, [100, 100], [-100, 150], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert r.count > 0
    _assert_accounts_for_axis(r, 1000, [100, 100])


def test_the_guard_does_not_fire_on_an_axis_too_short_to_hold_anything():
    """The check is a property of the PATTERN, not of the axis — a well-formed
    pattern in a tiny bay is still 'no members fit', never an error."""
    r = fit_pattern(10, [100], [-100 + 1], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert r.count == 0


# ---- fit_pattern_milli: contract.md:112-117, round once at the output -------
#
# `fit_pattern` itself needs no change (it is exact pure-integer arithmetic
# regardless of what its integers count) — the defect this closes is entirely
# about feeding it values that were already rounded to mm before being summed
# `count` times. `fit_pattern_milli` takes the same shape of input in
# thousandths of a millimetre instead.

def test_fit_pattern_milli_matches_fit_pattern_exactly_for_whole_mm_inputs():
    """When there is no sub-millimetre information at all (every input already
    an exact multiple of 1000), running in milli must reproduce the mm result
    byte for byte — this is what makes wiring real callers to the milli path
    safe today, before any caller actually has finer-than-mm data."""
    mm = fit_pattern(1737, [90, 40], [15, 15], justification="spread_to_fit",
                      excess="space", edge_margin_mm=12)
    milli = fit_pattern_milli(1737_000, [90_000, 40_000], [15_000, 15_000],
                               justification="spread_to_fit", excess="space",
                               edge_margin_milli=12_000)
    assert milli == mm


def test_fit_pattern_milli_matches_fit_pattern_for_truncate_too():
    mm = fit_pattern(2000, [100], [20], justification="start",
                      excess="truncate", edge_margin_mm=0)
    milli = fit_pattern_milli(2_000_000, [100_000], [20_000],
                               justification="start", excess="truncate",
                               edge_margin_milli=0)
    assert milli == mm


def test_fit_pattern_milli_closes_the_sphere_test_flip():
    """The exact real-world case the boundary negotiation measured: 2.5" pickets
    (63.5 mm), a 3/8" gap (9.525 mm) and a 3.5" margin (88.9 mm) on a 97" axis
    (2463.8 mm), `start`/`truncate`.

    Rounding each value to mm BEFORE the fit (today's `to_mm`-then-multiply
    order) gives a terminal opening of 91.0 mm — inside a 100 mm clear-gap
    limit. The true (exact-fraction) geometry's terminal opening is 120.65 mm
    — outside it. Feeding the true thousandths through `fit_pattern_milli` and
    rounding once at the end must land close to the true answer (121 mm, the
    0.35 mm gap being the ordinary cost of two independent single roundings —
    margin and slack — against a fully exact reference), and specifically on
    the correct side of a 100 mm limit, not the wrong one."""
    naive = fit_pattern(2464, [64], [10], justification="start",
                         excess="truncate", edge_margin_mm=89)
    naive_terminal = naive.openings_mm[-1]
    assert naive_terminal == 91  # the buggy engine's own number, for contrast

    fixed = fit_pattern_milli(2_463_800, [63_500], [9_525],
                               justification="start", excess="truncate",
                               edge_margin_milli=88_900)
    assert fixed.count == 31 == naive.count  # not a count artefact
    fixed_terminal = fixed.openings_mm[-1]
    assert fixed_terminal == 121
    LIMIT_MM = 100
    assert naive_terminal <= LIMIT_MM       # the false PASS this defect caused
    assert fixed_terminal > LIMIT_MM        # the true verdict is FAIL


def test_fit_pattern_milli_does_not_lose_the_spread_slack_to_early_rounding():
    """A slack that is an exact whole number of millimetres but does not
    divide evenly across the gaps must still land as whole extra millimetres
    on SOME gaps (today's mm-precision `_spread` already guarantees this) —
    rounding each gap's fractional milli share independently would send small
    shares to zero and lose the slack outright: `_spread(3000, 7)` distributes
    as [429, 429, 429, 429, 428, 428, 428] milli, every one of which rounds to
    0 mm on its own, when the true total is 3 mm that has to land somewhere."""
    # 5 members of 100mm with 4 gaps of 20mm = 580mm exactly, plus 3mm slack
    # spread across the 4 gaps.
    r = fit_pattern_milli(583_000, [100_000], [20_000],
                           justification="spread_to_fit", excess="space",
                           edge_margin_milli=0)
    assert r.count == 5
    assert sum(r.gaps_mm) == 4 * 20 + 3
    assert max(r.gaps_mm) - min(r.gaps_mm) <= 1


def test_fit_pattern_milli_rounding_matches_to_mm_exactly():
    """The rounding rule duplicated into `fit.py` (kept local so the module
    stays pure, no Pydantic, no other module) must never drift from the one
    real named point, `knowledge.parameters.to_mm` — checked directly rather
    than trusted, over values that exercise the half-away-from-zero tie rule
    and negative amounts."""
    from fenceai.fencemodel.fit import _round_milli
    from fenceai.knowledge.parameters import Quantity, to_mm

    for milli in (0, 1, 499, 500, 501, 999, 1000, 1500, 2500,
                  -1, -499, -500, -501, -1500, -2500, 63_500, 9_525, 88_900):
        assert _round_milli(milli) == to_mm(Quantity(unit="mm", amount_milli=milli))


def test_fit_pattern_milli_space_tiles_the_axis_exactly_on_fractional_input():
    """`excess: space` must CLOSE: margins + members + gaps + residual is the
    axis, exactly, the way `fit_pattern` closes by construction.

    Under `space` the gaps are not measurements of an authored value, they are
    the leftover shared out — so the amount shared has to be what the outputs
    already committed leave behind, derived after the per-gap rounding. Rounding
    the true slack independently instead hands out the whole leftover on top of
    gaps that were each rounded UP: 2.5" pickets (63.5 mm) at 3/8" (9.525 mm)
    over a 2000 mm axis then tile to 2013 mm and the last picket stands 13 mm
    past the frame. Whole-mm inputs cannot show this — every rounding is exact —
    which is why it stayed invisible behind callers that scale by 1000.
    """
    AXIS, WIDTH, GAP = 2_000_000, 63_500, 9_525
    r = fit_pattern_milli(AXIS, [WIDTH], [GAP], justification="spread_to_fit",
                           excess="space", edge_margin_milli=0)
    assert r.count == 27
    # The aggregate member width rounded once — this module's own basis; it
    # never rounds an individual member width.
    widths_mm = _round_milli(WIDTH * r.count)
    assert (r.edge_margin_start_mm + widths_mm + sum(r.gaps_mm)
            + r.residual_mm + r.edge_margin_end_mm) == _round_milli(AXIS)
    # ...and the tiling is still a spread, not a lump.
    assert max(r.gaps_mm) - min(r.gaps_mm) <= 1


def test_fit_pattern_milli_measuring_policies_keep_the_true_terminal_opening():
    """The counterweight to the test above, and it is deliberately NOT closure.

    Under `truncate` the residual is the terminal OPENING — the number the
    sphere test compares against a clear-gap limit. It is the true leftover
    rounded once (31.75 -> 32 mm), and it must not be re-derived as "whatever
    the rounded gaps leave": that would pour the accumulated rounding of 30
    gaps into the one safety-critical number, reporting 17 mm of leftover
    instead of 32 and a terminal opening of 106 mm instead of 121 against a
    true 120.65. Any clear-gap limit from 106 to 120 mm then reads PASS on a
    fence that fails. n+1 independently rounded openings not adding up to the
    axis is the price of every one of them being true to within half a
    millimetre, and that is the trade this path makes on purpose.
    """
    r = fit_pattern_milli(2_463_800, [63_500], [9_525], justification="start",
                           excess="truncate", edge_margin_milli=88_900)
    assert r.residual_mm == 32
    assert r.openings_mm[-1] == 121
    closure_residual = (_round_milli(2_463_800) - 2 * r.edge_margin_start_mm
                         - _round_milli(63_500 * r.count) - sum(r.gaps_mm))
    assert closure_residual == 17          # what closing the sum would report
    closed_terminal = r.edge_margin_end_mm + closure_residual
    assert closed_terminal == 106
    for limit_mm in (106, 113, 120):       # the band where the two disagree
        assert r.openings_mm[-1] > limit_mm >= closed_terminal
