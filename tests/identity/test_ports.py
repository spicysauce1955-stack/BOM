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
