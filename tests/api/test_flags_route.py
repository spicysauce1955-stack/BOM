"""`GET /api/projects/{id}/flags` — every problem on a job, placed.

The screen's second route. Its defining property, like `/sections`, is a
refusal it does NOT make: flags are how somebody finds out that the drawing
moved, so refusing to list them because the drawing moved is the wrong way
round.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _topology(revision: int = 0, length_mm: int = 8000) -> dict:
    return {
        "revision": revision,
        "nodes": [
            {"id": "n1", "x_mm": 0, "y_mm": 0},
            {"id": "n2", "x_mm": length_mm, "y_mm": 0},
        ],
        "runs": [{"id": "r1", "start_node_id": "n1", "end_node_id": "n2"}],
    }


def _drawn(client, revision: int = 0, length_mm: int = 8000) -> str:
    pid = client.post("/api/projects", json={"name": "bob"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/topology",
                   json=_topology(revision, length_mm))
    assert r.status_code == 200, r.text
    return pid


def _codes(body: dict) -> set[str]:
    return {f["code"] for f in body["flags"]}


def test_with_no_run_it_answers_handover_flags_and_says_there_is_no_run(client):
    """A normal 200, not an error and not an empty list.

    Before generation there are no posts, no bays and no warnings — but there
    is plenty wrong with a job nobody measured, and that is exactly what the
    office opens the screen to see.
    """
    pid = _drawn(client)
    body = client.get(f"/api/projects/{pid}/flags").json()
    assert body["run_id"] == ""
    assert _codes(body), "a job with a drawing and no height has findings"
    assert all(f["source"] != "strategy" for f in body["flags"])


def test_after_generating_it_carries_the_runs_own_warnings_too(client):
    pid = _drawn(client)
    assert client.post(f"/api/projects/{pid}/generate").status_code == 200
    body = client.get(f"/api/projects/{pid}/flags").json()
    assert body["run_id"], "the answer names the run it read"
    assert any(f["source"] == "strategy" for f in body["flags"]) or \
        any(f["source"] == "readiness" for f in body["flags"]), \
        "a generated job has run-scoped findings of some kind"


def test_every_flag_carries_at_least_one_place(client):
    """The whole point of the model: a finding with nowhere to go is a finding
    somebody scrolls past."""
    pid = _drawn(client)
    client.post(f"/api/projects/{pid}/generate")
    body = client.get(f"/api/projects/{pid}/flags").json()
    assert body["flags"]
    for flag in body["flags"]:
        assert flag["places"], f"{flag['code']} has nowhere to be drawn"


def test_a_run_from_another_job_is_refused_rather_than_answered(client):
    mine = _drawn(client)
    theirs = _drawn(client)
    client.post(f"/api/projects/{theirs}/generate")
    other_run = client.get(f"/api/projects/{theirs}/runs").json()[-1]["id"]

    r = client.get(f"/api/projects/{mine}/flags", params={"run_id": other_run})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "run_not_on_this_job"


def test_a_moved_drawing_is_still_answered(client):
    """Flags are how you find out something moved.

    `/structure` refuses a stale run with 409 `topology_changed` and is right
    to — it describes a fence laid out against a drawing that has changed. This
    route is the screen that TELLS somebody that happened, so refusing here
    would hide the answer behind the problem it is reporting.
    """
    pid = _drawn(client)
    client.post(f"/api/projects/{pid}/generate")
    assert client.put(f"/api/projects/{pid}/topology",
                      json=_topology(revision=1, length_mm=9000)).status_code == 200

    r = client.get(f"/api/projects/{pid}/flags")
    assert r.status_code == 200
    assert r.json()["flags"]


def test_an_unknown_project_is_a_404(client):
    assert client.get("/api/projects/proj_nope/flags").status_code == 404
