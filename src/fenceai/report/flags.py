"""Every problem on a job, carrying where it belongs on the drawing.

**This model finds nothing.** Three other models already found everything here:
`handover_gaps` answers *did the sale get captured*, `readiness` answers *what
has the office not done*, and a stored run came back with its own warnings. What
none of them does is say where to DRAW the answer, and until a screen can draw
it, a finding is a line in a list somebody scrolls past.

The industry's cautionary tale is a review dialog that accumulates thousands of
unlinked warnings, where a thousand warnings make the dialog useless — which is
precisely how critical problems hide for months. The fix is not fewer warnings.
It is that every one of them clicks through to the thing it is about.

**Nothing is ever dropped.** A flag whose place cannot be worked out is placed
on the job. A screen that silently swallowed a warning it could not draw would
be worse than one that lists it without a mark — the finding would disappear
because of a formatting change nobody noticed.

**A quoted document warning cannot reach this module**, and that is enforced by
the signature rather than by a filter: `job_flags` takes no argument a
`DocumentWarning` could arrive through. A manufacturer's sentence goes once into
the annexe and never onto a line (contract §3.3.5); placing one on a fence would
publish their liability text as our finding about this job. A filter is a rule
somebody can delete; a parameter that does not exist is a rule nobody can reach.

**Severity comes from the source, never from the code.** A table mapping codes
to severities here would be a second opinion about how bad something is, and the
first opinion — the rule that emitted it — is the one with the reasoning behind
it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.report.handover import HandoverGap
from fenceai.report.readiness import ReadinessItem
from fenceai.strategy.choices import ChoiceSet
from fenceai.strategy.model import StrategyWarning

#: Three bands, and the third is not a colour. `answered` means *requires
#: nothing from you* — it is drawn quietly or not at all, and it covers both an
#: informational notice and a question somebody has since answered.
Severity = Literal["blocking", "open", "answered"]

#: The order a list reads in, and the order marks are drawn in so a blocking
#: mark is never hidden under an open one.
_ORDER: dict[str, int] = {"blocking": 0, "open": 1, "answered": 2}

#: `StrategyWarning.severity` is the rule's own word for how bad this is.
_FROM_WARNING: dict[str, Severity] = {
    "error": "blocking", "warning": "open", "info": "answered",
}

#: What a choice's scope looks like: `gap:{run_id}:{seg_start}`
#: (`strategy/generator.py`). Parsed in exactly one place — this module.
_SCOPE_PREFIX = "gap:"


class Place(BaseModel):
    """Where a flag belongs on the drawing.

    Every field but `kind` is optional because the five kinds carry different
    handles, and `kind` is what says which to read. A renderer that guessed from
    whichever field was non-empty would draw a `node` place at station 0 of a
    run the node happens to touch.
    """

    kind: Literal["job", "run", "station", "node", "element"]
    run_id: str = ""
    #: `None`, never 0, where there is no station. Station 0 is the START of a
    #: stretch, which is a different claim from "this has no station".
    station_mm: Mm | None = None
    node_id: str = ""
    element_id: str = ""


class JobFlag(BaseModel):
    """One finding, and every place it belongs.

    `places` is a LIST because one finding genuinely covers several stretches:
    `height_assumed` on a three-run job is one thing nobody said, not three.
    Splitting it into three flags would make the list claim three problems and
    the count above it lie.
    """

    code: str
    params: dict = {}
    severity: Severity
    places: list[Place]
    source: Literal["handover", "readiness", "strategy"]


def _place_scope(scope: str) -> Place:
    """`gap:run2:4000` -> a station on run2.

    Anything else lands on the job. Scopes are a wider vocabulary than this
    screen can draw — `model:mfr/certainteed/rail` is a real one — and a scope
    this cannot place is not a malformed scope, it is a scope about something
    that is not a stretch of fence.
    """
    if not scope.startswith(_SCOPE_PREFIX):
        return Place(kind="job")
    parts = scope[len(_SCOPE_PREFIX):].split(":")
    if len(parts) != 2 or not parts[0]:
        return Place(kind="job")
    try:
        station = int(parts[1])
    except ValueError:
        return Place(kind="job")
    return Place(kind="station", run_id=parts[0], station_mm=station)


def _place_element(ref: str) -> Place:
    """`post@run1:4000` and `span@run1:1334-2667` -> that run and station.

    `core/ids.py: element_id` builds these as `{kind}@{run_ref}:{station}`, with
    a range for a span. A span is placed at its START rather than its middle:
    the station is where the setting-out sheet measures from, so the two
    surfaces point at the same tape measure.

    A ref with no parseable run — `gate@gate1` — keeps the element and carries
    no station. The screen resolves a gate by its id; inventing station 0 would
    put it at the start of a stretch it is not on.
    """
    element, _, tail = ref.partition("@")
    if not element or not tail or ":" not in tail:
        return Place(kind="element", element_id=ref)
    run_ref, _, station = tail.rpartition(":")
    start = station.split("-")[0]
    try:
        return Place(kind="element", element_id=ref, run_id=run_ref,
                     station_mm=int(start))
    except ValueError:
        return Place(kind="element", element_id=ref)


def _gap_places(params: dict) -> list[Place]:
    """`run_ids` is the handle `handover.py` carries and never renders — its own
    comment says the road's gap row uses it to select the stretch. This is the
    same handle, read by a second surface."""
    run_ids = params.get("run_ids") or []
    places = [Place(kind="run", run_id=str(r)) for r in run_ids]
    return places or [Place(kind="job")]


def _item_places(params: dict) -> list[Place]:
    scopes = params.get("scopes") or []
    places = [_place_scope(str(s)) for s in scopes]
    return places or [Place(kind="job")]


def _warning_places(warning: StrategyWarning) -> list[Place]:
    if warning.element_refs:
        return [_place_element(ref) for ref in warning.element_refs]
    node_id = warning.params.get("node_id")
    if node_id:
        return [Place(kind="node", node_id=str(node_id))]
    run_id = warning.params.get("run_id")
    if run_id:
        return [Place(kind="run", run_id=str(run_id))]
    return [Place(kind="job")]


def job_flags(
    *,
    gaps: list[HandoverGap],
    items: list[ReadinessItem],
    warnings: list[StrategyWarning],
    choice_sets: list[ChoiceSet],
) -> list[JobFlag]:
    """Every finding, placed, worst first.

    `choice_sets` is taken and not yet read, and that is deliberate rather than
    forgotten: `choices_unanswered` already carries its scopes, so the sets add
    nothing to PLACEMENT — but they carry the question and the options, which is
    what a screen needs the moment it offers to answer one in place. Named in
    the signature so the seam is visible instead of being discovered later as a
    missing argument.
    """
    out: list[JobFlag] = []

    for gap in gaps:
        out.append(JobFlag(
            code=gap.code, params=gap.params,
            severity="blocking" if gap.blocking else "open",
            places=_gap_places(gap.params), source="handover"))

    for item in items:
        # `readiness()` has no blocking items by design — contract 3.2.4 forbids
        # failing a run over a gap, and a step that stopped somebody generating
        # would be the first thing worked around. Read anyway rather than
        # hard-coded, so a future blocking item is not silently downgraded here.
        out.append(JobFlag(
            code=item.code, params=item.params,
            severity="blocking" if getattr(item, "blocking", False) else "open",
            places=_item_places(item.params), source="readiness"))

    for warning in warnings:
        out.append(JobFlag(
            code=warning.code, params=dict(warning.params),
            severity=_FROM_WARNING.get(warning.severity, "open"),
            places=_warning_places(warning), source="strategy"))

    # Stable within a band: the sources keep their own order, which is the order
    # the rules fired in. Sorting by code would shuffle a run's warnings out of
    # the sequence that produced them.
    out.sort(key=lambda f: _ORDER[f.severity])
    return out


__all__ = ["JobFlag", "Place", "Severity", "job_flags"]
