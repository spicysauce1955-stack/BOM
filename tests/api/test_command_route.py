"""One door: `POST /api/projects/{id}/actions`.

It was the FIRST gated route in this app; every route is gated now. What is
still particular to this one is the CAPACITY check — may this account perform
this command on a job in this state — which is a different question from the
gate's "may this person reach the API at all".
"""

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


def _as(client, capacity: str, user_id: str | None = None) -> User:
    """Become somebody with this capacity. No password: identity comes from the
    provider now, and the row carries only what the account may DO."""
    uid = user_id or f"u_{capacity}"
    u = User(id=uid, name=uid, email=f"{uid}@example.com", capacity=capacity)
    state.store.save_user(u)
    client.cookies.set(DEV_COOKIE, u.email)
    return u


def _project(client) -> dict:
    return client.post("/api/projects", json={"name": "x"}).json()


def _act(client, project_id: str, kind: str, payload: dict | None = None, **kw):
    return client.post(f"/api/projects/{project_id}/actions",
                       json={"kind": kind, "payload": payload or {}, **kw})


def _a_waiting_job(client) -> dict:
    """Handed over by the salesperson, through the same door. Building the state
    with a command rather than by writing the field keeps this test honest about
    what the queue actually contains."""
    dana = _as(client, "sales", user_id="u_dana")
    p = _project(client)
    assert _act(client, p["id"], "submit_job").status_code == 200
    # Stop being Dana; every caller becomes somebody else before acting again.
    client.cookies.delete(DEV_COOKIE)
    assert dana
    return p


# --- the door -----------------------------------------------------------------

def test_performing_a_command_needs_an_identity(client, monkeypatch):
    """A command names who did it, and `system` is not somebody who may take a
    job. This used to be the ONE route that said so; the refusal now comes from
    the gate, before the route runs, and says `no_identity` rather than
    `not_signed_in`.

    A second client, because emptying `FENCEAI_DEV_USER` only takes effect when
    `lifespan` builds the provider — clearing cookies against a running one
    leaves the seeded admin answering.
    """
    p = _project(client)
    monkeypatch.setenv("FENCEAI_DEV_USER", "")
    with TestClient(app) as anon:
        anon.cookies.clear()
        r = _act(anon, p["id"], "claim_job")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "no_identity"


def test_a_refusal_is_typed_and_localisable(client):
    _as(client, "sales", user_id="u_dana")
    p = _project(client)
    r = _act(client, p["id"], "claim_job")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "command_not_permitted"


def test_a_job_in_the_wrong_state_refuses_with_the_state_it_is_in(client):
    _as(client, "backoffice", user_id="u_yossi")
    p = _project(client)          # still `drafting`
    r = _act(client, p["id"], "claim_job")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "command_wrong_state"
    assert r.json()["detail"]["params"]["status"] == "drafting"


def test_a_kind_nobody_registered_is_a_404_and_not_a_500(client):
    _as(client, "admin", user_id="u_admin")
    p = _project(client)
    r = _act(client, p["id"], "drop_all_tables")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "command_unknown"


def test_a_payload_that_does_not_type_check_reaches_the_client_as_a_400(client):
    """Not a 500. A `return_to_sales` with no reason is a caller's mistake, and
    the sentence has to be one a screen can render."""
    _as(client, "backoffice", user_id="u_yossi")
    p = _a_waiting_job_owned_by(client, "u_yossi")
    r = _act(client, p["id"], "return_to_sales", {})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "command_payload_invalid"


def _a_waiting_job_owned_by(client, user_id: str) -> dict:
    p = _a_waiting_job(client)
    _as(client, "backoffice", user_id=user_id)
    assert _act(client, p["id"], "claim_job").status_code == 200
    return p


# --- the effect ---------------------------------------------------------------

def test_taking_a_job_is_stored_and_not_merely_returned(client):
    p = _a_waiting_job(client)
    _as(client, "backoffice", user_id="u_yossi")
    body = _act(client, p["id"], "claim_job").json()
    assert body["status"] == "planning" and body["assignee"] == "u_yossi"
    stored = client.get(f"/api/projects/{p['id']}").json()
    assert stored["status"] == "planning" and stored["assignee"] == "u_yossi"


def test_the_reason_a_job_came_back_is_on_the_project_in_the_words_written(client):
    p = _a_waiting_job_owned_by(client, "u_yossi")
    body = _act(client, p["id"], "return_to_sales",
                {"reason": "is the wall 600 or 900?"}).json()
    assert body["status"] == "returned" and body["assignee"] is None
    assert body["annotations"][-1]["text"] == "is the wall 600 or 900?"
    assert body["annotations"][-1]["author"] == "user:u_yossi"


def test_a_desk_command_does_not_bump_the_topology_revision(client):
    """Whose desk a job is on changes no quantity. A bump here would 409 the
    structure sheet because somebody picked the job up."""
    p = _a_waiting_job(client)
    before = client.get(f"/api/projects/{p['id']}").json()["topology"]["revision"]
    _as(client, "backoffice", user_id="u_yossi")
    after = _act(client, p["id"], "claim_job").json()["topology"]["revision"]
    assert after == before


# --- what the log says --------------------------------------------------------

def test_performing_a_command_writes_one_activity_row_naming_the_session(client):
    p = _a_waiting_job(client)
    _as(client, "backoffice", user_id="u_yossi")
    _act(client, p["id"], "claim_job")
    rows = [e for e in state.store.audit_entries(50) if e["action"] == "command:claim_job"]
    assert len(rows) == 1
    assert rows[0]["actor"] == "user:u_yossi"
    assert rows[0]["ref"].startswith(p["id"])


def test_who_proposed_it_and_who_performed_it_stay_two_different_facts(client):
    """"Yossi accepted the agent's suggestion" and "Yossi decided this himself"
    must not be the same row. `actor` is always the session; `origin` is who
    put the idea there."""
    p = _a_waiting_job(client)
    _as(client, "backoffice", user_id="u_yossi")
    _act(client, p["id"], "claim_job", origin="agent:ranker")
    row = next(e for e in state.store.audit_entries(50)
               if e["action"] == "command:claim_job")
    assert row["actor"] == "user:u_yossi"
    assert "agent:ranker" in row["ref"]


def test_a_refused_command_writes_no_row_at_all(client):
    """A refusal is not an event in the job's history. A log that recorded every
    attempt would make "who did what" a list of things nobody did."""
    _as(client, "sales", user_id="u_dana")
    p = _project(client)
    _act(client, p["id"], "claim_job")
    assert not [e for e in state.store.audit_entries(50)
                if e["action"].startswith("command:")]
