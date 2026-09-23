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

