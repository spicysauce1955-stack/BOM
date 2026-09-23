"""A database created in dev mode cannot be served under `iap`.

Slice 2's reviews found this by running the code: the dev seed writes an ACTIVE
admin row at an IANA-reserved address, `_bootstrap` fires only while no active
admin exists, and no Google account can ever authenticate as
`admin@example.com`. Every request is refused and the only cure is database
surgery.
"""

from __future__ import annotations

from fenceai.identity.dev import DEMO_ACCOUNTS, dev_seed_lockout
from fenceai.identity.model import User


def _demo_rows() -> list[User]:
    return [User(id=uid, name=name, email=email, capacity=cap)
            for uid, name, email, cap in DEMO_ACCOUNTS]


def test_dev_mode_is_never_refused_its_own_seed():
    """The whole point of the seed is that a developer lands somewhere."""
    assert dev_seed_lockout("dev", _demo_rows()) is None


def test_iap_refuses_a_database_holding_the_dev_seed():
    reason = dev_seed_lockout("iap", _demo_rows())
    assert reason is not None
    assert "admin@example.com" in reason
    assert "FENCEAI_DB" in reason, "the message must name the remedy, not just the fault"


def test_iap_is_content_with_a_database_of_real_accounts():
    """A company's own rows are what this must never refuse. Ids here are the
    shape `POST /api/users` actually mints."""
    real = [User(id="u_3f9a1c22", name="Dana", email="dana@fences.co.il",
                 capacity="sales"),
            User(id="u_b71e0d84", name="Yossi", email="yossi@fences.co.il",
                 capacity="admin")]
    assert dev_seed_lockout("iap", real) is None


def test_an_empty_database_is_the_normal_first_deploy():
    assert dev_seed_lockout("iap", []) is None


def test_a_demo_id_is_caught_even_at_a_company_address():
    """The id is the precise half of the fingerprint. `POST /api/users` mints
    `u_{uuid4().hex[:8]}` — hex — and `admin`, `dana` and `yossi` are not hex,
    so a real grant can never collide with one of these."""
    disguised = [User(id="u_admin", name="Admin", email="boss@fences.co.il",
                      capacity="admin")]
    assert dev_seed_lockout("iap", disguised) is not None


def test_a_demo_address_is_caught_even_under_a_minted_id():
    """And the address is the belt. `example.com` is IANA-reserved, so no Google
    account can hold one however the row got its id."""
    disguised = [User(id="u_3f9a1c22", name="Admin", email="ADMIN@example.com",
                      capacity="admin")]
    assert dev_seed_lockout("iap", disguised) is not None
