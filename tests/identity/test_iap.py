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
