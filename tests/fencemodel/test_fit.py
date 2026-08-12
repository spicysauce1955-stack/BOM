"""The 1-D fit that turns a panel width into a member count.

The gap list is the point: integer millimetres cannot express "23.5 mm each",
and a single rounded gap would hide openings that exceed a safety limit.
"""

from fenceai.fencemodel.fit import fit_pattern


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
