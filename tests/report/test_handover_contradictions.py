"""A stated fact can be wrong, and then it is a question the office asks."""

from __future__ import annotations

from fenceai.project.model import Annotation, Project, Stated
from fenceai.report.handover import HANDOVER_CODES, handover_gaps
from fenceai.topology.model import GatePayload, Node, PointEvent, Run, Topology
from fenceai.topology.station import make_anchor


def _drawn() -> Topology:
    """A one-run fence, so `no_fence_drawn` does not short-circuit the list."""
    return Topology(
        revision=0,
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=8000, y_mm=0)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2")],
    )


def _with_gate() -> Topology:
    """A gate is a `PointEvent` whose payload kind is `"gate"`.

    `PointEvent` carries an `Anchor`, never a bare station — anchors are
    segment-local so an event re-anchors proportionally when geometry is
    edited (ADR-0003). Author it with `make_anchor`, exactly as the frontend
    authors with `geom.anchorFor`; never hand-build the three fields.
    """
    topo = _drawn()
    run = topo.runs[0]
    run.point_events = [
        PointEvent(id="pe1", anchor=make_anchor(topo, run, 4000),
                   payload=GatePayload(width_mm=1000))
    ]
    return topo


def _codes(project: Project) -> list[str]:
    return [g.code for g in handover_gaps(project)]


def test_both_codes_are_registered():
    assert "gates_contradicted" in HANDOVER_CODES
    assert "promises_contradicted" in HANDOVER_CODES


def test_no_gates_with_no_gate_is_not_contradicted():
    p = Project(id="p", name="x", topology=_drawn(), stated=Stated(no_gates=True))
    assert "gates_contradicted" not in _codes(p)


def test_no_gates_with_a_gate_on_the_drawing_is_contradicted():
    p = Project(id="p", name="x", topology=_with_gate(),
                stated=Stated(no_gates=True))
    assert "gates_contradicted" in _codes(p)


def test_a_gate_without_the_claim_is_just_a_gate():
    """The check is about the CLAIM, not about gates. A job with gates and no
    claim has nothing to report."""
    p = Project(id="p", name="x", topology=_with_gate())
    assert "gates_contradicted" not in _codes(p)


def test_no_promises_with_an_annotation_is_contradicted():
    p = Project(id="p", name="x", topology=_drawn(),
                annotations=[Annotation(id="a1", target_ref="project",
                                        text="leave the gate clear")],
                stated=Stated(no_promises=True))
    assert "promises_contradicted" in _codes(p)


def test_no_promises_with_no_annotation_is_not_contradicted():
    p = Project(id="p", name="x", topology=_drawn(),
                stated=Stated(no_promises=True))
    assert "promises_contradicted" not in _codes(p)


def test_neither_code_blocks_the_estimate():
    """A contradicted claim is a question, not a reason to withhold a price.
    `blocking` is narrow on purpose — it gates the estimate."""
    p = Project(id="p", name="x", topology=_with_gate(),
                stated=Stated(no_gates=True))
    contradiction = next(g for g in handover_gaps(p)
                         if g.code == "gates_contradicted")
    assert contradiction.blocking is False


def test_an_undrawn_job_reports_only_that():
    """`no_fence_drawn` is returned ALONE. A contradiction on a blank project
    would be a second item under "you have not drawn anything"."""
    p = Project(id="p", name="x", stated=Stated(no_gates=True))
    assert _codes(p) == ["no_fence_drawn"]
