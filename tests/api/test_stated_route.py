"""Stating a fact is a project edit, and it revises nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project_id(client) -> str:
    return client.post("/api/projects", json={"name": "demo"}).json()["id"]


def test_stating_no_gates_persists(client, project_id):
    r = client.put(f"/api/projects/{project_id}/stated",
                   json={"no_gates": True, "no_promises": False})
    assert r.status_code == 200
    assert r.json()["stated"]["no_gates"] is True

    again = client.get(f"/api/projects/{project_id}").json()
    assert again["stated"]["no_gates"] is True


def test_stating_a_fact_does_not_bump_the_topology_revision(client, project_id):
    """Unrevisioned on purpose. A bump here would 409 the structure sheet
    because somebody said there are no gates."""
    before = client.get(f"/api/projects/{project_id}").json()["topology"]["revision"]
    client.put(f"/api/projects/{project_id}/stated", json={"no_gates": True})
    after = client.get(f"/api/projects/{project_id}").json()["topology"]["revision"]
    assert after == before


def test_a_fact_can_be_withdrawn(client, project_id):
    client.put(f"/api/projects/{project_id}/stated", json={"no_gates": True})
    client.put(f"/api/projects/{project_id}/stated", json={"no_gates": False})
    assert client.get(f"/api/projects/{project_id}").json()["stated"]["no_gates"] is False


def test_an_unknown_project_is_a_404(client):
    assert client.put("/api/projects/proj_nope/stated",
                      json={"no_gates": True}).status_code == 404
