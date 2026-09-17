"""`GET /api/my-jobs` and the two facts only routes can write: who created a
job (from the resolved identity, never the body) and who wrote a note."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.model import User


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _as(client, uid: str, capacity: str):
    """Become this person. No password: the identity comes from the provider,
    and the row carries only what the account may DO."""
    u = User(id=uid, name=uid, email=f"{uid}@example.com", capacity=capacity)
    state.store.save_user(u)
    client.cookies.set(DEV_COOKIE, u.email)


def test_nobody_is_refused_rather_than_shown_an_empty_list(monkeypatch):
    """"My" has no answer for a caller nobody can name, and an empty list would
    read as "you have no jobs". The refusal is the gate's now, one layer earlier
    than the route's own `not_signed_in` used to be.

    Its own client: `FENCEAI_DEV_USER` is read when `lifespan` builds the
    provider, so clearing cookies on a running one still leaves the seeded admin
    answering."""
    monkeypatch.setenv("FENCEAI_DEV_USER", "")
    with TestClient(app) as anon:
        anon.cookies.clear()
        r = anon.get("/api/my-jobs")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "no_identity"


def test_a_job_lands_on_the_list_of_whoever_created_it(client):
    _as(client, "u_sales_a", "sales")
    mine = client.post("/api/projects", json={"name": "mine"}).json()
    assert state.store.load_project(mine["id"]).created_by == "u_sales_a"
    _as(client, "u_sales_b", "sales")
    theirs = client.post("/api/projects", json={"name": "theirs"}).json()

    ids = [r["id"] for r in client.get("/api/my-jobs").json()["rows"]]
    assert theirs["id"] in ids and mine["id"] not in ids


def test_a_note_the_office_writes_reaches_her_list(client):
    _as(client, "u_sales_c", "sales")
    pid = client.post("/api/projects", json={"name": "job"}).json()["id"]
    own = client.post(f"/api/projects/{pid}/annotations",
                      json={"target_ref": "run:r1", "text": "mine", "author": "forged"}).json()
    # the resolved identity outranks the body, and the time is stamped
    assert own["author"] == "user:u_sales_c" and own["created_at"]

    _as(client, "u_office_c", "backoffice")
    client.post(f"/api/projects/{pid}/annotations",
                json={"target_ref": "landmark:lm1", "text": "Which side is the street?"})

    _as(client, "u_sales_c", "sales")
    row = next(r for r in client.get("/api/my-jobs").json()["rows"] if r["id"] == pid)
    assert row["office_notes"] == 1
    assert row["office_latest"] == "Which side is the street?"
    assert row["sales_status"] == "draft"


def test_the_creator_comes_from_the_identity_and_never_from_the_body(client):
    """A creator a client could name would put jobs on somebody else's list."""
    _as(client, "u_sales_d", "sales")
    pid = client.post("/api/projects", json={"name": "x", "created_by": "u_victim"}).json()["id"]
    assert state.store.load_project(pid).created_by == "u_sales_d"
    _as(client, "u_victim", "sales")
    assert pid not in [r["id"] for r in client.get("/api/my-jobs").json()["rows"]]
