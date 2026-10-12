"""What changed in a job between two saves (fenceai/project/changes.py).

Built on a Levi-shaped job — the one the owner's guide walks through: a 9 m
street section (A) with a 1 m gate at 4 m, turning at a junction into a 6 m
side section (B) that stands on a brick wall from 3 m. Each test makes the
smallest edit a person makes on screen and asserts the sentence it becomes.
"""

from __future__ import annotations

import pytest

from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.project.changes import AREAS, CHANGE_CODES, Change, diff_project, reletter
from fenceai.project.model import (
    Acknowledgement, Annotation, Job, Landmark, Project, Selection,
)
from fenceai.strategy.overrides import Override, PinPost
from fenceai.topology.model import (
    BasePayload, ElevationSamplePayload, FenceModelPayload, GatePayload, GateSpan,
    HeightIntentPayload, Node, PostTiltPayload, Run, Topology,
)
from fenceai.topology.station import make_anchor
from tests.conftest import add_interval_event, add_point_event


def levi() -> Project:
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0),
               Node(id="n2", x_mm=9000, y_mm=0, kind="junction"),
               Node(id="n3", x_mm=9000, y_mm=-6000)],
        runs=[Run(id="street", start_node_id="n1", end_node_id="n2"),
              Run(id="side", start_node_id="n2", end_node_id="n3")],
    )
    add_point_event(topo, "street", "gate", 4000, GatePayload(width_mm=1000))
    add_interval_event(topo, "street", "h-street", 0, 9000, HeightIntentPayload(height_mm=1800))
    add_interval_event(topo, "side", "wall", 3000, 6000, BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "side", "h-side", 0, 6000, HeightIntentPayload(height_mm=1800))
    return Project(
        id="proj_levi", name="Levi", topology=topo,
        job=Job(customer="Levi family", address="Herzl 12, Ramat Gan",
                sold_by="Dana", sold_on="2026-10-11"),
        context={"landmarks": [Landmark(id="house", kind="house", label="",
                                        points=[(1000, 1000), (6000, 1000),
                                                (6000, 5000), (1000, 5000)],
                                        closed=True)]},
        status="waiting",
    )


def edit(fn) -> tuple[Project, Project]:
    before = levi()
    after = before.model_copy(deep=True)
    fn(after)
    return before, after


def changes(fn) -> list[Change]:
    before, after = edit(fn)
    return diff_project(before, after)


def only(fn) -> Change:
    out = changes(fn)
    assert len(out) == 1, out
    return out[0]


def side(p: Project) -> Run:
    return p.topology.run("side")


def street(p: Project) -> Run:
    return p.topology.run("street")


# -- nothing, and a new job ------------------------------------------------------


def test_a_new_job_is_one_entry_naming_it():
    assert diff_project(None, levi()) == [
        Change(code="job_created", params={"name": levi().display_name()})]


def test_nothing_changed_is_no_change():
    assert changes(lambda p: None) == []


def test_a_revision_bump_alone_is_a_save_not_a_change():
    def bump(p):
        p.topology.revision += 3
        p.site.revision += 1
    assert changes(bump) == []


def test_the_same_two_documents_give_the_same_list():
    before, after = edit(lambda p: setattr(side(p).interval_events[1].payload,
                                           "height_mm", 1750))
    assert diff_project(before, after) == diff_project(before, after)


# -- the job and the desk --------------------------------------------------------


def test_a_job_field_names_the_field_and_both_values():
    assert only(lambda p: setattr(p.job, "address", "Herzl 14, Ramat Gan")) == Change(
        code="address_changed",
        params={"from": "Herzl 12, Ramat Gan", "to": "Herzl 14, Ramat Gan"})


def test_the_project_name():
    assert only(lambda p: setattr(p, "name", "Levi 2")) == Change(
        code="name_changed", params={"from": "Levi", "to": "Levi 2"})


def test_a_status_change_is_the_handover_line():
    def take(p):
        p.status = "planning"
        p.assignee = "u_yossi"
    assert changes(take) == [
        Change(code="status_changed",
               params={"from_state": "waiting", "to_state": "planning"}),
        Change(code="assignee_changed",
               params={"from_person": None, "to_person": "u_yossi"}),
    ]


def test_committing_and_releasing_a_plan():
    assert only(lambda p: setattr(p, "committed_run_id", "run_9")) == Change(
        code="plan_committed", params={"run_id": "run_9"})
    before, after = edit(lambda p: setattr(p, "committed_run_id", "run_9"))
    assert diff_project(after, before) == [
        Change(code="plan_released", params={"run_id": "run_9"})]


def test_an_acknowledgement():
    assert only(lambda p: p.acknowledgements.append(Acknowledgement(
        kind="sale_read", anchor="x", by="user:u_yossi", at="t"))) == Change(
        code="acknowledged", params={"what": "sale_read"})


# -- the property ----------------------------------------------------------------


def test_landmarks_added_moved_and_removed():
    tree = Landmark(id="tree", kind="tree", points=[(0, 8000), (400, 8400)])
    assert only(lambda p: p.context.landmarks.append(tree)) == Change(
        code="landmark_added", params={"landmark": "tree", "label": ""})

    def move_house(p):
        p.context.landmarks[0].points[0] = (1500, 1000)
    assert only(move_house).code == "landmark_changed"
    assert only(lambda p: p.context.landmarks.clear()) == Change(
        code="landmark_removed", params={"landmark": "house", "label": ""})


# -- the fence line ----------------------------------------------------------------


def test_sections_are_named_by_their_letter():
    def add_c(p):
        p.topology.nodes.append(Node(id="n4", x_mm=0, y_mm=-6000))
        p.topology.runs.append(Run(id="back", start_node_id="n3", end_node_id="n4"))
    assert only(add_c) == Change(code="section_added",
                                 params={"section": "C", "run": "back", "length_mm": 9000})

    def remove_b(p):
        p.topology.runs.pop()
        p.topology.nodes.pop()
    assert only(remove_b) == Change(code="section_removed",
                                    params={"section": "B", "run": "side", "length_mm": 6000})


def test_moving_a_corner_changes_the_length_of_every_section_at_it():
    def move_n2(p):
        p.topology.nodes[1].x_mm = 9500
    out = changes(move_n2)
    assert out[0] == Change(code="section_length_changed",
                            params={"section": "A", "run": "street", "from_mm": 9000, "to_mm": 9500})
    assert out[1].code == "section_length_changed" and out[1].params["section"] == "B"
    # the heights stretched with their sections; nobody moved them
    assert [c.code for c in out] == ["section_length_changed"] * 2


def test_turning_a_section_without_changing_its_length_is_a_reshape():
    def swing(p):
        p.topology.nodes[2].x_mm, p.topology.nodes[2].y_mm = 15000, 0
    assert only(swing) == Change(code="section_reshaped",
                             params={"section": "B", "run": "side"})


# -- the side view -------------------------------------------------------------------


def test_a_height_replacing_the_old_one_reads_from_and_to():
    """The owner's example: the office replaces Dana's 1800 with 1750."""
    def replace(p):
        run = side(p)
        run.interval_events = [e for e in run.interval_events if e.id != "h-side"]
        add_interval_event(p.topology, "side", "h-yossi", 0, 6000,
                           HeightIntentPayload(height_mm=1750))
    assert only(replace) == Change(code="height_changed", params={
        "section": "B", "run": "side", "from_mm": 1800, "to_mm": 1750,
        "start_mm": 0, "end_mm": 6000})


def test_a_carved_height_is_one_change_over_the_stretch_that_changed():
    """Carving stores Dana's 1800 as a shortened event and Yossi's 1750 as a new
    one. What the fence gets is 1750 over the second half and nothing else — and
    that is the whole entry: Dana's measurement is not re-credited to Yossi."""
    def carve(p):
        run = side(p)
        old = next(e for e in run.interval_events if e.id == "h-side")
        old.end_anchor = make_anchor(p.topology, run, 3000)
        add_interval_event(p.topology, "side", "h-yossi", 3000, 6000,
                           HeightIntentPayload(height_mm=1750))
    assert changes(carve) == [Change(code="height_changed", params={
        "section": "B", "run": "side", "from_mm": 1800, "to_mm": 1750,
        "start_mm": 3000, "end_mm": 6000})]


def test_a_height_split_around_a_new_one_credits_only_the_middle():
    """The remnant after the split is a NEW event holding Dana's 1800 — the
    case the reviewer found logged as the office setting 1800."""
    def split(p):
        run = side(p)
        old = next(e for e in run.interval_events if e.id == "h-side")
        old.end_anchor = make_anchor(p.topology, run, 3000)
        add_interval_event(p.topology, "side", "h-rest", 4000, 6000,
                           HeightIntentPayload(height_mm=1800))
        add_interval_event(p.topology, "side", "h-yossi", 3000, 4000,
                           HeightIntentPayload(height_mm=1750))
    assert changes(split) == [Change(code="height_changed", params={
        "section": "B", "run": "side", "from_mm": 1800, "to_mm": 1750,
        "start_mm": 3000, "end_mm": 4000})]


def test_reordering_heights_is_logged_when_it_changes_what_is_built():
    """The generator builds the FIRST height covering a station, so putting a
    later one first changes the fence — saved together with something else,
    which used to hide it behind the named change."""
    def stacked(p):
        add_interval_event(p.topology, "side", "h-under", 3000, 6000,
                           HeightIntentPayload(height_mm=1750))

    def reorder(p):
        run = side(p)
        heights = [e for e in run.interval_events if e.payload.kind == "height_intent"]
        others = [e for e in run.interval_events if e.payload.kind != "height_intent"]
        run.interval_events = others + heights[::-1]
        p.topology.nodes[1].z_mm = 100
    out = _with(stacked, reorder)
    assert [c.code for c in out] == ["height_changed", "ground_changed"]
    assert out[0].params["start_mm"] == 3000 and out[0].params["to_mm"] == 1750


def test_a_tool_replacing_an_event_with_an_identical_one_is_no_change():
    """The base tool removes and re-adds; re-saving it unchanged is a new id for
    the same fact, and a row for it would be a row for a save that did nothing."""
    def resave(p):
        run = side(p)
        run.interval_events = [e for e in run.interval_events if e.id != "wall"]
        add_interval_event(p.topology, "side", "wall-again", 3000, 6000,
                           BasePayload(surface="masonry_wall"))
    assert changes(resave) == []


def test_a_height_hidden_under_another_is_not_silent():
    """Built the same, stored to say something different."""
    assert only(lambda p: add_interval_event(
        p.topology, "side", "h-hidden", 0, 3000, HeightIntentPayload(height_mm=1500))) == \
        Change(code="section_changed", params={"section": "B", "run": "side"})


def test_a_height_edited_in_place():
    assert only(lambda p: setattr(side(p).interval_events[1].payload,
                                  "height_mm", 1750)).code == "height_changed"


def test_two_heights_removed_are_two_entries_not_a_pair():
    def clear(p):
        for run in p.topology.runs:
            run.interval_events = [e for e in run.interval_events
                                   if e.payload.kind != "height_intent"]
    out = changes(clear)
    assert [(c.code, c.params["section"]) for c in out] == [
        ("height_removed", "A"), ("height_removed", "B")]


def test_the_base_tool_replacing_a_base_reads_what_each_stretch_stands_on():
    """The wall ran 3000–6000 and the rest stood on soil by default. Replaced by
    soil over the whole section: the first half is now STATED soil, the second
    half changed from wall to soil."""
    def replace(p):
        run = side(p)
        run.interval_events = [e for e in run.interval_events if e.id != "wall"]
        add_interval_event(p.topology, "side", "soil", 0, 6000, BasePayload(surface="soil"))
    assert changes(replace) == [
        Change(code="base_added", params={
            "section": "B", "run": "side", "surface": "soil", "start_mm": 0,
            "end_mm": 3000}),
        Change(code="base_changed", params={
            "section": "B", "run": "side", "from_surface": "masonry_wall",
            "to_surface": "soil", "start_mm": 3000, "end_mm": 6000}),
    ]


def test_ground_at_a_corner_is_named_by_every_section_meeting_there():
    assert only(lambda p: setattr(p.topology.nodes[1], "z_mm", 250)) == Change(
        code="ground_changed", params={"section": "A/B", "run": "street/side",
                                       "from_mm": 0, "to_mm": 250})


def test_a_ground_point_along_a_section():
    assert only(lambda p: add_point_event(
        p.topology, "side", "z1", 2000, ElevationSamplePayload(z_mm=300))) == Change(
        code="ground_point_added",
        params={"section": "B", "run": "side", "value_mm": 300, "at_mm": 2000})


# -- gates and models ------------------------------------------------------------------


def test_a_gate_widened_moved_and_reswung():
    gate = lambda p: street(p).point_events[0]  # noqa: E731
    assert only(lambda p: setattr(gate(p).payload, "width_mm", 1200)) == Change(
        code="gate_changed",
        params={"section": "A", "run": "street", "from_mm": 1000, "to_mm": 1200,
                "at_mm": 4000})
    assert only(lambda p: setattr(gate(p), "anchor", make_anchor(
        p.topology, street(p), 5000))) == Change(
        code="gate_moved", params={"section": "A", "run": "street", "value_mm": 1000,
                                   "at_mm": 5000})
    # the width is the same and so is the place: still a change, not silence —
    # and not "width 1000 → 1000"
    assert only(lambda p: setattr(gate(p).payload, "opens_to", "left")) == Change(
        code="gate_details_changed", params={"section": "A", "run": "street"})


def test_a_gate_beside_the_fence_is_named_by_the_sections_it_joins():
    def add_span(p):
        p.topology.nodes.append(Node(id="n4", x_mm=10000, y_mm=0))
        p.topology.gates.append(GateSpan(id="g1", start_node_id="n2", end_node_id="n4"))
    assert only(add_span) == Change(code="gate_added", params={
        "section": "A/B", "run": "street/side", "value_mm": 1000})


def test_a_model_on_a_stretch_and_the_job_default():
    assert only(lambda p: add_interval_event(
        p.topology, "side", "m1", 0, 6000, FenceModelPayload(model_id="M-SLAT"))) == Change(
        code="model_added",
        params={"section": "B", "run": "side", "model": "M-SLAT", "start_mm": 0,
                "end_mm": 6000})
    assert only(lambda p: setattr(p, "fence_model",
                                  FenceModelChoice(model_id="M-SLAT"))) == Change(
        code="default_model_changed", params={"from_model": None, "to_model": "M-SLAT"})


# -- notes and claims ------------------------------------------------------------------


def test_a_note_is_quoted_with_the_section_it_is_on():
    assert only(lambda p: p.annotations.append(Annotation(
        id="a1", target_ref="run:side", text="level with the neighbour, ~1750"))) == Change(
        code="note_added",
        params={"text": "level with the neighbour, ~1750", "section": "B", "run": "side"})


def test_a_stated_claim():
    assert only(lambda p: setattr(p.stated, "no_gates", True)) == Change(
        code="stated_changed", params={"what": "no_gates", "value": True})


# -- nothing changes silently ----------------------------------------------------------


def test_a_kind_of_event_with_no_sentence_still_names_its_section():
    assert only(lambda p: add_interval_event(
        p.topology, "side", "tilt", 0, 6000, PostTiltPayload(mode="perpendicular"))) == \
        Change(code="section_changed", params={"section": "B", "run": "side"})


def test_an_unnamed_change_is_reported_beside_a_named_one():
    def both(p):
        add_interval_event(p.topology, "side", "tilt", 0, 6000,
                           PostTiltPayload(mode="perpendicular"))
        side(p).interval_events[1].payload.height_mm = 1750
    assert [c.code for c in changes(both)] == ["height_changed", "section_changed"]


def test_a_node_kind_alone_is_a_drawing_change():
    assert only(lambda p: setattr(p.topology.nodes[1], "kind", "terminal")) == Change(
        code="area_changed", params={"area": "drawing"})


def test_a_node_kind_changed_beside_a_named_change_is_still_said():
    """The area fallback covers a change made ALONE; this is the case it cannot."""
    def both(p):
        side(p).interval_events[1].payload.height_mm = 1750
        p.topology.nodes[1].kind = "terminal"
    assert [c.code for c in changes(both)] == ["height_changed", "area_changed"]


def test_a_loose_node_moved_beside_a_named_change_is_still_said():
    def both(p):
        side(p).interval_events[1].payload.height_mm = 1750
        p.topology.nodes.append(Node(id="loose", x_mm=20000, y_mm=0))
    assert [c.code for c in changes(both)] == ["height_changed", "area_changed"]


# -- the pairing rule, at its edges ------------------------------------------------


def test_one_height_replacing_two_reports_both_stretches():
    """What carving produces when a new height covers two older ones: each
    stretch that was built to a different height says so — never one change
    that silently swallows the second."""
    def two(p):
        run = side(p)
        old = next(e for e in run.interval_events if e.id == "h-side")
        old.end_anchor = make_anchor(p.topology, run, 3000)
        add_interval_event(p.topology, "side", "h-second", 3000, 6000,
                           HeightIntentPayload(height_mm=1750))
    before, after = edit(two)
    replaced = after.model_copy(deep=True)
    run = replaced.topology.run("side")
    run.interval_events = [e for e in run.interval_events
                           if e.payload.kind != "height_intent"]
    add_interval_event(replaced.topology, "side", "h-one", 0, 6000,
                       HeightIntentPayload(height_mm=1700))
    assert [(c.code, c.params["from_mm"], c.params["start_mm"])
            for c in diff_project(after, replaced)] == [
        ("height_changed", 1800, 0), ("height_changed", 1750, 3000)]


def test_a_wall_redrawn_elsewhere_reads_where_it_now_is_and_is_not():
    def rewall(p):
        run = side(p)
        run.interval_events = [e for e in run.interval_events if e.id != "wall"]
        add_interval_event(p.topology, "side", "wall2", 0, 3000,
                           BasePayload(surface="masonry_wall"))
    assert [(c.code, c.params["start_mm"]) for c in changes(rewall)] == [
        ("base_added", 0), ("base_removed", 3000)]


# -- every code the vocabulary has is reachable ----------------------------------------


def _drop(run: Run, event_id: str) -> None:
    run.interval_events = [e for e in run.interval_events if e.id != event_id]
    run.point_events = [e for e in run.point_events if e.id != event_id]


def _sample(p: Project) -> None:
    add_point_event(p.topology, "side", "z1", 2000, ElevationSamplePayload(z_mm=300))


def _model(p: Project) -> None:
    add_interval_event(p.topology, "side", "m1", 0, 6000, FenceModelPayload(model_id="M-SLAT"))


def _with(setup, then):
    """`then` applied to a job `setup` already changed — the before is `setup`'s."""
    before = levi()
    setup(before)
    after = before.model_copy(deep=True)
    then(after)
    return diff_project(before, after)


@pytest.mark.parametrize("setup, then, code", [
    (lambda p: None, lambda p: add_interval_event(
        p.topology, "street", "b1", 0, 9000, BasePayload(surface="concrete")), "base_added"),
    (lambda p: None, lambda p: _drop(side(p), "wall"), "base_removed"),
    (_model, lambda p: setattr(side(p).interval_events[-1].payload, "model_id", "M-V"),
     "model_changed"),
    (_model, lambda p: _drop(side(p), "m1"), "model_removed"),
    (_model, lambda p: setattr(side(p).interval_events[-1], "end_anchor",
                               make_anchor(p.topology, side(p), 3000)), "model_removed"),
    (_sample, lambda p: setattr(side(p).point_events[0].payload, "z_mm", 400),
     "ground_point_changed"),
    (_sample, lambda p: _drop(side(p), "z1"), "ground_point_removed"),
    (_sample, lambda p: setattr(side(p).point_events[0], "anchor",
                                make_anchor(p.topology, side(p), 2500)), "ground_point_moved"),
    (lambda p: None, lambda p: _drop(street(p), "gate"), "gate_removed"),
])
def test_every_kind_of_event_change_is_reachable(setup, then, code):
    assert [c.code for c in _with(setup, then)] == [code]


def test_a_gate_beside_the_fence_moved_without_changing_width():
    def span(p):
        p.topology.nodes.append(Node(id="n4", x_mm=10000, y_mm=0))
        p.topology.gates.append(GateSpan(id="g1", start_node_id="n2", end_node_id="n4"))

    def slide(p):
        n4 = p.topology.node("n4")
        n4.x_mm, n4.y_mm = 9000, 1000   # still 1000 from n2, turned 90°
    assert [c.code for c in _with(span, slide)] == ["gate_moved"]


def test_a_models_options_changed_alone_is_not_silent():
    def options(p):
        side(p).interval_events[-1].payload.options = {"colour": "anthracite"}
    assert [c.code for c in _with(_model, options)] == ["section_changed"]


# -- a letter is a position; the run id is the name ------------------------------------


def test_a_section_is_relettered_from_the_drawing_it_is_read_against():
    """Delete section A: the old "B" is drawn as A now, and its history must say so."""
    entry = [c.model_dump() for c in changes(
        lambda p: setattr(side(p).interval_events[1].payload, "height_mm", 1750))]
    assert entry[0]["params"]["section"] == "B"
    now = levi().topology
    now.runs = [r for r in now.runs if r.id != "street"]
    assert reletter(entry, now)[0]["params"]["section"] == "A"
    assert "section_gone" not in reletter(entry, now)[0]["params"]


def test_a_section_no_longer_drawn_keeps_its_letter_and_says_so():
    entry = [{"code": "height_changed", "params": {"section": "B", "run": "side"}},
             {"code": "section_removed", "params": {"section": "B", "run": "side"}},
             {"code": "address_changed", "params": {"from": "a", "to": "b"}}]
    now = levi().topology
    now.runs = [r for r in now.runs if r.id != "side"]
    out = reletter(entry, now)
    assert out[0]["params"] == {"section": "B", "run": "side", "section_gone": True}
    # a removal already says the section is gone
    assert out[1]["params"] == {"section": "B", "run": "side"}
    assert out[2] == entry[2]



@pytest.mark.parametrize("area, fn", [
    ("posts", lambda p: p.overrides.append(Override(
        id="o1", run_id="street", directive=PinPost(station_mm=2000)))),
    ("site", lambda p: setattr(p.site, "frost_depth_mm", 600)),
    ("policy", lambda p: p.policy.update({"default_height_mm": 1500})),
    ("choices", lambda p: p.choices.append(
        Selection(choice_set="bay_widths", scope="run:street", widths=[1500]))),
])
def test_an_area_with_no_sentence_is_named(area, fn):
    assert only(fn) == Change(code="area_changed", params={"area": area})


def test_every_field_of_a_job_belongs_to_exactly_one_area():
    """A field nobody placed would change on every save with nothing said."""
    placed = [f for fields in AREAS.values() for f in fields]
    assert sorted(placed) == sorted(Project.model_fields), (
        "a Project field is missing from changes.AREAS, or in it twice")


#: One edit per Project field. Kept beside the test below so a field added to
#: `Project` without an edit here fails `test_every_field_has_an_edit`.
FIELD_EDITS = {
    "id": lambda p: setattr(p, "id", "proj_other"),
    "name": lambda p: setattr(p, "name", "other"),
    "created_at": lambda p: setattr(p, "created_at", "2026-01-01"),
    "created_by": lambda p: setattr(p, "created_by", "u_other"),
    "job": lambda p: setattr(p, "job", None),
    "status": lambda p: setattr(p, "status", "planning"),
    "assignee": lambda p: setattr(p, "assignee", "u_yossi"),
    "submitted_at": lambda p: setattr(p, "submitted_at", "2026-10-11T18:05"),
    "closed_at": lambda p: setattr(p, "closed_at", "2026-10-12"),
    "committed_run_id": lambda p: setattr(p, "committed_run_id", "run_1"),
    "acknowledgements": lambda p: p.acknowledgements.append(Acknowledgement(
        kind="warnings_reviewed", anchor="r", by="user:u", at="t")),
    "context": lambda p: p.context.landmarks.clear(),
    "topology": lambda p: setattr(p.topology.nodes[2], "y_mm", -7000),
    "fence_model": lambda p: setattr(p, "fence_model", FenceModelChoice(model_id="M")),
    "annotations": lambda p: p.annotations.append(Annotation(
        id="a", target_ref="job", text="t")),
    "stated": lambda p: setattr(p.stated, "no_promises", True),
    "site": lambda p: setattr(p.site, "hvhz", True),
    "overrides": lambda p: p.overrides.append(Override(
        id="o", run_id="side", directive=PinPost(station_mm=100))),
    "choices": lambda p: p.choices.append(Selection(choice_set="c", scope="s")),
    "policy": lambda p: p.policy.update({"x": 1}),
}


def test_every_field_has_an_edit():
    assert sorted(FIELD_EDITS) == sorted(Project.model_fields)


@pytest.mark.parametrize("field", sorted(FIELD_EDITS))
def test_changing_any_field_is_never_silent(field):
    out = changes(FIELD_EDITS[field])
    assert out, f"changing {field} produced no change"
    assert {c.code for c in out} <= CHANGE_CODES
