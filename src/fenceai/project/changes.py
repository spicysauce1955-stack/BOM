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

**Facts, not storage.** A height is compared by what each stretch of the fence
is BUILT to (`topology.station.built_stretches`), never by its events. The editor
stores one height as one event or, after carving, as three; a later height can
sit hidden under an earlier one; a tool can replace an event with an identical
one under a new id. None of that is a change anybody made to the fence, and a
log that reported it would credit the office with the salesperson's measurement.
The same holds for bases and fence models, the other kinds the generator reads
first-covering-wins. Ids, storage order and revision counters are not facts.

**Nothing changes silently.** The vocabulary names the facts a person enters on
the two roads. Everything else is covered by completeness passes: a section that
differs in something no sentence reads gets `section_changed`, the drawing gets
`area_changed` for what no section or gate names (node kinds, loose nodes, the
order sections are lettered in), and every other area of the job gets
`area_changed` when it differs and nothing named it. So the vocabulary can be
behind the model — and it always will be — without a fact going unrecorded.

**Words, not ids — and the ids too.** Sections are named by their letter
(`topology.naming.section_tag`), positions by station along the section, lengths
in `…_mm` params the screen renders in the reader's unit. Every section-bearing
change ALSO carries `run`, the run id(s) it is about, because a letter is a
position and changes when an earlier section is deleted: `reletter` names the
section again at read time, the way the route resolves people's names.
"""

from __future__ import annotations

import json
from typing import Callable

from pydantic import BaseModel

from fenceai.core.errors import InvalidTopology
from fenceai.project.model import Project
from fenceai.topology.model import GateSpan, Run, Topology
from fenceai.topology.naming import section_tag
from fenceai.topology.station import (
    anchor_station, built_stretches, gate_opening_mm, run_length,
)

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

#: The area a save is logged under when its difference could not be worked out
#: at all (`unreadable`). Not in `AREAS`: no field belongs to it.
UNKNOWN_AREA = "unknown"

# Counters of saves, not facts anybody entered: a revision that moved with
# nothing else is a save, not a change (`topology.revision`, `site.revision`).
_IGNORED = {"topology": {"revision"}, "site": {"revision"}}

#: Interval kinds the vocabulary names — the three the generator reads
#: first-covering-wins — and how each reads. `prefix` names the codes
#: (`<prefix>_added|removed|changed`); `value` reads the payload's one fact a
#: sentence shows; `unit` says how it travels in params: "mm" under `…_mm` keys
#: the screen converts, anything else a word the screen looks up (`surface`) or
#: an id it shows (`model`).
_INTERVAL_KINDS: dict[str, tuple[str, Callable, str]] = {
    "height_intent": ("height", lambda p: p.height_mm, "mm"),
    "base": ("base", lambda p: p.surface, "surface"),
    "fence_model": ("model", lambda p: p.model_id, "model"),
}
#: Point kinds, matched by id: a point is a thing at a place, and a moved gate
#: is the same gate.
_POINT_KINDS: dict[str, tuple[str, Callable, str]] = {
    "gate": ("gate", lambda p: p.width_mm, "mm"),
    "elevation_sample": ("ground_point", lambda p: p.z_mm, "mm"),
}
# Who wrote an interval is not part of what it says: a height of 1800 confirmed
# from a note and one typed in are the same height.
_NOT_A_FACT = {"kind", "source"}

_JOB_FIELDS = ("customer", "address", "sold_by", "sold_on")
_STATED_FIELDS = ("no_gates", "no_promises")

#: Every code `diff_project` can emit. The locale test reads this, and the
#: per-field tests assert every emitted code is in it.
CHANGE_CODES: frozenset[str] = frozenset(
    {
        "job_created", "name_changed",
        *(f"{f}_changed" for f in _JOB_FIELDS),
        "status_changed", "assignee_changed", "plan_committed", "plan_released",
        "acknowledged",
        "landmark_added", "landmark_removed", "landmark_changed",
        "section_added", "section_removed", "section_length_changed",
        "section_reshaped", "ground_changed",
        *(f"{prefix}_{verb}" for prefix, _, _ in _INTERVAL_KINDS.values()
          for verb in ("added", "removed", "changed")),
        *(f"{prefix}_{verb}" for prefix, _, _ in _POINT_KINDS.values()
          for verb in ("added", "removed", "changed", "moved")),
        "gate_details_changed",
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
        # The drawing carries its own completeness pass, over facts: a new id
        # for an identical base is a different DOCUMENT and the same fence.
        if area != "drawing" and not named \
                and _area_dump(before, area) != _area_dump(after, area):
            out.append(Change(code="area_changed", params={"area": area}))
    return out


def unreadable() -> list[Change]:
    """What to log when the difference cannot be worked out at all.

    The store saves the job regardless: a bug in this module must not stop a
    salesperson saving a customer's fence. The entry still says that somebody
    changed the job, and when.
    """
    return [Change(code="area_changed", params={"area": UNKNOWN_AREA})]


def reletter(changes: list[dict], topology: Topology) -> list[dict]:
    """Name each change's section by the letter it has NOW.

    A stored letter is a position: delete section A and the old "B" is drawn as
    A. Every section-bearing change carries `run`, the run id(s) it is about, so
    the letter is taken again from the current drawing — and a section that is no
    longer drawn keeps the letter it had, marked `section_gone`, because no
    current letter is its name.
    """
    letters = {r.id: section_tag(i) for i, r in enumerate(topology.runs)}
    out = []
    for change in changes:
        params = dict(change.get("params") or {})
        run = params.get("run")
        if run and change.get("code") != "section_removed":
            ids = str(run).split("/")
            if all(i in letters for i in ids):
                params["section"] = "/".join(letters[i] for i in ids)
            else:
                params["section_gone"] = True
        out.append({**change, "params": params})
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
        where = {"section": section_tag(index), "run": run_id}
        if run_id not in old_runs:
            out.append(Change(code="section_added", params={
                **where, "length_mm": run_length(after, run)}))
            continue
        _, old_run = old_runs[run_id]
        named, unnamed = _section(before, old_run, after, run, where)
        out.extend(named)
        if unnamed or _unnamed(old_run) != _unnamed(run):
            out.append(Change(code="section_changed", params=where))

    for run_id, (index, run) in old_runs.items():
        if run_id not in new_runs:
            out.append(Change(code="section_removed", params={
                "section": section_tag(index), "run": run_id,
                "length_mm": run_length(before, run)}))

    out.extend(_ground(before, after))
    out.extend(_gate_spans(before, after))
    if _unnamed_drawing_changed(before, after):
        out.append(Change(code="area_changed", params={"area": "drawing"}))
    return out


def _section(before: Topology, old: Run, after: Topology, new: Run,
             where: dict[str, Param]) -> tuple[list[Change], bool]:
    """The named changes to one section, and whether anything about the kinds
    it names changed in a way no sentence reads (a model's options, a height
    hidden under another)."""
    out: list[Change] = []
    unnamed = False
    old_len, new_len = run_length(before, old), run_length(after, new)
    if old_len != new_len:
        out.append(Change(code="section_length_changed", params={
            **where, "from_mm": old_len, "to_mm": new_len}))
    elif _geometry(before, old) != _geometry(after, new):
        out.append(Change(code="section_reshaped", params=where))

    for kind, (prefix, value, unit) in _INTERVAL_KINDS.items():
        old_evs = [e for e in old.interval_events if e.payload.kind == kind]
        new_evs = [e for e in new.interval_events if e.payload.kind == kind]
        named, hidden = _stretches(before, old, after, new, old_evs, new_evs,
                                   prefix, value, unit, where)
        out.extend(named)
        unnamed = unnamed or hidden

    for kind, (prefix, value, unit) in _POINT_KINDS.items():
        out.extend(_points(
            [e for e in old.point_events if e.payload.kind == kind],
            [e for e in new.point_events if e.payload.kind == kind],
            prefix, value, unit, where,
            at_old=lambda e: {"at_mm": anchor_station(before, old, e.anchor)},
            at_new=lambda e: {"at_mm": anchor_station(after, new, e.anchor)},
        ))
    return out, unnamed


def _stretches(before: Topology, old: Run, after: Topology, new: Run,
               old_evs: list, new_evs: list, prefix: str, value: Callable,
               unit: str, where: dict[str, Param]) -> tuple[list[Change], bool]:
    """What one interval kind builds along a section, before and after.

    The old events are resolved against the NEW geometry, so a stretched section
    does not read as a moved height: their anchors re-scale exactly as they will
    when the fence is built. Only when the old anchors no longer fit the new
    shape (a vertex added or taken away) is the old geometry used instead.
    """
    def fact(p) -> tuple:
        return (value(p), json.dumps(p.model_dump(mode="json", exclude=_NOT_A_FACT),
                                     sort_keys=True))

    try:
        was = built_stretches(after, new, old_evs, fact)
    except InvalidTopology:
        was = built_stretches(before, old, old_evs, fact)
    now = built_stretches(after, new, new_evs, fact)

    cuts = sorted({s for a, b, _ in (*was, *now) for s in (a, b)})
    pieces: list[tuple[int, int, tuple | None, tuple | None]] = []
    for a, b in zip(cuts, cuts[1:]):
        mid = (a + b) / 2
        v0 = next((v for s0, s1, v in was if s0 <= mid <= s1), None)
        v1 = next((v for s0, s1, v in now if s0 <= mid <= s1), None)
        if v0 == v1:
            continue
        if pieces and pieces[-1][1] == a and pieces[-1][2:] == (v0, v1):
            pieces[-1] = (pieces[-1][0], b, v0, v1)
        else:
            pieces.append((a, b, v0, v1))

    out: list[Change] = []
    unnamed = False
    for a, b, v0, v1 in pieces:
        span = {"start_mm": a, "end_mm": b}
        if v0 is None:
            out.append(Change(code=f"{prefix}_added",
                              params={**where, **_value("value", v1[0], unit), **span}))
        elif v1 is None:
            out.append(Change(code=f"{prefix}_removed",
                              params={**where, **_value("value", v0[0], unit), **span}))
        elif v0[0] != v1[0]:
            out.append(Change(code=f"{prefix}_changed", params={
                **where, **_value("from", v0[0], unit), **_value("to", v1[0], unit),
                **span}))
        else:
            unnamed = True      # same shown value, another fact (a model's options)

    # Built the same, stored differently in a way that says something different —
    # a height hidden under another, say. Not a change to the fence, but not
    # nothing either; ids and storage order alone never reach this.
    if not out and not unnamed:
        try:
            old_facts = _facts(after, new, old_evs, fact)
        except InvalidTopology:
            old_facts = _facts(before, old, old_evs, fact)
        unnamed = old_facts != _facts(after, new, new_evs, fact)
    return out, unnamed


def _facts(topo: Topology, run: Run, events: list, fact: Callable) -> list:
    return sorted((anchor_station(topo, run, e.start_anchor),
                   anchor_station(topo, run, e.end_anchor), fact(e.payload)[1])
                  for e in events)


def _points(old: list, new: list, prefix: str, value: Callable, unit: str,
            where: dict[str, Param], at_old: Callable, at_new: Callable) -> list[Change]:
    """Added, removed, changed and moved points of one kind on one section.

    Matched by id. One removed and one added in one save is the same point
    re-authored, and reads as what actually differs between the two — nothing at
    all, when nothing does.

    *Moved* compares the stored ANCHORS of a matched point, never the stations
    they resolve to: a point anchored proportionally slides when its section is
    stretched, and nobody moved it — the section's length change is that save's
    entry.
    """
    old_by_id = {e.id: e for e in old}
    new_by_id = {e.id: e for e in new}
    removed = [e for e in old if e.id not in new_by_id]
    added = [e for e in new if e.id not in old_by_id]
    out: list[Change] = []

    def one(verb: str, v: Param, at: dict) -> Change:
        return Change(code=f"{prefix}_{verb}",
                      params={**where, **_value("value", v, unit), **at})

    def compare(prior, ev, moved: bool) -> Change | None:
        v0, v1 = value(prior.payload), value(ev.payload)
        if v0 != v1:
            return Change(code=f"{prefix}_changed", params={
                **where, **_value("from", v0, unit), **_value("to", v1, unit),
                **at_new(ev)})
        if moved:
            return one("moved", v1, at_new(ev))
        if prior.payload != ev.payload:
            # the one fact a sentence reads is the same, and so is the place —
            # something else about it changed (which way a gate opens)
            return Change(code=f"{prefix}_details_changed", params=where) \
                if f"{prefix}_details_changed" in CHANGE_CODES \
                else Change(code="section_changed", params=where)
        return None

    for ev in new:
        prior = old_by_id.get(ev.id)
        if prior is not None:
            change = compare(prior, ev, moved=prior.anchor != ev.anchor)
            if change:
                out.append(change)

    if len(removed) == 1 and len(added) == 1:
        prior, ev = removed[0], added[0]
        change = compare(prior, ev, moved=at_old(prior) != at_new(ev))
        if change:
            out.append(change)
        return out

    out.extend(one("added", value(e.payload), at_new(e)) for e in added)
    out.extend(one("removed", value(e.payload), at_old(e)) for e in removed)
    return out


def _value(key: str, v: Param, unit: str) -> dict[str, Param]:
    """`value`/`from`/`to` under the name the screen reads it by: `…_mm` for a
    length (converted to the reader's unit), else `surface`/`from_surface` or
    `model`/`from_model` — the param name says which vocabulary it is from."""
    if unit == "mm":
        return {f"{key}_mm": v}
    return {unit if key == "value" else f"{key}_{unit}": v}


def _ground(before: Topology, after: Topology) -> list[Change]:
    """Ground height at a corner or end — a NODE's z, shared by every section
    that meets there, so it is named by all of their letters."""
    old = {n.id: n for n in before.nodes}
    out: list[Change] = []
    for node in after.nodes:
        prior = old.get(node.id)
        if prior is not None and prior.z_mm != node.z_mm:
            out.append(Change(code="ground_changed", params={
                **_sections_at(after, {node.id}),
                "from_mm": prior.z_mm, "to_mm": node.z_mm}))
    return out


def _gate_spans(before: Topology, after: Topology) -> list[Change]:
    """Gates drawn BESIDE the runs (`GateSpan`), named by the sections they join."""
    old = {g.id: g for g in before.gates}
    new = {g.id: g for g in after.gates}
    out: list[Change] = []

    def where(topo: Topology, gate: GateSpan) -> dict[str, Param]:
        return _sections_at(topo, {gate.start_node_id, gate.end_node_id})

    for gate_id, gate in new.items():
        width = gate_opening_mm(after, gate)
        if gate_id not in old:
            out.append(Change(code="gate_added",
                              params={**where(after, gate), "value_mm": width}))
            continue
        prior = old[gate_id]
        prior_width = gate_opening_mm(before, prior)
        if prior_width != width:
            out.append(Change(code="gate_changed", params={
                **where(after, gate), "from_mm": prior_width, "to_mm": width}))
        elif prior != gate:
            out.append(Change(code="gate_details_changed", params=where(after, gate)))
        elif _span_nodes(before, prior) != _span_nodes(after, gate):
            out.append(Change(code="gate_moved",
                              params={**where(after, gate), "value_mm": width}))
    for gate_id, gate in old.items():
        if gate_id not in new:
            out.append(Change(code="gate_removed", params={
                **where(before, gate), "value_mm": gate_opening_mm(before, gate)}))
    return out


def _sections_at(topo: Topology, node_ids: set[str]) -> dict[str, Param]:
    """`section` and `run` for every section that starts or ends at one of these
    nodes, `/`-joined in drawing order — both `""` when none does."""
    hits = [(section_tag(i), r.id) for i, r in enumerate(topo.runs)
            if r.start_node_id in node_ids or r.end_node_id in node_ids]
    return {"section": "/".join(t for t, _ in hits), "run": "/".join(i for _, i in hits)}


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

    Three things can: the kind of a node both drawings have; a node that no
    section or gate touches — added, removed or moved on its own; and the ORDER
    of the sections both drawings have, which is what their letters are. A node
    added WITH a section or a gate is that section's or gate's addition, and is
    already said.
    """
    old = {n.id: n for n in before.nodes}
    if any(n.id in old and old[n.id].kind != n.kind for n in after.nodes):
        return True

    def loose(topo: Topology) -> set[tuple]:
        touched = {n for r in topo.runs for n in (r.start_node_id, r.end_node_id)}
        touched |= {n for g in topo.gates for n in (g.start_node_id, g.end_node_id)}
        return {(n.id, n.x_mm, n.y_mm) for n in topo.nodes if n.id not in touched}

    if loose(before) != loose(after):
        return True
    both = {r.id for r in before.runs} & {r.id for r in after.runs}
    return [r.id for r in before.runs if r.id in both] != \
        [r.id for r in after.runs if r.id in both]


# -- the model, the notes, the claims ------------------------------------------


def _default_model(before: Project, after: Project) -> list[Change]:
    """The job's default model, by id. A change of version pin or options only
    is left to the area pass, which names it without a misleading "M → M"."""
    old = before.fence_model.model_id if before.fence_model else None
    new = after.fence_model.model_id if after.fence_model else None
    if old == new:
        return []
    return [Change(code="default_model_changed",
                   params={"from_model": old, "to_model": new})]


def _notes(before: Project, after: Project) -> list[Change]:
    seen = {a.id for a in before.annotations}
    sections = {f"run:{r.id}": (section_tag(i), r.id)
                for i, r in enumerate(after.topology.runs)}
    out = []
    for a in after.annotations:
        if a.id in seen:
            continue
        letter, run = sections.get(a.target_ref, ("", ""))
        params: dict[str, Param] = {"text": a.text, "section": letter}
        if run:
            params["run"] = run
        out.append(Change(code="note_added", params=params))
    return out


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
