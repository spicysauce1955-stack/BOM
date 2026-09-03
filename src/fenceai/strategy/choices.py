"""A choice set: a question the data leaves open, and the points that answer it.

**A fifth kind, deliberately not folded into the other four.** A hard constraint
says *must*; a preference says *nicer if*; an objective says *minimise this*; an
override says *the engine got this wrong here*. A choice set says **two right
answers** — nothing was wrong and neither point is nicer, so the only honest
resolver is a person, or the stated default.

That is also why a selection is anchored to a SCOPE while an override is anchored
to a STATION: an override dies when the fence is redrawn, and a choice should
not. And why a selection is not a CORRECTION (contract obligation 7): a
correction says the engine got it wrong, a selection picks between answers that
are all right.

Pure leaf — `core.units` only. Measuring a point takes a whole generation and
happens in the generator, so this module holds the types and the two rules that
decide what a person is shown, and both fit on one screen.

**Axes are OPEN, and that is the correction of a real mistake.** The first draft
used four fixed measures (posts, boards, cuts, "has an odd bay") and would have
printed *"same posts, same boards, same cuts"* for two footing schedules 25%
apart in concrete — because on a 3 m run both schedules give identical posts and
boards. A point carries the axes it actually differs on.

Design: `docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md`
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm


class DesignPoint(BaseModel):
    """One admissible answer to a choice set.

    `widths` is a bay list where the point IS a layout; `bindings` are parameter
    values where it asserts some — a `paired` row's depth and span. The two are
    handled differently downstream and the distinction is load-bearing: a
    binding becomes a synthesized `KnowledgeVersion` so `resolve_param` still
    decides, while a width list binds no parameter and needs no synthesizing.
    Reading that the other way round is how a run came to report *"no rule
    states max_span_mm"* about a sealed engineering table.

    `lexemes` carries the source's own words per binding — `24"` beside 610 —
    because contract obligation 5 is *"convert units once, at the boundary, and
    keep the source lexeme for display."* A panel showing only our millimetres
    has thrown away what a reader checks against.

    `axes` are physical counts measured BY a probe: never money. A stored price
    goes stale the moment the catalog moves, and ADR-0011 puts what a fence
    costs in a `SupplyRun` against one yard.

    `is_default` marks what the engine builds. A default is never eliminated.
    """

    id: str
    label: str
    widths: list[Mm] = []
    bindings: dict[str, Mm] = {}
    lexemes: dict[str, str] = {}
    axes: dict[str, int] = {}
    # What choosing this would change relative to the baseline, on shared axes.
    delta: dict[str, int] = {}
    is_default: bool = False


class ChoiceSet(BaseModel):
    """A question, its points, and what it depends on.

    `scope` is a GAP between fixed stations, not a section. Any corner, gate
    edge, terrain step or single pinned post makes a run several gaps, and a
    section-scoped answer would be applied to a gap it was never measured for —
    which is a wrong fence, and self-defeating besides: the moment a person pins
    a post the run becomes two gaps.

    `depends_on` names a set whose answer must settle first. The placement
    question exists only while the chosen widths leave a stub, and a dependent
    set whose parent moved is dropped rather than orphaned.
    """

    id: str
    scope: str
    question: str
    points: list[DesignPoint] = []
    depends_on: str | None = None

    def default(self) -> DesignPoint | None:
        """The point the engine built, which is always present."""
        return next((p for p in self.points if p.is_default), None)


def dominates(a: DesignPoint, b: DesignPoint) -> bool:
    """Is `a` at least as good as `b` on every axis BOTH carry, and better on one?

    **Only shared axes are compared.** Treating a missing axis as zero would let
    a footing point measured in concrete dominate a layout point measured in
    boards, on an axis the second never claimed.

    The strict improvement is what stops two points measuring the same from each
    eliminating the other and leaving nothing offered.

    Every axis minimises, which is exactly why "has an odd bay" is not an axis:
    it is taste, and taste does not eliminate. It is printed on the row instead.
    Keeping it as a filter axis was the only thing hiding that this engine's own
    default layout is dominated on posts, boards and cuts.
    """
    shared = set(a.axes) & set(b.axes)
    if not shared:
        return False
    return (all(a.axes[k] <= b.axes[k] for k in shared)
            and any(a.axes[k] < b.axes[k] for k in shared))


def offered(points: list[DesignPoint]) -> list[DesignPoint]:
    """The points worth showing, in the order they were generated.

    **The default is exempt.** Without that the layout the engine builds can be
    absent from its own panel — and a stored selection naming it would then
    report `choice_unavailable` for a layout being built on the same screen.
    That one rule also retires a `min_span` rule which only warns in
    `layout_segment` while rejecting in candidate generation, and a
    `prefer_equal=False` baseline that no generator proposes.

    Order is preserved rather than sorted by any axis: sorting would make the
    panel's first row a judgement this module has no basis for, and the
    generators' order is already meaningful — the default, then the manufactured
    tiling, then yield.
    """
    return [
        p for p in points
        if p.is_default
        or not any(o is not p and dominates(o, p) for o in points)
    ]
