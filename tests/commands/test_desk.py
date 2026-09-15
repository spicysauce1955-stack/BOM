"""The six things a desk may do to a job, and the order the door asks in.

Backoffice design §4 (lifecycle), §5 (assignee), §10 (one door). These tests are
about the EFFECT and the refusal; `test_registry.py` is about the table shape.

The refusal order is asserted first and on purpose. Capacity before status means
a salesperson who tries to take a job is told the same thing whether the job was
takeable or not — a refusal that changed its words would answer a question the
asker was not allowed to ask.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.commands import perform
from fenceai.commands.desk import NoPayload
from fenceai.commands.model import CommandRefused
from fenceai.commands.registry import spec_for
from fenceai.project.lifecycle import FINISHED_STATES, OPEN_STATES, TRANSITIONS
from fenceai.project.model import Project

NOW = "2026-09-15T08:00:00+00:00"

#: The rows this module owns. Written out rather than read off the table, for
#: `agent/registry.py::KINDS`' reason: a list derived from the registry would
#: grow whatever somebody registered next, and these assertions would stop
#: saying which commands exist.
DESK_KINDS = ("assign_job", "cancel_job", "claim_job", "reopen_job",
              "return_to_sales", "submit_job")


def _job(status: str, **kw) -> Project:
    return Project(id="p1", name="x", status=status, **kw)


# --- the three questions, in order -------------------------------------------

def test_a_capacity_that_may_not_do_it_is_refused_before_anything_changes():
    p = _job("waiting")
    with pytest.raises(CommandRefused) as e:
        perform("claim_job", {}, p, actor="user:u_dana", capacity="sales", now=NOW)
    assert e.value.code == "command_not_permitted"
    assert p.status == "waiting" and p.assignee is None


def test_a_job_in_the_wrong_state_is_refused_and_says_which_state_it_is_in():
    p = _job("delivered")
    with pytest.raises(CommandRefused) as e:
        perform("claim_job", {}, p, actor="user:u_y", capacity="backoffice", now=NOW)
    assert e.value.code == "command_wrong_state"
    assert e.value.params["status"] == "delivered"


def test_the_wrong_capacity_is_told_the_same_thing_whatever_state_the_job_is_in():
    """The reason capacity is checked FIRST. If the state check ran first, the
    two answers below would differ and the refusal would leak whether a job this
    account may not touch is sitting on the queue."""
    takeable = _job("waiting")
    finished = _job("delivered")
    codes = set()
    for p in (takeable, finished):
        with pytest.raises(CommandRefused) as e:
            perform("claim_job", {}, p, actor="user:u_dana", capacity="sales", now=NOW)
        codes.add((e.value.code, tuple(sorted(e.value.params))))
    assert len(codes) == 1


def test_a_payload_that_does_not_type_check_is_refused_after_both_permissions():
    p = _job("planning", assignee="u_y")
    with pytest.raises(ValidationError):
        perform("return_to_sales", {"reasen": "typo"}, p,
                actor="user:u_y", capacity="backoffice", now=NOW)
    assert p.status == "planning"


def test_a_kind_nobody_registered_has_no_word():
    with pytest.raises(KeyError):
        perform("drop_all_tables", {}, _job("waiting"),
                actor="user:u_admin", capacity="admin", now=NOW)


@pytest.fixture
def unperformable_row():
    """A row a capacity MAY reach and nothing performs — `materialize=None` with
    the permission column filled in. Registered rather than imagined, because the
    only row shaped like this today (`select_choice_point`) also names no
    capacity, so it never gets past the first question and the second one would
    go untested."""
    from fenceai.commands.model import CommandSpec
    from fenceai.commands.registry import _TABLE, register

    register(CommandSpec(
        kind="_test_only_proposed", payload_model=NoPayload, rung="note",
        i18n_key="command._test_only_proposed", capacities=frozenset({"admin"}),
    ))
    try:
        yield "_test_only_proposed"
    finally:
        _TABLE.pop("_test_only_proposed", None)


def test_a_row_nothing_performs_by_hand_is_refused_rather_than_crashing(
        unperformable_row):
    """`materialize` is `Callable | None` and `None` is a real row — something an
    agent may PROPOSE that no button performs yet. The door has to answer that
    with a refusal; calling `None` would reach a person as a 500 that says the
    app is broken when the honest answer is "not through this door"."""
    with pytest.raises(CommandRefused) as e:
        perform(unperformable_row, {}, _job("planning"),
                actor="user:u_admin", capacity="admin", now=NOW)
    assert e.value.code == "command_not_performable"


# --- sales hands over ---------------------------------------------------------

def test_submitting_is_never_gated_on_completeness():
    """`blocking` withholds the ESTIMATE, not the handover. A sheet that refused
    an incomplete handover would be worked around within a week."""
    p = _job("drafting")   # nothing drawn at all
    out = perform("submit_job", {}, p, actor="user:u_dana", capacity="sales", now=NOW)
    assert out.status == "waiting"
    assert out.submitted_at == NOW


def test_a_returned_job_can_be_answered_and_sent_back():
    """`returned` is a status, not a dead end — the salesperson answers the
    question and hands it over again."""
    p = _job("returned")
    out = perform("submit_job", {}, p, actor="user:u_dana", capacity="sales", now=NOW)
    assert out.status == "waiting"


def test_the_backoffice_does_not_hand_over_on_a_salespersons_behalf():
    p = _job("drafting")
    with pytest.raises(CommandRefused) as e:
        perform("submit_job", {}, p, actor="user:u_y", capacity="backoffice", now=NOW)
    assert e.value.code == "command_not_permitted"


# --- the queue ----------------------------------------------------------------

def test_taking_a_job_does_two_things_in_one_act():
    """It becomes yours AND moves waiting -> planning, because in the office
    those are one gesture."""
    p = _job("waiting")
    out = perform("claim_job", {}, p, actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.assignee == "u_y"
    assert out.status == "planning"


def test_the_name_on_the_folder_is_the_account_not_the_log_reference():
    """`actor` is `user:u_y` because one log column carries three kinds of actor;
    `assignee` is a user id because it is joined against the people list."""
    out = perform("claim_job", {}, _job("waiting"),
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.assignee == "u_y"


def test_a_job_already_taken_cannot_be_taken_again():
    """Not a lock — `planning` is simply not a state `claim_job` runs from, so
    the second person is told to ask rather than silently taking the folder."""
    with pytest.raises(CommandRefused) as e:
        perform("claim_job", {}, _job("planning", assignee="u_y"),
                actor="user:u_z", capacity="backoffice", now=NOW)
    assert e.value.code == "command_wrong_state"


def test_assigning_puts_the_job_on_a_named_desk_and_takes_it_off_the_queue():
    p = _job("waiting")
    out = perform("assign_job", {"user_id": "u_z"}, p,
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.assignee == "u_z"
    assert out.status == "planning"


def test_passing_a_job_somebody_is_already_planning_changes_only_the_name():
    """`planning -> planning` is not a transition, and inventing one so that
    passing a folder could reuse the claim path would put a move in the code
    that the lifecycle table says does not exist."""
    p = _job("planning", assignee="u_y")
    out = perform("assign_job", {"user_id": "u_z"}, p,
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.assignee == "u_z"
    assert out.status == "planning"


def test_returning_to_sales_takes_the_job_off_the_backoffice_desk():
    """Or the queue stops meaning "work I can do"."""
    p = _job("planning", assignee="u_y")
    out = perform("return_to_sales", {"reason": "wall height?"}, p,
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.status == "returned"
    assert out.assignee is None


def test_the_reason_a_job_was_returned_is_kept_verbatim():
    """Never a code. Whoever reads it has to see the question in the words
    somebody actually wrote."""
    p = _job("planning", assignee="u_y")
    out = perform("return_to_sales", {"reason": "  is the wall 600 or 900?  "}, p,
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.annotations[-1].text == "is the wall 600 or 900?"
    assert out.annotations[-1].author == "user:u_y"
    assert out.annotations[-1].target_ref == "job"
    assert out.annotations[-1].created_at == NOW


def test_a_job_cannot_be_returned_with_nothing_said():
    """The whole point of `returned` is the question. A blank reason hands the
    job back with no way for the salesperson to know what to answer."""
    p = _job("planning", assignee="u_y")
    for blank in ({}, {"reason": ""}, {"reason": "   "}):
        with pytest.raises(ValidationError):
            perform("return_to_sales", blank, p,
                    actor="user:u_y", capacity="backoffice", now=NOW)
    assert p.status == "planning" and not p.annotations


def test_a_job_can_be_cancelled_from_every_open_state():
    for status in sorted(OPEN_STATES):
        out = perform("cancel_job", {}, _job(status),
                      actor="user:u_y", capacity="backoffice", now=NOW)
        assert out.status == "cancelled", status


def test_a_finished_job_is_not_cancelled_twice():
    for status in sorted(FINISHED_STATES):
        with pytest.raises(CommandRefused):
            perform("cancel_job", {}, _job(status),
                    actor="user:u_y", capacity="backoffice", now=NOW)


def test_reopening_puts_a_cancelled_job_back_on_the_queue_with_nobody_s_name_on_it():
    """It goes back to `waiting`, not to whoever happened to hold it when it was
    cancelled — that person may have left the company."""
    out = perform("reopen_job", {}, _job("cancelled", assignee="u_y"),
                  actor="user:u_z", capacity="backoffice", now=NOW)
    assert out.status == "waiting"
    assert out.assignee is None


# --- the rows themselves ------------------------------------------------------

def test_every_desk_row_names_the_capacities_that_may_perform_it():
    """`capacities` defaults to the empty set, which means NOBODY. A row whose
    author forgot the column refuses everybody — silently, and only for the
    people who needed it."""
    for kind in DESK_KINDS:
        assert spec_for(kind).capacities, kind


def test_every_desk_row_can_actually_be_performed():
    for kind in DESK_KINDS:
        assert spec_for(kind).materialize is not None, kind


def test_the_super_user_may_perform_every_desk_command():
    """Three personas, and the third is the super user. An admin locked out of
    the queue would have to be given a second account to unstick anything."""
    for kind in DESK_KINDS:
        assert "admin" in spec_for(kind).capacities, kind


def test_no_desk_row_may_run_from_a_state_the_lifecycle_table_has_never_heard_of():
    """Two tables that describe the same eight states have to agree, or a row
    lists `in_progress` and simply never fires."""
    for kind in DESK_KINDS:
        assert set(spec_for(kind).from_states) <= set(TRANSITIONS), kind


def test_every_move_a_desk_row_makes_is_one_the_lifecycle_table_allows():
    """The rows and `TRANSITIONS` are two descriptions of one lifecycle. This
    drives every row from every state it declares and asserts the result is a
    move the table sanctions — so the two cannot drift apart in silence."""
    payloads = {"return_to_sales": {"reason": "why"}, "assign_job": {"user_id": "u_z"}}
    for kind in DESK_KINDS:
        spec = spec_for(kind)
        for status in sorted(spec.from_states or set(TRANSITIONS)):
            out = perform(kind, payloads.get(kind, {}), _job(status),
                          actor="user:u_admin", capacity="admin", now=NOW)
            assert out.status == status or out.status in TRANSITIONS[status], (
                f"{kind}: {status} -> {out.status} is not in TRANSITIONS")


def test_a_desk_command_never_touches_the_drawing():
    """Whose desk a job is on changes no quantity. If any of these bumped the
    topology revision, taking a job would 409 every derived view of it."""
    before = _job("waiting").topology.revision
    out = perform("claim_job", {}, _job("waiting"),
                  actor="user:u_y", capacity="backoffice", now=NOW)
    assert out.topology.revision == before


def test_closing_a_job_stamps_when_it_left_the_open_list():
    """`closed_at` was declared, documented, and rendered in the Finished list's
    Closed column — and written by NOTHING. The column was blank on every job
    and the whole suite was green, which is the exact shape of defect this repo
    keeps finding: a feature that exists everywhere except where it happens."""
    p = Project(id="p", name="x", status="planning")
    out = perform("cancel_job", {}, p, actor="user:u_y", capacity="backoffice",
                  now=NOW)
    assert out.closed_at == NOW


def test_reopening_clears_the_closing_date():
    """A job back on the open list has no closing date, and a stale one would
    sort it into last month on the finished list it is no longer in."""
    p = Project(id="p", name="x", status="planning")
    p = perform("cancel_job", {}, p, actor="user:u_y", capacity="backoffice", now=NOW)
    p = perform("reopen_job", {}, p, actor="user:u_y", capacity="backoffice",
                now="2026-09-16T09:00:00+00:00")
    assert p.closed_at == ""


def test_an_open_move_never_stamps_it():
    for kind, start in [("claim_job", "waiting"), ("return_to_sales", "planning")]:
        p = Project(id="p", name="x", status=start, assignee="u_y")
        payload = {"reason": "why"} if kind == "return_to_sales" else {}
        out = perform(kind, payload, p, actor="user:u_y", capacity="backoffice",
                      now=NOW)
        assert out.closed_at == "", kind


def test_a_bad_payload_from_a_capacity_that_may_not_act_says_so_first():
    """The ordering leak the existing test could not see: its fixture passed both
    permission checks, so hoisting `parse_payload` to the first line of `perform`
    survived 591 tests.

    It matters because a salesperson sending a malformed `claim_job` would learn
    the PAYLOAD was the problem — which tells them the command exists and that
    they got as far as its shape — instead of `command_not_permitted`."""
    with pytest.raises(CommandRefused) as e:
        perform("assign_job", {"nonsense": True}, Project(id="p", name="x",
                                                          status="waiting"),
                actor="user:u_dana", capacity="sales", now=NOW)
    assert e.value.code == "command_not_permitted"


def test_a_bad_payload_in_the_wrong_state_reports_the_state_first():
    """Same argument one rung down: state outranks shape, so somebody is told
    the job moved rather than being sent to look at their own request."""
    with pytest.raises(CommandRefused) as e:
        perform("claim_job", {"nonsense": True},
                Project(id="p", name="x", status="delivered"),
                actor="user:u_y", capacity="backoffice", now=NOW)
    assert e.value.code == "command_wrong_state"


def test_the_lifecycle_guard_refuses_a_row_the_table_disagrees_with():
    """`_move` raises `ValueError` — not a `CommandRefused` — when a row's
    `from_states` names a move `TRANSITIONS` does not have. Deleting the guard
    survived every test, because the existing fitness test asserts what the
    guard enforces and so can only fail if a ROW is edited."""
    from fenceai.commands.desk import _move

    with pytest.raises(ValueError):
        _move(Project(id="p", name="x", status="delivered"), "waiting", now=NOW)
