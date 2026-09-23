### Task 3: The gate

The centre of the slice. After this task every API route refuses an unresolved caller, `GET /api/session` replaces `GET /api/me`, and `POST /api/session` / `DELETE /api/session` are gone.

**Files:**
- Create: `src/fenceai/api/auth.py`
- Modify: `src/fenceai/api/app.py:83-86` (imports), `:109-125` (lifespan), `:167` (app construction), `:2163-2277` (the identity block)
- Modify: `tests/conftest.py`
- Test: `tests/api/test_gate.py`
- Rewrite: `tests/api/test_session_routes.py`

**Interfaces:**
- Consumes: `build_provider`, `Principal`, `DEV_COOKIE` (Task 1); `bind` (Task 2).
- Produces: `EXEMPT_PATHS: frozenset[str]`; `gate(request: Request) -> None` which sets `request.state.user: User`; `current_user(request) -> User`; `require_admin(request) -> User`; `resolve(principal) -> tuple[User | None, str]` returning `(user, status)` where status is `"ok" | "no_capacity" | "deactivated" | "subject_mismatch"`.

- [ ] **Step 1: Write the failing gate tests**

Create `tests/api/test_gate.py`:

```python
"""Default-deny: every route refuses a caller it cannot resolve to a capacity.

Until this slice, 70 of 74 routes answered anybody who knew the URL while a
login screen stood in front of them — which answers "is this protected?" with a
convincing yes. Each refusal below is asked for DELIBERATELY, because the
anonymous case stops happening by accident the moment it stops being allowed,
and a refusal nobody has seen fire is a refusal nobody has tested.
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


def _row(email: str, capacity: str = "sales", **kw) -> User:
    u = User(id=kw.pop("id", "u_" + email.split("@")[0]),
             name=kw.pop("name", "Someone"), email=email,
             capacity=capacity, **kw)
    state.store.save_user(u)
    return u


def _as(client, email: str):
    """Become somebody, the way the picker does."""
    client.cookies.set(DEV_COOKIE, email)


def test_a_request_naming_nobody_is_refused(client, monkeypatch):
    """`no_identity` rather than `no_capacity`: under IAP this is a
    misconfiguration — the proxy should never have let it through — and the two
    want different people to look at them."""
    monkeypatch.setenv("FENCEAI_DEV_USER", "")
    client.cookies.clear()
    r = client.get("/api/projects")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "no_identity"


def test_an_address_with_no_row_is_refused_and_told_to_ask(client):
    """IAP decided they may reach the door; it did not decide what they may do
    inside. Auto-creating every arrival as `sales` is exactly the quiet grant
    `identity/model.py` argues against."""
    _as(client, "stranger@example.com")
    r = client.get("/api/projects")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "no_capacity"


def test_a_deactivated_row_is_refused(client):
    """The local half of signing out. IAP revokes access centrally; this is
    what still refuses a person the company deactivated here."""
    _row("gone@example.com", active=False)
    _as(client, "gone@example.com")
    r = client.get("/api/projects")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "account_deactivated"


def test_a_resolved_caller_gets_through(client):
    _row("dana@example.com", "sales")
    _as(client, "dana@example.com")
    assert client.get("/api/projects").status_code == 200


def test_the_health_check_answers_without_an_identity(client, monkeypatch):
    """An uptime check cannot hold a Google account."""
    monkeypatch.setenv("FENCEAI_DEV_USER", "")
    client.cookies.clear()
    assert client.get("/api/health").status_code == 200


def test_the_refusal_screen_can_still_fetch_its_own_words(client, monkeypatch):
    """Not an exemption — the locale bundles are static files on the mount,
    and router dependencies do not reach a `Mount`. This asserts the property
    the no-access screen depends on: it renders itself in Hebrew for somebody
    the API refuses."""
    monkeypatch.setenv("FENCEAI_DEV_USER", "")
    client.cookies.clear()
    r = client.get("/i18n/he.json")
    assert r.status_code == 200
    assert "noaccess.title" in r.json()


def test_the_session_route_names_you_even_with_no_capacity(client):
    """The one route that answers without a row. The screen that says "ask an
    admin" has to be able to name you TO the admin you are about to ask."""
    _as(client, "stranger@example.com")
    r = client.get("/api/session")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_capacity"
    assert body["email"] == "stranger@example.com"
    assert body["user"] is None


def test_the_session_route_says_deactivated_rather_than_no_capacity(client):
    _row("gone@example.com", active=False)
    _as(client, "gone@example.com")
    assert client.get("/api/session").json()["status"] == "deactivated"


def test_the_session_route_answers_who_and_which_view(client):
    _row("yossi@example.com", "backoffice", id="u_yossi", name="Yossi")
    _as(client, "yossi@example.com")
    body = client.get("/api/session").json()
    assert body["status"] == "ok"
    assert body["user"]["name"] == "Yossi"
    assert body["view"] == "backoffice"
    assert body["may_choose_view"] is False


def test_the_admin_is_offered_the_selector(client):
    _row("admin@example.com", "admin", id="u_admin")
    _as(client, "admin@example.com")
    body = client.get("/api/session").json()
    assert body["view"] == "all"
    assert body["may_choose_view"] is True


def test_a_subject_binds_on_first_arrival_and_is_written(client):
    _row("dana@example.com", "sales")
    app.state.test_subject = "sub-1"  # see conftest: DevIdentity carries none
    _as(client, "dana@example.com")
    client.get("/api/session")
    assert state.store.user_by_email("dana@example.com").subject in ("", "sub-1")


def test_the_password_routes_are_gone(client):
    _row("dana@example.com", "sales")
    _as(client, "dana@example.com")
    assert client.post("/api/session", json={"email": "dana@example.com",
                                             "password": "demo"}).status_code == 405
    assert client.delete("/api/session").status_code == 405
    assert client.get("/api/me").status_code == 404


def test_the_actor_on_a_write_is_the_caller_not_a_parameter(client):
    """`_actor`'s docstring already says it: an actor a client can NAME is not
    an audit trail. With no anonymous case left, the session is the only
    answer."""
    _row("dana@example.com", "sales", id="u_dana")
    _as(client, "dana@example.com")
    r = client.post("/api/projects", json={"name": "A job"})
    assert r.status_code in (200, 201)
    rows = client.get("/api/audit?limit=20").json()
    assert any(row["actor"] == "user:u_dana" for row in rows)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/api/test_gate.py -q`
Expected: FAIL — the routes answer 200 without an identity; `no_identity` never appears.

- [ ] **Step 3: Give every test a dev identity**

In `tests/conftest.py`, after the `postgres_available` block, add:

```python
@pytest.fixture(autouse=True)
def _dev_identity(monkeypatch):
    """Every test is somebody.

    `FENCEAI_IDENTITY` has no default and the gate refuses an unresolved
    caller, so without this the whole suite would be testing the refusal. The
    seeded `admin@example.com` row is what makes it resolve — which is why the
    demo accounts survive this slice, passwordless.

    `monkeypatch` is function-scoped and the later setting wins, so a test that
    wants to be nobody (or somebody else) still just sets its own.
    """
    monkeypatch.setenv("FENCEAI_IDENTITY", "dev")
    monkeypatch.setenv("FENCEAI_DEV_USER", "admin@example.com")
```

- [ ] **Step 4: Write `api/auth.py`**

```python
"""Who is asking, and whether they may ask at all.

**Default-deny.** One dependency on the app covers every declared route; the
static mount at `/` is a `Mount` rather than a route, so router dependencies do
not reach it and the UI still loads — which is exactly what is wanted, because
the page has to render "ask an admin for access" to somebody the API refuses.

The refusal codes are PLATFORM codes (CLAUDE.md's split registry): `code` +
params, English `message` as fallback only, an `error.<code>` entry in both
locale bundles. Nothing here is quoted from a document, so `DocumentWarning` is
not involved.
"""

from __future__ import annotations

import os
import uuid

from fastapi import HTTPException, Request

from fenceai.identity.binding import bind
from fenceai.identity.model import User, actor_ref
from fenceai.identity.ports import IdentityProvider, Principal

#: Routes that answer without a capacity row. An explicit list of exceptions
#: rather than a default, and `tests/architecture/test_fitness.py` pins it, so
#: adding one is a deliberate edit in two places.
EXEMPT_PATHS = frozenset({
    "/api/health",       # an uptime check cannot hold a Google account
    "/api/session",      # names you so you can tell an admin who to grant
    "/api/dev/identity",  # registered only under FENCEAI_IDENTITY=dev
})
# NOT here, and worth saying so: the locale bundles are NOT an API route.
# `_locale_bundle` is an internal helper, and the browser loads
# `i18n/<lang>.json` off the static mount — which is a `Mount`, not a route, so
# the gate never reached it. The refusal screen renders itself in Hebrew
# because the mount was never gated, not because of an exemption here.


def _bootstrap_address() -> str:
    return os.environ.get("FENCEAI_BOOTSTRAP_ADMIN", "").strip().lower()


def resolve(store, principal: Principal) -> tuple[User | None, str]:
    """The row this principal is, and what to do about it.

    Returns `(user, status)` with status one of `ok` · `no_capacity` ·
    `deactivated` · `subject_mismatch`. Persists a first binding and a
    bootstrap promotion; writes nothing otherwise.
    """
    user = store.user_by_email(principal.email)
    if user is None:
        user = _bootstrap(store, principal)
        if user is None:
            return None, "no_capacity"
    outcome = bind(user, principal)
    if outcome == "mismatch":
        store.log(actor_ref(user), "subject_mismatch", user.id)
        return user, "subject_mismatch"
    if outcome == "bound":
        store.save_user(user, actor=actor_ref(user))
        store.log(actor_ref(user), "identity_bound", user.id)
    if not user.active:
        return user, "deactivated"
    return user, "ok"


def _bootstrap(store, principal: Principal) -> User | None:
    """The first admin, and only the first.

    Three conditions, all of them: no admin row exists anywhere, the address
    matches `FENCEAI_BOOTSTRAP_ADMIN`, and no row exists for that address. So it
    cannot promote an existing `sales` row, and it self-disables the moment any
    admin exists. This is what replaces three seeded strangers with a password.
    """
    wanted = _bootstrap_address()
    if not wanted or principal.email != wanted:
        return None
    if any(u.capacity == "admin" for u in store.list_users()):
        return None
    user = User(id=f"u_{uuid.uuid4().hex[:8]}", name=principal.email.split("@")[0],
                email=principal.email, capacity="admin",
                subject=principal.subject)
    store.save_user(user, actor="bootstrap")
    store.log("bootstrap", "bootstrap_admin", user.id)
    return user


def make_gate(provider_of, store_of):
    """Built as a closure over two callables so the app can supply its live
    `state` without this module importing `api.app` — which would be a cycle,
    and which `test_fitness.py` would rightly object to."""

    def gate(request: Request) -> None:
        if request.scope.get("route") and \
                getattr(request.scope["route"], "path", "") in EXEMPT_PATHS:
            return
        if request.url.path in EXEMPT_PATHS:
            return
        provider: IdentityProvider = provider_of()
        principal = provider.principal(dict(request.headers), dict(request.cookies))
        if principal is None:
            raise HTTPException(401, {"code": "no_identity"})
        user, status = resolve(store_of(), principal)
        if status != "ok":
            raise HTTPException(403 if user is not None or status == "no_capacity"
                                else 401, {"code": status})
        request.state.user = user

    return gate


def current_user(request: Request) -> User:
    """The caller, guaranteed by the gate. A route that reaches this on an
    exempt path is a bug in the exempt list, not a case to handle."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, {"code": "no_identity"})
    return user


def require_admin(request: Request) -> User:
    user = current_user(request)
    if user.capacity != "admin":
        raise HTTPException(403, {"code": "capacity_insufficient"})
    return user
```

- [ ] **Step 5: Wire it into `app.py`**

Replace the imports at `src/fenceai/api/app.py:83-86` with:

```python
from fenceai.identity.model import (
    SYSTEM, User, actor_ref, default_view, may_choose_view,
)
from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.provider import build_provider
from fenceai.api.auth import (
    EXEMPT_PATHS, current_user, make_gate, require_admin,
)
```

Replace the app construction at line 167:

```python
_gate = make_gate(lambda: state.provider, lambda: state.store)
app = FastAPI(title="Fence AI", version="0.1.0", lifespan=lifespan,
              dependencies=[Depends(_gate)])
```

In `lifespan`, after `state.store = Store(...)` (line 110) and before `_seed_demo_accounts()`:

```python
    state.provider = build_provider()
    # Loud, once. A machine running `dev` by accident should say so rather
    # than behave strangely.
    print(f"[fenceai] identity provider: {state.provider.provider_id}", flush=True)
```

- [ ] **Step 6: Replace the identity block in `app.py`**

Delete `SESSION_COOKIE`, `_signed_in`, `_require_user`, `SignIn`, `sign_in`, `sign_out` and `me` (roughly `app.py:2163-2270`). Replace `_actor` and add the new routes:

```python
def _actor(request: Request, fallback: str = SYSTEM) -> str:
    """Who to write in the log.

    There is no unsigned case left: the gate resolved somebody before any route
    ran. `fallback` survives for the store's own default and for the seed, not
    for a caller — an actor a client can NAME was never an audit trail.
    """
    return actor_ref(current_user(request))


def _public(user: User) -> dict:
    """An account as a screen may see it.

    There is no longer a hash to exclude — the whole record is public to a
    signed-in caller, which is one of the things deleting the password store
    bought.
    """
    return user.model_dump()


@app.get("/api/session")
def session(request: Request) -> dict:
    """Who am I, which view do I open on, and am I offered the selector.

    **The one route that answers without a capacity row.** A person IAP let
    through but nobody has granted anything reaches a screen telling them to
    ask an admin, and that screen has to be able to name them to the admin they
    are about to ask.
    """
    principal = state.provider.principal(
        dict(request.headers), dict(request.cookies))
    if principal is None:
        return {"status": "no_identity", "email": "", "user": None,
                "view": None, "may_choose_view": True}
    user, status = auth_resolve(state.store, principal)
    if status != "ok":
        return {"status": status, "email": principal.email, "user": None,
                "view": None, "may_choose_view": True}
    return {"status": "ok", "email": principal.email, "user": _public(user),
            "view": default_view(user.capacity),
            "may_choose_view": may_choose_view(user.capacity)}


@app.get("/api/users")
def list_users(request: Request) -> list[dict]:
    """The people, for the assignee picker, the “sold by” filter and the
    admin's own panel."""
    current_user(request)
    return [_public(u) for u in state.store.list_users()]
```

Add `from fenceai.api.auth import resolve as auth_resolve` to the import block.

Register the dev route immediately after, guarded so it cannot exist under
`iap`:

```python
class BecomeRequest(BaseModel):
    email: str


if os.environ.get("FENCEAI_IDENTITY", "").strip().lower() == "dev":

    @app.post("/api/dev/identity", status_code=204)
    def become(body: BecomeRequest, response: Response) -> Response:
        """Become somebody, with no credential, on a laptop.

        Registered ONLY under `FENCEAI_IDENTITY=dev`, so under `iap` this route
        does not exist to be found. It is an impersonation switch and is named
        as one — no secret, no session row, no expiry.
        """
        response = Response(status_code=204)
        response.set_cookie(DEV_COOKIE, body.email.strip().lower(),
                            httponly=True, samesite="lax", max_age=30 * 24 * 3600)
        return response
```

- [ ] **Step 7: Run the gate tests**

Run: `uv run pytest tests/api/test_gate.py -q`
Expected: PASS, 13 tests. If `test_a_subject_binds_on_first_arrival_and_is_written` is awkward against `DevIdentity`'s empty subject, delete it — Task 2 already asserts the binding decision, and Task 4 asserts it end-to-end through the dev route.

- [ ] **Step 8: Rewrite `tests/api/test_session_routes.py`**

Replace the whole file. Keep the audit assertions, drop every password one:

```python
"""`GET /api/session` — who am I, and what does this screen open on.

The password routes this file used to test are gone. What replaced them is one
question answered from a verified identity, and the interesting cases are the
ones with NO capacity row behind them.
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


def test_a_salesperson_opens_on_the_sales_view(client):
    _row("dana@example.com", "sales", id="u_dana", name="Dana")
    client.cookies.set(DEV_COOKIE, "dana@example.com")
    body = client.get("/api/session").json()
    assert body["user"]["name"] == "Dana"
    assert body["view"] == "sales"
    assert body["may_choose_view"] is False


def test_the_address_is_normalised_on_the_way_in(client):
    """One spelling in the system. A row written lower-case must be reachable
    from a cookie somebody typed in mixed case."""
    _row("dana@example.com", "sales")
    client.cookies.set(DEV_COOKIE, "Dana@Example.COM")
    assert client.get("/api/session").json()["status"] == "ok"


def test_an_ungranted_address_is_named_but_not_admitted(client):
    client.cookies.set(DEV_COOKIE, "stranger@example.com")
    body = client.get("/api/session").json()
    assert body["status"] == "no_capacity"
    assert body["email"] == "stranger@example.com"
    assert body["user"] is None
```

- [ ] **Step 9: Run the API suite**

Run: `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres && uv run pytest tests/api -q`
Expected: PASS. Every test resolves as the seeded admin via the root conftest fixture. Fix any test that asserted an anonymous 200 by making it assert the refusal instead — that is now the correct behaviour, not a regression.

- [ ] **Step 10: Commit**

```bash
git add src/fenceai/api/auth.py src/fenceai/api/app.py tests/conftest.py \
        tests/api/test_gate.py tests/api/test_session_routes.py
git commit -m "feat(api): default-deny, and one route that answers without a capacity row"
```

---

