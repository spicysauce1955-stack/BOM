"""Accounts and sessions in the store."""

from __future__ import annotations

from fenceai.identity.model import User
from fenceai.identity.session import start
from fenceai.store.db import Store


def _store() -> Store:
    return Store(":memory:")


def _user(**kw) -> User:
    base = dict(id="u_yossi", name="Yossi", email="yossi@example.com",
                capacity="backoffice")
    u = User(**{**base, **kw})
    u.set_password("pw")
    return u


def test_an_account_is_found_by_any_casing_of_its_address():
    """The bug this test was written against: the model kept the address as
    typed, the store lower-cased on write and stripped on read, and the two
    normalisations disagreed — so an account created with a trailing space was
    unreachable from the machine that created it.

    Normalising in `User.email` is what makes one spelling exist; this asserts
    the whole round trip rather than the validator alone.
    """
    s = _store()
    s.save_user(_user(email="  Yossi@Example.COM "))
    for spelling in ("yossi@example.com", "YOSSI@EXAMPLE.COM", " Yossi@Example.com "):
        assert s.user_by_email(spelling) is not None, spelling


def test_an_unknown_address_is_none_rather_than_an_error():
    assert _store().user_by_email("nobody@example.com") is None


def test_saving_an_account_again_updates_it_rather_than_duplicating():
    s = _store()
    s.save_user(_user())
    u = s.user("u_yossi")
    u.capacity = "admin"
    s.save_user(u)
    assert len(s.list_users()) == 1
    assert s.user("u_yossi").capacity == "admin"


def test_the_password_hash_survives_the_round_trip():
    """It is on the model, so it rides in the document. If it did not, every
    stored account would silently become one that can never be signed in to."""
    from fenceai.identity.model import verify_password

    s = _store()
    s.save_user(_user())
    assert verify_password(s.user("u_yossi"), "pw") is True


def test_a_session_resolves_to_its_account_and_stops_when_deleted():
    s = _store()
    s.save_user(_user())
    sess = start("u_yossi")
    s.save_session(sess)
    assert s.session(sess.token).user_id == "u_yossi"
    s.delete_session(sess.token)
    assert s.session(sess.token) is None


def test_deactivating_can_take_every_browser_with_it():
    """`active=False` on its own is a label somebody is still signed in behind.
    Revoking the sessions is the other half, and the store has to be able to do
    it in one call or the caller will do it in a loop and miss one."""
    s = _store()
    s.save_user(_user())
    for _ in range(3):
        s.save_session(start("u_yossi"))
    s.save_session(start("u_dana"))
    assert s.delete_sessions_for("u_yossi") == 3
    assert s.delete_sessions_for("u_yossi") == 0


def test_an_unknown_token_is_none_and_never_a_stranger():
    assert _store().session("not-a-real-token") is None


def test_saving_an_account_names_who_did_it_in_the_audit_log():
    """The column has always been there and has always said `system`. This is
    the first row that can say a person instead."""
    s = _store()
    s.save_user(_user(), actor="user:u_admin")
    entry = [e for e in s.audit_entries(50) if e["action"] == "save_user"][0]
    assert entry["actor"] == "user:u_admin"
    assert entry["ref"] == "u_yossi"
