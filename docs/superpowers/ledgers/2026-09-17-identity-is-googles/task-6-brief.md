### Task 6: Granting a capacity

**Files:**
- Modify: `src/fenceai/api/app.py` (after `list_users`)
- Test: `tests/api/test_user_admin_routes.py`

**Interfaces:**
- Consumes: `require_admin` (Task 3), `_public` (Task 3).
- Produces: `POST /api/users` → 201 `_public`; `PATCH /api/users/{user_id}` → 200 `_public`. Codes: `user_exists` (409), `user_not_found` (404), `last_admin` (409), `capacity_insufficient` (403).

- [ ] **Step 1: Write the failing test**

```python
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
    client.cookies.set(DEV_COOKIE, "boss@example.com")


def test_an_admin_grants_a_capacity_to_somebody_who_has_never_signed_in(client):
    _as_admin(client)
    r = client.post("/api/users", json={"email": "dana@company.com",
                                        "name": "Dana", "capacity": "sales"})
    assert r.status_code == 201
    body = r.json()
    assert body["capacity"] == "sales"
    assert body["subject"] == "", "nobody has arrived yet"
    assert body["active"] is True


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
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/api/test_user_admin_routes.py -q`
Expected: FAIL — `POST /api/users` is 405, `PATCH` is 405.

- [ ] **Step 3: Add the routes**

In `src/fenceai/api/app.py`, after `list_users`:

```python
class GrantRequest(BaseModel):
    email: str
    name: str
    capacity: Capacity


class AmendRequest(BaseModel):
    capacity: Capacity | None = None
    active: bool | None = None


def _would_strand_the_admins(target: User, body: AmendRequest) -> bool:
    """Is this the edit that leaves nobody able to grant anything?

    Asked before the write, because after it the only cure is
    `FENCEAI_BOOTSTRAP_ADMIN` and a redeploy — and that variable is removed
    after the first deploy precisely so it is not a standing way in.
    """
    losing_admin = (body.capacity is not None and body.capacity != "admin") \
        or body.active is False
    if target.capacity != "admin" or not losing_admin:
        return False
    others = [u for u in state.store.list_users()
              if u.id != target.id and u.capacity == "admin" and u.active]
    return not others


@app.post("/api/users", status_code=201)
def grant_capacity(request: Request, body: GrantRequest) -> dict:
    """Give an address a capacity, before its owner has ever signed in.

    That order is the point: an admin grants Dana her capacity on Monday and
    Dana arrives on Tuesday, at which moment her Google `sub` binds to this row.
    """
    admin = require_admin(request)
    if state.store.user_by_email(body.email) is not None:
        raise HTTPException(409, {"code": "user_exists"})
    user = User(id=f"u_{uuid.uuid4().hex[:8]}", name=body.name,
                email=body.email, capacity=body.capacity)
    state.store.save_user(user, actor=actor_ref(admin))
    state.store.log(actor_ref(admin), "grant_capacity", user.id)
    return _public(user)


@app.patch("/api/users/{user_id}")
def amend_capacity(request: Request, user_id: str, body: AmendRequest) -> dict:
    """Change what somebody may do, or stop them doing anything.

    Deactivated, never deleted — the audit log names people who have left, so a
    row must keep resolving to a name for ever.
    """
    admin = require_admin(request)
    user = state.store.user(user_id)
    if user is None:
        raise HTTPException(404, {"code": "user_not_found"})
    if _would_strand_the_admins(user, body):
        raise HTTPException(409, {"code": "last_admin"})
    if body.capacity is not None:
        user.capacity = body.capacity
    if body.active is not None:
        user.active = body.active
    state.store.save_user(user, actor=actor_ref(admin))
    state.store.log(actor_ref(admin), "amend_capacity", user.id)
    return _public(user)
```

Add `import uuid` and `Capacity` to the imports (`from fenceai.identity.model import Capacity, ...`).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/api/test_user_admin_routes.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/api/app.py tests/api/test_user_admin_routes.py
git commit -m "feat(api): an admin grants a capacity, and cannot strand the last one"
```

---

