"""`GET /api/session` — who am I, and what does this screen open on.

The password routes this file used to test are gone. What replaced them is one
question answered from a verified identity, and the interesting cases are the
ones with NO capacity row behind them.

The actor assertions survive the rewrite, because the rule they hold did not
change — it got stronger. `?author=` never outranked a session; now there is no
unsigned case for it to win by default either.
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


def _row(email: str, capacity: str, **kw) -> User:
    u = User(id=kw.pop("id", "u_" + email.split("@")[0]),
             name=kw.pop("name", "Someone"), email=email, capacity=capacity, **kw)
    state.store.save_user(u)
    return u


def _as(client, email: str):
    client.cookies.set(DEV_COOKIE, email)


# --- who am I ----------------------------------------------------------------

def test_a_salesperson_opens_on_the_sales_view(client):
    _row("dana@example.com", "sales", id="u_dana", name="Dana")
    _as(client, "dana@example.com")
    body = client.get("/api/session").json()
    assert body["user"]["name"] == "Dana"
    assert body["view"] == "sales"
    assert body["may_choose_view"] is False


def test_the_address_is_normalised_on_the_way_in(client):
    """One spelling in the system. A row written lower-case must be reachable
    from a cookie somebody typed in mixed case."""
    _row("dana@example.com", "sales")
    _as(client, "Dana@Example.COM")
    assert client.get("/api/session").json()["status"] == "ok"


def test_an_ungranted_address_is_named_but_not_admitted(client):
    _as(client, "stranger@example.com")
    body = client.get("/api/session").json()
    assert body["status"] == "no_capacity"
    assert body["email"] == "stranger@example.com"
    assert body["user"] is None


def test_the_password_hash_never_crosses_the_wire(client):
    """The field is gone from `User` now; this pins the wire shape rather than
    the model's current fields, so a hash re-added for any reason still never
    reaches this route."""
    _row("yossi@example.com", "backoffice", id="u_yossi")
    _as(client, "yossi@example.com")
    assert "password_hash" not in client.get("/api/session").json()["user"]


# --- the actor on a write ----------------------------------------------------

def _last_actor_for(action: str) -> str:
    rows = [e for e in state.store.audit_entries(80) if e["action"] == action]
    assert rows, f"no audit row for {action}"
    return rows[0]["actor"]


def test_the_identity_names_the_actor_and_the_query_string_cannot(client):
    """The rule this is here to hold: an actor a client can NAME is not an audit
    trail. Twelve routes took `?author=` and handed it straight to the store, so
    anybody could sign the log as anybody. The resolved caller outranks it —
    and, now that there is no anonymous case, is the only answer."""
    _row("writer@example.com", "admin", id="u_writer")
    _as(client, "writer@example.com")

    project = client.post("/api/projects", json={"name": "actor test"}).json()
    r = client.put(f"/api/projects/{project['id']}/site",
                   json={"exposure_category": "C"}, params={"author": "somebody-else"})
    assert r.status_code == 200
    assert _last_actor_for("save_project") == "user:u_writer"


def test_the_creator_is_the_caller_so_the_job_lands_on_their_own_screen(client):
    """`created_by` is what puts the job on `GET /api/my-jobs`. Taken from the
    identity and never from the body, or one salesperson could file a job onto
    another's home screen."""
    _row("dana@example.com", "sales", id="u_dana")
    _as(client, "dana@example.com")
    project = client.post("/api/projects", json={"name": "hers"}).json()
    assert project["created_by"] == "u_dana"


# --- the people list ---------------------------------------------------------

def test_the_people_list_is_for_the_assignee_picker_and_carries_no_hashes(client):
    _row("picker@example.com", "backoffice", id="u_picker", name="Picker")
    _as(client, "picker@example.com")
    rows = client.get("/api/users").json()
    assert any(u["name"] == "Picker" for u in rows)
    assert all("password_hash" not in u for u in rows)


def test_the_people_list_says_whether_google_is_bound_never_the_id(client):
    """`subject` is Google's stable account id, and every signed-in capacity —
    not only an admin — can reach this route. A colleague's raw Google id has
    no consumer here and no reason to leave the server; `subject_bound` answers
    the only question a people panel actually needs."""
    _row("bound@example.com", "backoffice", id="u_bound", subject="sub-123")
    _row("unbound@example.com", "backoffice", id="u_unbound")
    _as(client, "bound@example.com")
    rows = {u["email"]: u for u in client.get("/api/users").json()}
    assert rows["bound@example.com"]["subject_bound"] is True
    assert rows["unbound@example.com"]["subject_bound"] is False
    assert "subject" not in rows["bound@example.com"]
    assert "subject" not in rows["unbound@example.com"]
