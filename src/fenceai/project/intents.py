"""Confirmation flow: a human confirms a proposed intent, which materializes it as
first-class topology state (event/override) with provenance back to the annotation.

Until confirmation, intents influence nothing (ADR-0009 hard boundary).
"""

from __future__ import annotations

from fenceai.core.ids import new_id
from fenceai.project.model import Project
from fenceai.strategy.overrides import Override, PinPost
from fenceai.topology.model import (
    HeightIntentPayload,
    IntervalEvent,
    TopLinePayload,
)
from fenceai.topology.station import make_anchor, run_length


def confirm_intent(
    project: Project,
    annotation_id: str,
    intent_id: str,
    run_id: str,
    confirmed_by: str = "user",
) -> str:
    """Confirm one candidate intent; returns the id of the materialized object."""
    annotation = next((a for a in project.annotations if a.id == annotation_id), None)
    if annotation is None:
        raise ValueError(f"annotation {annotation_id} not found")
    record = next(
        (r for r in annotation.interpretations if any(c.id == intent_id for c in r.candidates)),
        None,
    )
    if record is None:
        raise ValueError(f"intent {intent_id} not found on annotation {annotation_id}")
    intent = next(c for c in record.candidates if c.id == intent_id)
    if intent.status == "confirmed":
        raise ValueError(f"intent {intent_id} already confirmed")

    run = project.topology.run(run_id)
    total = run_length(project.topology, run)
    provenance = record.id  # interpretation record id — chains to annotation + verbatim text

    if intent.kind == "height_intent":
        event = IntervalEvent(
            id=new_id("ev"),
            start_anchor=make_anchor(project.topology, run, 0),
            end_anchor=make_anchor(project.topology, run, total),
            payload=HeightIntentPayload(height_mm=int(intent.params["height_mm"]), source=provenance),
        )
        run.interval_events.append(event)
        result_id = event.id
    elif intent.kind == "top_line":
        event = IntervalEvent(
            id=new_id("ev"),
            start_anchor=make_anchor(project.topology, run, 0),
            end_anchor=make_anchor(project.topology, run, total),
            payload=TopLinePayload(
                mode=intent.params.get("mode", "level"),  # type: ignore[arg-type]
                z_mm=int(intent.params["z_mm"]) if "z_mm" in intent.params else None,
                source=provenance,
            ),
        )
        run.interval_events.append(event)
        result_id = event.id
    elif intent.kind == "post_request" and "station_mm" in intent.params:
        override = Override(
            id=new_id("ov"),
            run_id=run_id,
            directive=PinPost(station_mm=int(intent.params["station_mm"])),
            origin="user",
            author=confirmed_by,
            note=f"from interpretation {provenance}",
        )
        project.overrides.append(override)
        result_id = override.id
    else:
        raise ValueError(f"intent kind {intent.kind} cannot be materialized automatically")

    intent.status = "confirmed"
    intent.confirmed_by = confirmed_by
    # any topology mutation must bump the revision so GenerationRun.topology_revision
    # keeps identifying content (critic finding 2)
    if intent.kind in ("height_intent", "top_line"):
        project.topology.revision += 1
    return result_id
