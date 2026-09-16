"""`GET /api/projects/{id}/sections` — what each stretch is, with no run.

The route the office job screen opens on. Its defining property is the one it
does NOT have: it cannot go stale, because it reads the topology itself. Every
other per-stretch view in this app is a view over a stored run and refuses with
409 when the drawing moves underneath it; this one answers the new drawing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _project(client, topology: dict) -> str:
    pid = client.post("/api/projects", json={"name": "bob"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/topology", json=topology)
    assert r.status_code == 200, r.text
    return pid


def _three_runs(revision: int = 0) -> dict:
    return {
        "revision": revision,
        "nodes": [
            {"id": "n1", "x_mm": 0, "y_mm": 0},
            {"id": "n2", "x_mm": 8000, "y_mm": 0},
            {"id": "n3", "x_mm": 8000, "y_mm": -12000},
            {"id": "n4", "x_mm": 16000, "y_mm": -12000},
        ],
        "runs": [
            {"id": "r1", "start_node_id": "n1", "end_node_id": "n2"},
            {"id": "r2", "start_node_id": "n2", "end_node_id": "n3"},
            {"id": "r3", "start_node_id": "n3", "end_node_id": "n4"},
        ],
    }


def test_one_entry_per_run_lettered_in_drawing_order(client):
    pid = _project(client, _three_runs())
    body = client.get(f"/api/projects/{pid}/sections").json()
    assert [s["tag"] for s in body["sections"]] == ["A", "B", "C"]
    assert [s["run_id"] for s in body["sections"]] == ["r1", "r2", "r3"]
    assert [s["length_mm"] for s in body["sections"]] == [8000, 12000, 8000]


def test_an_unknown_project_is_a_404(client):
    assert client.get("/api/projects/proj_nope/sections").status_code == 404


def test_it_answers_the_new_drawing_rather_than_refusing_as_stale(client):
    """The one route on this screen that CANNOT be stale.

    `/structure` and `/sections/{run}/decisions` both 409 `topology_changed`,
    and rightly: they describe a stored run that was generated from a drawing
    that has since moved. This describes the drawing, so when the drawing moves
    it has a new answer, not a refusal.
    """
    pid = _project(client, _three_runs())
    before = client.get(f"/api/projects/{pid}/sections").json()["sections"]
    assert before[0]["length_mm"] == 8000

    moved = _three_runs(revision=1)
    moved["nodes"][1]["x_mm"] = 9000
    assert client.put(f"/api/projects/{pid}/topology", json=moved).status_code == 200

    r = client.get(f"/api/projects/{pid}/sections")
    assert r.status_code == 200, "a moved drawing is a new answer, never a 409"
    assert r.json()["sections"][0]["length_mm"] == 9000


def test_a_job_with_nothing_drawn_answers_an_empty_list(client):
    """Not a 404 and not an error: a job nobody has drawn yet is a real state,
    and the screen renders it."""
    pid = client.post("/api/projects", json={"name": "empty"}).json()["id"]
    r = client.get(f"/api/projects/{pid}/sections")
    assert r.status_code == 200
    assert r.json() == {"sections": []}


def test_a_stretch_with_no_base_event_reports_the_silent_default(client):
    """The route carries the read model's honesty through to the wire."""
    pid = _project(client, _three_runs())
    body = client.get(f"/api/projects/{pid}/sections").json()
    assert all(s["base_surface"] == "soil" for s in body["sections"])
    assert all(s["height_intent_mm"] is None for s in body["sections"])
    assert all(s["height_covered_mm"] == 0 for s in body["sections"])
