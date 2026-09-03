"""Project aggregate: topology + annotations + overrides + policy."""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.ai.records import InterpretationRecord
from fenceai.core.units import Mm
from fenceai.fencemodel.selection import FenceModelChoice
# Re-exported, not redefined: `SiteConditions` moved to its own leaf module so
# `fencemodel.model` can read the dimension vocabulary without importing this
# aggregate. Every caller that already said `from fenceai.project.model import
# SiteConditions` still resolves, and there is still exactly one definition.
from fenceai.project.site import SITE_DIMENSIONS, SiteConditions
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Topology


class Annotation(BaseModel):
    id: str
    target_ref: str  # "project" | "run:<id>" | "node:<id>" | "event:<id>"
    text: str  # verbatim, immutable
    author: str = "user"
    created_at: str = ""
    interpretations: list[InterpretationRecord] = []


class Selection(BaseModel):
    """A person's answer to a choice set — the fifth kind, beside hard constraint,
    preference, objective and override (spec §3).

    A choice set is a QUESTION: two or more design points, all admissible, where
    nothing in the data prefers one. Nothing was wrong, so a selection is not an
    override; neither point is nicer, so it is not a preference; and it is not a
    correction (contract obligation 7) — a correction says the engine got it
    wrong, a selection picks between answers that are all right.

    **Anchored to a SCOPE, not a station.** That is the whole difference from an
    override. An override anchors to `(run_id, anchor, kind)` and dies when the
    fence is redrawn, because the station it named may no longer be anywhere; a
    scope — `gap:run1:0`, `model:M-VINYL`, `model:mfr/certainteed/rail` — names
    the question rather than a place on today's drawing, so the answer survives a
    redraw. A scope may contain slashes, which is why the DELETE route carries it
    as a query parameter and not as a path segment.

    **`asked=False` is a PIN**, not a different record: "we always dig 610, stop
    asking". Choosing answers *this* project and keeps offering the alternative;
    pinning says *this is how we work*. The two differ in what happens NEXT, not
    in what was decided, so they are one type with one flag rather than two
    stores that could disagree about the same question.

    It carries the widths or bindings it CHOSE, never the name of the generator
    that proposed them: `fewest_posts` is defined relative to `max_span`, so
    answering a footing question would silently change what such a name meant
    (spec §12). A `widths` list answers a layout point and binds nothing; a
    `bindings` map answers a parameter point, and because a `paired` row binds
    depth and span together, pinning either bound parameter resolves the point.
    """

    choice_set: str
    scope: str
    widths: list[Mm] = []
    bindings: dict[str, Mm] = {}
    asked: bool = True
    author: str = "user"
    created_at: str = ""

    def key(self) -> tuple[str, str]:
        """The upsert identity. The scope is part of it because two gaps on one
        run are two separate questions: a set-only key made one answer apply to a
        gap it was never measured for."""
        return (self.choice_set, self.scope)


class Project(BaseModel):
    id: str
    name: str
    created_at: str = ""
    topology: Topology = Topology()
    annotations: list[Annotation] = []
    overrides: list[Override] = []
    # Answers to choice sets, keyed by `(choice_set, scope)`. Beside `overrides`
    # rather than among them: an override patches a generated output at a
    # station, a selection is an INPUT to generation anchored to a scope.
    choices: list[Selection] = []
    policy: dict = {}
    # The model a stretch of this project's fence is built to unless a fence_model
    # interval event says otherwise. A typed field rather than another key in the
    # bare `policy` dict: it is resolved against the model library and stamped on
    # the run, so a typo has to fail at the boundary, not at generation.
    # None keeps the compatibility path (M-LEGACY, seeded from demand skus).
    fence_model: FenceModelChoice | None = None
    # What kind of site this is. A typed field rather than another key in the
    # bare `policy` dict, for `fence_model`'s reason: it is stamped on the run
    # and guards every derived view, so a typo has to fail at the boundary.
    site: SiteConditions = SiteConditions()
