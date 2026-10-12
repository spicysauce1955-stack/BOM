"""`GET /api/projects/{id}/changes` — a job's history, with names.

The owner's example end to end through the real routes: Dana sells 1800 on the
side section and hands the job over; Yossi takes it and replaces the height
with 1750. The history says so, in that order, under their names.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.model import User
from fenceai.topology.model import HeightIntentPayload, Node, Run, Topology
from tests.conftest import add_interval_event


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _as(client, user_id: str, name: str, capacity: str) -> None:
    user = User(id=user_id, name=name, email=f"{user_id}@example.com", capacity=capacity)
    state.store.save_user(user)
    client.cookies.set(DEV_COOKIE, user.email)


def _side(height_mm: int, event_id: str) -> dict:
    topo = Topology(nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=6000, y_mm=0)],
                    runs=[Run(id="side", start_node_id="n1", end_node_id="n2")])
    add_interval_event(topo, "side", event_id, 0, 6000, HeightIntentPayload(height_mm=height_mm))
    return topo.model_dump(mode="json")


def _history(client, project_id: str) -> dict:
    r = client.get(f"/api/projects/{project_id}/changes")
    assert r.status_code == 200, r.text
    return r.json()


def test_the_office_replacing_a_sold_height_is_in_the_history_under_its_name(client):
    _as(client, "u_dana", "Dana", "sales")
    pid = client.post("/api/projects", json={"name": "Levi"}).json()["id"]
    assert client.put(f"/api/projects/{pid}/topology", json=_side(1800, "h-dana")).status_code == 200
    assert client.post(f"/api/projects/{pid}/actions",
                       json={"kind": "submit_job", "payload": {}}).status_code == 200

    _as(client, "u_yossi", "Yossi", "backoffice")
    assert client.post(f"/api/projects/{pid}/actions",
                       json={"kind": "claim_job", "payload": {}}).status_code == 200
    assert client.put(f"/api/projects/{pid}/topology", json=_side(1750, "h-yossi")).status_code == 200

    history = _history(client, pid)
    entries = history["entries"]
    codes = [[c["code"] for c in e["changes"]] for e in entries]
    assert codes == [
        ["height_changed"],
        ["status_changed", "assignee_changed"],
        ["status_changed"],
        ["section_added"],
        ["job_created"],
    ]
    assert [e["actor"] for e in entries] == [
        "user:u_yossi", "user:u_yossi", "user:u_dana", "user:u_dana", "user:u_dana"]
    assert entries[0]["changes"][0]["params"] == {
        "section": "A", "run": "side", "from_mm": 1800, "to_mm": 1750,
        "start_mm": 0, "end_mm": 6000}
    assert entries[2]["changes"][0]["params"] == {
        "from_state": "drafting", "to_state": "waiting"}
    # actors by ref, and the person a change is ABOUT by bare id
    assert history["names"] == {"user:u_yossi": "Yossi", "user:u_dana": "Dana",
                                "u_yossi": "Yossi"}


def test_a_section_is_named_by_the_drawing_as_it_is_now(client):
    """Delete the first section and the second is drawn as A. Its history,
    written when it was B, must read A — or, for a section no longer drawn, keep
    its letter and say it is gone."""
    _as(client, "u_dana", "Dana", "sales")
    pid = client.post("/api/projects", json={"name": "Levi"}).json()["id"]
    topo = Topology(nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=9000, y_mm=0),
                           Node(id="n3", x_mm=9000, y_mm=6000)],
                    runs=[Run(id="street", start_node_id="n1", end_node_id="n2"),
                          Run(id="side", start_node_id="n2", end_node_id="n3")])
    add_interval_event(topo, "side", "h", 0, 6000, HeightIntentPayload(height_mm=1800))
    client.put(f"/api/projects/{pid}/topology", json=topo.model_dump(mode="json"))
    topo.run("side").interval_events[0].payload.height_mm = 1750
    client.put(f"/api/projects/{pid}/topology", json=topo.model_dump(mode="json"))
    assert _history(client, pid)["entries"][0]["changes"][0]["params"]["section"] == "B"

    topo.runs = [r for r in topo.runs if r.id != "street"]
    topo.nodes = [n for n in topo.nodes if n.id != "n1"]
    client.put(f"/api/projects/{pid}/topology", json=topo.model_dump(mode="json"))
    entries = _history(client, pid)["entries"]
    assert entries[0]["changes"][0]["code"] == "section_removed"
    height = entries[1]["changes"][0]
    assert height["code"] == "height_changed"
    assert height["params"]["section"] == "A"
    assert "section_gone" not in height["params"]


def test_both_people_in_a_reassignment_are_named(client):
    _as(client, "u_dana", "Dana", "sales")
    pid = client.post("/api/projects", json={"name": "Levi"}).json()["id"]
    client.post(f"/api/projects/{pid}/actions", json={"kind": "submit_job", "payload": {}})
    _as(client, "u_avi", "Avi", "backoffice")
    _as(client, "u_yossi", "Yossi", "backoffice")
    client.post(f"/api/projects/{pid}/actions", json={"kind": "claim_job", "payload": {}})
    r = client.post(f"/api/projects/{pid}/actions",
                    json={"kind": "assign_job", "payload": {"user_id": "u_avi"}})
    assert r.status_code == 200, r.text
    history = _history(client, pid)
    assert history["entries"][0]["changes"] == [{"code": "assignee_changed", "params": {
        "from_person": "u_yossi", "to_person": "u_avi"}}]
    assert history["names"]["u_yossi"] == "Yossi"
    assert history["names"]["u_avi"] == "Avi"


def test_a_job_that_does_not_exist_is_a_404_not_an_empty_history(client):
    _as(client, "u_dana", "Dana", "sales")
    assert client.get("/api/projects/proj_nope/changes").status_code == 404


def test_the_limit_is_honoured(client):
    _as(client, "u_dana", "Dana", "sales")
    pid = client.post("/api/projects", json={"name": "v0"}).json()["id"]
    for n in range(1, 4):
        client.put(f"/api/projects/{pid}/job", json={"customer": f"c{n}"})
    r = client.get(f"/api/projects/{pid}/changes", params={"limit": 2})
    assert [e["changes"][0]["params"]["to"] for e in r.json()["entries"]] == ["c3", "c2"]
