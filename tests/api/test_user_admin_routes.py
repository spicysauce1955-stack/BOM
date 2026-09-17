"""An admin grants a capacity — the first real capacity check in this app.

Rows are created BY EMAIL, before that person has ever signed in: an admin
grants Dana her capacity on Monday and Dana arrives on Tuesday. Everything else
in this file is about the ways that can go wrong.
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
    u = User(id=kw.pop("id", "u_" + email.split("@")[0].replace(".", "")),
             name=kw.pop("name", "Someone"), email=email, capacity=capacity, **kw)
    state.store.save_user(u)
    return u


def _as_admin(client):
    _row("boss@example.com", "admin", id="u_boss")
    # Dev mode seeds DEMO_ACCOUNTS (including an active `admin@example.com`
    # admin) into every fresh database the moment `TestClient(app)` runs
    # `lifespan` — before this fixture's body gets to run at all. Left alone,
    # `u_boss` is never actually the sole admin these tests mean to set up,
    # and the last-admin guard would pass its own tests for the wrong reason
    # (another active admin always happens to be sitting there). Neutralise
    # it so `u_boss` is the one active admin under test.
    seeded = state.store.user_by_email("admin@example.com")
    if seeded is not None:
        seeded.active = False
        state.store.save_user(seeded)
    client.cookies.set(DEV_COOKIE, "boss@example.com")


def test_an_admin_grants_a_capacity_to_somebody_who_has_never_signed_in(client):
    _as_admin(client)
    r = client.post("/api/users", json={"email": "dana@company.com",
                                        "name": "Dana", "capacity": "sales"})
    assert r.status_code == 201
    body = r.json()
    assert body["capacity"] == "sales"
    # `_public` sends `subject_bound`, not the raw `subject` (see CLAUDE.md's
    # split registry / brief note 1) — a fresh grant has not been bound yet.
    assert body["subject_bound"] is False, "nobody has arrived yet"
    assert body["active"] is True
    assert "subject" not in body, "_public must not leak the raw Google id"


def test_the_granted_person_can_then_get_in(client):
    _as_admin(client)
    client.post("/api/users", json={"email": "dana@company.com",
                                    "name": "Dana", "capacity": "sales"})
    client.cookies.set(DEV_COOKIE, "dana@company.com")
    assert client.get("/api/session").json()["status"] == "ok"


def test_a_salesperson_may_not_grant_anything(client):
    """A capacity is what an account may DO and is read on the server. Hiding
    the panel would be a presentation fact and no protection at all."""
    _row("dana@example.com", "sales", id="u_dana")
    client.cookies.set(DEV_COOKIE, "dana@example.com")
    r = client.post("/api/users", json={"email": "x@y.com", "name": "X",
                                        "capacity": "admin"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "capacity_insufficient"


def test_the_backoffice_may_not_either(client):
    _row("yossi@example.com", "backoffice", id="u_yossi")
    client.cookies.set(DEV_COOKIE, "yossi@example.com")
    assert client.post("/api/users", json={"email": "x@y.com", "name": "X",
                                           "capacity": "sales"}).status_code == 403


def test_a_salesperson_may_not_amend_anybody_either(client):
    """The PATCH twin of `test_a_salesperson_may_not_grant_anything`: the
    brief's own test list never called PATCH as a non-admin, which would have
    left that gate's mutation invisible to this file — a guard proven only by
    an admin-invoked test proves nothing about the guard itself."""
    _row("dana@example.com", "sales", id="u_dana")
    target = _row("target@example.com", "sales", id="u_target")
    client.cookies.set(DEV_COOKIE, "dana@example.com")
    r = client.patch(f"/api/users/{target.id}", json={"capacity": "backoffice"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "capacity_insufficient"


def test_granting_the_same_address_twice_is_refused(client):
    """Email is the UNIQUE key and the way a row is found. A second row for one
    address would make which one resolves a question about insertion order."""
    _as_admin(client)
    client.post("/api/users", json={"email": "dana@company.com",
                                    "name": "Dana", "capacity": "sales"})
    r = client.post("/api/users", json={"email": "Dana@Company.com",
                                        "name": "Dana again", "capacity": "admin"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "user_exists"


def test_an_unknown_capacity_is_refused_by_the_model(client):
    _as_admin(client)
    assert client.post("/api/users", json={"email": "x@y.com", "name": "X",
                                           "capacity": "superuser"}).status_code == 422


def test_an_admin_changes_somebody_s_capacity(client):
    _as_admin(client)
    dana = _row("dana@example.com", "sales", id="u_dana")
    r = client.patch(f"/api/users/{dana.id}", json={"capacity": "backoffice"})
    assert r.status_code == 200
    assert r.json()["capacity"] == "backoffice"
    assert state.store.user("u_dana").capacity == "backoffice"


def test_an_admin_deactivates_somebody_and_they_stop_getting_in(client):
    _as_admin(client)
    dana = _row("dana@example.com", "sales", id="u_dana")
    assert client.patch(f"/api/users/{dana.id}",
                        json={"active": False}).status_code == 200
    client.cookies.set(DEV_COOKIE, "dana@example.com")
    r = client.get("/api/projects")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "account_deactivated"


def test_patching_somebody_who_does_not_exist_is_a_404(client):
    _as_admin(client)
    r = client.patch("/api/users/u_nobody", json={"active": False})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "user_not_found"


def test_the_last_admin_cannot_demote_themselves(client):
    """Otherwise one PATCH locks every human out of granting anything, and the
    only cure is `FENCEAI_BOOTSTRAP_ADMIN` and a redeploy."""
    _as_admin(client)
    r = client.patch("/api/users/u_boss", json={"capacity": "sales"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "last_admin"


def test_the_last_admin_cannot_deactivate_themselves(client):
    _as_admin(client)
    r = client.patch("/api/users/u_boss", json={"active": False})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "last_admin"


def test_one_of_two_admins_may_step_down(client):
    _as_admin(client)
    _row("other@example.com", "admin", id="u_other")
    assert client.patch("/api/users/u_boss",
                        json={"capacity": "sales"}).status_code == 200


def test_granting_is_written_to_the_log(client):
    _as_admin(client)
    client.post("/api/users", json={"email": "dana@company.com",
                                    "name": "Dana", "capacity": "sales"})
    rows = client.get("/api/audit?limit=20").json()
    assert any(r["actor"] == "user:u_boss" and r["action"] == "grant_capacity"
               for r in rows)
