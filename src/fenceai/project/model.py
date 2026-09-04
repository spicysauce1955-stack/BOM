"""Project aggregate: topology + annotations + overrides + policy."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator

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

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class Job(BaseModel):
    """Who bought this fence, where, who sold it, and when.

    A salesperson does not sell a project; they sell a fence to a person at an
    address on a day. `Project` was `id, name`, so every screen after the first
    read as *"project 7"* — and the office person receiving the layout needs all
    four of these before anything else on the page means much.

    **Typed rather than four loose fields**, following `SiteConditions` and
    `fence_model`: it reaches the handover, so a typo has to fail at the boundary
    rather than at rendering, and *"is this job identified?"* has one answer in
    one place instead of four `if`s spread across the surfaces that ask.

    **Blank is allowed everywhere except everywhere-at-once.** The salesperson
    enters this after the visit, from paper; refusing a job because the address
    is not typed yet would make the first field they fill in the one that blocks
    them. Completeness is REPORTED by the handover sheet, not enforced here — the
    two are different jobs and conflating them turns a checklist into a gate.
    What is refused is a `Job` with nothing in it at all, which would make
    `job is not None` a lie the handover then reports as an identified job.
    """

    customer: str = ""
    address: str = ""
    # Who sold it. Not an auth claim — this app has no accounts; it is what the
    # salesperson types so the office person knows whom to phone.
    sold_by: str = ""
    # ISO date, or "" for nobody has said. Validated because it reaches the
    # handover and any later "when was this sold" question: a free-form string
    # would let "yesterday" through and fail somewhere far from whoever typed it.
    sold_on: str = ""

    @field_validator("customer", "address", "sold_by", "sold_on", mode="before")
    @classmethod
    def _strip(cls, v):
        # Two jobs for "Dana Levy" and "Dana Levy " are one customer. Stripped
        # at the boundary rather than at every comparison, so it stays true
        # everywhere including the picker's sort.
        return v.strip() if isinstance(v, str) else v

    @field_validator("sold_on")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        if v and not _DATE_RE.fullmatch(v):
            raise ValueError(f"sold_on must be an ISO date (YYYY-MM-DD), got {v!r}")
        return v

    @model_validator(mode="after")
    def _not_entirely_blank(self) -> "Job":
        if not any((self.customer, self.address, self.sold_by, self.sold_on)):
            raise ValueError("a Job with no field set carries less than no job "
                             "at all — leave Project.job as None instead")
        return self

    def label(self) -> str:
        """What a person would call this job.

        Customer first, because that is how a salesperson refers to a job out
        loud; the address disambiguates two fences for the same person.
        """
        parts = [p for p in (self.customer, self.address) if p]
        return " — ".join(parts) if parts else (self.sold_by or self.sold_on)


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
    # Who bought this fence, where, who sold it and when. `None` means nobody
    # has said — every project that exists today has no job on it, and none of
    # them may break.
    job: Job | None = None
    # What kind of site this is. A typed field rather than another key in the
    # bare `policy` dict, for `fence_model`'s reason: it is stamped on the run
    # and guards every derived view, so a typo has to fail at the boundary.
    site: SiteConditions = SiteConditions()

    def display_name(self) -> str:
        """What to call this project on any surface a person reads.

        Exists so no surface has to know whether a job is set: the picker, the
        title and the handover all call this one method. `name` remains the
        field 59 routes and the whole existing suite key on — a job that also has
        a customer simply DISPLAYS as the customer.
        """
        return self.job.label() if self.job else self.name
