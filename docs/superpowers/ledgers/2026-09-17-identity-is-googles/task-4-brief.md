### Task 4: The dev route, and its absence under IAP

**Files:**
- Test: `tests/api/test_dev_identity_route.py`

**Interfaces:**
- Consumes: `POST /api/dev/identity` and `DEV_COOKIE` from Task 3.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
"""The picker's server half — and the fact that it does not exist in production.

A dev-only impersonation route is safe because of WHERE it is registered, not
because of what it checks. So the test that matters most is the absent one.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.model import User


@pytest.fixture()
def client():
    from fenceai.api.app import app
    with TestClient(app) as c:
        yield c


def test_becoming_somebody_sets_the_cookie_and_the_next_request_is_them(client):
    from fenceai.api.app import state
    state.store.save_user(User(id="u_dana", name="Dana",
                               email="dana@example.com", capacity="sales"))
    assert client.post("/api/dev/identity",
                       json={"email": "dana@example.com"}).status_code == 204
    assert client.cookies.get(DEV_COOKIE) == "dana@example.com"
    assert client.get("/api/session").json()["user"]["name"] == "Dana"


def test_becoming_somebody_with_no_row_still_sets_the_cookie(client):
    """The route says who you ARE; the gate says what you may DO. Refusing an
    unknown address here would make the no-capacity screen unreachable, which
    is the screen that tells somebody what to ask for."""
    assert client.post("/api/dev/identity",
                       json={"email": "stranger@example.com"}).status_code == 204
    assert client.get("/api/session").json()["status"] == "no_capacity"


def test_the_route_does_not_exist_under_iap(monkeypatch):
    """Not "refuses" — does not exist. A guard inside the handler is one edit
    away from being removed by somebody who did not know why it was there."""
    monkeypatch.setenv("FENCEAI_IDENTITY", "iap")
    monkeypatch.setenv("FENCEAI_IAP_AUDIENCE", "/projects/1/global/backendServices/2")
    import fenceai.api.app as app_module
    importlib.reload(app_module)
    try:
        paths = {r.path for r in app_module.app.routes if hasattr(r, "methods")}
        assert "/api/dev/identity" not in paths
    finally:
        monkeypatch.setenv("FENCEAI_IDENTITY", "dev")
        importlib.reload(app_module)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/api/test_dev_identity_route.py -q`
Expected: PASS if Task 3's route is right; FAIL on the reload test if the registration is not module-level-conditional. Fix by moving the `if` to module scope as Task 3 Step 6 shows.

- [ ] **Step 3: Run the whole API suite to check the reload did not poison it**

Run: `uv run pytest tests/api -q`
Expected: PASS. If other files fail only when this one runs first, the reload is leaking — make the reload test the last in the file and re-import `app` in the `finally`, which the code above already does.

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_dev_identity_route.py
git commit -m "test(api): the dev picker's route, and the fact that IAP never registers it"
```

---

