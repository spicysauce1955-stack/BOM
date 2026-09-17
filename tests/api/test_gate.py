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
from fenceai.api.auth import resolve
from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.model import User
from fenceai.identity.ports import Principal


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def nobody(monkeypatch):
    """A client carrying no identity at all.

    A fixture rather than a line in each test, because emptying
    `FENCEAI_DEV_USER` has to happen BEFORE the client starts: `DevIdentity`
    takes its default address once, when `lifespan` builds the provider, so a
    test that clears the variable against an already-running client is still
    talking to a provider that defaults to the seeded admin — and would pass for
    the wrong reason if the gate were missing.
    """
    monkeypatch.setenv("FENCEAI_DEV_USER", "")
    with TestClient(app) as c:
        c.cookies.clear()
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


def test_a_request_naming_nobody_is_refused(nobody):
    """`no_identity` rather than `no_capacity`: under IAP this is a
    misconfiguration — the proxy should never have let it through — and the two
    want different people to look at them."""
    r = nobody.get("/api/projects")
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


def test_a_write_route_is_refused_too(nobody):
    """The gate is on the app, not on the read routes. A POST that answered
    while a GET refused would be the worst of both."""
    r = nobody.post("/api/projects", json={"name": "A job"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "no_identity"


def test_the_health_check_answers_without_an_identity(nobody):
    """An uptime check cannot hold a Google account."""
    assert nobody.get("/api/health").status_code == 200


def test_the_refusal_screen_can_still_fetch_its_own_words(nobody):
    """Not an exemption — the locale bundles are static files on the mount, and
    router dependencies do not reach a `Mount`. This asserts the property the
    no-access screen depends on: it renders itself in Hebrew for somebody the
    API refuses."""
    r = nobody.get("/i18n/he.json")
    assert r.status_code == 200
    # any long-lived key; the point is that a bundle came back, not which one
    assert "error.topology_changed" in r.json()


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


def test_the_session_route_says_no_identity_for_nobody(nobody):
    """Exempt means it answers, not that it invents somebody."""
    body = nobody.get("/api/session").json()
    assert body["status"] == "no_identity"
    assert body["user"] is None


def test_the_session_route_answers_who_and_which_view(client):
    _row("yossi@example.com", "backoffice", id="u_yossi", name="Yossi")
    _as(client, "yossi@example.com")
    body = client.get("/api/session").json()
    assert body["status"] == "ok"
    assert body["user"]["name"] == "Yossi"
    assert body["view"] == "backoffice"
    assert body["may_choose_view"] is False


def test_the_session_route_never_answers_with_a_password_hash(client):
    """The hash is still on the record until its own task deletes it, and this
    is the route the browser calls on every load. `_public` is what keeps it off
    the wire in the meantime."""
    _row("dana@example.com", "sales")
    _as(client, "dana@example.com")
    assert "password_hash" not in client.get("/api/session").json()["user"]


def test_the_admin_is_offered_the_selector(client):
    _row("admin@example.com", "admin", id="u_admin")
    _as(client, "admin@example.com")
    body = client.get("/api/session").json()
    assert body["view"] == "all"
    assert body["may_choose_view"] is True


def test_a_dev_principal_never_writes_a_subject(client):
    """`DevIdentity` carries no subject, deliberately: there is no Google behind
    it, and binding a fabricated `sub` to a row would refuse the real person's
    first arrival with `subject_mismatch` against a value nobody set. So an
    arrival through the dev provider must leave the column exactly as empty as
    it found it — which is `bind`'s "ok", and `resolve` must not persist on it.
    """
    _row("dana@example.com", "sales")
    _as(client, "dana@example.com")
    assert client.get("/api/session").json()["status"] == "ok"
    assert state.store.user_by_email("dana@example.com").subject == ""


def test_the_password_routes_are_gone(client):
    _row("dana@example.com", "sales")
    _as(client, "dana@example.com")
    assert client.post("/api/session", json={"email": "dana@example.com",
                                             "password": "demo"}).status_code == 405
    assert client.delete("/api/session").status_code == 405
    assert client.get("/api/me").status_code == 404


def test_the_actor_on_a_write_is_the_caller_not_a_parameter(client):
    """`_actor`'s docstring already says it: an actor a client can NAME is not
    an audit trail. With no anonymous case left, the identity is the only
    answer."""
    _row("dana@example.com", "sales", id="u_dana")
    _as(client, "dana@example.com")
    r = client.post("/api/projects", json={"name": "A job"})
    assert r.status_code in (200, 201)
    rows = client.get("/api/audit?limit=20").json()
    assert any(row["actor"] == "user:u_dana" for row in rows)


# --- resolve(), directly ------------------------------------------------------
#
# The gate's own tests can only reach `resolve` through `DevIdentity`, which
# carries no subject by design. These call it with a principal that does, which
# is the only way to exercise the binding branch before IAP is in front of it.

def test_a_subject_is_bound_on_first_arrival_and_persisted(client):
    """`bind` MUTATES the row and reports that it did. This is the point where
    that shape becomes a real bug if the caller gets it wrong: not saving here
    would re-bind the same subject on every request for ever, and the mismatch
    below would have nothing stored to catch a swapped account against."""
    _row("goog@example.com", "sales", id="u_goog")
    user, status = resolve(state.store, Principal(email="goog@example.com",
                                                  subject="sub-1"))
    assert status == "ok"
    assert user.subject == "sub-1"
    assert state.store.user_by_email("goog@example.com").subject == "sub-1"


def test_the_same_account_arriving_again_binds_nothing_more(client):
    """The other half of the same rule: `"ok"` must not persist. One
    `identity_bound` row, however many times she signs in."""
    _row("goog@example.com", "sales", id="u_goog")
    p = Principal(email="goog@example.com", subject="sub-1")
    resolve(state.store, p)
    resolve(state.store, p)
    bound = [e for e in state.store.audit_entries(50)
             if e["action"] == "identity_bound"]
    assert len(bound) == 1


def test_a_different_google_account_on_the_same_address_is_refused(client):
    """An address can be reissued; a `sub` cannot. Refused rather than rebound,
    and the stored subject is left exactly as it was — overwriting it would hand
    the row to whoever holds the address today."""
    _row("goog@example.com", "sales", id="u_goog", subject="sub-1")
    user, status = resolve(state.store, Principal(email="goog@example.com",
                                                  subject="sub-2"))
    assert status == "subject_mismatch"
    assert state.store.user_by_email("goog@example.com").subject == "sub-1"
    assert any(e["action"] == "subject_mismatch"
               for e in state.store.audit_entries(50))


# --- the impersonation switch -------------------------------------------------

def test_the_dev_route_makes_the_browser_somebody(client):
    """It sets the cookie `DevIdentity` reads, and nothing else — no secret, no
    session row, no expiry. Registered only under `FENCEAI_IDENTITY=dev`, which
    `tests/conftest.py` sets at import for exactly this reason."""
    _row("dana@example.com", "sales", id="u_dana")
    client.cookies.clear()
    assert client.post("/api/dev/identity",
                       json={"email": "Dana@Example.com"}).status_code == 204
    assert DEV_COOKIE in client.cookies
    # The round trip is the assertion, not the stored spelling: an address
    # contains `@`, which `set_cookie` quotes on the way out — so what matters is
    # that the provider reads back the same person on the NEXT request.
    assert client.get("/api/session").json()["user"]["id"] == "u_dana"
