"""The advice route. It reads; it changes nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app

# 5000mm against the demo knowledge's `max_span_mm = 1800` (tests/strategy/
# test_choice_generation.py) leaves `bay_layout` with more than one admissible
# answer — an equal split and a fewest-posts alternative — so a run generated
# over it is exactly the "open question" case this route exists to answer.
_LENGTH_MM = 5000


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project_id(client) -> str:
    return client.post("/api/projects", json={"name": "advice"}).json()["id"]


def _put_topology(client, project_id: str) -> None:
    r = client.put(f"/api/projects/{project_id}/topology", json={
        "revision": 1,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": _LENGTH_MM, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    assert r.status_code == 200, r.text


@pytest.fixture()
def seeded_run(client, project_id) -> str:
    _put_topology(client, project_id)
    gen = client.post(f"/api/projects/{project_id}/generate")
    assert gen.status_code == 200, gen.text
    return gen.json()["result"]["run"]["id"]


@pytest.fixture()
def moved_topology(client, project_id, seeded_run) -> None:
    """Bumps the project's topology revision past the one the run was
    generated from, by PUTting it again — `PUT` always assigns
    `project.topology.revision + 1` (`app.py`'s `put_topology`), so a second
    PUT after `seeded_run` already moves it."""
    _put_topology(client, project_id)


def test_advice_on_a_run_with_an_open_question(client, seeded_run):
    r = client.get(f"/api/runs/{seeded_run}/advice")
    assert r.status_code == 200
    body = r.json()
    assert body["evaluated"] is True
    assert body["task_id"] == "rank_choice_set"
    for proposal in body["proposals"]:
        assert proposal["source_class"] == "ai_proposal"
        assert proposal["claims"], "a proposal with no rationale is not a proposal"


def test_advice_never_mutates_the_project(client, seeded_run, project_id):
    before = client.get(f"/api/projects/{project_id}").json()
    client.get(f"/api/runs/{seeded_run}/advice")
    assert client.get(f"/api/projects/{project_id}").json() == before


def test_advice_is_the_same_on_two_calls(client, seeded_run):
    a = client.get(f"/api/runs/{seeded_run}/advice").json()
    b = client.get(f"/api/runs/{seeded_run}/advice").json()
    assert [p["id"] for p in a["proposals"]] == [p["id"] for p in b["proposals"]]


def test_advice_refuses_a_run_whose_topology_moved(client, seeded_run, moved_topology):
    r = client.get(f"/api/runs/{seeded_run}/advice")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "topology_changed"
