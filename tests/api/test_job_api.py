"""Creating and editing the job identity over the API (slice 1).

Two routes, and the second is the one that matters. A salesperson enters this
after the visit from paper notes: they will start a job with a customer name,
draw for twenty minutes, and only then find the address on the sketch. A create
form that was the ONLY way to set this would make them delete the drawing and
start again.

`name` is left alone deliberately. It is what the project picker, 59 routes and
the whole existing suite key on, so a job that also has a customer DISPLAYS as
the customer rather than renaming the underlying field.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client():
    # Context-managed, so the lifespan runs and `state.store` exists — the
    # module-level `TestClient(app)` other suites avoid for the same reason.
    with TestClient(app) as c:
        yield c


def _new(client, **job) -> dict:
    body = {"name": "untitled"}
    if job:
        body["job"] = job
    r = client.post("/api/projects", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_project_can_still_be_created_with_only_a_name(client):
    """Every existing caller — the demo project the app creates on first boot,
    the smoke suite, 2400 tests — posts exactly this."""
    p = _new(client)
    assert p["job"] is None
    assert p["name"] == "untitled"


def test_a_job_can_be_named_at_creation(client):
    p = _new(client, customer="Dana Levy", address="Herzl 12", sold_by="bob",
             sold_on="2026-09-04")
    assert p["job"]["customer"] == "Dana Levy"
    assert p["job"]["sold_on"] == "2026-09-04"


def test_the_job_can_be_completed_afterwards_without_losing_the_drawing(client):
    """The route that matters. The address turns up on the sketch after twenty
    minutes of drawing, and finding it must not cost the drawing."""
    p = _new(client, customer="Dana Levy")
    client.put(f"/api/projects/{p['id']}/topology", json={
        "revision": 0,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 5000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    r = client.put(f"/api/projects/{p['id']}/job",
                   json={"customer": "Dana Levy", "address": "Herzl 12",
                         "sold_by": "bob", "sold_on": "2026-09-04"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["job"]["address"] == "Herzl 12"
    assert len(out["topology"]["runs"]) == 1, "the drawing survived"


def test_a_bad_date_is_refused_at_the_boundary_and_changes_nothing(client):
    """422 rather than a stored "yesterday" that fails on the handover sheet
    three screens later — and the project is left exactly as it was."""
    p = _new(client, customer="Dana Levy")
    r = client.put(f"/api/projects/{p['id']}/job",
                   json={"customer": "Dana Levy", "sold_on": "yesterday"})
    assert r.status_code == 422
    after = client.get(f"/api/projects/{p['id']}").json()
    assert after["job"]["customer"] == "Dana Levy"
    assert after["job"]["sold_on"] == ""


def test_the_listing_shows_what_a_person_would_call_the_job(client):
    """The picker said "project 7". It is the first thing a salesperson sees and
    the last thing that told them anything."""
    p = _new(client, customer="Dana Levy", address="Herzl 12")
    row = next(r for r in client.get("/api/projects").json() if r["id"] == p["id"])
    assert row["label"] == "Dana Levy — Herzl 12"
    # `name` stays on the row: the picker is not the only caller, and something
    # that keyed on it must not start reading a customer's name instead.
    assert row["name"] == "untitled"


def test_a_project_with_no_job_still_lists_under_its_name(client):
    p = _new(client)
    row = next(r for r in client.get("/api/projects").json() if r["id"] == p["id"])
    assert row["label"] == "untitled"
