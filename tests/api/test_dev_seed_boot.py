"""The scenario, staged end to end: a dev database, then an iap boot.

Two `TestClient`s in one test is a shape no other test in this suite uses, and
here it IS the subject — the lockout only exists in the transition. Runs over
both backends through the `dsn` fixture, because the database that will actually
be promoted by mistake is the Postgres one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app
from fenceai.identity.ports import Principal
from fenceai.store.db import Store


class _Iap:
    """Enough of an IdentityProvider to make `lifespan` build an iap-shaped app.
    A stand-in rather than the real adapter, which would want Google's keys."""

    provider_id = "iap"

    def principal(self, headers, cookies):
        return Principal(email="founder@fences.co.il", subject="sub-founder")


def test_a_dev_seeded_database_refuses_to_boot_under_iap(monkeypatch):
    """`tests/api/conftest.py`'s autouse `_isolated_store` has already pointed
    FENCEAI_DB at this run's backend, so both boots below share one database —
    which is the whole scenario."""
    with TestClient(app):
        pass  # a dev boot; `_seed_demo_accounts` writes the three demo rows

    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: _Iap())
    with pytest.raises(RuntimeError) as e:
        with TestClient(app):
            pass

    reason = str(e.value)
    assert "admin@example.com" in reason
    assert "FENCEAI_DB" in reason


def test_a_fresh_database_boots_under_iap_normally(monkeypatch):
    """The refusal must not fire on the arrangement every real first deploy
    has. Nothing has booted this database in dev mode."""
    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: _Iap())
    with TestClient(app) as c:
        assert c.get("/api/health").json()["ok"] is True


def test_the_refusal_survives_a_failing_close(monkeypatch):
    """Protects `lifespan`'s `try: state.store.close() / except Exception:
    pass` around the lockout's `raise`. That wrapper exists so a failing
    close (a dropped connection, a Postgres wobble) cannot swallow the
    sentence that names the remedy — without it, the operator would see
    whatever `close()` raised instead of `dev_seed_lockout`'s message, or a
    hang (removing the `close()` call itself hangs the Postgres leg of
    `test_a_dev_seeded_database_refuses_to_boot_under_iap` at DROP SCHEMA,
    which is a poor regression signal: CI times out rather than fails). This
    was previously proven twice by throwaway scripts, both deleted; this is
    the same experiment, committed."""
    with TestClient(app):
        pass  # a dev boot; seeds the three demo rows including admin@example.com

    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: _Iap())
    real_close = Store.close

    def _raising_close(self) -> None:
        # Actually close the connection (leaving it open is a second,
        # unrelated way to hang a Postgres teardown — the DROP SCHEMA this
        # docstring warns about) and THEN raise, so the test isolates the
        # one thing under test: does a failing close swallow the refusal.
        real_close(self)
        raise RuntimeError("close failed")

    monkeypatch.setattr(Store, "close", _raising_close)
    with pytest.raises(RuntimeError) as e:
        with TestClient(app):
            pass

    reason = str(e.value)
    assert "admin@example.com" in reason
    assert "FENCEAI_DB" in reason
