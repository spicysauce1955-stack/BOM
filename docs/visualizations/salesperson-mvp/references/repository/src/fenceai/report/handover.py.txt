"""What the office still needs — slice 4 of the salesperson MVP.

The MVP's success condition is *a sold job, captured completely enough that the
office person never has to phone the salesperson*. Completeness, not accuracy. So
the deliverable is the list of questions the office would otherwise have to ring
up and ask, shown to the salesperson while they can still answer them.

**A read model, derived and never stored** — the rule the rest of `report/`
follows. It is a pure function of the PROJECT, deliberately not of a run: by the
time a `Strategy` exists the silent defaults have already been applied and look
decided, and this sheet's whole job is to catch them before that.

**Reported, never enforced.** A sheet that refused to hand over an incomplete job
would be worked around within a week. `blocking` is the one exception and it is
narrow: it withholds the ESTIMATE, not the handover, because a price for a fence
with no model chosen is a number with nothing behind it.

The two silent defaults are the point of the exercise. A run with no height
intent is built at `DEFAULT_POLICY["default_height_mm"]`; a station with no base
event stands on `soil` (`topology/station.py: base_surface_at`). Neither is
wrong, and neither was ever said — so today a fence nobody measured reaches the
office indistinguishable from one confirmed at 1.8 m.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.project.model import Project

# The default a run with no height intent is BUILT at. Imported rather than
# repeated: two copies of this number would disagree the first time either moved,
# and the whole value of the item is that it reports what will actually happen.
from fenceai.strategy.generator import DEFAULT_POLICY

# What `base_surface_at` falls back to when no base interval covers a station.
DEFAULT_SURFACE = "soil"


class HandoverGap(BaseModel):
    """One question the office would otherwise have to phone about.

    `code` + `params`, like every other platform-emitted item in this system: the
    sentence lives in both locale bundles and is rendered there, never assembled
    here. English text built in Python would reach a Hebrew-first reader as
    English (CLAUDE.md, the split warning registry).
    """

    code: str
    params: dict = {}
    # Whether the office literally cannot start. Narrow on purpose — it gates
    # the estimate, and calling everything blocking would gate it always.
    blocking: bool = False


def _job_gaps(project: Project) -> list[HandoverGap]:
    """One item per blank field, never a single "job incomplete".

    The office person phones about a specific missing thing; an item naming the
    category instead of the field would not save the call.
    """
    job = project.job
    out = []
    for field in ("customer", "address", "sold_by", "sold_on"):
        if not (job and getattr(job, field)):
            out.append(HandoverGap(code=f"{field}_missing"))
    return out


def handover_gaps(project: Project) -> list[HandoverGap]:
    """Everything the office still needs, most blocking first.

    Order is deliberate: a fence that was never drawn makes every other item
    moot, and an address for a fence that does not exist is not progress.
    """
    topo = project.topology
    if not topo.runs:
        # Returned ALONE. Listing four blank job fields under "you have not drawn
        # anything" is a checklist that has not read itself.
        return [HandoverGap(code="no_fence_drawn", blocking=True)]

    out: list[HandoverGap] = []

    if not any(ev.payload.kind == "fence_model" for r in topo.runs
               for ev in r.interval_events) and project.fence_model is None:
        out.append(HandoverGap(code="no_model_chosen", blocking=True))

    out += _job_gaps(project)

    if not project.context.landmarks:
        # The reason slice 3 exists: an office person holding a bare coordinate
        # plane has to ask which side faces the road.
        out.append(HandoverGap(code="no_property_context"))

    silent_height = [r for r in topo.runs
                     if not any(ev.payload.kind == "height_intent"
                                for ev in r.interval_events)]
    if silent_height:
        # The number is in the params because "no height" and "assumed 1800" are
        # different sentences, and only the second one a person can act on.
        out.append(HandoverGap(code="height_assumed", params={
            "height_mm": DEFAULT_POLICY["default_height_mm"],
            "runs": len(silent_height)}))

    silent_base = [r for r in topo.runs
                   if not any(ev.payload.kind == "base"
                              for ev in r.interval_events)]
    if silent_base:
        out.append(HandoverGap(code="base_assumed", params={
            "surface": DEFAULT_SURFACE, "runs": len(silent_base)}))

    return out


# Every code this module can emit. Hand-maintained beside the emitting sites for
# the reason `tests/web/test_locale_bundles.py` keeps such a list at all: a code
# with no entry in both bundles reaches a screen as its own key, and that has
# shipped green four times in this repo already.
HANDOVER_CODES = [
    "no_fence_drawn",
    "no_model_chosen",
    "customer_missing",
    "address_missing",
    "sold_by_missing",
    "sold_on_missing",
    "no_property_context",
    "height_assumed",
    "base_assumed",
]
