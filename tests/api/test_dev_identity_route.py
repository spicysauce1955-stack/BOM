"""The picker's server half — and the fact that it does not exist in production.

A dev-only impersonation route is safe because of WHERE it is registered, not
because of what it checks. So the test that matters most is the absent one.

`DELETE /api/dev/identity` (E1) is the other half of the same switch:
`js/session.js`'s `signOut()` calls it inside a try/catch precisely because it
is expected to not exist under `iap`.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest
from fastapi.testclient import TestClient

from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.model import User


@pytest.fixture()
def client():
    from fenceai.api.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def nobody(monkeypatch):
    """A client carrying no identity at all — see `tests/api/test_gate.py`'s
    fixture of the same name and the same reasoning: `FENCEAI_DEV_USER` must be
    cleared BEFORE the client (and therefore `lifespan`'s provider) is built,
    or a caller presenting no cookie still resolves as the seeded admin and
    every assertion below would pass for the wrong reason."""
    monkeypatch.setenv("FENCEAI_DEV_USER", "")
    from fenceai.api.app import app
    with TestClient(app) as c:
        c.cookies.clear()
        yield c


def test_becoming_somebody_sets_the_cookie_and_the_next_request_is_them(client):
    from fenceai.api.app import state
    state.store.save_user(User(id="u_dana", name="Dana",
                               email="dana@example.com", capacity="sales"))
    assert client.post("/api/dev/identity",
                       json={"email": "dana@example.com"}).status_code == 204
    # The round trip is the assertion, not the stored spelling: an address
    # contains `@`, which `set_cookie` quotes on the way out (see
    # `test_gate.py`'s identical note) — so what matters is that the SERVER
    # reads back the same person on the next request, not the literal jar
    # string on the client.
    assert DEV_COOKIE in client.cookies
    assert client.get("/api/session").json()["user"]["name"] == "Dana"


def test_becoming_somebody_with_no_row_still_sets_the_cookie(client):
    """The route says who you ARE; the gate says what you may DO. Refusing an
    unknown address here would make the no-capacity screen unreachable, which
    is the screen that tells somebody what to ask for."""
    assert client.post("/api/dev/identity",
                       json={"email": "stranger@example.com"}).status_code == 204
    assert client.get("/api/session").json()["status"] == "no_capacity"


def test_signing_out_clears_the_cookie_and_the_next_request_is_nobody(nobody):
    """E1: `signOut()` DELETEs this same route. Becoming somebody and then
    signing out must leave the browser with no cookie and no session — not
    merely a different one.

    Built from `nobody`, not the plain `client`: every other test in this
    suite runs with `FENCEAI_DEV_USER=admin@example.com` set (see
    `tests/conftest.py`'s autouse fixture), so a caller presenting NO cookie
    still silently resolves as the seeded admin — which would make this
    assertion pass whether or not the cookie was actually cleared. Only a
    client built after clearing that variable can tell "signed out" apart
    from "signed in as the fallback"."""
    from fenceai.api.app import state
    client = nobody
    state.store.save_user(User(id="u_dana", name="Dana",
                               email="dana@example.com", capacity="sales"))
    client.post("/api/dev/identity", json={"email": "dana@example.com"})
    assert client.get("/api/session").json()["status"] == "ok"

    assert client.delete("/api/dev/identity").status_code == 204
    assert DEV_COOKIE not in client.cookies
    assert client.get("/api/session").json()["status"] == "no_identity"


def test_signing_out_clears_the_cookie_even_for_nobody(nobody):
    """The exemption that lets an unresolved caller reach this route matches
    by PATH, not by method (`auth.EXEMPT_PATHS`) — so a browser that IAP or the
    dev provider cannot resolve to any capacity row must still be able to
    clear its own impersonation cookie. This is exactly the caller
    `no-access-signout` drives: somebody with `no_capacity`, asking to try a
    different address.

    The cookie is set through the real POST rather than `client.cookies.set`
    directly: the test client's cookie jar scopes a manually-set cookie to a
    different domain than one arriving in a response, so a later delete would
    look like it succeeded (204, a well-formed clearing `Set-Cookie`) while
    silently leaving the manually-set cookie behind under the other domain —
    a false pass that proves nothing about the route."""
    client = nobody
    client.post("/api/dev/identity", json={"email": "stranger@example.com"})
    assert client.get("/api/session").json()["status"] == "no_capacity"

    assert client.delete("/api/dev/identity").status_code == 204
    assert DEV_COOKIE not in client.cookies
    assert client.get("/api/session").json()["status"] == "no_identity"


def test_the_route_exists_with_both_methods_under_dev(client):
    """Companion to the absence test below: under `dev`, both halves of the
    switch are registered on the same path."""
    from fenceai.api.app import app as dev_app
    methods_by_path: dict[str, set[str]] = {}
    for r in dev_app.routes:
        if hasattr(r, "methods"):
            methods_by_path.setdefault(r.path, set()).update(r.methods or set())
    assert {"POST", "DELETE"} <= methods_by_path.get("/api/dev/identity", set())


def test_the_route_does_not_exist_under_iap(monkeypatch):
    """Not "refuses" — does not exist. A guard inside the handler is one edit
    away from being removed by somebody who did not know why it was there.

    Loaded as an INDEPENDENT copy of the module under its own name, exactly as
    `test_gate.py`'s `_app_module_under` does, rather than
    `importlib.reload(fenceai.api.app)` in place. The plan's own draft of this
    test used a plain reload, and it poisons every OTHER test file that wrote
    `from fenceai.api.app import app, state` at collection time (most of
    `tests/api` does): reload rebinds those two names inside
    `fenceai.api.app`'s namespace to brand-new objects, but a name another
    module already imported does not follow the rebinding — it keeps pointing
    at the pre-reload objects. The original `app`'s `lifespan`, though, is a
    closure that reads the CURRENT `fenceai.api.app.state` global at call
    time, so re-entering that stale `app` under `TestClient` starts writing to
    the reloaded `state` while every helper in the other file still reads the
    old one — whose `.store` is a connection some earlier test already
    closed. `uv run pytest tests/api -q` went from 0 failures to 98 with a
    literal `importlib.reload` here, all of them "connection is closed", none
    of them mentioning this file — which is exactly the shape of poisoning
    Step 3 of the brief warns about. A same-named copy, popped from
    `sys.modules` when done, never touches the real module's globals, so nothing
    outside this test can observe it.
    """
    monkeypatch.setenv("FENCEAI_IDENTITY", "iap")
    monkeypatch.setenv("FENCEAI_IAP_AUDIENCE", "/projects/1/global/backendServices/2")
    import fenceai.api.app as app_module

    name = "_fenceai_app_under_iap_dev_identity_route_test"
    spec = importlib.util.spec_from_file_location(name, app_module.__file__)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        paths = {r.path for r in module.app.routes if hasattr(r, "methods")}
        assert "/api/dev/identity" not in paths
    finally:
        sys.modules.pop(name, None)
