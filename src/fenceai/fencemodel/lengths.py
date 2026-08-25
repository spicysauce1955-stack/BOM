"""Length rules — how long a member is cut, as data rather than an if-chain.

Was `LengthRule = Literal[...]` in `model.py` plus a five-branch chain in
`resolve._length_for`. See `core/registry.py` for the rule this moves across.

**The signature is the contract**: `(PartRequirement, PanelContext) -> Mm | None`.
`None` means *this rule cannot be answered from the bay alone* — which is a real
answer, not a failure, and `between_frame` is the case: it measures against the
panel's own frame and fixes where the member sits as well as how long it is, so
`resolve_panel` answers it separately with the frame it just placed passed in,
never reached for, so resolution stays a pure function of its arguments.

**The slope factor is per RULE, not a tail applied to whatever came back.** It
corrects a HORIZONTAL member for running along the grade, so a rule producing a
vertical member must not get it — which is why `panel_height` returned early from
the old chain, and why the correction lives in `along_grade()` for rules to opt
into rather than in the caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from fenceai.core.registry import Registry
from fenceai.core.units import Mm

if TYPE_CHECKING:  # pragma: no cover - typing only, and avoids an import cycle
    from fenceai.fencemodel.model import PartRequirement
    from fenceai.fencemodel.resolve import PanelContext

LengthRuleFn = Callable[["PartRequirement", "PanelContext"], "Mm | None"]

LENGTH_RULES: Registry[LengthRuleFn] = Registry("length rule")


def along_grade(base: Mm, ctx: "PanelContext") -> Mm:
    """The slope correction, for the rules it applies to.

    A raked bay's rails run along the grade and are longer than the plan width by
    exactly the difference between the two. Applied to the RULE's answer, never
    to a raw width: the rule decides what is being measured, and this decides
    whether that measurement follows the ground.
    """
    if ctx.length_basis == "slope" and ctx.slope_len_mm is not None:
        return base + (ctx.slope_len_mm - ctx.centre_width_mm)
    return base


@LENGTH_RULES.register("clear_between_posts")
def _clear_between_posts(req: "PartRequirement", ctx: "PanelContext") -> Mm | None:
    return along_grade(ctx.clear_width_mm, ctx)


@LENGTH_RULES.register("centre_to_centre")
def _centre_to_centre(req: "PartRequirement", ctx: "PanelContext") -> Mm | None:
    return along_grade(ctx.centre_width_mm, ctx)


@LENGTH_RULES.register("overlap")
def _overlap(req: "PartRequirement", ctx: "PanelContext") -> Mm | None:
    return along_grade(ctx.centre_width_mm + req.overlap_mm, ctx)


@LENGTH_RULES.register("panel_height")
def _panel_height(req: "PartRequirement", ctx: "PanelContext") -> Mm | None:
    """A member spanning the panel's full height — a picket, a slat, a baluster.

    Constant in every vertical mode: a raked bay's top follows the grade and its
    bottom follows the ground, so the two datums stay parallel, and a stepped bay
    is a rectangle. A member constrained to a frame slot (`base_ref`/`top_ref`)
    can vary along the bay, which is what `between_frame` is for.

    No slope correction, deliberately: it corrects a HORIZONTAL member for
    running along the grade, and a vertical member does not run along it at all.
    """
    return ctx.height_mm


@LENGTH_RULES.register("between_frame")
def _between_frame(req: "PartRequirement", ctx: "PanelContext") -> Mm | None:
    """Answered by `resolve_panel` with the placed frame, not from the bay. A
    frame slot that declares the rule is refused at load, so it gets no length
    here rather than quietly getting a width."""
    return None


# --- how a member built to a rule combines ACROSS an intermediate post -------
#
# A member that runs through a post is one piece covering several bays, and how
# long that piece is depends on what the rule was measuring. This is arithmetic
# over lengths the bays ALREADY resolved — never a second evaluation of the rule
# — which is the only way the cut list and the drawing can agree about a piece
# that belongs to no single bay (contract §3.1.12).
#
# **A rule with no registered join is not continuable.** That is a real answer,
# not a gap: `panel_height` measures a VERTICAL member, which meets no
# intermediate post at all, and `between_frame` measures inside one panel's own
# frame, which the next bay does not share. Registering a join is what says "a
# member built to this rule can be one piece across two bays", so a new rule is
# per-bay until someone says how it would join — the safe direction, because the
# unsafe one buys a piece nobody can cut.
#
# The signature: `(lengths, widths, faces) -> Mm`, all of one candidate group in
# order — `lengths` the per-bay resolved cut lengths, `widths` the bays'
# centre-to-centre widths, `faces` the face widths of the n+1 posts the group
# runs between (`faces[1:-1]` are the ones the member passes THROUGH).
JoinFn = Callable[[list[Mm], list[Mm], list[Mm]], Mm]

CONTINUITY_JOINS: Registry[JoinFn] = Registry("continuity join")


@CONTINUITY_JOINS.register("centre_to_centre")
def _join_centre_to_centre(lengths: list[Mm], widths: list[Mm], faces: list[Mm]) -> Mm:
    """Centre to centre of the OUTER posts — which is the sum, exactly."""
    return sum(lengths)


@CONTINUITY_JOINS.register("clear_between_posts")
def _join_clear_between_posts(lengths: list[Mm], widths: list[Mm], faces: list[Mm]) -> Mm:
    """The one opening the group leaves, measured the way every opening is.

    Through `clear_opening_mm` itself rather than by adding the interior faces
    back onto the bays' own openings: that recomposition is right to within the
    integer half of an odd face width, and "right to within a millimetre" is the
    class of number this system refuses to put on a cut list. The import is
    deferred because `resolve` imports this module — the direction that matters
    is that there is ONE definition of a clear opening, not which file it sits in.
    """
    from fenceai.fencemodel.resolve import clear_opening_mm
    return clear_opening_mm(sum(widths), faces[0], faces[-1])


@CONTINUITY_JOINS.register("overlap")
def _join_overlap(lengths: list[Mm], widths: list[Mm], faces: list[Mm]) -> Mm:
    """Centre to centre of the outer posts, plus the ONE authored overlap.

    The overlap is a run-out past the ends, so it is spent once over the whole
    piece rather than once per bay: `lengths[0] - widths[0]` is the authored
    `overlap_mm` read back off the answer the rule already gave, not a second
    reading of the requirement.
    """
    return sum(widths) + (lengths[0] - widths[0])
