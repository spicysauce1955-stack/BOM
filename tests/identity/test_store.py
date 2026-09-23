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


def test_two_creations_of_one_address_conflict_rather_than_raising(store):
    """A double-click on the people screen's submit button, at store level.

    `users.email` is UNIQUE while `save_user`'s upsert targets `id` only, so two
    `save_user` calls with a fresh id and the same address raised the DRIVER's
    `IntegrityError` — a different class per backend, sharing no base but
    `Exception` (`store/dialect.py`), which is why no route caught it and the
    admin got a 500 for a refusal that already has a locale string. This asserts
    the CONFLICT rather than the exception: `create_user_guarded` does the check
    and the insert under one lock and answers `user_exists`.

    Both backends, because the constraint and the upsert are both SQL: SQLite
    reporting the conflict while Postgres reported a duplicate row, or the other
    way round, is the exact drift the `dsn`/`backend` fixtures exist to catch.
    """
    first, status = store.create_user_guarded(
        _user(id="u_one", email="dana@example.com"), actor="user:u_admin")
    assert status == "ok"
    assert first is not None

    second, status = store.create_user_guarded(
        _user(id="u_two", email="dana@example.com"), actor="user:u_admin")
    assert status == "user_exists"
    assert second is None

    # One row, and it is the FIRST one — a conflict must not have half-applied.
    assert [u.id for u in store.list_users()] == ["u_one"]


def test_a_refused_creation_writes_no_audit_row(store):
    """The refusal is not an event that happened to somebody's account.

    Worth pinning separately because the guard returns early, before the two
    `_audit` calls — and an audit log naming a grant that was never made would
    be worse than no line at all, since `audit_log` is the record that has to
    keep resolving for people who have left.
    """
    store.create_user_guarded(_user(id="u_one", email="dana@example.com"),
                             actor="user:u_admin")
    before = len(store.audit_entries(200))
    store.create_user_guarded(_user(id="u_two", email="dana@example.com"),
                              actor="user:u_admin")
    assert len(store.audit_entries(200)) == before


def test_creating_an_account_is_still_found_by_any_casing(store):
    """`create_user_guarded` reads `users.email` directly rather than going
    through `user_by_email`, so it needs its own proof that the two spellings
    agree — the SELECT compares against `User.email`'s normalised value, and a
    guard that missed a differently-cased duplicate would let the UNIQUE
    constraint raise after all, which is the whole failure it replaces."""
    store.create_user_guarded(_user(id="u_one", email="  Dana@Example.COM "))
    assert store.create_user_guarded(
        _user(id="u_two", email="dana@example.com"))[1] == "user_exists"
    assert store.user_by_email("DANA@example.com") is not None


def test_saving_an_account_names_who_did_it_in_the_audit_log(store):
    """The column has always been there and has always said `system`. This is
    the first row that can say a person instead."""
    store.save_user(_user(), actor="user:u_admin")
    entry = [e for e in store.audit_entries(50) if e["action"] == "save_user"][0]
    assert entry["actor"] == "user:u_admin"
    assert entry["ref"] == "u_yossi"
