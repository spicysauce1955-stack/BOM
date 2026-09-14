"""Sessions: opaque, server-side, and revocable."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fenceai.identity.session import SESSION_DAYS, Session, is_live, new_token, start

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)


def test_a_token_is_long_and_never_the_same_twice():
    """Guessability is the whole risk. Two tokens colliding would sign one
    person in as another."""
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 32 for t in tokens)


def test_a_token_carries_nothing_about_the_account():
    """Opaque, so that signing out can actually sign out: the server forgets the
    row. A self-describing token would stay valid in a pocket until it expired,
    which makes "deactivate this account" a promise we cannot keep."""
    s = start("u_yossi", now=NOW)
    assert "yossi" not in s.token
    assert "u_" not in s.token


def test_a_fresh_session_is_live_and_an_old_one_is_not():
    s = start("u_yossi", now=NOW)
    assert is_live(s, now=NOW) is True
    assert is_live(s, now=NOW + timedelta(days=SESSION_DAYS - 1)) is True
    assert is_live(s, now=NOW + timedelta(days=SESSION_DAYS, seconds=1)) is False


def test_an_unreadable_expiry_is_dead_rather_than_live():
    """A row we cannot parse is not a reason to let somebody in. This repo keeps
    finding the opposite shape — a null cache reading as a clean bill of health
    — and this is the same decision made the other way."""
    assert is_live(Session(token="t", user_id="u", created_at="",
                           expires_at="not a date"), now=NOW) is False


def test_an_expiry_with_no_timezone_is_dead_rather_than_guessed():
    """A naive timestamp is ambiguous by exactly the offset nobody wrote down.
    Guessing UTC would silently extend or shorten every session written by a
    process that forgot — so it refuses instead."""
    naive = Session(token="t", user_id="u", created_at="",
                    expires_at="2099-01-01T00:00:00")
    assert is_live(naive, now=NOW) is False
