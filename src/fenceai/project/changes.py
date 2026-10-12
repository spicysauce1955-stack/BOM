"""What changed in a job between two saves, in words a person on the job reads.

The office may change what the salesperson entered — a height, a gate, the model
— and the owner's answer to *what happens then* is **log it**
(docs/superpowers/specs/2026-10-12-office-desk-without-ai-design.md). The audit
log already names who saved; it cannot say what they changed, and the job is one
row each save overwrites, so the value before the save is gone the moment it
lands. This module is the missing half: two documents in, a list of changes out.

**Pure.** No store, no clock, no identity: the store calls it inside
`save_project` with the document it is about to overwrite, which is the only
moment both halves exist. Same two documents, same list, same order.

**Platform text.** A change is `code + params`, never a sentence, and every code
has a `change.<code>` sentence in both locale bundles — the rule the warning
registry follows, for the same reason: the reader's language is the screen's
business, and an English sentence stored in a row cannot be re-read in Hebrew.

**Nothing changes silently.** The vocabulary below names the facts a person
enters on the two roads. Everything else a job can carry is covered by a
completeness pass at the end: a section that differs and was named by nothing
gets `section_changed`, and an area of the job that differs and was named by
nothing gets `area_changed`. So the vocabulary can be behind the model — and it
always will be — without a change ever going unrecorded.

**Words, not ids.** Sections are named by their letter (`report.sections.
section_tag`, the letters the office's job screen and the setting-out sheet
print), positions by station along the section, lengths in `…_mm` params that
the screen renders in the reader's unit.
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from fenceai.project.model import Project
from fenceai.report.sections import section_tag
from fenceai.topology.model import GateSpan, Run, Topology
from fenceai.topology.station import anchor_station, gate_opening_mm, run_length

Param = str | int | bool | None


class Change(BaseModel):
    """One thing that changed. `code` is a key into the `change.*` sentences."""

    code: str
    params: dict[str, Param] = {}


#: Which Project fields each area of the job covers. EVERY field belongs to
#: exactly one area — `tests/project/test_changes.py` holds that — so a field
#: added to `Project` fails a test until somebody decides which area it is in,
#: rather than changing silently on every save.
AREAS: dict[str, tuple[str, ...]] = {
    "job": ("id", "name", "created_at", "created_by", "job"),
    "desk": ("status", "assignee", "submitted_at", "closed_at", "committed_run_id",
             "acknowledgements"),
    "property": ("context",),
    "drawing": ("topology",),
    "model": ("fence_model",),
    "notes": ("annotations",),
    "stated": ("stated",),
    "site": ("site",),
    "posts": ("overrides",),
    "choices": ("choices",),
    "policy": ("policy",),
}

# Counters of saves, not facts anybody entered: a revision that moved with
# nothing else is a save, not a change (`topology.revision`, `site.revision`).
_IGNORED = {"topology": {"revision"}, "site": {"revision"}}

#: Interval and point event kinds the vocabulary names, and how each reads.
#: `prefix` names the codes (`<prefix>_added|removed|changed|moved`); `value`
#: reads the payload's one fact; `unit` says how that fact travels in params —
#: "mm" puts it under `…_mm` keys so the screen converts it, anything else is a
#: word the screen looks up (`surface`) or shows as an id (`model`).
_INTERVAL_KINDS: dict[str, tuple[str, Callable, str]] = {
    "height_intent": ("height", lambda p: p.height_mm, "mm"),
    "base": ("base", lambda p: p.surface, "surface"),
    "fence_model": ("model", lambda p: p.model_id, "model"),
}
_POINT_KINDS: dict[str, tuple[str, Callable, str]] = {
    "gate": ("gate", lambda p: p.width_mm, "mm"),
    "elevation_sample": ("ground_point", lambda p: p.z_mm, "mm"),
}
_VERBS = ("added", "removed", "changed", "moved")

_JOB_FIELDS = ("customer", "address", "sold_by", "sold_on")
_STATED_FIELDS = ("no_gates", "no_promises")

#: Every code `diff_project` can emit. The locale test reads this, so a code
#: added to the diff and not here is caught by the test that asserts the emitted
#: codes are a subset of it.
CHANGE_CODES: frozenset[str] = frozenset(
    {
        "job_created", "name_changed",
        *(f"{f}_changed" for f in _JOB_FIELDS),
        "status_changed", "assignee_changed", "plan_committed", "plan_released",
        "acknowledged",
        "landmark_added", "landmark_removed", "landmark_changed",
        "section_added", "section_removed", "section_length_changed",
        "section_reshaped", "ground_changed",
        *(f"{prefix}_{verb}"
          for prefix, _, _ in (*_INTERVAL_KINDS.values(), *_POINT_KINDS.values())
          for verb in _VERBS),
        "default_model_changed", "note_added", "stated_changed",
        "section_changed", "area_changed",
    }
)


def diff_project(before: Project | None, after: Project) -> list[Change]:
    """Everything that changed from `before` to `after`.

    `None` before means the job is new: one `job_created`, and nothing about
    what it was created with — that is the job's starting point, not a change
    to it.
    """
    if before is None:
        return [Change(code="job_created", params={"name": after.display_name()})]

    by_area: dict[str, list[Change]] = {
        "job": _job(before, after),
        "desk": _desk(before, after),
        "property": _property(before, after),
        "drawing": _drawing(before.topology, after.topology),
        "model": _default_model(before, after),
        "notes": _notes(before, after),
        "stated": _stated(before, after),
    }
    out: list[Change] = []
    for area in AREAS:
        named = by_area.get(area, [])
        out.extend(named)
        if not named and _area_dump(before, area) != _area_dump(after, area):
            out.append(Change(code="area_changed", params={"area": area}))
    return out


# -- the job and the desk ------------------------------------------------------


def _job(before: Project, after: Project) -> list[Change]:
    out: list[Change] = []
    if before.name != after.name:
        out.append(Change(code="name_changed",
                          params={"from": before.name, "to": after.name}))
    for field in _JOB_FIELDS:
        old = getattr(before.job, field) if before.job else ""
        new = getattr(after.job, field) if after.job else ""
        if old != new:
            out.append(Change(code=f"{field}_changed", params={"from": old, "to": new}))
    return out


def _desk(before: Project, after: Project) -> list[Change]:
    out: list[Change] = []
    if before.status != after.status:
        out.append(Change(code="status_changed", params={
            "from_state": before.status, "to_state": after.status}))
    if before.assignee != after.assignee:
        out.append(Change(code="assignee_changed", params={
            "from_person": before.assignee, "to_person": after.assignee}))
    if before.committed_run_id != after.committed_run_id:
        if after.committed_run_id:
            out.append(Change(code="plan_committed",
                              params={"run_id": after.committed_run_id}))
        else:
            out.append(Change(code="plan_released",
                              params={"run_id": before.committed_run_id}))
    seen = {(a.kind, a.anchor) for a in before.acknowledgements}
    for ack in after.acknowledgements:
        if (ack.kind, ack.anchor) not in seen:
            out.append(Change(code="acknowledged", params={"what": ack.kind}))
    return out


# -- the property --------------------------------------------------------------


def _property(before: Project, after: Project) -> list[Change]:
    old = {lm.id: lm for lm in before.context.landmarks}
    new = {lm.id: lm for lm in after.context.landmarks}
    out: list[Change] = []
    for lm_id, lm in new.items():
        params = {"landmark": lm.kind, "label": lm.label}
        if lm_id not in old:
            out.append(Change(code="landmark_added", params=params))
        elif old[lm_id] != lm:
            out.append(Change(code="landmark_changed", params=params))
    for lm_id, lm in old.items():
        if lm_id not in new:
            out.append(Change(code="landmark_removed",
                              params={"landmark": lm.kind, "label": lm.label}))
    return out


# -- the drawing ---------------------------------------------------------------


def _drawing(before: Topology, after: Topology) -> list[Change]:
    old_runs = {r.id: (i, r) for i, r in enumerate(before.runs)}
    new_runs = {r.id: (i, r) for i, r in enumerate(after.runs)}
    out: list[Change] = []

    for run_id, (index, run) in new_runs.items():
        section = section_tag(index)
        if run_id not in old_runs:
            out.append(Change(code="section_added", params={
                "section": section, "length_mm": run_length(after, run)}))
            continue
        _, old_run = old_runs[run_id]
        out.extend(_section(before, old_run, after, run, section))
        if _unnamed(old_run) != _unnamed(run):
            out.append(Change(code="section_changed", params={"section": section}))

    for run_id, (index, run) in old_runs.items():
        if run_id not in new_runs:
            out.append(Change(code="section_removed", params={
                "section": section_tag(index), "length_mm": run_length(before, run)}))

    out.extend(_ground(before, after))
    out.extend(_gate_spans(before, after))
    if _unnamed_drawing_changed(before, after):
        out.append(Change(code="area_changed", params={"area": "drawing"}))
    return out


def _section(before: Topology, old: Run, after: Topology, new: Run,
             section: str) -> list[Change]:
    out: list[Change] = []
    old_len, new_len = run_length(before, old), run_length(after, new)
    if old_len != new_len:
        out.append(Change(code="section_length_changed", params={
            "section": section, "from_mm": old_len, "to_mm": new_len}))
    elif _geometry(before, old) != _geometry(after, new):
        out.append(Change(code="section_reshaped", params={"section": section}))

    for kind, (prefix, value, unit) in _INTERVAL_KINDS.items():
        out.extend(_events(
            [e for e in old.interval_events if e.payload.kind == kind],
            [e for e in new.interval_events if e.payload.kind == kind],
            prefix, value, unit, section,
            anchors=lambda e: (e.start_anchor, e.end_anchor),
            where_old=lambda e: _range(before, old, e),
            where_new=lambda e: _range(after, new, e),
        ))
    for kind, (prefix, value, unit) in _POINT_KINDS.items():
        out.extend(_events(
            [e for e in old.point_events if e.payload.kind == kind],
            [e for e in new.point_events if e.payload.kind == kind],
            prefix, value, unit, section,
            anchors=lambda e: e.anchor,
            where_old=lambda e: {"at_mm": anchor_station(before, old, e.anchor)},
            where_new=lambda e: {"at_mm": anchor_station(after, new, e.anchor)},
        ))
    return out


def _events(old: list, new: list, prefix: str, value: Callable, unit: str,
            section: str, anchors: Callable, where_old: Callable,
            where_new: Callable) -> list[Change]:
    """Added, removed, changed and moved events of one kind on one section.

    Matched by id. One removed and one added in the same save is ONE change from
    the old value to the new — that is how the base and model tools replace, and
    how a height now replaces what it covers; reporting it as a removal and an
    addition would make the reader do the pairing the save already did.

    *Moved* compares the stored ANCHORS, never the stations they resolve to. A
    height anchored proportionally stretches with its section when a corner is
    dragged; its stations change and nobody moved it. The section's own length
    change is the entry for that save.
    """
    old_by_id = {e.id: e for e in old}
    new_by_id = {e.id: e for e in new}
    removed = [e for e in old if e.id not in new_by_id]
    added = [e for e in new if e.id not in old_by_id]
    out: list[Change] = []

    def one(verb: str, v: Param, where: dict) -> Change:
        return Change(code=f"{prefix}_{verb}",
                      params={"section": section, **_value("value", v, unit), **where})

    def changed(v0: Param, v1: Param, where: dict) -> Change:
        return Change(code=f"{prefix}_changed", params={
            "section": section, **_value("from", v0, unit), **_value("to", v1, unit),
            **where})

    for ev in new:
        if ev.id not in old_by_id:
            continue
        prior = old_by_id[ev.id]
        v0, v1 = value(prior.payload), value(ev.payload)
        if v0 != v1:
            out.append(changed(v0, v1, where_new(ev)))
        elif anchors(prior) != anchors(ev):
            out.append(one("moved", v1, where_new(ev)))
        elif prior.payload != ev.payload:
            # the one fact this vocabulary reads is the same and so is the
            # place — something else on the payload moved (a gate's swing)
            out.append(changed(v0, v1, where_new(ev)))

    if len(removed) == 1 and len(added) == 1:
        v0, v1 = value(removed[0].payload), value(added[0].payload)
        if v0 != v1:
            out.append(changed(v0, v1, where_new(added[0])))
        else:
            out.append(one("moved", v1, where_new(added[0])))
        return out

    out.extend(one("added", value(e.payload), where_new(e)) for e in added)
    out.extend(one("removed", value(e.payload), where_old(e)) for e in removed)
    return out


def _value(key: str, v: Param, unit: str) -> dict[str, Param]:
    """`value`/`from`/`to` under the name the screen reads it by: `…_mm` for a
    length (converted to the reader's unit), else `surface`/`from_surface` or
    `model`/`from_model` — the param name says which vocabulary it is from."""
    if unit == "mm":
        return {f"{key}_mm": v}
    return {unit if key == "value" else f"{key}_{unit}": v}


def _range(topo: Topology, run: Run, ev) -> dict[str, Param]:
    return {"start_mm": anchor_station(topo, run, ev.start_anchor),
            "end_mm": anchor_station(topo, run, ev.end_anchor)}


def _ground(before: Topology, after: Topology) -> list[Change]:
    """Ground height at a corner or end — a NODE's z, shared by every section
    that meets there, so it is named by all of their letters."""
    old = {n.id: n for n in before.nodes}
    out: list[Change] = []
    for node in after.nodes:
        prior = old.get(node.id)
        if prior is not None and prior.z_mm != node.z_mm:
            out.append(Change(code="ground_changed", params={
                "section": _sections_at(after, {node.id}),
                "from_mm": prior.z_mm, "to_mm": node.z_mm}))
    return out


def _gate_spans(before: Topology, after: Topology) -> list[Change]:
    """Gates drawn BESIDE the runs (`GateSpan`), named by the sections they join."""
    old = {g.id: g for g in before.gates}
    new = {g.id: g for g in after.gates}
    out: list[Change] = []

    def params(topo: Topology, gate: GateSpan) -> dict[str, Param]:
        return {"section": _sections_at(topo, {gate.start_node_id, gate.end_node_id})}

    for gate_id, gate in new.items():
        width = gate_opening_mm(after, gate)
        if gate_id not in old:
            out.append(Change(code="gate_added",
                              params={**params(after, gate), "value_mm": width}))
            continue
        prior = old[gate_id]
        prior_width = gate_opening_mm(before, prior)
        if prior_width != width or prior != gate:
            out.append(Change(code="gate_changed", params={
                **params(after, gate), "from_mm": prior_width, "to_mm": width}))
        elif _span_nodes(before, prior) != _span_nodes(after, gate):
            out.append(Change(code="gate_moved",
                              params={**params(after, gate), "value_mm": width}))
    for gate_id, gate in old.items():
        if gate_id not in new:
            out.append(Change(code="gate_removed", params={
                **params(before, gate), "value_mm": gate_opening_mm(before, gate)}))
    return out


def _sections_at(topo: Topology, node_ids: set[str]) -> str:
    """The letters of every section that starts or ends at one of these nodes,
    `/`-joined in drawing order — `""` when none does."""
    return "/".join(section_tag(i) for i, r in enumerate(topo.runs)
                    if r.start_node_id in node_ids or r.end_node_id in node_ids)


def _span_nodes(topo: Topology, gate: GateSpan) -> tuple:
    return tuple((n.x_mm, n.y_mm) for n in
                 (topo.node(gate.start_node_id), topo.node(gate.end_node_id)))


def _geometry(topo: Topology, run: Run) -> tuple:
    start, end = topo.node(run.start_node_id), topo.node(run.end_node_id)
    return ((start.x_mm, start.y_mm), tuple(map(tuple, run.interior_vertices)),
            (end.x_mm, end.y_mm))


def _unnamed(run: Run) -> dict:
    """What the vocabulary does not name about one section: the kinds of event it
    has no sentence for, and which nodes the section joins. Its shape is named
    (length, reshaped), and so is every event of a kind it reads."""
    data = run.model_dump(mode="json", exclude={"interior_vertices"})
    data["interval_events"] = [e for e in data["interval_events"]
                               if e["payload"]["kind"] not in _INTERVAL_KINDS]
    data["point_events"] = [e for e in data["point_events"]
                            if e["payload"]["kind"] not in _POINT_KINDS]
    return data


def _unnamed_drawing_changed(before: Topology, after: Topology) -> bool:
    """Did anything change that no section and no gate names?

    Two things can: the kind of a node both drawings have, and a node that no
    section or gate touches — added, removed or moved on its own. A node added
    WITH a section or a gate is that section's or gate's addition, and is
    already said.
    """
    old = {n.id: n for n in before.nodes}
    if any(n.id in old and old[n.id].kind != n.kind for n in after.nodes):
        return True

    def loose(topo: Topology) -> set[tuple]:
        touched = {n for r in topo.runs for n in (r.start_node_id, r.end_node_id)}
        touched |= {n for g in topo.gates for n in (g.start_node_id, g.end_node_id)}
        return {(n.id, n.x_mm, n.y_mm) for n in topo.nodes if n.id not in touched}

    return loose(before) != loose(after)


# -- the model, the notes, the claims ------------------------------------------


def _default_model(before: Project, after: Project) -> list[Change]:
    if before.fence_model == after.fence_model:
        return []
    return [Change(code="default_model_changed", params={
        "from_model": before.fence_model.model_id if before.fence_model else None,
        "to_model": after.fence_model.model_id if after.fence_model else None,
    })]


def _notes(before: Project, after: Project) -> list[Change]:
    seen = {a.id for a in before.annotations}
    sections = {f"run:{r.id}": section_tag(i) for i, r in enumerate(after.topology.runs)}
    return [
        Change(code="note_added", params={
            "text": a.text, "section": sections.get(a.target_ref, "")})
        for a in after.annotations if a.id not in seen
    ]


def _stated(before: Project, after: Project) -> list[Change]:
    return [
        Change(code="stated_changed",
               params={"what": field, "value": getattr(after.stated, field)})
        for field in _STATED_FIELDS
        if getattr(before.stated, field) != getattr(after.stated, field)
    ]


# -- completeness ----------------------------------------------------------------


def _area_dump(project: Project, area: str) -> dict:
    data = project.model_dump(mode="json", include=set(AREAS[area]))
    for field, ignored in _IGNORED.items():
        if field in data and isinstance(data[field], dict):
            data[field] = {k: v for k, v in data[field].items() if k not in ignored}
    return data
