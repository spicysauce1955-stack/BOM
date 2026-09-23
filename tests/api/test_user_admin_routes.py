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
from fenceai.identity.ports import Principal


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _row(email: str, capacity: str, **kw) -> User:
    u = User(id=kw.pop("id", "u_" + email.split("@")[0].replace(".", "")),
             name=kw.pop("name", "Someone"), email=email, capacity=capacity, **kw)
    state.store.save_user(u)
    return u


def _blind_to(monkeypatch, address: str):
    """Make the route's pre-read answer `None` for ONE address.

    The forced half of the double-click: both requests read no existing row.
    Narrowed to one address because `user_by_email` is also how the `dev`
    provider resolves the CALLER — stubbed wholesale it makes the admin
    unidentifiable and the route answers 403 `no_capacity`, which proves nothing
    about the duplicate at all.
    """
    real = state.store.user_by_email
    monkeypatch.setattr(
        state.store, "user_by_email",
        lambda email: None if email.strip().lower() == address else real(email))


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


def test_a_double_clicked_grant_is_a_409_and_not_a_500(client, monkeypatch):
    """Two POSTs for one address where BOTH read no existing row.

    This is the double-click. `people.js`'s submit handler did not disable its
    button during `await apiSend(...)`, so two POSTs went out, the route's
    `user_by_email` read answered `None` in both, and the second reached
    `users.email`'s UNIQUE constraint — `sqlite3.IntegrityError`, which no route
    catches, so an admin who clicked twice got a 500 and a generic alert for a
    refusal that has had a locale string in both bundles all along.

    The interleaving is forced rather than raced: `user_by_email` is stubbed to
    `None` for the second call, which is exactly what the second thread saw.
    Real threads would prove the same thing less reliably and say less about
    WHERE the window was. `Store.create_user_guarded` does its own read in SQL,
    under the lock it holds across the insert, so the stub cannot defeat it —
    which is the point: the guard is at the write, not in the route.
    """
    _as_admin(client)
    first = client.post("/api/users", json={"email": "dana@company.com",
                                            "name": "Dana", "capacity": "sales"})
    assert first.status_code == 201

    _blind_to(monkeypatch, "dana@company.com")
    r = client.post("/api/users", json={"email": "dana@company.com",
                                        "name": "Dana", "capacity": "sales"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "user_exists"


def test_a_refused_duplicate_grant_leaves_one_row_and_one_grant_in_the_audit(client, monkeypatch):
    """The refusal above must not be a half-write.

    A second row for one address makes "which one resolves" a question about
    insertion order, and a `grant_capacity` audit line for a grant that never
    happened misreports what an admin did. Both are asserted here because the
    guard returns before the INSERT and before both `_audit` calls, and only a
    test that looks at the table can tell that from a guard that returns after.
    """
    _as_admin(client)
    client.post("/api/users", json={"email": "dana@company.com",
                                    "name": "Dana", "capacity": "sales"})
    _blind_to(monkeypatch, "dana@company.com")
    client.post("/api/users", json={"email": "dana@company.com",
                                    "name": "Dana again", "capacity": "admin"})

    rows = [u for u in state.store.list_users() if u.email == "dana@company.com"]
    assert len(rows) == 1
    assert rows[0].capacity == "sales", "the refused grant must not have landed"
    grants = [e for e in state.store.audit_entries(200)
              if e["action"] == "grant_capacity" and e["ref"] == rows[0].id]
    assert len(grants) == 1


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


# --- the guard under concurrency, which is how it was actually defeated --------

def test_two_admins_cannot_strand_the_deployment_by_leaving_at_once(client):
    """The last-admin guard, raced.

    Sequentially it holds — the tests above prove that. Across two concurrent
    `PATCH`es it did not: the check read `list_users()` and the write was a
    second store call, so with two admins and two in-flight demotions each
    request saw the OTHER as the admin still standing, and both committed.
    Reproduced 41 times in 60 unassisted trials before the fix.

    What makes it worth a threaded test rather than a note: the result is
    unrecoverable. `_bootstrap` only admits an address with NO row, so
    `FENCEAI_BOOTSTRAP_ADMIN` cannot rescue either of the two admins it
    stranded — the cure is a brand-new address and a redeploy, or somebody with
    database access.
    """
    import threading

    # The caller (`admin@example.com` = `u_admin`, seeded) is one of the two,
    # so these really are the only active admins — a third would make either
    # demotion legitimate and the race unobservable.
    state.store.save_user(User(id="u_b", name="B", email="b@example.com",
                               capacity="admin"))
    assert sorted(u.id for u in state.store.list_users()
                  if u.capacity == "admin" and u.active) == ["u_admin", "u_b"]

    results: list[int] = []
    barrier = threading.Barrier(2)

    def demote(uid: str) -> None:
        barrier.wait()          # start both inside the same window
        r = client.patch(f"/api/users/{uid}", json={"active": False})
        results.append(r.status_code)

    threads = [threading.Thread(target=demote, args=(u,))
               for u in ("u_admin", "u_b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    still_standing = [u for u in state.store.list_users()
                      if u.capacity == "admin" and u.active]
    assert still_standing, (
        "both demotions committed and the deployment has no active admin left; "
        f"responses were {results}")
    # At most one may be allowed through. The loser is refused with 409
    # `last_admin`, or — if it arrived after the caller's own row went
    # inactive — 403 by the gate. Either is a refusal; two 200s is the defect.
    assert results.count(200) <= 1, results


class _Iap:
    """Enough of an IdentityProvider to make `lifespan` build an iap-shaped
    app — the shape `dev_seed_lockout` refuses under. Mirrors the stand-in in
    `tests/api/test_dev_seed_boot.py`."""

    provider_id = "iap"

    def principal(self, headers, cookies):
        return Principal(email="founder@fences.co.il", subject="sub-founder")


def test_granting_admin_at_example_com_is_refused(monkeypatch):
    """`dev_seed_lockout` refuses a database at BOOT if it holds a seeded row
    at `admin@example.com` — but nothing stopped `POST /api/users` from
    creating exactly that row under `iap`. On Cloud Run `lifespan` runs on
    EVERY new instance, not only at deploy, so such a row would leave the
    instance that created it healthy and make every SUBSEQUENT instance
    refuse to start, on the next scale-out or recycle. Closing the write
    trades that delayed, uncorrectable failure for an immediate 409 — proven
    here without ever booting a second `TestClient` under the lockout."""
    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: _Iap())
    with TestClient(app) as client:
        # No dev-mode seeding happens under `iap`, so the caller has to be
        # granted directly against the store.
        state.store.save_user(User(id="u_founder", name="Founder",
                                   email="founder@fences.co.il",
                                   capacity="admin"))

        r = client.post("/api/users", json={"email": "admin@example.com",
                                            "name": "Somebody",
                                            "capacity": "sales"})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "reserved_address"
        assert state.store.user_by_email("admin@example.com") is None

        # An ordinary company address is unaffected by the guard.
        r2 = client.post("/api/users", json={"email": "dana@company.com",
                                             "name": "Dana",
                                             "capacity": "sales"})
        assert r2.status_code == 201
