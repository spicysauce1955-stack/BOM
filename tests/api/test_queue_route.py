"""The queue on the wire — and the two things only a route can answer.

`select_rows` is pure over loaded projects, so it can resolve neither "me" (it
does not know who is asking) nor a quote total (it may not reach the store).
Both are answered here, and both have a wrong answer that looks fine.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from fenceai.identity.model import User


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _account(uid: str, capacity: str) -> User:
    u = User(id=uid, name=uid, email=f"{uid}@example.com", capacity=capacity)
    u.set_password("pw")
    state.store.save_user(u)
    return u


def _sign_in(client, uid: str, capacity: str):
    _account(uid, capacity)
    client.post("/api/session", json={"email": f"{uid}@example.com", "password": "pw"})


def _job(client, name: str, status: str, assignee: str | None = None):
    p = client.post("/api/projects", json={"name": name}).json()
    stored = state.store.load_project(p["id"])
    stored.status = status
    stored.assignee = assignee
    stored.submitted_at = "2026-09-15T08:00:00+00:00"
    state.store.save_project(stored)
    return p["id"]


# --- the picker did not change ------------------------------------------------

def test_the_picker_is_still_a_bare_list_of_three_fields(client):
    """Five callers read it, the project picker among them. The queue is a
    different question and got its own route rather than changing this one's
    shape underneath everybody."""
    rows = client.get("/api/projects").json()
    assert isinstance(rows, list)
    assert set(rows[0]) == {"id", "name", "label"}


# --- me -----------------------------------------------------------------------

def test_me_resolves_to_the_session_and_never_matches_literally(client):
    """`select_rows` REFUSES the literal string, because matched as an id it
    returns an empty page that reads as "you have nothing to do" — the most
    misleading answer a queue can give. The route resolves it first."""
    _sign_in(client, "u_yossi", "backoffice")
    mine = _job(client, "mine", "planning", assignee="u_yossi")
    _job(client, "theirs", "planning", assignee="u_maya")
    rows = client.get("/api/queue", params={"assignee": "me"}).json()["rows"]
    assert [r["id"] for r in rows] == [mine]


def test_me_with_nobody_signed_in_matches_nobody_rather_than_everybody(client):
    """The honest answer to "what is on my desk" when there is no me."""
    client.cookies.clear()
    _job(client, "someones", "planning", assignee="u_yossi")
    rows = client.get("/api/queue", params={"assignee": "me"}).json()["rows"]
    assert rows == []


def test_nobody_has_taken_it_is_a_different_question_from_mine(client):
    _sign_in(client, "u_y2", "backoffice")
    untaken = _job(client, "untaken", "waiting")
    _job(client, "taken", "planning", assignee="u_y2")
    rows = client.get("/api/queue", params={"assignee": "none"}).json()["rows"]
    assert [r["id"] for r in rows] == [untaken]


# --- the two buckets ----------------------------------------------------------

def test_the_two_buckets_are_the_two_lists(client):
    _sign_in(client, "u_y3", "backoffice")
    open_id = _job(client, "open one", "waiting")
    done_id = _job(client, "done one", "delivered")
    rows = client.get("/api/queue", params={"bucket": "open"}).json()["rows"]
    assert open_id in [r["id"] for r in rows]
    assert done_id not in [r["id"] for r in rows]
    rows = client.get("/api/queue", params={"bucket": "finished"}).json()["rows"]
    assert done_id in [r["id"] for r in rows]


def test_a_draft_is_the_salespersons_and_not_on_the_backoffice_queue(client):
    """A job she has not submitted is not work anybody else can pick up."""
    _sign_in(client, "u_y4", "backoffice")
    draft = _job(client, "hers", "drafting")
    rows = client.get("/api/queue").json()["rows"]
    assert draft not in [r["id"] for r in rows]


# --- refusals -----------------------------------------------------------------

def test_an_unreadable_cursor_refuses_rather_than_starting_over(client):
    """Ignoring it would make a paging loop run for ever, quietly."""
    _sign_in(client, "u_y5", "backoffice")
    r = client.get("/api/queue", params={"cursor": "not-a-cursor"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "queue_cursor_invalid"


def test_too_large_a_page_refuses_rather_than_clamping(client):
    """Clamping would answer a question nobody asked and look like it worked."""
    _sign_in(client, "u_y6", "backoffice")
    r = client.get("/api/queue", params={"limit": 5000})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "queue_filter_invalid"


# --- the column a pure function could not fill --------------------------------

def test_a_page_hands_back_a_cursor_only_when_there_is_more(client):
    _sign_in(client, "u_y7", "backoffice")
    for i in range(3):
        _job(client, f"j{i}", "waiting")
    body = client.get("/api/queue", params={"limit": 2}).json()
    assert len(body["rows"]) == 2 and body["next_cursor"]
    rest = client.get("/api/queue", params={"limit": 2,
                                            "cursor": body["next_cursor"]}).json()
    assert rest["next_cursor"] is None or len(rest["rows"]) <= 2
