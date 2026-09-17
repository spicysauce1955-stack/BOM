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

from fenceai.api import app as app_module
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
    """The field is gone from the model now, but this pins the shape of what
    the browser gets on every load rather than the accident of what fields
    `User` happens to carry — a hash field re-added here for any reason must
    still never reach this route."""
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


def test_the_people_list_is_refused_to_an_unresolved_caller(nobody):
    """Every account in the company, with their addresses and capacities. The
    assignee picker needs it; a stranger at the door does not."""
    r = nobody.get("/api/users")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "no_identity"


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


def _saves(user_id: str) -> int:
    """How many times this row has been WRITTEN, as the log counts it."""
    return sum(1 for e in state.store.audit_entries(200)
               if e["action"] == "save_user" and e["ref"] == user_id)


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


def test_the_same_account_arriving_again_writes_nothing(client):
    """Counted on the WRITE and not on the `identity_bound` note beside it,
    because those are two statements and only one of them is expensive. Hoisting
    `save_user` out of its branch leaves the note where it is, keeps every other
    assertion green, and costs a database write and an audit row PER REQUEST
    from every person in the company — drowning the log this app's whole audit
    story rests on, in rows recording that nothing happened."""
    _row("goog@example.com", "sales", id="u_goog")
    p = Principal(email="goog@example.com", subject="sub-1")
    resolve(state.store, p)
    after_first = _saves("u_goog")
    resolve(state.store, p)
    resolve(state.store, p)
    assert _saves("u_goog") == after_first


def test_a_different_google_account_on_the_same_address_is_refused(client):
    """An address can be reissued; a `sub` cannot. Refused rather than rebound,
    and the stored subject is left exactly as it was — overwriting it would hand
    the row to whoever holds the address today."""
    _row("goog@example.com", "sales", id="u_goog", subject="sub-1")
    before = _saves("u_goog")
    user, status = resolve(state.store, Principal(email="goog@example.com",
                                                  subject="sub-2"))
    assert status == "subject_mismatch"
    assert state.store.user_by_email("goog@example.com").subject == "sub-1"
    assert any(e["action"] == "subject_mismatch"
               for e in state.store.audit_entries(50))
    # A refusal writes the audit note and NOT the row. `bind` leaves the record
    # untouched on a mismatch, so a save here would be invisible in the data and
    # visible only as a write nobody asked for.
    assert _saves("u_goog") == before


# --- the impersonation switch -------------------------------------------------

def test_the_dev_route_answers_a_browser_that_is_still_nobody(nobody):
    """It sets the cookie `DevIdentity` reads, and nothing else — no secret, no
    session row, no expiry. Registered only under `FENCEAI_IDENTITY=dev`, which
    `tests/conftest.py` sets at import for exactly this reason.

    Driven by a client that is genuinely NOBODY, which is the whole point of its
    exemption: a browser arrives at the picker with no identity at all, and a
    route it must use to GET one cannot require one. Run as the seeded admin
    instead, this test passes with the exemption deleted."""
    client = nobody
    _row("dana@example.com", "sales", id="u_dana")
    assert client.post("/api/dev/identity",
                       json={"email": "Dana@Example.com"}).status_code == 204
    assert DEV_COOKIE in client.cookies
    # The round trip is the assertion, not the stored spelling: an address
    # contains `@`, which `set_cookie` quotes on the way out — so what matters is
    # that the provider reads back the same person on the NEXT request.
    assert client.get("/api/session").json()["user"]["id"] == "u_dana"


# --- the first admin ----------------------------------------------------------
#
# The only way into a production deployment. Under `iap` nothing is seeded, so
# the `users` table of a company that has just deployed is EMPTY — and a gate
# that refuses everybody it cannot resolve would refuse everybody for ever
# without this. These drive the app through a stand-in for IAP rather than the
# dev provider, because the dev provider is exactly the case that seeds three
# accounts and turns the bootstrap off.


class _NotDev:
    """A provider shaped like IAP: it verifies somebody, it carries a subject,
    and it is not `dev`. Substituted at the port, which is what the port is for.
    """

    provider_id = "iap"

    def __init__(self, email: str = "") -> None:
        self.email = email

    def principal(self, headers, cookies):
        if not self.email:
            return None
        return Principal(email=self.email, subject=f"sub-{self.email}")


@pytest.fixture()
def under_iap(monkeypatch):
    """Boot the app on the stand-in, and hand back a `(client, provider)` pair
    so a test can change who is arriving without restarting it."""
    provider = _NotDev()
    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: provider)
    with TestClient(app) as c:
        yield c, provider


def test_a_production_database_is_seeded_with_nobody(under_iap):
    """The C1 regression, and the reason the bootstrap can fire at all. Seeding
    `u_admin` unconditionally put an admin row in every fresh database before
    the first request arrived — which disabled `FENCEAI_BOOTSTRAP_ADMIN` for
    ever and left a real company's first admin with no way in."""
    assert state.store.list_users() == []


def test_the_bootstrap_address_arrives_and_is_admin(under_iap, monkeypatch):
    client, provider = under_iap
    monkeypatch.setenv("FENCEAI_BOOTSTRAP_ADMIN", "founder@example.com")
    provider.email = "founder@example.com"

    assert client.get("/api/projects").status_code == 200
    row = state.store.user_by_email("founder@example.com")
    assert row is not None and row.capacity == "admin"
    assert row.subject == "sub-founder@example.com"
    assert any(e["action"] == "bootstrap_admin"
               for e in state.store.audit_entries(50))


def test_any_other_address_is_not_promoted(under_iap, monkeypatch):
    """It admits ONE named address, not the first arrival. A bootstrap that
    promoted whoever knocked first is a race a stranger can win."""
    client, provider = under_iap
    monkeypatch.setenv("FENCEAI_BOOTSTRAP_ADMIN", "founder@example.com")
    provider.email = "someone.else@example.com"

    r = client.get("/api/projects")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "no_capacity"
    assert state.store.user_by_email("someone.else@example.com") is None


def test_an_admin_anywhere_disables_the_bootstrap(under_iap, monkeypatch):
    """It self-disables the moment the company has an admin of its own, so the
    variable left in a deployment's environment for ever is inert rather than a
    permanent back door."""
    client, provider = under_iap
    state.store.save_user(User(id="u_theirs", name="Theirs",
                               email="theirs@example.com", capacity="admin"))
    monkeypatch.setenv("FENCEAI_BOOTSTRAP_ADMIN", "founder@example.com")
    provider.email = "founder@example.com"

    assert client.get("/api/projects").status_code == 403
    assert state.store.user_by_email("founder@example.com") is None


def test_a_deactivated_only_admin_deployment_is_recovered_by_the_bootstrap(
        under_iap, monkeypatch):
    """The bug: `_bootstrap` used to count EVERY admin row, active or not, as
    blocking — so a deployment whose only admin has been deactivated (a
    restore, a manual edit, any future path) was locked out for ever. No human
    could reach a route that reactivates the row, because `make_gate` refuses
    everybody it cannot resolve, and `_bootstrap` would not fire because an
    admin row still exists.

    Counting only ACTIVE admins as blocking is symmetric with `app.py`'s
    `_would_strand_the_admins`, which already treats an inactive admin as
    nobody who "could still act". A different, row-less address matching
    `FENCEAI_BOOTSTRAP_ADMIN` must now be seated as a fresh admin while the
    only admin on file is inactive."""
    client, provider = under_iap
    state.store.save_user(User(id="u_gone", name="Gone",
                               email="gone@example.com", capacity="admin",
                               active=False))
    monkeypatch.setenv("FENCEAI_BOOTSTRAP_ADMIN", "founder@example.com")
    provider.email = "founder@example.com"

    assert client.get("/api/projects").status_code == 200
    row = state.store.user_by_email("founder@example.com")
    assert row is not None and row.capacity == "admin"
    assert any(e["action"] == "bootstrap_admin"
               for e in state.store.audit_entries(50))


def test_the_deactivated_admins_own_address_is_still_refused_not_resurrected(
        under_iap, monkeypatch):
    """The half that matters: the deactivated admin's OWN address must not be
    quietly re-promoted just because the bootstrap can now fire for somebody
    else. `resolve()` only calls `_bootstrap` for an email with NO existing row
    at all, so `gone@example.com` still resolves to its existing inactive row
    and is still refused with `account_deactivated` — even if, by coincidence
    or attack, `FENCEAI_BOOTSTRAP_ADMIN` were set to that same address. Get
    this wrong and deactivation stops meaning anything."""
    client, provider = under_iap
    state.store.save_user(User(id="u_gone", name="Gone",
                               email="gone@example.com", capacity="admin",
                               active=False))
    monkeypatch.setenv("FENCEAI_BOOTSTRAP_ADMIN", "gone@example.com")
    provider.email = "gone@example.com"

    r = client.get("/api/projects")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "account_deactivated"
    row = state.store.user_by_email("gone@example.com")
    assert row.active is False and row.capacity == "admin"
    assert not any(e["action"] == "bootstrap_admin"
                   for e in state.store.audit_entries(50))


def test_an_existing_row_on_that_address_is_not_promoted(under_iap, monkeypatch):
    """The narrow case that would be a privilege escalation: a `sales` account
    already exists at the named address. It resolves as itself — the bootstrap
    CREATES a row and never edits one, so a variable cannot re-grade somebody."""
    client, provider = under_iap
    state.store.save_user(User(id="u_founder", name="Founder",
                               email="founder@example.com", capacity="sales"))
    monkeypatch.setenv("FENCEAI_BOOTSTRAP_ADMIN", "founder@example.com")
    provider.email = "founder@example.com"

    assert client.get("/api/session").json()["user"]["capacity"] == "sales"
    assert state.store.user_by_email("founder@example.com").capacity == "sales"


def test_the_demo_accounts_are_a_dev_thing(client):
    """The other half of the C1 fix: they still exist where they earn their
    keep. The browser smoke and a laptop need somebody to BE."""
    emails = {u.email for u in state.store.list_users()}
    assert {"dana@example.com", "yossi@example.com",
            "admin@example.com"} <= emails


# --- E3: a boot-time notice when nobody can ever become the first admin ------
#
# Unset is the SAFE state — every deployment past its first admin runs that
# way for the rest of its life — so this is a log line an operator can grep
# for, never a refusal to boot. `capsys` reads the same stdout `print(...,
# flush=True)` already used for "[fenceai] identity provider: …", which
# `TestClient.__enter__` triggers by running `lifespan`.

def test_a_forgotten_bootstrap_variable_is_named_at_boot(monkeypatch, capsys):
    """A fresh `iap` deployment with no admin row and no
    `FENCEAI_BOOTSTRAP_ADMIN` set boots happily and would otherwise refuse
    everybody with `no_capacity` forever, with nothing telling the operator
    what to set. The notice names the variable LITERALLY, so it is
    greppable.

    Built inline rather than from the `under_iap` fixture: `capsys` only
    captures a test's `call` phase, and a fixture's own `TestClient` runs
    `lifespan` — and therefore this print — during `setup`, before `capsys`
    would see it (visible instead under pytest's separate "Captured stdout
    setup" section). This caught itself: the first version of this test used
    `under_iap` and failed with an empty string although the notice was
    firing correctly."""
    provider = _NotDev()
    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: provider)
    with TestClient(app):
        pass
    out = capsys.readouterr().out
    assert "FENCEAI_BOOTSTRAP_ADMIN" in out


def test_the_notice_is_silent_once_the_variable_is_set(monkeypatch, capsys):
    """Unset is what triggers it — not an empty table by itself. A deployment
    that correctly set the variable and simply has not had its first admin
    arrive yet must not be told it forgot something it did not forget."""
    monkeypatch.setenv("FENCEAI_BOOTSTRAP_ADMIN", "founder@example.com")
    provider = _NotDev()
    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: provider)
    with TestClient(app):
        pass
    out = capsys.readouterr().out
    assert "FENCEAI_BOOTSTRAP_ADMIN" not in out


def test_the_notice_is_silent_once_an_admin_exists(under_iap, capsys, monkeypatch):
    """And not once the table already has one — the variable being unset is
    only a problem while it is the only door in."""
    capsys.readouterr()  # discard the first boot's output
    _client, provider = under_iap
    state.store.save_user(User(id="u_admin2", name="Admin Two",
                               email="admin2@example.com", capacity="admin"))
    provider.email = "admin2@example.com"
    with TestClient(app):
        pass
    out = capsys.readouterr().out
    assert "FENCEAI_BOOTSTRAP_ADMIN" not in out


def test_a_boot_with_no_capacity_row_still_refuses(under_iap):
    """E3 is a LOG LINE, not a refusal to boot — the no-capacity wall a
    stranger sees is unchanged."""
    client, provider = under_iap
    provider.email = "stranger@example.com"
    r = client.get("/api/projects")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "no_capacity"


# --- E4: import-time and lifespan-time identity readings can disagree --------
#
# In a real process the two reads of `FENCEAI_IDENTITY` are nil apart and can
# never disagree. `under_iap` substitutes the PROVIDER rather than the
# environment, so `_DEV` (read once, at import, under the suite's own
# `FENCEAI_IDENTITY=dev`) stays `True` while `state.provider.provider_id`
# becomes `"iap"` at `lifespan` — manufacturing, deliberately, the exact
# mismatch E4 exists to warn about.

def test_a_provider_swapped_underneath_the_import_reading_warns(monkeypatch, capsys):
    """Built inline, not from `under_iap` — see the note on the bootstrap
    version of this test for why a fixture's own boot print is invisible to
    `capsys` here."""
    provider = _NotDev()
    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: provider)
    with TestClient(app):
        pass
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "dev" in out and "iap" in out


def test_no_warning_when_the_two_readings_agree(capsys):
    """The ordinary case — the whole suite runs under `dev` at both import and
    startup — must stay quiet, or the warning is noise nobody can act on.

    Built inline rather than from the `client` fixture, and for the same
    reason as the two tests above: a fixture's own boot print happens during
    `setup`, which `capsys` does not see, so checking it there would pass
    vacuously whether or not the line was ever suppressed."""
    with TestClient(app):
        pass
    out = capsys.readouterr().out
    assert "[fenceai] identity provider: dev" in out
    assert "WARNING" not in out


# --- what is not there at all under `iap` -------------------------------------

def _app_module_under(monkeypatch, identity: str):
    """Import `api/app.py` again with a different `FENCEAI_IDENTITY`.

    Two of that module's decisions are made at IMPORT and are absences rather
    than refusals: the impersonation route, and the OpenAPI/docs routes. A
    running app cannot be asked what it would have been, so the only honest test
    loads the module a second time under its own name. Registered in
    `sys.modules` for the duration because pydantic resolves a model's
    annotations through the module its class claims, and popped afterwards so
    nothing else can import this copy by accident.
    """
    import importlib.util
    import sys

    monkeypatch.setenv("FENCEAI_IDENTITY", identity)
    name = f"_fenceai_app_under_{identity}"
    spec = importlib.util.spec_from_file_location(name, app_module.__file__)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _paths(module) -> set[str]:
    return {getattr(r, "path", "") for r in module.app.routes}


def test_the_schema_and_its_two_readers_are_gone_outside_dev(monkeypatch):
    """`/openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc` are
    OUTSIDE the gate and cannot be brought inside it — FastAPI registers them as
    plain `Route`s, so the router's dependencies never reach them. Left on, they
    hand the whole API surface, account administration included, to anybody who
    reaches the service. That is the precise thing verifying IAP's assertion
    exists to stop, so under `iap` they do not exist."""
    prod = _app_module_under(monkeypatch, "iap")
    assert prod.app.openapi_url is None
    assert prod.app.docs_url is None
    assert prod.app.redoc_url is None
    assert not {"/openapi.json", "/docs", "/docs/oauth2-redirect",
                "/redoc"} & _paths(prod)


def test_the_impersonation_route_does_not_exist_outside_dev(monkeypatch):
    """A 404 for a route that exists still tells a stranger the shape of what
    they found. This one is never registered."""
    prod = _app_module_under(monkeypatch, "iap")
    assert "/api/dev/identity" not in _paths(prod)


def test_dev_keeps_the_schema_and_the_switch(monkeypatch):
    """The other direction, or the two tests above would pass against an app
    that had simply lost both features."""
    dev = _app_module_under(monkeypatch, "dev")
    assert dev.app.openapi_url == "/openapi.json"
    assert {"/openapi.json", "/docs", "/redoc", "/api/dev/identity"} <= _paths(dev)


def test_no_route_still_lets_a_caller_name_the_actor():
    """`_actor`'s docstring called it: "an actor a client can NAME is not an
    audit trail". The parameter survived only as the fallback for the
    unsigned-in case, and default-deny deleted that case.

    Checks both shapes this took: a bare `author: str = "..."` route
    parameter (read from the query string), and an `author` field on one of
    app.py's own request DTOs (`AnnotationCreate`, `QuoteCreate`,
    `CorrectionCreate`, `KnowledgeCreate`) that was spread or passed into
    `_actor`'s now-dead `fallback` argument. It does NOT flag `Override.author`
    or `Selection.author` — those are genuine domain fields (who chose or
    overrode something) that never touched `_actor` and must survive; a check
    that flagged every model with a field named "author" would be too broad to
    mean anything and would have to be silenced rather than satisfied."""
    import inspect
    offenders = []
    for route in app_module.app.routes:
        fn = getattr(route, "endpoint", None)
        if fn is None:
            continue
        if "author" in inspect.signature(fn).parameters:
            offenders.append(f"{route.path} ({fn.__name__}): param 'author'")
    for dto_name in ("AnnotationCreate", "QuoteCreate", "CorrectionCreate", "KnowledgeCreate"):
        dto = getattr(app_module, dto_name)
        if "author" in dto.model_fields:
            offenders.append(f"{dto_name}.author")
    assert not offenders, offenders
