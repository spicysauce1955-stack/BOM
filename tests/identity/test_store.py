"""Accounts in the store. There are no sessions any more — see
`test_the_store_no_longer_keeps_sessions`."""

from __future__ import annotations

from fenceai.identity.model import User


def _user(**kw) -> User:
    base = dict(id="u_yossi", name="Yossi", email="yossi@example.com",
                capacity="backoffice")
    return User(**{**base, **kw})


def test_an_account_is_found_by_any_casing_of_its_address(store):
    """The bug this test was written against: the model kept the address as
    typed, the store lower-cased on write and stripped on read, and the two
    normalisations disagreed — so an account created with a trailing space was
    unreachable from the machine that created it.

    Normalising in `User.email` is what makes one spelling exist; this asserts
    the whole round trip rather than the validator alone.
    """
    store.save_user(_user(email="  Yossi@Example.COM "))
    for spelling in ("yossi@example.com", "YOSSI@EXAMPLE.COM", " Yossi@Example.com "):
        assert store.user_by_email(spelling) is not None, spelling


def test_an_unknown_address_is_none_rather_than_an_error(store):
    assert store.user_by_email("nobody@example.com") is None


def test_saving_an_account_again_updates_it_rather_than_duplicating(store):
    store.save_user(_user())
    u = store.user("u_yossi")
    u.capacity = "admin"
    store.save_user(u)
    assert len(store.list_users()) == 1
    assert store.user("u_yossi").capacity == "admin"


def test_the_store_no_longer_keeps_sessions():
    """The row WAS the session, and there are no sessions. An existing SQLite
    file keeps its table — dropping it from the baseline does not remove it,
    and per the deployment spec §4 that is not worth a migration — but nothing
    creates or reads one."""
    from fenceai.store import db

    assert "CREATE TABLE IF NOT EXISTS sessions" not in db._SCHEMA
    for name in ("save_session", "session", "delete_session", "delete_sessions_for"):
        assert not hasattr(db.Store, name), name


def test_saving_an_account_names_who_did_it_in_the_audit_log(store):
    """The column has always been there and has always said `system`. This is
    the first row that can say a person instead."""
    store.save_user(_user(), actor="user:u_admin")
    entry = [e for e in store.audit_entries(50) if e["action"] == "save_user"][0]
    assert entry["actor"] == "user:u_admin"
    assert entry["ref"] == "u_yossi"
