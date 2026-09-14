"""Signing in, and what the log says afterwards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from fenceai.identity.model import User


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _account(email: str, capacity: str, password: str = "pw", **kw) -> User:
    u = User(id=kw.pop("id", email.split("@")[0]), name=kw.pop("name", "Someone"),
             email=email, capacity=capacity, **kw)
    u.set_password(password)
    state.store.save_user(u)
    return u


def _sign_in(client, email: str, password: str = "pw"):
    return client.post("/api/session", json={"email": email, "password": password})


# --- signing in --------------------------------------------------------------

def test_the_right_password_signs_you_in_and_says_who_you_are(client):
    _account("yossi@example.com", "backoffice", id="u_yossi", name="Yossi")
    r = _sign_in(client, "yossi@example.com")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["name"] == "Yossi"
    assert body["user"]["capacity"] == "backoffice"


def test_the_password_hash_never_crosses_the_wire(client):
    """Not secret in the sense that it unlocks anything, and still not something
    to hand out: it is the one field on the record that is worth attacking
    offline, and no screen has a use for it."""
    _account("yossi2@example.com", "backoffice", id="u_yossi2")
    body = _sign_in(client, "yossi2@example.com").json()
    assert "password_hash" not in body["user"]
    me = client.get("/api/me").json()
    assert "password_hash" not in me["user"]


def test_a_wrong_password_and_an_unknown_address_fail_identically(client):
    """Two different answers would turn the sign-in form into a way of asking
    whether somebody has an account here."""
    _account("dana@example.com", "sales", id="u_dana")
    wrong = _sign_in(client, "dana@example.com", "not-it")
    unknown = _sign_in(client, "nobody@example.com", "pw")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_a_deactivated_account_cannot_sign_in(client):
    _account("gone@example.com", "sales", id="u_gone", active=False)
    assert _sign_in(client, "gone@example.com").status_code == 401


def test_the_address_is_matched_whatever_casing_is_typed(client):
    _account("mixed@example.com", "backoffice", id="u_mixed")
    assert _sign_in(client, "  MIXED@Example.com ").status_code == 200


# --- who am I ----------------------------------------------------------------

def test_me_is_401_when_nobody_is_signed_in(client):
    client.cookies.clear()
    assert client.get("/api/me").status_code == 401


def test_me_carries_the_view_to_open_on_and_whether_a_selector_is_offered(client):
    """The safe flip of the default the sales MVP deferred: the server says
    which view this account opens on, so nobody has to choose a global default."""
    _account("dana2@example.com", "sales", id="u_dana2")
    _sign_in(client, "dana2@example.com")
    me = client.get("/api/me").json()
    assert me["view"] == "sales"
    assert me["may_choose_view"] is False

    client.cookies.clear()
    _account("admin@example.com", "admin", id="u_admin")
    _sign_in(client, "admin@example.com")
    me = client.get("/api/me").json()
    assert me["view"] == "all"
    assert me["may_choose_view"] is True


def test_signing_out_stops_the_token_working(client):
    _account("bye@example.com", "backoffice", id="u_bye")
    _sign_in(client, "bye@example.com")
    assert client.get("/api/me").status_code == 200
    assert client.delete("/api/session").status_code in (200, 204)
    assert client.get("/api/me").status_code == 401


def test_a_token_nobody_issued_is_refused_rather_than_crashing(client):
    client.cookies.set("fenceai_session", "not-a-real-token")
    assert client.get("/api/me").status_code == 401


# --- the actor on a write ----------------------------------------------------

def _last_actor_for(action: str) -> str:
    rows = [e for e in state.store.audit_entries(80) if e["action"] == action]
    assert rows, f"no audit row for {action}"
    return rows[0]["actor"]


def test_a_signed_in_session_names_the_actor_and_the_query_string_cannot(client):
    """The rule this is here to hold: an actor a client can NAME is not an audit
    trail. Twelve routes took `?author=` and handed it straight to the store, so
    anybody could sign the log as anybody. A session outranks it."""
    _account("writer@example.com", "admin", id="u_writer")
    _sign_in(client, "writer@example.com")

    project = client.post("/api/projects", json={"name": "actor test"}).json()
    r = client.put(f"/api/projects/{project['id']}/site",
                   json={"exposure_category": "C"}, params={"author": "somebody-else"})
    assert r.status_code == 200
    assert _last_actor_for("save_project") == "user:u_writer"


def test_with_nobody_signed_in_the_old_behaviour_is_untouched(client):
    """3041 tests and 428 browser checks call these routes with no session. They
    must keep working and keep writing `system`, or accounts would be a breaking
    change dressed as an addition."""
    client.cookies.clear()
    project = client.post("/api/projects", json={"name": "anon"}).json()
    client.put(f"/api/projects/{project['id']}/site", json={"exposure_category": "B"})
    assert _last_actor_for("save_project") == "system"


# --- the people list ---------------------------------------------------------

def test_the_people_list_needs_a_session(client):
    client.cookies.clear()
    assert client.get("/api/users").status_code == 401


def test_the_people_list_is_for_the_assignee_picker_and_carries_no_hashes(client):
    _account("picker@example.com", "backoffice", id="u_picker", name="Picker")
    _sign_in(client, "picker@example.com")
    rows = client.get("/api/users").json()
    assert any(u["name"] == "Picker" for u in rows)
    assert all("password_hash" not in u for u in rows)
