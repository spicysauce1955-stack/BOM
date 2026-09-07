"""`Stated` — what the salesperson says this job does NOT have."""

from __future__ import annotations

from fenceai.project.model import Project, Stated


def test_a_new_project_states_nothing():
    """Absence of a claim is not a claim. Every project that exists today has
    no `stated` on it and none of them may break."""
    p = Project(id="proj_1", name="x")
    assert p.stated == Stated()
    assert p.stated.no_gates is False
    assert p.stated.no_promises is False


def test_a_project_round_trips_a_stated_fact():
    p = Project(id="proj_1", name="x", stated=Stated(no_gates=True))
    back = Project.model_validate_json(p.model_dump_json())
    assert back.stated.no_gates is True
    assert back.stated.no_promises is False


def test_stating_a_fact_does_not_touch_the_topology_revision():
    """The whole reason `stated` sits beside `job` rather than in `Topology`:
    a claim about what is absent changes no quantity, so it must not make a
    derived view stale."""
    p = Project(id="proj_1", name="x")
    before = p.topology.revision
    p.stated.no_gates = True
    assert p.topology.revision == before


def test_an_old_document_with_no_stated_key_still_loads():
    """Forward compatibility in the direction that actually happens: the
    projects already in the database were written before this field."""
    p = Project.model_validate_json('{"id": "proj_1", "name": "x"}')
    assert p.stated == Stated()
