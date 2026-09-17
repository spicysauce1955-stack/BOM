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


def test_an_assertion_missing_exp_is_nobody(provider, keys):
    """PyJWT only checks a claim's VALUE when the claim is present — `exp`
    absent is not the same failure as `exp` expired, and without `require` it
    verifies fine. A correctly signed assertion that simply omits `exp` would
    otherwise be trusted forever instead of for the hour Google intends."""
    private, _ = keys
    claims = {
        "iss": "https://cloud.google.com/iap",
        "aud": AUD,
        "email": "dana@example.com",
        "sub": "accounts.google.com:117",
        "iat": int(time.time()) - 5,
    }
    tok = jwt.encode(claims, private, algorithm="ES256", headers={"kid": KID})
    assert provider.principal({IAP_HEADER: tok}, {}) is None


def test_an_hs256_token_signed_with_the_public_key_is_nobody(provider, keys):
    """The classic asymmetric-to-symmetric confusion attack: anyone who knows
    the EC public key can mint an HS256 token whose "signature" is just an
    HMAC over that same public key, and a verifier that trusts the token's own
    `alg` header would accept it as genuinely Google's.

    **This test proves the end-to-end refusal, not that `algorithms=["ES256"]`
    is what causes it — it is NOT the pin's regression net.** Confirmed by
    widening `iap.py`'s `algorithms=["ES256"]` to include `"HS256"` and
    re-running this test: it still passes, but refused for the wrong reason —
    the `provider` fixture's `_key_for` hands `jwt.decode` a `cryptography` EC
    key OBJECT (not the PEM string production actually gets from gstatic), and
    with HS256 now permitted PyJWT raises `TypeError: Expected a string value`
    trying to HMAC an object it can't treat as key material. Handed a PEM
    STRING instead (`test_fetch_keys_returning_a_pem_string_still_resolves`'s
    shape), the same widened list raises PyJWT's OWN
    `InvalidKeyError: ... should not be used as an HMAC secret` instead — a
    different guard, still not this file's pin. Either way, the refusal
    survives widening the algorithm list, so this test alone cannot detect
    that regression. `test_the_algorithm_pin_is_exactly_es256` below is the
    one that actually depends on the pin.

    Forged by hand rather than via `jwt.encode`: PyJWT's encoder applies that
    same PEM-as-HMAC-secret guard at encode time too, which would have
    prevented constructing the forged token in the first place rather than
    testing what `principal()` does with one already in hand. An attacker
    computing the HMAC directly bypasses the encoder-side guard; only the
    decoder-side ones (and, if they were ever removed, the algorithm pin)
    stand between that forged token and a `Principal`.
    """
    import base64
    import hashlib
    import hmac as hmac_mod
    import json

    from cryptography.hazmat.primitives import serialization

    _, public = keys
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header = {"alg": "HS256", "typ": "JWT", "kid": KID}
    claims = {
        "iss": "https://cloud.google.com/iap",
        "aud": AUD,
        "email": "dana@example.com",
        "sub": "accounts.google.com:117",
        "iat": int(time.time()) - 5,
        "exp": int(time.time()) + 600,
    }
    signing_input = (b64url(json.dumps(header, separators=(",", ":")).encode())
                      + "." + b64url(json.dumps(claims, separators=(",", ":")).encode()))
    signature = hmac_mod.new(pem, signing_input.encode(), hashlib.sha256).digest()
    forged = signing_input + "." + b64url(signature)

    assert provider.principal({IAP_HEADER: forged}, {}) is None


def test_an_alg_none_token_is_nobody(provider):
    """The other classic JWT attack: a token that declares it needs no
    signature at all.

    **This is not the pin's regression net either.** Confirmed by widening
    `iap.py`'s `algorithms` to include `"none"` and re-running: still passes,
    but refused by PyJWT's own
    `InvalidKeyError: When alg = "none", key value must be None` — `_key_for`
    hands `jwt.decode` a real key, and PyJWT refuses to pair `alg: none` with
    a non-`None` key regardless of whether `"none"` is an allowed algorithm.
    The refusal here is end-to-end and worth keeping, but it is PyJWT's guard
    doing the work, not this file's pin — see
    `test_the_algorithm_pin_is_exactly_es256` for the test that depends on
    the pin itself.
    """
    claims = {
        "iss": "https://cloud.google.com/iap",
        "aud": AUD,
        "email": "dana@example.com",
        "sub": "accounts.google.com:117",
        "iat": int(time.time()) - 5,
        "exp": int(time.time()) + 600,
    }
    tok = jwt.encode(claims, None, algorithm="none", headers={"kid": KID})
    assert provider.principal({IAP_HEADER: tok}, {}) is None


def test_the_algorithm_pin_is_exactly_es256(provider, keys, monkeypatch):
    """The actual regression net for `algorithms=["ES256"]` in `principal()`.

    The two attack tests above (`..._hs256_..._is_nobody`,
    `..._alg_none_token_is_nobody`) prove the end-to-end refusal, but PyJWT's
    own key-type guards do that work for them — both keep passing even when
    `algorithms` is widened to include `"HS256"` and `"none"` (verified; see
    the fix report). This test is the one that is actually sensitive to the
    pin: it captures the `algorithms` keyword `principal()` passes into
    `jwt.decode` and asserts it is exactly `["ES256"]`, which is the only
    thing that fails if that list is ever widened, independent of whether
    PyJWT's own guards happen to catch a given forged token anyway.
    """
    private, _ = keys
    captured: dict[str, object] = {}
    real_decode = jwt.decode

    def spy(*args, **kwargs):
        captured["algorithms"] = kwargs.get("algorithms")
        return real_decode(*args, **kwargs)

    monkeypatch.setattr(jwt, "decode", spy)

    assert provider.principal({IAP_HEADER: _token(private)}, {}) is not None
    assert captured["algorithms"] == ["ES256"]


def test_fetch_keys_returning_a_pem_string_still_resolves(keys):
    """Production gets PEM STRINGS back from gstatic's JSON response; every
    other test in this file hands `IapIdentity` the `cryptography` object
    directly, which is not the shape the real endpoint ever produces. This is
    the one test that drives `_fetch_google_keys`'s actual return type."""
    private, public = keys
    from cryptography.hazmat.primitives import serialization
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    prov = IapIdentity(audience=AUD, fetch_keys=lambda: {KID: pem})
    p = prov.principal({IAP_HEADER: _token(private)}, {})
    assert p is not None
    assert p.email == "dana@example.com"


def test_a_stale_key_fetch_failure_still_resolves_within_the_grace_window(monkeypatch, keys):
    """A gstatic blip must not turn into "nobody" for every caller while the
    keys already cached are still the ones that verified a signature moments
    ago. Only the grace window's expiry — not the TTL alone — should."""
    private, public = keys
    calls = {"n": 0}

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            return {KID: public}
        raise RuntimeError("gstatic blip")

    clock = {"t": 0.0}
    monkeypatch.setattr("fenceai.identity.iap.time.monotonic", lambda: clock["t"])

    prov = IapIdentity(audience=AUD, fetch_keys=flaky_fetch)
    assert prov.principal({IAP_HEADER: _token(private)}, {}) is not None

    # Past the TTL, comfortably inside the grace window: the refresh this
    # triggers fails, and the still-good cached key must still be served.
    clock["t"] = 3600 + 60 + 1
    assert prov.principal({IAP_HEADER: _token(private)}, {}) is not None
    assert calls["n"] == 2


def test_a_stale_key_fetch_failure_refuses_once_past_the_grace_window(monkeypatch, keys):
    """Past the grace window, a key Google may since have rotated away is no
    longer trustworthy enough to accept a signature against — the fallback
    that keeps a blip from locking everyone out must not become a fallback
    that never expires."""
    private, public = keys
    calls = {"n": 0}

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            return {KID: public}
        raise RuntimeError("gstatic blip")

    clock = {"t": 0.0}
    monkeypatch.setattr("fenceai.identity.iap.time.monotonic", lambda: clock["t"])

    prov = IapIdentity(audience=AUD, fetch_keys=flaky_fetch)
    assert prov.principal({IAP_HEADER: _token(private)}, {}) is not None

    # Far enough past the TTL that the grace window itself has elapsed.
    clock["t"] = 3600 + 6 * 3600 + 1
    assert prov.principal({IAP_HEADER: _token(private)}, {}) is None
