"""Which answers a person is offered, and the two rules that decide.

Rev 1 of the design filtered on four fixed measures including "has an odd bay" —
and an adversarial review found that dropping that one axis makes the tiling
layout dominate the layout this engine ships today. A taste axis was the only
thing hiding that. So two rules replace it: the default is never eliminated, and
only commensurable physical axes eliminate anything.

`docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md` §5.
"""

from __future__ import annotations

from fenceai.strategy.choices import DesignPoint, dominates, offered


def _p(pid: str, *, default: bool = False, **axes: int) -> DesignPoint:
    return DesignPoint(id=pid, label=pid, axes=axes, is_default=default)


def test_a_point_worse_on_every_shared_axis_is_dominated():
    assert dominates(_p("equal", posts=4, boards=30, cuts=30),
                     _p("metre", posts=6, boards=50, cuts=50))


def test_the_tiling_layout_dominates_the_one_this_engine_builds():
    """The finding the whole design turns on, asserted rather than described.

    On a 5 m run: `2000·2000·1000` and `1667·1667·1666` need the same posts and
    the same boards, and the tiling layout takes a third of the saw cuts. So on
    commensurable counts it DOMINATES our own default — and the only thing that
    kept the equal-bay layout on the panel in the first draft was an axis
    asserting that unequal bays are worse, which is taste.

    This is why `offered` exempts the default instead."""
    assert dominates(_p("tiling", posts=4, boards=30, cuts=10),
                     _p("equal", posts=4, boards=30, cuts=30))


def test_two_points_that_each_win_on_a_different_axis_both_survive():
    """The genuine trade, and the case a person has to settle: two extra posts
    against five fewer boards is a price question the engine may not answer for
    them (§7 — never money)."""
    fewer_posts = _p("fewer_posts", posts=4, boards=30, cuts=30)
    fewer_boards = _p("fewer_boards", posts=6, boards=25, cuts=25)
    assert not dominates(fewer_posts, fewer_boards)
    assert not dominates(fewer_boards, fewer_posts)


def test_identical_axes_do_not_dominate_each_other():
    """`dominates` needs a STRICT improvement, or two points measuring the same
    would each eliminate the other and nothing would be offered. Two DISTINCT
    objects, so the `is not` guard in `offered` is actually exercised."""
    assert not dominates(_p("a", posts=4, boards=30, cuts=30),
                         _p("b", posts=4, boards=30, cuts=30))


def test_only_shared_axes_are_compared():
    """A footing point carries concrete; a layout point does not. Comparing a
    point against one measured on different axes must not silently treat a
    missing axis as zero — that would make every footing point dominate every
    layout point on an axis the second never claimed."""
    footing = _p("deep", posts=6, concrete_l=334)
    layout = _p("tiling", posts=6, boards=30)
    assert not dominates(footing, layout)
    assert not dominates(layout, footing)


def test_a_point_with_no_axes_in_common_is_never_dropped():
    kept = offered([_p("a", posts=4), DesignPoint(id="taste", label="taste")])
    assert [p.id for p in kept] == ["a", "taste"]


def test_the_default_survives_even_when_dominated():
    """The rule that retires four separate failures: the built layout is always a
    row, so no `choice_unavailable` can ever fire for a point the engine is
    building on the same screen."""
    kept = offered([_p("equal", default=True, posts=4, boards=30, cuts=30),
                    _p("tiling", posts=4, boards=30, cuts=10)])
    assert [p.id for p in kept] == ["equal", "tiling"]


def test_a_non_default_dominated_point_is_dropped_and_order_is_kept():
    """Order is the generators' order, so the panel lists what the engine
    reaches for first, first — and two runs of one project never disagree."""
    kept = offered([_p("equal", default=True, posts=4, boards=30, cuts=30),
                    _p("tiling", posts=4, boards=30, cuts=10),
                    _p("sixths", posts=7, boards=30, cuts=60)])
    assert [p.id for p in kept] == ["equal", "tiling"]


def test_a_point_carries_the_sources_own_words_beside_our_millimetres():
    """Contract obligation 5: convert once at the boundary and keep the source
    lexeme for display. A footing point states 610 mm because a page said 24
    inches, and the page's own words are what a reader checks against."""
    point = DesignPoint(id="shallow", label="shallow",
                        bindings={"footing_depth_mm": 610},
                        lexemes={"footing_depth_mm": '24"'})
    assert point.bindings["footing_depth_mm"] == 610
    assert point.lexemes["footing_depth_mm"] == '24"'
