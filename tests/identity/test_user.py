"""Who an account is, and what it may do — the first thing in this repo that is
a PERMISSION rather than a preference.

`view.js` insists, twice, that its `view` is "a PRESENTATION preference,
emphatically not a permission". `capacity` is the other half of that sentence,
and these tests exist to keep the two from sliding back together.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.identity.model import CAPACITIES, SYSTEM, User, actor_ref, is_agent


def _user(**kw) -> User:
    base = dict(id="u_yossi", name="Yossi", email="yossi@example.com",
                capacity="backoffice")
    return User(**{**base, **kw})


# --- the capacity vocabulary -------------------------------------------------

def test_the_three_capacities_are_the_accounts_the_company_issues():
    """`sales | backoffice | admin`. Deliberately NOT the view list: a view is
    `all` for everybody who is allowed to choose it, and no account is ever
    issued as `all`."""
    assert CAPACITIES == ("sales", "backoffice", "admin")
    assert "all" not in CAPACITIES


def test_an_unknown_capacity_is_refused_at_the_boundary():
    """A typo in a capacity is not a cosmetic defect the way a typo in a view
    is: it decides what an account may do. It fails where it is written."""
    with pytest.raises(ValidationError):
        _user(capacity="office")          # the OLD word, and the likeliest typo
    with pytest.raises(ValidationError):
        _user(capacity="superuser")


def test_a_capacity_is_required_and_has_no_default():
    """There is no safe default. Defaulting to the narrowest would silently
    lock somebody out; defaulting to the widest would silently let them in."""
    with pytest.raises(ValidationError):
        User(id="u1", name="X", email="x@example.com")


# --- the actor string --------------------------------------------------------

def test_an_actor_names_what_KIND_of_thing_acted():
    """`audit_log.actor` is one column and three kinds of thing write to it. A
    bare id would make `u_yossi` and an agent called `u_yossi` the same row."""
    assert actor_ref(_user()) == "user:u_yossi"
    assert SYSTEM == "system"


def test_an_agent_actor_is_told_apart_from_a_person():
    """The whole point of two names in the log. `origin` records who PROPOSED,
    `actor` who performed — and a reader has to be able to see that an agent
    performed something without parsing a name."""
    assert is_agent("agent:ranker") is True
    assert is_agent("user:u_yossi") is False
    assert is_agent(SYSTEM) is False


def test_a_user_id_that_would_forge_another_kind_is_refused():
    """`actor_ref` builds `user:<id>`, so an id carrying a colon could spell
    `user:agent:ranker` and read as an agent to anything that splits on the
    first colon. Refused where the id is made, not where it is read."""
    with pytest.raises(ValidationError):
        _user(id="agent:ranker")
    with pytest.raises(ValidationError):
        _user(id="a:b")


# --- no credential ------------------------------------------------------------

def test_an_account_carries_no_credential_at_all():
    """Not "an empty password" — no field. Google holds the identity; this row
    holds what that identity may do. A credential here would be the second
    password this slice exists to delete."""
    u = User(id="u_dana", name="Dana", email="dana@example.com", capacity="sales")
    assert not hasattr(u, "password_hash")
    assert not hasattr(u, "set_password")
    assert "password" not in u.model_dump()


def test_the_model_module_offers_no_way_to_verify_one():
    import fenceai.identity.model as model
    assert not hasattr(model, "verify_password")


def test_there_is_no_session_module_left():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fenceai.identity.session")


# --- the view a capacity opens on --------------------------------------------

def test_each_capacity_opens_on_its_own_view_and_only_admin_gets_the_choice():
    """The safe way to flip the default the sales MVP deferred: a salesperson
    lands in the sales view because of who they are, while the browser smoke
    signs in as an admin and keeps seeing today's app."""
    from fenceai.identity.model import default_view, may_choose_view

    assert default_view("sales") == "sales"
    assert default_view("backoffice") == "backoffice"
    assert default_view("admin") == "all"

    assert may_choose_view("admin") is True
    assert may_choose_view("sales") is False
    assert may_choose_view("backoffice") is False


def test_choosing_a_view_is_not_a_permission_and_this_test_says_so_out_loud():
    """`may_choose_view` gates a SELECTOR, not access. Hiding is CSS and anybody
    can edit localStorage, so nothing may ever consult this function to decide
    whether an ACTION is allowed — that is `capacity`'s job, server-side.

    Pinned as a test rather than a comment because the day somebody writes
    `if may_choose_view(...)` around a mutation, this is the thing that should
    have stopped them."""
    import inspect

    from fenceai.identity import model

    src = inspect.getsource(model)
    assert "presentation" in src.lower(), (
        "the module must say, in words, that a view is a presentation "
        "preference — the next reader needs it more than we do")
