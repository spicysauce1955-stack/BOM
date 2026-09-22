"""Binding Google's `sub` to a row that was created by email.

Rows are found by EMAIL, because an admin grants Dana her capacity on Monday and
Dana arrives on Tuesday. `subject` is therefore verification and not a key — it
answers "is this still the same Google account?" and nothing else.
"""

from __future__ import annotations

from fenceai.identity.binding import bind
from fenceai.identity.model import User
from fenceai.identity.ports import Principal


def _row(**kw) -> User:
    return User(id="u_dana", name="Dana", email="dana@example.com",
                capacity="sales", **kw)


def test_an_empty_subject_binds_on_first_arrival():
    user = _row()
    assert bind(user, Principal(email="dana@example.com", subject="sub-1")) == "bound"
    assert user.subject == "sub-1"


def test_the_same_subject_arriving_again_changes_nothing():
    user = _row(subject="sub-1")
    assert bind(user, Principal(email="dana@example.com", subject="sub-1")) == "ok"
    assert user.subject == "sub-1"


def test_a_different_subject_on_the_same_address_is_refused():
    """The address belonged to one Google account and now presents another —
    a deleted-and-recreated Workspace account, or something worth a person
    looking at. An admin reconciles it; the app never does, because silently
    rebinding would hand the row to whoever holds the address today."""
    user = _row(subject="sub-1")
    assert bind(user, Principal(email="dana@example.com", subject="sub-2")) == "mismatch"
    assert user.subject == "sub-1", "a refused binding must not have written"


def test_a_principal_with_no_subject_binds_nothing_and_refuses_nothing():
    """`DevIdentity` carries no subject. It must neither bind an empty string
    (which would then mismatch the real `sub` for ever) nor be refused against
    a row a real sign-in has already bound."""
    fresh = _row()
    assert bind(fresh, Principal(email="dana@example.com", subject="")) == "ok"
    assert fresh.subject == ""

    bound = _row(subject="sub-1")
    assert bind(bound, Principal(email="dana@example.com", subject="")) == "ok"
    assert bound.subject == "sub-1"


def test_subject_defaults_to_empty_on_a_row_nobody_has_signed_in_as():
    assert _row().subject == ""
