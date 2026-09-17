# Identity is Google's Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the local password store, take identity from Google through a port, and close all 74 API routes behind a single default-deny dependency — leaving an admin able to grant a capacity.

**Architecture:** An `IdentityProvider` port (`fenceai/identity/ports.py`) with two implementations — `IapIdentity` verifying Google's signed JWT assertion, `DevIdentity` reading a credential-less cookie — mirroring the port-and-stub shape of `fenceai/ai/`. One app-level FastAPI dependency resolves a principal to a `User` row by email, stashes it on `request.state.user`, and refuses with a typed code otherwise. The `users` table stops being an account store and becomes a capacity assignment table; `subject` is bound on first arrival and is verification, never a lookup key.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite/Postgres via `store/dialect.py`, `pyjwt[crypto]` (new, optional extra), vanilla ES modules + SVG frontend.

**Spec:** `docs/superpowers/specs/2026-09-17-identity-is-googles-design.md`
(and its parent, `docs/superpowers/specs/2026-09-17-gcp-deployment-design.md` §5)

## Global Constraints

- **`FENCEAI_IDENTITY` has no default.** It must read `iap` or `dev`; anything else — including unset — refuses to boot, naming both. Precedent: `User.capacity` refuses a default for the same reason.
- **The offline property is not spendable.** `uv sync` with no extras must leave the app and the whole suite working. `pyjwt` goes in a new `iap` optional extra and is imported **inside** `IapIdentity`, never at module scope.
- **Platform refusal codes carry `code` + params.** Every new code needs an `error.<code>` entry in **both** `i18n/en.json` and `i18n/he.json`, whose key sets must stay identical (`tests/web/test_locale_bundles.py`). Follow the existing precedent `error.not_signed_in`, `error.assignee_unknown` — these are refusals, not `warning.*`/`critique.*`, and nothing here is a `DocumentWarning`.
- **Nothing quoted from a document is involved.** Do not touch `core/warnings.py`, `report/annexe.py` or `js/doc-warnings.js`.
- **Integer millimetres and cents at rest** (ADR-0002) — untouched by this slice, but do not introduce a float anywhere.
- **`generate()` stays pure and deterministic.** No task here goes near `fenceai/strategy/`.
- **The integration contract is frozen at v1.3.** contract.md line 502 puts the authentication mechanism explicitly out of scope, so no amendment is needed and no contract file may be edited.
- **ES modules communicate only via `state.js`.** No module touches another's DOM subtree. Every user-visible string goes through `t("key")` or `data-i18n`. CSS logical properties only.
- **Run the suite against both backends.** `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres` before `uv run pytest -q`, or the Postgres half skips silently and green means half a suite.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `src/fenceai/identity/ports.py` | `Principal` record, `IdentityProvider` Protocol. No framework imports. |
| `src/fenceai/identity/dev.py` | `DevIdentity` — cookie, then env var. Credential-less by design. |
| `src/fenceai/identity/iap.py` | `IapIdentity` — verifies `X-Goog-IAP-JWT-Assertion`. Lazy `jwt` import. |
| `src/fenceai/identity/provider.py` | `build_provider()` — reads `FENCEAI_IDENTITY`, refuses anything else. |
| `src/fenceai/identity/binding.py` | `bind(user, principal)` — pure decision about `subject`. |
| `src/fenceai/api/auth.py` | The gate, the refusal codes, the exempt set, the bootstrap admin. |
| `src/fenceai/web/static/js/people.js` | The admin's people panel. Owns `#tab-people` and nothing else. |
| `tests/identity/test_ports.py` | `Principal`, `DevIdentity`, `build_provider`. |
| `tests/identity/test_iap.py` | Offline signature verification against a generated key pair. |
| `tests/identity/test_binding.py` | The three `bind()` outcomes. |
| `tests/api/test_gate.py` | Every refusal code, asked for deliberately. |
| `tests/api/test_dev_identity_route.py` | The dev route, and its absence under `iap`. |
| `tests/api/test_user_admin_routes.py` | Granting, patching, the last-admin guard. |
| `tests/web/test_people_module.py` | Node test for the panel's pure half. |
| `docs/adr/0013-identity-is-delegated.md` | The decision record. |

**Modified:**

| File | Change |
|---|---|
| `src/fenceai/identity/model.py` | `+subject`; `-password_hash`, `-set_password`, `-verify_password`. |
| `src/fenceai/identity/session.py` | **Deleted.** |
| `src/fenceai/store/db.py:79-85` | `sessions` table out of `_SCHEMA`; four session methods deleted. |
| `src/fenceai/api/app.py` | Gate wired; `/api/session` swapped; `/api/me` deleted; user admin routes; eleven `?author=` parameters removed. |
| `src/fenceai/web/static/index.html` | Password field → picker; no-access screen; people tab. |
| `src/fenceai/web/static/app.js` | `wireIdentity()` rewritten for the picker and the no-access screen. |
| `src/fenceai/web/static/js/session.js` | `signIn`→`become`; `loadMe`→`loadSession`; `signOut` redirects. |
| `src/fenceai/web/static/js/view.js` | `people` in `ALL_TABS`; hidden for `sales` and `backoffice`. |
| `src/fenceai/web/static/i18n/{en,he}.json` | New `error.*`, `signin.*`, `noaccess.*`, `people.*`, `tabs.people`. |
| `tests/conftest.py` | Autouse fixture giving every test a dev identity. |
| `tests/api/test_session_routes.py` | Rewritten for the new route. |
| `tests/architecture/test_fitness.py` | The gate fitness test. |
| `docs/architecture/04-backend.md` | Route count, Identity row, table count. |
| `tools/ui_smoke.py` | Persona switching through the picker. |
| `pyproject.toml` | `iap` optional extra. |
| `.env.example` | `FENCEAI_IDENTITY=dev`, `FENCEAI_DEV_USER=`. |

---

### Task 1: The port and its two providers

Pure domain. Nothing in this task touches FastAPI, so it lands green on its own.

**Files:**
- Create: `src/fenceai/identity/ports.py`, `src/fenceai/identity/dev.py`, `src/fenceai/identity/iap.py`, `src/fenceai/identity/provider.py`
- Modify: `pyproject.toml:13-17`
- Test: `tests/identity/test_ports.py`, `tests/identity/test_iap.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Principal(email: str, subject: str)`; `IdentityProvider` Protocol with `provider_id: str` and `principal(headers: Mapping[str, str], cookies: Mapping[str, str]) -> Principal | None`; `DevIdentity(default_email: str = "")`; `IapIdentity(audience: str, fetch_keys: Callable[[], dict[str, Any]] | None = None)`; `build_provider() -> IdentityProvider`; `DEV_COOKIE = "fenceai_dev_user"`.

- [ ] **Step 1: Write the failing tests for the port and `DevIdentity`**

Create `tests/identity/test_ports.py`:

```python
"""The identity port, and the stand-in that keeps the laptop working.

`DevIdentity` is an impersonation switch and is tested as one: it carries no
secret and refuses nothing, because the thing that refuses is the capacity row
it resolves to. Its whole job is to name somebody.
"""

from __future__ import annotations

import pytest

from fenceai.identity.dev import DEV_COOKIE, DevIdentity
from fenceai.identity.ports import Principal
from fenceai.identity.provider import build_provider


def test_a_principal_normalises_its_address_the_way_a_user_does():
    """One spelling of an address in the system, or a row written by one
    casing becomes unreachable from the other — the failure `User._normalised`
    already exists to prevent, repeated here because this is the other end of
    the same lookup."""
    p = Principal(email="  Dana@Example.COM ", subject="sub-1")
    assert p.email == "dana@example.com"


def test_dev_identity_prefers_the_cookie_over_the_environment():
    """The env var is what a bare `uvicorn` opens as; the cookie is how one
    browser becomes somebody else without restarting the server."""
    prov = DevIdentity(default_email="admin@example.com")
    p = prov.principal({}, {DEV_COOKIE: "dana@example.com"})
    assert p is not None and p.email == "dana@example.com"


def test_dev_identity_falls_back_to_the_environment_when_there_is_no_cookie():
    prov = DevIdentity(default_email="admin@example.com")
    p = prov.principal({}, {})
    assert p is not None and p.email == "admin@example.com"


def test_dev_identity_names_nobody_when_nothing_says_who():
    """None is the ordinary answer, not an error. The gate turns it into a
    refusal; a provider that raised would make every caller catch."""
    assert DevIdentity(default_email="").principal({}, {}) is None


def test_dev_identity_carries_no_subject():
    """`subject` is Google's `sub`. There is no Google here, and fabricating
    one would let a dev cookie BIND a subject to a row that real sign-in would
    then be refused against (`subject_mismatch`)."""
    p = DevIdentity(default_email="dana@example.com").principal({}, {})
    assert p is not None and p.subject == ""


def test_the_provider_refuses_to_be_guessed(monkeypatch):
    """No default, and both admissible values named in the refusal. The
    narrowest choice silently locks somebody out and the widest silently lets
    them in — `User.capacity`'s argument, one level up, failing at startup
    rather than per request."""
    monkeypatch.delenv("FENCEAI_IDENTITY", raising=False)
    with pytest.raises(RuntimeError) as e:
        build_provider()
    assert "FENCEAI_IDENTITY" in str(e.value)
    assert "iap" in str(e.value) and "dev" in str(e.value)

    monkeypatch.setenv("FENCEAI_IDENTITY", "sometimes")
    with pytest.raises(RuntimeError):
        build_provider()


def test_the_provider_builds_the_one_it_was_told_to(monkeypatch):
    monkeypatch.setenv("FENCEAI_IDENTITY", "dev")
    monkeypatch.setenv("FENCEAI_DEV_USER", "admin@example.com")
    assert build_provider().provider_id == "dev"

    monkeypatch.setenv("FENCEAI_IDENTITY", "iap")
    monkeypatch.setenv("FENCEAI_IAP_AUDIENCE", "/projects/1/global/backendServices/2")
    assert build_provider().provider_id == "iap"


def test_iap_without_an_audience_refuses_to_boot(monkeypatch):
    """An unchecked `aud` is the difference between "Google signed this" and
    "Google signed this FOR US" — a valid assertion minted for any other
    service would otherwise be accepted."""
    monkeypatch.setenv("FENCEAI_IDENTITY", "iap")
    monkeypatch.delenv("FENCEAI_IAP_AUDIENCE", raising=False)
    with pytest.raises(RuntimeError) as e:
        build_provider()
    assert "FENCEAI_IAP_AUDIENCE" in str(e.value)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/identity/test_ports.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.identity.dev'`

- [ ] **Step 3: Write `ports.py`**

```python
"""What a signed-in person IS, before anything decides what they may do.

Two layers, kept apart on purpose. A provider answers *who is this* from
whatever the transport carries — a signed assertion from Google, a cookie on a
laptop. It answers nothing about permission: the `users` table does that, and
the whole point of this slice is that Google holds the identity and we hold the
capacity.

The signature takes mappings rather than a `Request` so both implementations
are testable without FastAPI — the same split `base-top.js` and `session.js`'s
`applyMe` make on the frontend.
"""

from __future__ import annotations

from typing import Mapping, Protocol

from pydantic import BaseModel, field_validator


class Principal(BaseModel):
    """A verified identity. NOT an account — there may be no row for it."""

    email: str
    #: Google's stable `sub` claim. Empty from a provider that has no Google
    #: behind it, which `binding.bind` treats as "nothing to bind" rather than
    #: as a subject of its own.
    subject: str = ""

    @field_validator("email")
    @classmethod
    def _normalised(cls, v: str) -> str:
        """Stripped and lower-cased HERE, the way `User._normalised` does it.
        The two halves of one lookup have to agree on the spelling, or a row
        written by one casing is unreachable from the other."""
        return v.strip().lower()


class IdentityProvider(Protocol):
    provider_id: str

    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None:
        """Who is this request, or None. Never raises for an absent identity —
        "nobody" is an ordinary answer that the gate turns into a refusal."""
        ...
```

- [ ] **Step 4: Write `dev.py`**

```python
"""Who you are on a laptop.

**This is an impersonation switch and is named as one.** No secret, no session
row, no expiry, nothing that could be mistaken for authentication — it exists
so the app keeps working with no Google, which is the same offline property
`ai/stub.py` protects. Like the stub, it must stay capped: if it ever grows a
credential it has become a second, worse implementation of the thing it stands
in for.

`provider.py` registers it only when `FENCEAI_IDENTITY=dev`, and `api/app.py`
registers `POST /api/dev/identity` on the same condition, so under `iap` the
route does not exist to be found.
"""

from __future__ import annotations

import os
from typing import Mapping

from fenceai.identity.ports import Principal

#: Named for what it is. Not `session`, which would suggest it were one.
DEV_COOKIE = "fenceai_dev_user"


class DevIdentity:
    """Cookie first, environment second.

    The env var is what a bare `uvicorn` opens as, so a developer who has set
    nothing still lands somewhere. The cookie is how ONE browser becomes
    somebody else without restarting the server — which the browser smoke needs,
    because it switches persona mid-run.
    """

    provider_id = "dev"

    def __init__(self, default_email: str = "") -> None:
        self._default = default_email

    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None:
        email = (cookies.get(DEV_COOKIE) or self._default or "").strip()
        if not email:
            return None
        # No subject. There is no Google here, and inventing one would BIND a
        # fabricated `sub` to a row — after which the real person's first
        # arrival is refused with `subject_mismatch` by a database nobody can
        # explain.
        return Principal(email=email, subject="")


def dev_identity_from_env() -> DevIdentity:
    return DevIdentity(default_email=os.environ.get("FENCEAI_DEV_USER", ""))
```

- [ ] **Step 5: Run the `DevIdentity` tests**

Run: `uv run pytest tests/identity/test_ports.py -q -k "dev or principal"`
Expected: PASS for the `Principal` and `DevIdentity` tests; the `build_provider` ones still fail.

- [ ] **Step 6: Write `iap.py`**

```python
"""Google's Identity-Aware Proxy, verified rather than trusted.

`X-Goog-Authenticated-User-Email` is a header, and a header is spoofable by
anything that reaches the service directly — which includes the `*.run.app` URL
Cloud Run publishes alongside the load balancer. So the signed assertion is
verified against Google's public keys AND the deployment locks ingress to
internal-and-load-balancer. Either alone is a hole; this file is the first half.

`jwt` is imported INSIDE the methods. `pyjwt` lives in the optional `iap`
extra, and a module-level import would make `uv sync` with no extras fail to
start the app — spending the offline property CLAUDE.md states, in a file that
only a deployment ever constructs.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Mapping

from fenceai.identity.ports import Principal

IAP_HEADER = "x-goog-iap-jwt-assertion"
_ISSUER = "https://cloud.google.com/iap"
_KEY_URL = "https://www.gstatic.com/iap/verify/public_key"
#: Long enough that every request is not a fetch, short enough that a rotation
#: is picked up without a redeploy.
_KEY_TTL_SECONDS = 3600


class IapIdentity:
    """Verifies the assertion and returns who Google says this is.

    `fetch_keys` is injectable for exactly one reason: a test that needed the
    real Google to run would not be run. The tests generate their own ES256 key
    pair and hand the public half in here, so the signature check under test is
    the real one and only the issuer is fabricated.
    """

    provider_id = "iap"

    def __init__(self, audience: str,
                 fetch_keys: Callable[[], dict[str, Any]] | None = None) -> None:
        if not audience:
            raise RuntimeError(
                "IapIdentity needs an audience: an unchecked `aud` accepts an "
                "assertion Google minted for somebody else's service")
        self._audience = audience
        self._fetch = fetch_keys or self._fetch_google_keys
        self._keys: dict[str, Any] | None = None
        self._fetched_at = 0.0

    def _fetch_google_keys(self) -> dict[str, Any]:
        import json
        import urllib.request
        with urllib.request.urlopen(_KEY_URL, timeout=5) as r:
            return json.loads(r.read())

    def _key_for(self, kid: str) -> Any:
        now = time.time()
        if self._keys is None or now - self._fetched_at > _KEY_TTL_SECONDS:
            self._keys = self._fetch()
            self._fetched_at = now
        return self._keys.get(kid)

    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None:
        import jwt

        token = ""
        for name, value in headers.items():
            if name.lower() == IAP_HEADER:
                token = value
                break
        if not token:
            return None
        try:
            kid = jwt.get_unverified_header(token).get("kid", "")
            key = self._key_for(kid)
            if key is None:
                return None
            claims = jwt.decode(
                token, key, algorithms=["ES256"],
                audience=self._audience, issuer=_ISSUER)
        except Exception:
            # A token we cannot verify is nobody. Not an error the caller must
            # distinguish: "bad signature" and "no header" are the same answer
            # to "who is this", and telling them apart on the wire would say
            # more than a refusal should.
            return None
        email = str(claims.get("email", ""))
        subject = str(claims.get("sub", ""))
        if not email or not subject:
            return None
        return Principal(email=email, subject=subject)


def iap_identity_from_env() -> IapIdentity:
    return IapIdentity(audience=os.environ.get("FENCEAI_IAP_AUDIENCE", ""))
```

- [ ] **Step 7: Write `provider.py`**

```python
"""Which identity this process runs on — decided once, at startup.

`FENCEAI_IDENTITY` has NO DEFAULT, and the refusal names both admissible
values. The precedent is `User.capacity`, which refuses a default because
"there is no safe one: the narrowest silently locks somebody out, the widest
silently lets them in, and both failures are quiet". The same argument holds one
level up, and failing at boot is strictly better than failing per request.
"""

from __future__ import annotations

import os

from fenceai.identity.dev import dev_identity_from_env
from fenceai.identity.ports import IdentityProvider

_CHOICES = ("iap", "dev")


def build_provider() -> IdentityProvider:
    choice = os.environ.get("FENCEAI_IDENTITY", "").strip().lower()
    if choice == "dev":
        return dev_identity_from_env()
    if choice == "iap":
        from fenceai.identity.iap import iap_identity_from_env
        if not os.environ.get("FENCEAI_IAP_AUDIENCE", "").strip():
            raise RuntimeError(
                "FENCEAI_IDENTITY=iap needs FENCEAI_IAP_AUDIENCE: without it "
                "`aud` goes unchecked and an assertion Google minted for "
                "another service is accepted")
        return iap_identity_from_env()
    raise RuntimeError(
        f"FENCEAI_IDENTITY must be one of {_CHOICES}, got {choice!r}. There is "
        "no default: the narrowest silently locks somebody out and the widest "
        "silently lets them in, and both failures are quiet")
```

- [ ] **Step 8: Add the optional extra**

In `pyproject.toml`, after the `postgres` extra (line 17):

```toml
# Only an IAP deployment needs this. Imported inside `identity/iap.py`, never
# at module scope, so `uv sync` with no extras keeps the offline property
# CLAUDE.md states: the app and the whole suite run with nothing installed.
iap = ["pyjwt[crypto]>=2.9,<3"]
```

- [ ] **Step 9: Run the port tests**

Run: `uv run pytest tests/identity/test_ports.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 10: Write the offline IAP signature tests**

Create `tests/identity/test_iap.py`:

```python
"""Real signature verification, fabricated issuer.

A test that needed Google to run would not be run, so these generate an ES256
key pair and hand the public half to `IapIdentity`. What is under test is the
actual `jwt.decode` path — signature, audience, issuer, expiry — with only the
key source replaced.
"""

from __future__ import annotations

import time

import pytest

from fenceai.identity.iap import IAP_HEADER, IapIdentity

jwt = pytest.importorskip("jwt", reason="the `iap` extra is not installed")
pytest.importorskip("cryptography")

AUD = "/projects/1/global/backendServices/2"
KID = "test-key"


@pytest.fixture(scope="module")
def keys():
    from cryptography.hazmat.primitives.asymmetric import ec
    private = ec.generate_private_key(ec.SECP256R1())
    return private, private.public_key()


@pytest.fixture()
def provider(keys):
    _, public = keys
    return IapIdentity(audience=AUD, fetch_keys=lambda: {KID: public})


def _token(private, **overrides):
    claims = {
        "iss": "https://cloud.google.com/iap",
        "aud": AUD,
        "email": "dana@example.com",
        "sub": "accounts.google.com:117",
        "iat": int(time.time()) - 5,
        "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="ES256", headers={"kid": KID})


def test_a_good_assertion_names_the_person(provider, keys):
    private, _ = keys
    p = provider.principal({IAP_HEADER: _token(private)}, {})
    assert p is not None
    assert p.email == "dana@example.com"
    assert p.subject == "accounts.google.com:117"


def test_no_header_is_nobody(provider):
    assert provider.principal({}, {}) is None


def test_a_header_under_any_casing_is_found(provider, keys):
    """ASGI lower-cases header names and a test client may not. Reading the
    map case-sensitively would work in every test and fail in production."""
    private, _ = keys
    assert provider.principal({"X-Goog-IAP-JWT-Assertion": _token(private)}, {})


def test_an_assertion_signed_by_somebody_else_is_nobody(provider):
    from cryptography.hazmat.primitives.asymmetric import ec
    other = ec.generate_private_key(ec.SECP256R1())
    assert provider.principal({IAP_HEADER: _token(other)}, {}) is None


def test_an_assertion_for_another_service_is_nobody(provider, keys):
    """The difference between "Google signed this" and "Google signed this FOR
    US". Without the `aud` check, any other IAP-protected service's token is a
    way in."""
    private, _ = keys
    tok = _token(private, aud="/projects/9/global/backendServices/9")
    assert provider.principal({IAP_HEADER: tok}, {}) is None


def test_an_expired_assertion_is_nobody(provider, keys):
    private, _ = keys
    tok = _token(private, exp=int(time.time()) - 10)
    assert provider.principal({IAP_HEADER: tok}, {}) is None


def test_an_assertion_from_another_issuer_is_nobody(provider, keys):
    private, _ = keys
    tok = _token(private, iss="https://example.com/not-iap")
    assert provider.principal({IAP_HEADER: tok}, {}) is None


def test_an_unknown_key_id_is_nobody(provider, keys):
    private, _ = keys
    tok = jwt.encode({"iss": "https://cloud.google.com/iap", "aud": AUD,
                      "email": "x@y.com", "sub": "1",
                      "exp": int(time.time()) + 60},
                     private, algorithm="ES256", headers={"kid": "rotated-away"})
    assert provider.principal({IAP_HEADER: tok}, {}) is None


def test_an_assertion_with_no_email_is_nobody(provider, keys):
    """A verified token that names nobody cannot be resolved to a row, and
    treating it as a principal would send an empty string to `user_by_email`."""
    private, _ = keys
    assert provider.principal({IAP_HEADER: _token(private, email="")}, {}) is None
```

- [ ] **Step 11: Install the extra and run**

Run: `uv sync --extra postgres --extra iap && uv run pytest tests/identity/test_iap.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 12: Prove the offline property still holds**

Run: `uv run python -c "import fenceai.api.app; import fenceai.identity.provider; print('imports clean')"`
Expected: `imports clean` — nothing at import time reaches `jwt`.

- [ ] **Step 13: Commit**

```bash
git add src/fenceai/identity/ports.py src/fenceai/identity/dev.py \
        src/fenceai/identity/iap.py src/fenceai/identity/provider.py \
        tests/identity/test_ports.py tests/identity/test_iap.py pyproject.toml
git commit -m "feat(identity): a port, a proxy that is verified, and a stand-in that is not"
```

---

### Task 2: `subject`, and the decision to bind it

Still pure domain. `User` gains a field and loses nothing yet — the password machinery is still referenced by `app.py` and comes out in Task 5.

**Files:**
- Modify: `src/fenceai/identity/model.py:56-100`
- Create: `src/fenceai/identity/binding.py`
- Test: `tests/identity/test_binding.py`

**Interfaces:**
- Consumes: `Principal` from Task 1.
- Produces: `User.subject: str`; `bind(user: User, principal: Principal) -> Literal["ok", "bound", "mismatch"]`, which MUTATES `user.subject` only on `"bound"`.

- [ ] **Step 1: Write the failing test**

Create `tests/identity/test_binding.py`:

```python
"""Binding Google's `sub` to a row that was created by email.

Rows are found by EMAIL, because an admin grants Dana her capacity on Monday and
Dana arrives on Tuesday. `subject` is therefore verification and not a key — it
answers "is this still the same Google account?" and nothing else.
"""

from __future__ import annotations

from fenceai.identity.binding import bind
from fenceai.identity.model import User
from fenceai.identity.ports import Principal


def _row(**kw) -> User:
    return User(id="u_dana", name="Dana", email="dana@example.com",
                capacity="sales", **kw)


def test_an_empty_subject_binds_on_first_arrival():
    user = _row()
    assert bind(user, Principal(email="dana@example.com", subject="sub-1")) == "bound"
    assert user.subject == "sub-1"


def test_the_same_subject_arriving_again_changes_nothing():
    user = _row(subject="sub-1")
    assert bind(user, Principal(email="dana@example.com", subject="sub-1")) == "ok"
    assert user.subject == "sub-1"


def test_a_different_subject_on_the_same_address_is_refused():
    """The address belonged to one Google account and now presents another —
    a deleted-and-recreated Workspace account, or something worth a person
    looking at. An admin reconciles it; the app never does, because silently
    rebinding would hand the row to whoever holds the address today."""
    user = _row(subject="sub-1")
    assert bind(user, Principal(email="dana@example.com", subject="sub-2")) == "mismatch"
    assert user.subject == "sub-1", "a refused binding must not have written"


def test_a_principal_with_no_subject_binds_nothing_and_refuses_nothing():
    """`DevIdentity` carries no subject. It must neither bind an empty string
    (which would then mismatch the real `sub` for ever) nor be refused against
    a row a real sign-in has already bound."""
    fresh = _row()
    assert bind(fresh, Principal(email="dana@example.com", subject="")) == "ok"
    assert fresh.subject == ""

    bound = _row(subject="sub-1")
    assert bind(bound, Principal(email="dana@example.com", subject="")) == "ok"
    assert bound.subject == "sub-1"


def test_subject_defaults_to_empty_on_a_row_nobody_has_signed_in_as():
    assert _row().subject == ""
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/identity/test_binding.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.identity.binding'`

- [ ] **Step 3: Add `subject` to `User`**

In `src/fenceai/identity/model.py`, immediately after the `capacity` field and before `active`:

```python
    #: Google's stable `sub` claim, bound on this person's first arrival and
    #: never used to FIND them. Rows are created by email, because an admin
    #: grants Dana her capacity before Dana has ever signed in. This is the
    #: field that then answers "is this still the same Google account?" —
    #: see `identity/binding.py`. Empty means nobody has arrived yet.
    subject: str = ""
```

- [ ] **Step 4: Write `binding.py`**

```python
"""Is this arrival the same Google account the row was bound to?

One pure function with three answers, kept out of the gate so the decision can
be read and tested without a request. The gate turns `"mismatch"` into a 403 and
persists the row on `"bound"`.
"""

from __future__ import annotations

from typing import Literal

from fenceai.identity.model import User
from fenceai.identity.ports import Principal

Outcome = Literal["ok", "bound", "mismatch"]


def bind(user: User, principal: Principal) -> Outcome:
    """`"bound"` means the caller must SAVE the row; `"ok"` means it must not.

    A principal with no subject binds nothing. `DevIdentity` has no Google
    behind it, and writing its empty string as a subject would make the real
    person's first arrival a `mismatch` against a value nobody set.
    """
    if not principal.subject:
        return "ok"
    if not user.subject:
        user.subject = principal.subject
        return "bound"
    return "ok" if user.subject == principal.subject else "mismatch"
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/identity/test_binding.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the identity suite and the API suite**

Run: `uv run pytest tests/identity tests/api -q`
Expected: PASS — `subject` has a default, so every existing row still validates.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/identity/model.py src/fenceai/identity/binding.py \
        tests/identity/test_binding.py
git commit -m "feat(identity): User.subject, bound on first arrival and never used to find a row"
```

---

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

### Task 5: Delete the password machinery

Nothing references it after Task 3. This task is pure subtraction, and a reviewer can accept Task 3 and reject this one.

**Files:**
- Modify: `src/fenceai/identity/model.py` (remove `password_hash`, `set_password`, `verify_password`, the scrypt constants, `hashlib`/`hmac`/`os` imports)
- Delete: `src/fenceai/identity/session.py`
- Modify: `src/fenceai/store/db.py:79-85` and `:952-975`
- Modify: `src/fenceai/api/app.py:2140-2161` (`_seed_demo_accounts`)
- Modify: `tests/identity/test_user.py`, `tests/identity/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a `User` with no credential; a `Store` with no session methods.

- [ ] **Step 1: Write the failing test**

Append to `tests/identity/test_user.py`:

```python
def test_an_account_carries_no_credential_at_all():
    """Not "an empty password" — no field. Google holds the identity; this row
    holds what that identity may do. A credential here would be the second
    password this slice exists to delete."""
    u = User(id="u_dana", name="Dana", email="dana@example.com", capacity="sales")
    assert not hasattr(u, "password_hash")
    assert not hasattr(u, "set_password")
    assert "password" not in u.model_dump()


def test_the_model_module_offers_no_way_to_verify_one():
    import fenceai.identity.model as model
    assert not hasattr(model, "verify_password")


def test_there_is_no_session_module_left():
    import importlib
    import pytest
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fenceai.identity.session")
```

Append to `tests/store/test_dialect.py` (or `tests/identity/test_store.py`):

```python
def test_the_store_no_longer_keeps_sessions():
    """The row WAS the session, and there are no sessions. An existing SQLite
    file keeps its table — dropping it from the baseline does not remove it,
    and per the deployment spec §4 that is not worth a migration — but nothing
    creates or reads one."""
    from fenceai.store import db
    assert "CREATE TABLE IF NOT EXISTS sessions" not in db._SCHEMA
    for name in ("save_session", "session", "delete_session", "delete_sessions_for"):
        assert not hasattr(db.Store, name), name
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/identity tests/store/test_dialect.py -q`
Expected: FAIL on all four new tests.

- [ ] **Step 3: Strip the credential from `User`**

In `src/fenceai/identity/model.py`: delete the `password_hash` field, `set_password`, `verify_password`, `_SCRYPT`, `_SALT_BYTES`, and the now-unused `hashlib`, `hmac` and `os` imports. Update the `User` docstring — it currently says *"`verify_password` refuses it"*, which will name a function that no longer exists:

```python
    """A person with an account.

    **Deactivated, never deleted.** The audit log names people who have left the
    company, so a row has to keep resolving to a name for ever. `active=False`
    is what a company does instead, and `api/auth.py`'s gate refuses it — the
    two halves of that decision belong together or deactivating becomes a label
    somebody still signs in behind.

    **There is no credential here.** Google holds the identity; this row holds
    what that identity may DO. `subject` records which Google account it was
    bound to and is never used to find the row.
    """
```

- [ ] **Step 4: Delete `session.py` and the store's session half**

```bash
git rm src/fenceai/identity/session.py
```

In `src/fenceai/store/db.py`, delete the `sessions` table from `_SCHEMA` (lines 81-85, comment included) and the four session methods (lines 952-975). Rename the section comment at line 928 from `-- accounts and sessions` to `-- capacity assignments`, and add above `save_user`:

```python
    # The `users` table is no longer an account store. Google holds the
    # identity; a row here says what an identity may DO. `sessions` was deleted
    # with the password store — an existing SQLite file keeps the table, which
    # nothing creates or reads.
```

- [ ] **Step 5: Make the demo rows passwordless**

In `src/fenceai/api/app.py`, replace the `DEMO_ACCOUNTS` comment and `_seed_demo_accounts`:

```python
#: One capacity row per capacity, so a fresh database has somebody to be. They
#: carry NO credential, which is what makes them safe to keep: under IAP a row
#: only matters if Google authenticates that address, and `example.com` is
#: IANA-reserved, so nobody ever can. A real deployment grants its own people
#: through `POST /api/users` and these three never resolve.
DEMO_ACCOUNTS = [
    ("u_dana", "Dana", "dana@example.com", "sales"),
    ("u_yossi", "Yossi", "yossi@example.com", "backoffice"),
    ("u_admin", "Admin", "admin@example.com", "admin"),
]


def _seed_demo_accounts() -> None:
    """Only on an empty table. A company that has made its own accounts must
    never find three strangers in the list after an upgrade."""
    if state.store.list_users():
        return
    for uid, name, email, capacity in DEMO_ACCOUNTS:
        state.store.save_user(
            User(id=uid, name=name, email=email, capacity=capacity), actor="seed")
```

Delete `DEMO_PASSWORD`.

- [ ] **Step 6: Purge the remaining references**

Run: `grep -rn "password\|set_password\|verify_password\|DEMO_PASSWORD\|identity.session\|fenceai_session" src/ tests/ tools/`
Expected: only `autocomplete="username"` in `index.html` (Task 8 removes the password input) and the new tests asserting absence. Fix `tests/identity/test_store.py`, `tests/api/test_command_route.py` and `tests/api/test_queue_route.py` by replacing `_account(..., password=...)` + `_sign_in(...)` with a saved `User` and `client.cookies.set(DEV_COOKIE, email)`.

- [ ] **Step 7: Run the full suite**

Run: `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres && uv run pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -u src/fenceai/identity/model.py src/fenceai/store/db.py \
        src/fenceai/api/app.py tests/identity tests/store/test_dialect.py \
        tests/api/test_command_route.py tests/api/test_queue_route.py
git commit -m "refactor(identity): delete the password store, the sessions table and the cookie"
```

---

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

### Task 7: The eleven `?author=` parameters

**Files:**
- Modify: `src/fenceai/api/app.py` — lines 914, 1215, 1292, 1387, 1626, 1697, 1763, 1783, 1818, 1841, 1860
- Modify: any test passing `?author=`

**Interfaces:**
- Consumes: `_actor` (Task 3).
- Produces: eleven routes whose actor is the caller and nothing else.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_gate.py`:

```python
def test_no_route_still_lets_a_caller_name_the_actor():
    """`_actor`'s docstring called it: "an actor a client can NAME is not an
    audit trail". The parameter survived only as the fallback for the
    unsigned-in case, and default-deny deleted that case."""
    import inspect
    from fenceai.api import app as app_module
    offenders = []
    for route in app_module.app.routes:
        fn = getattr(route, "endpoint", None)
        if fn is None:
            continue
        if "author" in inspect.signature(fn).parameters:
            offenders.append(f"{route.path} ({fn.__name__})")
    assert not offenders, offenders
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/api/test_gate.py::test_no_route_still_lets_a_caller_name_the_actor -q`
Expected: FAIL listing eleven routes.

- [ ] **Step 3: Remove them one file-scan at a time**

For each of the eleven sites, delete the `author: str = "user"` (or `"expert"`) parameter and replace every use of `author` in the body with `_actor(request)`. Add `request: Request` to any handler that does not already take one. Example, at line 1292:

```python
# before
def accept_quote(request: Request, quote_id: str, author: str = "user") -> Quote:
    ...
    state.store.save_quote(q, actor=_actor(request, author))

# after
def accept_quote(request: Request, quote_id: str) -> Quote:
    ...
    state.store.save_quote(q, actor=_actor(request))
```

- [ ] **Step 4: Run it again**

Run: `uv run pytest tests/api/test_gate.py::test_no_route_still_lets_a_caller_name_the_actor -q`
Expected: PASS.

- [ ] **Step 5: Fix the callers**

Run: `grep -rn "author=" tests/ tools/ src/fenceai/web/`
Expected: every hit is a test or a frontend `fetch` passing the query. Delete the parameter from each; the actor is now the caller.

- [ ] **Step 6: Run the full suite**

Run: `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres && uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -u src/fenceai/api/app.py src/fenceai/web/static tests/
git commit -m "refactor(api): the actor is the caller, at all eleven sites that let it be named"
```

---

### Task 8: The frontend — picker, banner, no-access screen

**Files:**
- Modify: `src/fenceai/web/static/index.html:14-27`, `src/fenceai/web/static/app.js:64-118,186`, `src/fenceai/web/static/js/session.js`, `src/fenceai/web/static/style.css`
- Modify: `src/fenceai/web/static/i18n/en.json`, `src/fenceai/web/static/i18n/he.json`
- Test: `tests/web/test_login_screen.py` (extend), `tests/web/test_locale_bundles.py` (passes as-is)

**Interfaces:**
- Consumes: `GET /api/session`, `POST /api/dev/identity` (Tasks 3-4).
- Produces: `loadSession() -> boolean`; `become(email) -> "ok" | "refused" | "unreachable"`; `signOut()`; `sessionState(body)` pure, returning `{user, view, selector, status, email}`.

- [ ] **Step 1: Write the failing node test**

Create `tests/web/test_session_module.py`. **There is no shared `run_node` helper** — copy `tests/web/test_base_top_module.py`'s shape exactly: a module-scoped `SCRIPT` string, run through `node --input-type=module -e` with `cwd=STATIC`, returning parsed JSON from one `console.log`.

```python
"""`session.js`'s pure half, in node.

`sessionState` decides nothing about what may be DONE — it answers which
screen this is and who to name on it. Pure, so node can check it without a
browser: `base-top.js`'s split applied again.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { sessionState } from "./js/session.js";

const out = {};
out.ok = sessionState({status:"ok", email:"d@e.com",
                       user:{id:"u1", name:"Dana", capacity:"sales"},
                       view:"sales", may_choose_view:false});
out.none = sessionState({status:"no_capacity", email:"s@e.com", user:null});
out.off = sessionState({status:"deactivated", email:"g@e.com", user:null});
out.anon = sessionState({status:"no_identity", email:"", user:null});
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def ss():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_resolved_answer_carries_the_person_and_their_view(ss):
    assert ss["ok"]["user"]["name"] == "Dana"
    assert ss["ok"]["view"] == "sales"
    assert ss["ok"]["selector"] is False


def test_a_refused_answer_names_the_address_but_nobody(ss):
    """The screen that says "ask an admin" has to be able to name you TO the
    admin you are about to ask — so `email` survives where `user` does not."""
    assert ss["none"]["status"] == "no_capacity"
    assert ss["none"]["email"] == "s@e.com"
    assert ss["none"]["user"] is None


def test_deactivated_is_its_own_answer_and_not_no_capacity(ss):
    """They HAVE a row. Telling them to ask for access would send them asking
    for something they already have."""
    assert ss["off"]["status"] == "deactivated"


def test_nobody_at_all_leaves_the_view_alone(ss):
    """`view: null` means *leave it alone*, and that is the point rather than a
    missing value — returning "all" here made every unsigned page load
    overwrite the remembered toggle, which the browser smoke caught once
    already."""
    assert ss["anon"]["status"] == "no_identity"
    assert ss["anon"]["view"] is None
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/web/test_session_module.py -q`
Expected: FAIL — `sessionState` is not exported.

- [ ] **Step 3: Rewrite `session.js`'s exported surface**

Replace the header comment and the four functions. Keep `applyMe`'s successor pure; keep `lastProjectKey` and `pickProject` exactly as they are.

```javascript
// Who is signed in. The ONE module that talks to `/api/session` — everything
// else reads `state.me` or listens for `signed-in` / `signed-out`.
//
// **Google holds the identity; we hold the capacity.** There is no password
// here and no session cookie of ours. Under `iap` a signed assertion names the
// person before the request reaches the app; under `dev` a credential-less
// cookie does, set by the picker below. Either way this module asks one
// question — `GET /api/session` — and the server answers who, which view, and
// whether there is a capacity row at all.
//
// **Every API route now refuses a caller with no capacity row.** The screen is
// no longer the only thing between somebody and the data, which is what it
// was when it shipped.

/** What a `/api/session` answer means for the screen. Pure, for node. */
export function sessionState(body) {
  const ok = body.status === "ok";
  return {
    status: body.status,
    email: body.email || "",
    user: ok ? body.user : null,
    view: ok ? body.view : null,
    selector: ok ? body.may_choose_view : true,
  };
}

/** Ask who we are.
 *  @returns false when the server could not be reached at all — the caller
 *  must SAY so, or the page is a picker that silently does nothing. */
export async function loadSession() {
  let r;
  try {
    r = await fetch("/api/session");
  } catch {
    await apply(sessionState({ status: "no_identity", user: null }));
    return false;
  }
  if (!r.ok) {
    await apply(sessionState({ status: "no_identity", user: null }));
    return true;
  }
  await apply(sessionState(await r.json()));
  return true;
}

/** Become somebody, on a laptop. There is no credential: `POST
 *  /api/dev/identity` exists only under `FENCEAI_IDENTITY=dev`, and under
 *  `iap` this returns "refused" because the route is not there.
 *  @returns `"ok"`, `"refused"`, or `"unreachable"`. */
export async function become(email) {
  let r;
  try {
    r = await fetch("/api/dev/identity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
  } catch {
    return "unreachable";
  }
  if (!r.ok) return "refused";
  return (await loadSession()) ? "ok" : "unreachable";
}

/** Signing out stops being ours.
 *
 *  IAP keeps the promise better than a row we delete — revoking access is
 *  removing the grant, centrally, for every device at once — but the APP
 *  cannot do it. So this is a redirect, not a DELETE. Under `dev` there is a
 *  cookie to clear and nothing to revoke.
 */
export async function signOut() {
  try { await fetch("/api/dev/identity", { method: "DELETE" }); } catch { /* iap */ }
  location.href = "/?gcp-iap-mode=CLEAR_LOGIN_COOKIE";
}
```

Update `apply()` to take the new shape and set `document.documentElement.dataset.auth`:

```javascript
async function apply(shape) {
  state.me = shape.user;
  state.mayChooseView = shape.selector;
  state.authStatus = shape.status;
  state.authEmail = shape.email;
  document.documentElement.dataset.selector = shape.selector ? "yes" : "no";
  if (shape.view) {
    const { setView } = await import("./view.js");
    setView(shape.view);
  }
  emit(shape.user ? "signed-in" : "signed-out", shape.user);
}
```

Add `DELETE /api/dev/identity` to `app.py` beside the POST (same `if`), clearing the cookie and returning 204.

- [ ] **Step 4: Replace the form in `index.html`**

```html
  <!-- The front door. Google decides who reaches it; a capacity row decides
       what they may do once inside. Under `dev` this is a picker with no
       password — an impersonation switch, and named as one. `html[data-auth]`
       drives the hiding (style.css), `app.js` sets it. -->
  <section id="login-screen" aria-labelledby="login-title">
    <form id="sign-in">
      <h1 id="login-title">Fence AI</h1>
      <input id="sign-in-email" type="email" autocomplete="username" required
             data-i18n-placeholder="signin.email" placeholder="Email">
      <button type="submit" class="primary" data-i18n="signin.become">Continue</button>
      <p id="sign-in-error" class="warning error" hidden data-i18n="error.no_identity"></p>
      <p id="sign-in-unreachable" class="warning error" hidden data-i18n="error.server_unreachable"></p>
    </form>
  </section>

  <!-- IAP let them to the door; nobody has said what they may do inside. -->
  <section id="no-access" aria-labelledby="no-access-title" hidden>
    <h1 id="no-access-title" data-i18n="noaccess.title">No access yet</h1>
    <p data-i18n="noaccess.body">Ask an administrator to give this address access.</p>
    <p><span data-i18n="noaccess.signed_in_as">Signed in as</span>
       <bdi id="no-access-email" class="sku"></bdi></p>
    <button id="no-access-signout" data-i18n="signin.out">Sign out</button>
  </section>
```

- [ ] **Step 5: Rewrite `wireIdentity()` in `app.js`**

```javascript
function wireIdentity() {
  const form = document.getElementById("sign-in");
  const chip = document.getElementById("signed-in-as");
  const err = document.getElementById("sign-in-error");
  const unreachable = document.getElementById("sign-in-unreachable");
  const noAccess = document.getElementById("no-access");

  const render = () => {
    const me = state.me;
    const refused = state.authStatus === "no_capacity" ||
                    state.authStatus === "deactivated" ||
                    state.authStatus === "subject_mismatch";
    document.documentElement.dataset.auth = me ? "in" : (refused ? "denied" : "out");
    chip.hidden = !me;
    noAccess.hidden = !refused;
    if (refused)
      document.getElementById("no-access-email").textContent = state.authEmail;
    if (!me) return;
    document.getElementById("me-name").textContent = me.name;
    document.getElementById("me-capacity").textContent =
      t(`signin.capacity.${me.capacity}`);
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    unreachable.hidden = true;
    const outcome = await become(document.getElementById("sign-in-email").value);
    if (outcome === "refused") err.hidden = false;
    else if (outcome === "unreachable") unreachable.hidden = false;
  });
  document.getElementById("sign-out").addEventListener("click", signOut);
  document.getElementById("no-access-signout").addEventListener("click", signOut);

  on("signed-in", async () => { render(); await openWorkspace(); });
  on("signed-out", render);
  on("project-opened", (id) => {
    if (!state.me) return;
    try { localStorage.setItem(lastProjectKey(state.me.id), id); } catch { /* storage off */ }
  });
}
```

Change the import at line 31 to `import { become, lastProjectKey, loadSession, pickProject, signOut } from "./js/session.js";` and line 186 to `if (!(await loadSession()))`.

- [ ] **Step 6: Add the `denied` state to `style.css`**

Beside the existing `data-auth` rules, keyed on NOT so `pending` still hides everything:

```css
/* Three states now, not two. Keyed on :not() for the reason the other two
   are: a rule written as [data-auth="denied"] #no-access would flash the
   refusal on every signed-in reload. */
html:not([data-auth="denied"]) #no-access { display: none; }
html[data-auth="denied"] body > :not(#no-access) { display: none; }
```

- [ ] **Step 7: Add the locale keys to BOTH bundles**

`en.json` — add, and delete `signin.password` and `error.sign_in_failed`:

```json
"signin.become": "Continue",
"error.no_identity": "This browser is not signed in.",
"error.no_capacity": "This address has no access here yet.",
"error.account_deactivated": "This account has been deactivated.",
"error.subject_mismatch": "This address is registered to a different Google account. Ask an administrator.",
"error.capacity_insufficient": "You do not have permission to do that.",
"error.user_exists": "Somebody already has that address.",
"error.user_not_found": "No such person.",
"error.last_admin": "This is the only administrator left.",
"noaccess.title": "No access yet",
"noaccess.body": "Ask an administrator to give this address access.",
"noaccess.signed_in_as": "Signed in as",
"tabs.people": "People",
"people.title": "Who may use this",
"people.add": "Give somebody access",
"people.name": "Name",
"people.email": "Email",
"people.capacity": "May do",
"people.active": "Active",
"people.deactivate": "Deactivate",
"people.reactivate": "Reactivate",
"people.never_signed_in": "has not signed in yet"
```

`he.json` — the same keys, Hebrew values:

```json
"signin.become": "המשך",
"error.no_identity": "הדפדפן הזה אינו מחובר.",
"error.no_capacity": "לכתובת הזו אין עדיין גישה כאן.",
"error.account_deactivated": "החשבון הזה הושבת.",
"error.subject_mismatch": "הכתובת רשומה לחשבון Google אחר. פנו למנהל.",
"error.capacity_insufficient": "אין לכם הרשאה לפעולה הזו.",
"error.user_exists": "הכתובת הזו כבר שייכת למישהו.",
"error.user_not_found": "אין אדם כזה.",
"error.last_admin": "זה המנהל האחרון שנותר.",
"noaccess.title": "אין עדיין גישה",
"noaccess.body": "בקשו ממנהל לתת גישה לכתובת הזו.",
"noaccess.signed_in_as": "מחוברים בתור",
"tabs.people": "אנשים",
"people.title": "מי רשאי להשתמש",
"people.add": "תנו למישהו גישה",
"people.name": "שם",
"people.email": "דוא״ל",
"people.capacity": "רשאי/ת",
"people.active": "פעיל",
"people.deactivate": "השבתה",
"people.reactivate": "הפעלה מחדש",
"people.never_signed_in": "עדיין לא התחבר/ה"
```

- [ ] **Step 8: Update `test_login_screen.py`**

Replace `test_the_login_screen_holds_the_form_and_the_header_does_not` assertions about the password field, and add:

```python
def test_the_front_door_asks_for_no_password():
    """There is none. A field for one would be asking for a secret the system
    cannot check and must never store."""
    html = (STATIC / "index.html").read_text()
    assert 'type="password"' not in html
    assert "sign-in-password" not in html


def test_a_refused_arrival_gets_a_screen_of_their_own():
    """Not a blank app and not the picker again. IAP let them to the door;
    this is the screen that tells them what to ask for."""
    html = (STATIC / "index.html").read_text()
    assert 'id="no-access"' in html
    assert 'data-i18n="noaccess.body"' in html
    css = _css()
    assert re.search(
        r'html:not\(\[data-auth="denied"\]\)\s+#no-access\s*\{\s*display:\s*none', css)
    assert re.search(
        r'html\[data-auth="denied"\]\s+body\s*>\s*:not\(#no-access\)\s*\{\s*display:\s*none', css)
```

- [ ] **Step 9: Run the web tests**

Run: `uv run pytest tests/web -q`
Expected: PASS, including `test_locale_bundles.py`'s identical-key-set check.

- [ ] **Step 10: Commit**

```bash
git add src/fenceai/web/static tests/web
git commit -m "feat(web): a front door with no password, and a screen for somebody nobody has granted"
```

---

### Task 9: The people panel

**Files:**
- Create: `src/fenceai/web/static/js/people.js`
- Modify: `src/fenceai/web/static/index.html` (tab button + `#tab-people`), `src/fenceai/web/static/app.js` (init), `src/fenceai/web/static/js/view.js:52-123`
- Test: `tests/web/test_people_module.py`

**Interfaces:**
- Consumes: `GET /api/users`, `POST /api/users`, `PATCH /api/users/{id}` (Task 6); `esc` from `api.js`; `t` from `i18n.js`.
- Produces: `initPeople()`; `peopleRows(users) -> [{id, name, email, capacity, active, bound}]` pure.

- [ ] **Step 1: Write the failing node test**

Same shape as Task 8 Step 1 — a module-scoped `SCRIPT`, `node --input-type=module -e`, `cwd=STATIC`. There is no `run_node` helper to call.

```python
SCRIPT = """
import { peopleRows } from "./js/people.js";
console.log(JSON.stringify(peopleRows([
  {id:"u1", name:"Dana", email:"d@e.com", capacity:"sales",
   active:true, subject:"sub-1"},
  {id:"u2", name:"New", email:"n@e.com", capacity:"sales",
   active:true, subject:""},
  {id:"u3", name:"Gone", email:"g@e.com", capacity:"backoffice",
   active:false, subject:"sub-3"},
])));
"""


def test_a_grant_nobody_has_used_says_so(rows):
    """An empty `subject` is a row an admin made that nobody has signed in
    against yet — the normal state between granting and arriving, and the one
    an admin hunting a mistyped address has to be able to see."""
    assert [r["bound"] for r in rows] == [True, False, True]


def test_a_deactivated_person_is_still_listed(rows):
    """Deactivated, never deleted: the audit log names people who have left, so
    a row must keep resolving to a name for ever. A panel that hid them would
    make reactivating impossible."""
    assert rows[2]["active"] is False
    assert rows[2]["name"] == "Gone"
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/web/test_people_module.py -q`
Expected: FAIL — no such module.

- [ ] **Step 3: Write `people.js`**

```javascript
// Who may use this, and what each of them may do. The admin's panel, and the
// only screen in the app that WRITES a capacity.
//
// Owned entirely by this module: nothing else touches `#tab-people`, and this
// touches no other subtree. It talks to the rest of the app through `state.js`
// alone.
//
// Hiding this tab for a non-admin is a PRESENTATION fact and no protection at
// all — `POST /api/users` checks the capacity on the server, and that check is
// the one that matters. `view.js` carries the same paragraph.

import { apiGet, apiSend, esc } from "./api.js";
import { t } from "./i18n.js";
import { state } from "./state.js";

/** Pure, for node: what a row on this screen SAYS. */
export function peopleRows(users) {
  return (users || []).map((u) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    capacity: u.capacity,
    active: u.active,
    // Bound means somebody has actually signed in against this row. An admin
    // hunting a mistyped address needs to see which grants nobody has used.
    bound: Boolean(u.subject),
  }));
}

function rowHtml(r) {
  const never = r.bound ? "" :
    ` <span class="muted">(${esc(t("people.never_signed_in"))})</span>`;
  return `<tr data-user="${esc(r.id)}"${r.active ? "" : ' class="inactive"'}>
    <td>${esc(r.name)}</td>
    <td><bdi class="sku">${esc(r.email)}</bdi>${never}</td>
    <td>${capacitySelect(r)}</td>
    <td><button class="toggle">${esc(t(r.active ? "people.deactivate"
                                               : "people.reactivate"))}</button></td>
  </tr>`;
}
```

Complete the module with `capacitySelect`, `render`, `initPeople` (a `change` listener PATCHing the capacity, a `click` listener toggling `active`, and a form POSTing a new grant), each refusal rendered by `t("error." + code)`.

- [ ] **Step 4: Add the tab**

In `index.html`, after the `models` button (line 67):

```html
    <button data-tab="people" data-i18n="tabs.people">People</button>
```

and a `<section id="tab-people" class="tab">` holding an `<h2 data-i18n="people.title">`, a `<table id="people-table">` and an add form with email, name and a capacity `<select>`.

In `view.js`, add `"people"` to `ALL_TABS`, and `'[data-tab="people"]'` to both `SALES_HIDDEN` and `BACKOFFICE_HIDDEN` — the admin view is the only one that shows it.

In `app.js`, call `initPeople()` beside `initEvidence()`.

- [ ] **Step 5: Run the web tests**

Run: `uv run pytest tests/web -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static tests/web/test_people_module.py
git commit -m "feat(web): the people panel — the one screen that writes a capacity"
```

---

### Task 10: Fitness test, docs, ADR, and the smoke suite

**Files:**
- Modify: `tests/architecture/test_fitness.py`, `docs/architecture/04-backend.md:135-160`, `tools/ui_smoke.py`, `.env.example`
- Create: `docs/adr/0013-identity-is-delegated.md`

**Interfaces:**
- Consumes: `EXEMPT_PATHS` (Task 3).
- Produces: nothing new.

- [ ] **Step 1: Write the failing fitness test**

Append to `tests/architecture/test_fitness.py`:

```python
def test_every_api_route_is_gated_by_the_app_itself():
    """Not route by route. Seventy routes were born ungated by omission, and
    the only fix that cannot be forgotten is one dependency on the app."""
    from fastapi import Depends
    from fenceai.api.app import app
    assert app.router.dependencies, "the app carries no gate"


def test_the_exempt_list_is_exactly_what_it_should_be():
    """An exemption is a hole, so adding one is a deliberate edit HERE as well
    as there. Each of these four has a sentence in `api/auth.py` saying why."""
    from fenceai.api.auth import EXEMPT_PATHS
    assert EXEMPT_PATHS == frozenset({
        "/api/health", "/api/session", "/api/dev/identity",
    })


def test_every_exempt_path_is_a_route_that_exists():
    """An exemption for a path nobody serves is a stale hole waiting for a
    route to be added onto it."""
    from fenceai.api.auth import EXEMPT_PATHS
    assert EXEMPT_PATHS <= _route_paths()
```

- [ ] **Step 2: Run the architecture suite**

Run: `uv run pytest tests/architecture -q`
Expected: FAIL on the route count and route table tests (the routes changed), PASS on the three new ones.

- [ ] **Step 3: Update `04-backend.md`**

Change `74 routes.` at line 135 to the number the test reports. Replace the Identity row (line 157) with:

```
| Identity | `GET /api/session`, `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST/DELETE /api/dev/identity` (dev only) | **Google holds the identity; a row here holds the capacity.** There is no password in this app and no session of ours: under `iap` a signed `X-Goog-IAP-JWT-Assertion` names the person before the request arrives, verified against Google's keys with the `aud` checked, because the plain header is spoofable by anything that reaches the service directly. `users` is a capacity assignment table — rows are created BY EMAIL before that person has ever signed in, and `subject` (Google's `sub`) binds on first arrival and is never used to FIND a row. A subject arriving on an address bound to a different one is `subject_mismatch`, refused and audited, because an admin reconciles that and the app must not hand the row to whoever holds the address today. **Every route in this table is gated**: one app-level dependency refuses `no_identity` · `no_capacity` · `account_deactivated` · `subject_mismatch` · `capacity_insufficient`, and the exempt list is four paths pinned by `tests/architecture/test_fitness.py`. `GET /api/session` is the one that answers without a row, because the screen telling somebody to ask an admin has to name them to the admin they are about to ask. Signing out is a redirect to IAP's logout — revoking access is central and for every device at once, which the app could never promise; `active=False` is the local half that still refuses. `FENCEAI_BOOTSTRAP_ADMIN` admits the first admin and self-disables the moment one exists |
```

Update the table count line if the `sessions` table removal changed it.

- [ ] **Step 4: Run the architecture suite again**

Run: `uv run pytest tests/architecture -q`
Expected: PASS.

- [ ] **Step 5: Write ADR-0013**

Create `docs/adr/0013-identity-is-delegated.md` following ADR-0012's shape: context (a local password store and 70 open routes behind a login screen), decision (delegate identity to Google through a port; make `users` a capacity table; default-deny at the app), consequences (signing out stops being ours; `active=False` is the local half; a dev provider keeps the offline property; per-capacity authorization is still a separate slice), and alternatives rejected (mirroring Google accounts locally; auto-creating every IAP arrival as `sales`; gating route by route).

- [ ] **Step 6: Update `.env.example`**

```
# No default. Must be `dev` or `iap`, or the app refuses to boot.
FENCEAI_IDENTITY=dev
# Who a bare `uvicorn` opens as, when no picker cookie has been set.
FENCEAI_DEV_USER=admin@example.com
# IAP only: the backend service the assertion must be addressed to.
FENCEAI_IAP_AUDIENCE=
# Set for the first deploy, removed after. Self-disables once an admin exists.
FENCEAI_BOOTSTRAP_ADMIN=
```

- [ ] **Step 7: Move the smoke suite onto the picker**

In `tools/ui_smoke.py`: launch the server with `FENCEAI_IDENTITY=dev`; replace the two `fetch('/api/session', {method:'POST', ... password ...})` calls (around lines 2673 and 3680) with `fetch('/api/dev/identity', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email:'dana@example.com'})})`; replace the `DELETE /api/session` (line 2690) with `DELETE /api/dev/identity`; and delete the line setting `sign-in-password`.

- [ ] **Step 8: Run the smoke suite**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: every check passes. A failure here is a real one — this is the only place the picker, the no-access screen and the people panel are exercised in a browser.

- [ ] **Step 9: Run everything**

Run: `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres && uv run pytest -q && uv run pytest tests/scenarios -q && uv run pytest tests/architecture -q`
Expected: all PASS.

- [ ] **Step 10: Verify the offline and zero-setup properties**

Run:
```bash
cd $(mktemp -d) && git clone <repo> fa && cd fa && uv sync && \
  FENCEAI_IDENTITY=dev FENCEAI_DEV_USER=admin@example.com \
  uv run python -c "
from fastapi.testclient import TestClient
from fenceai.api.app import app
with TestClient(app) as c:
    print(c.get('/api/session').json()['status'])"
```
Expected: `ok` — a clean clone, no extras, no Postgres, no Google, and the app resolves the seeded admin.

- [ ] **Step 11: Commit**

```bash
git add tests/architecture/test_fitness.py docs/architecture/04-backend.md \
        docs/adr/0013-identity-is-delegated.md .env.example tools/ui_smoke.py
git commit -m "docs(adr): ADR-0013, the route table, and a smoke suite with no password in it"
```

---

### Task 11: Review and checkpoint

- [ ] **Step 1: Run both project reviewers**

Per CLAUDE.md, this slice touches domain abstractions and the frontend contracts, so both are required before declaring it done:

```
architecture-critic: review this slice against docs/product/architecture-foundation-v0.1.md §15
and docs/superpowers/specs/2026-09-17-identity-is-googles-design.md
test-reviewer: review the tests added in this slice for weak assertions and missing invariants
```

They mutate the code. Re-run the full suite after each, and do not treat green at the previous count as evidence that nothing moved.

- [ ] **Step 2: Update `plan/current-status.md`** with the slice-2 checkpoint.

- [ ] **Step 3: The checkpoint is a person watching it work.** Green tests are not the checkpoint. Run the app, sign in as Dana through the picker, confirm she lands on the sales view; become a stranger and confirm the no-access screen names them; become the admin, grant the stranger `sales`, and confirm they get in.

```bash
FENCEAI_IDENTITY=dev FENCEAI_DEV_USER=admin@example.com \
  uv run uvicorn fenceai.api.app:app --reload
```

- [ ] **Step 4: Open the PR** once the product owner has seen it run.

---

## Self-Review

**Spec coverage.** §2 the port → Task 1. §2.1 `IapIdentity` in this slice → Task 1 Steps 6, 10-11. §3 what leaves → Task 5 (with the passwordless seed and the left-behind `sessions` table both stated). §4 default-deny, the five codes, the exempt list, the fitness test → Tasks 3 and 10. §5 the laptop, the cookie, the picker, sign-out as a redirect → Tasks 3, 4 and 8. §6 granting, the two routes, the panel, the bootstrap admin's three conditions → Tasks 3 (`_bootstrap`) and 6 and 9. §7 binding and the three outcomes → Task 2. §8 `?author=` → Task 7. §9 testing — conftest, every refusal deliberately, offline IAP tests, dev precedence, the route's absence under `iap`, the fitness test, node tests, the smoke, both bundles → Tasks 1-10. §10 what this does not do → nothing to build. §11 the contract → untouched, and no task edits it.

**Two claims in the first draft were wrong and are corrected in place.** There is no `/api/i18n/{lang}` route — `_locale_bundle` is an internal helper and the browser loads `i18n/<lang>.json` off the static mount, so the exempt list is three paths and the refusal screen renders in Hebrew because the mount was never gated. And there is no shared `run_node` test helper: every node test in `tests/web/` builds its own module-scoped `SCRIPT` and runs `node --input-type=module -e` with `cwd=STATIC`. Both were checked against the tree rather than assumed, which is the only reason they are not in the plan an implementer would have followed.

**Known gaps, stated rather than hidden.** Task 9's `people.js` is given as a skeleton with its pure half complete and its rendering half described — the panel's exact markup depends on the table styling in `style.css`, and inventing it here would be a fixture written blind. Task 10 Step 3's route count is deliberately not a number: the test reports it, and writing a guess into a plan is how the doc came to claim 47 routes over a 51-route app in the first place.

**Type consistency.** `Principal(email, subject)` is constructed in Tasks 1, 2 and 3 with the same two fields. `bind(user, principal) -> "ok" | "bound" | "mismatch"` is defined in Task 2 and consumed in Task 3's `resolve` only. `resolve(store, principal) -> (User | None, str)` is defined in Task 3's `auth.py` and imported into `app.py` as `auth_resolve` in the same task. `DEV_COOKIE` is defined once in Task 1 and imported by Tasks 3, 4, 6 and the tests. `sessionState(body)` is exported in Task 8 and tested in Task 8. `peopleRows(users)` is exported in Task 9 and tested in Task 9. `current_user` / `require_admin` are defined in Task 3 and used in Tasks 3, 6 and 7.
