"""The queue query — what the backoffice should work on next.

Every fixture below builds a REAL `Project`, never a stub, because the one
number on this screen that is worth reading — the open-question count — is
`handover_gaps` run over an actual drawing. A fake project would let the count
be whatever the test wanted and prove nothing about the column.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.project.lifecycle import OPEN_STATES, TRANSITIONS
from fenceai.project.model import Job, Landmark, Project, SiteContext
from fenceai.project.queue import QueueFilter, QueueRow, select_rows
from fenceai.report.handover import handover_gaps
from fenceai.topology.model import (
    BasePayload, HeightIntentPayload, IntervalEvent, Node, Run, Topology,
)
from fenceai.topology.station import make_anchor

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def _drawn() -> Topology:
    """A five-metre run. The queue never reads geometry, but `handover_gaps`
    returns `no_fence_drawn` ALONE for an empty topology — so a fixture with no
    runs would make every open-question count 1 and hide the column's real
    behaviour behind a short circuit."""
    return Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=5000, y_mm=0)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2")],
    )


def _job(pid: str, status: str, *, assignee: str | None = None,
         waited_days: float | None = None, customer: str = "Dana Levy",
         address: str = "Herzl 12, Netanya", sold_by: str = "dana",
         sold_on: str = "2026-09-01") -> Project:
    return Project(
        id=pid, name=pid, topology=_drawn(), status=status, assignee=assignee,
        submitted_at="" if waited_days is None else _ago(waited_days),
        created_by="u_dana",
        job=Job(customer=customer, address=address,
                sold_by=sold_by, sold_on=sold_on),
    )


#: One job in each of the eight states, all submitted, so a bucket test is
#: measuring the bucket and not an accident of who filled in `submitted_at`.
EVERY_STATE = [_job(f"p_{s}", s, waited_days=i + 1)
               for i, s in enumerate(sorted(TRANSITIONS))]

#: A desk's worth of open work: two nobody has taken, two Yossi has, one
#: somebody else has. Distinct waiting times, because the default sort is over
#: them and equal values would let a broken sort pass.
JOBS = [
    _job("p_a", "waiting", waited_days=9, customer="Avi Cohen"),
    _job("p_b", "waiting", waited_days=4, customer="Bar Levi"),
    _job("p_c", "planning", assignee="u_yossi", waited_days=7,
         customer="Gal Mizrahi"),
    _job("p_d", "planned", assignee="u_yossi", waited_days=2,
         customer="Dor Peretz"),
    _job("p_e", "planning", assignee="u_rina", waited_days=5,
         customer="Hila Shani"),
]

#: Sixty, because the page is twenty-five and two full pages plus a remainder is
#: the only shape that catches a cursor that repeats or skips a row.
JOBS_60 = [_job(f"p_{i:02d}", "waiting", waited_days=i + 1) for i in range(60)]


def _job_with_no_height_stated() -> Project:
    """Drawn, sold, and nobody said how tall. The job that the open-question
    column exists for."""
    return _job("p_silent", "waiting", waited_days=3)


def _job_with_everything_stated() -> Project:
    """The same job with every handover question actually answered, so the
    `has_open` filter has a row on the other side of it to find. Built the long
    way — model, context, height, base — because a fixture that merely looked
    complete would make the filter pass while answering nothing."""
    p = _job("p_said", "waiting", waited_days=1)
    p.fence_model = FenceModelChoice(model_id="M-VINYL")
    p.context = SiteContext(landmarks=[
        Landmark(id="lm1", kind="house", closed=True,
                 points=[(0, 3000), (5000, 3000), (5000, 8000)]),
    ])
    run = p.topology.runs[0]
    a0 = make_anchor(p.topology, run, 0)
    a1 = make_anchor(p.topology, run, 5000)
    run.interval_events = [
        IntervalEvent(id="e1", start_anchor=a0, end_anchor=a1,
                      payload=HeightIntentPayload(height_mm=1500)),
        IntervalEvent(id="e2", start_anchor=a0, end_anchor=a1,
                      payload=BasePayload(surface="soil")),
    ]
    assert handover_gaps(p) == [], "the fixture must actually be complete"
    return p


# --- the two lists -----------------------------------------------------------

def test_the_two_buckets_are_the_two_lists_and_nothing_falls_between():
    rows, _ = select_rows(EVERY_STATE, QueueFilter(bucket="open"), now=NOW)
    assert {r.status for r in rows} == set(OPEN_STATES)
    rows, _ = select_rows(EVERY_STATE, QueueFilter(bucket="finished"), now=NOW)
    assert {r.status for r in rows} == {"delivered", "cancelled"}


def test_drafting_jobs_are_the_salespersons_and_not_on_the_backoffice_queue():
    """A job she has not submitted is not work anybody else can pick up."""
    rows, _ = select_rows(EVERY_STATE,
                          QueueFilter(bucket="open", for_capacity="backoffice"),
                          now=NOW)
    assert "drafting" not in {r.status for r in rows}


def test_a_salesperson_still_sees_her_own_drafts():
    """The same filter, the other desk. Hiding a draft from the person writing
    it would make the queue useless to the only capacity that has one."""
    rows, _ = select_rows(EVERY_STATE,
                          QueueFilter(bucket="open", for_capacity="sales"),
                          now=NOW)
    assert "drafting" in {r.status for r in rows}


# --- who has it --------------------------------------------------------------

def test_assignee_me_and_assignee_none_are_different_questions():
    rows, _ = select_rows(JOBS, QueueFilter(assignee="u_yossi"), now=NOW)
    assert rows, "the fixture has jobs on Yossi's desk; a vacuous all() proves nothing"
    assert all(r.assignee == "u_yossi" for r in rows)
    rows, _ = select_rows(JOBS, QueueFilter(assignee="none"), now=NOW)
    assert rows
    assert all(r.assignee is None for r in rows)


def test_me_is_refused_rather_than_matched_as_a_user_id():
    """`me` is the route's word, resolved against the session before it gets
    here. Matched literally it would find no user, return an empty page, and
    read on screen as "you have nothing to do" — a wrong answer that looks
    exactly like a right one."""
    with pytest.raises(ValueError):
        select_rows(JOBS, QueueFilter(assignee="me"), now=NOW)


# --- the column that earns its place -----------------------------------------

def test_the_open_question_count_is_the_handover_sheet_and_nothing_else():
    """Not the office's own work. A fresh job has a bay width to choose and a
    plan to commit BY DEFINITION, so counting those would make every row read
    the same and tell the reader nothing."""
    p = _job_with_no_height_stated()
    rows, _ = select_rows([p], QueueFilter(), now=NOW)
    assert rows[0].open_questions == len(handover_gaps(p))
    assert rows[0].open_questions > 0


def test_has_open_separates_the_job_worth_opening_from_the_one_that_is_ready():
    silent, said = _job_with_no_height_stated(), _job_with_everything_stated()
    rows, _ = select_rows([silent, said], QueueFilter(has_open=True), now=NOW)
    assert [r.id for r in rows] == ["p_silent"]
    ready, _ = select_rows([silent, said], QueueFilter(has_open=False), now=NOW)
    assert [r.id for r in ready] == ["p_said"]


# --- waiting -----------------------------------------------------------------

def test_the_default_sort_is_longest_waiting_first():
    rows, _ = select_rows(JOBS, QueueFilter(), now=NOW)
    waited = [r.waiting_seconds for r in rows]
    assert waited == sorted(waited, reverse=True)


def test_a_job_nobody_submitted_has_not_been_waiting():
    """Its age is not its wait. Counting from creation would float every
    abandoned draft to the top of the list, above the customers who are
    actually waiting."""
    never = _job("p_draft", "drafting", waited_days=None)
    rows, _ = select_rows([never], QueueFilter(), now=NOW)
    assert rows[0].waiting_seconds == 0
    assert rows[0].submitted_at == ""


# --- paging ------------------------------------------------------------------

def test_a_page_is_bounded_and_hands_back_a_cursor():
    """Paging is a correctness requirement: the open-question count is DERIVED,
    and deriving it for an unbounded list is what would make the rule 'read
    models are derived, never stored' unaffordable."""
    rows, cursor = select_rows(JOBS_60, QueueFilter(limit=25), now=NOW)
    assert len(rows) == 25 and cursor is not None
    rest, nxt = select_rows(JOBS_60, QueueFilter(limit=25, cursor=cursor), now=NOW)
    assert len(rest) == 25 and nxt is not None
    assert {r.id for r in rows} & {r.id for r in rest} == set()


def test_the_last_page_says_so_and_walking_the_pages_sees_every_job_once():
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        rows, cursor = select_rows(
            JOBS_60, QueueFilter(limit=25, cursor=cursor), now=NOW)
        seen += [r.id for r in rows]
        if cursor is None:
            break
    assert cursor is None, "the walk must terminate, not run out of iterations"
    assert seen == sorted({p.id for p in JOBS_60},
                          key=lambda i: [p.submitted_at for p in JOBS_60
                                         if p.id == i][0])
    assert len(seen) == len(JOBS_60)


def test_a_cursor_that_cannot_be_read_is_refused_rather_than_ignored():
    """Ignoring it restarts the walk at page one, and a caller looping on the
    cursor would then page forever."""
    with pytest.raises(ValueError):
        select_rows(JOBS_60, QueueFilter(cursor="not-a-cursor"), now=NOW)


def test_the_page_size_has_a_ceiling_and_it_refuses_rather_than_clamps():
    """A silently clamped `limit=500` hands back 100 rows and no way to tell
    that 400 were left behind."""
    with pytest.raises(ValueError):
        QueueFilter(limit=500)


# --- the stored columns ------------------------------------------------------

def test_the_row_carries_the_picker_fields_it_always_carried():
    """`GET /api/projects` is rebuilt, not replaced. Something keyed on `id`,
    `name` or `label` must not silently start reading a customer's name."""
    rows, _ = select_rows([_job("p_1", "waiting", waited_days=1)],
                          QueueFilter(), now=NOW)
    row = rows[0]
    assert isinstance(row, QueueRow)
    assert row.id == "p_1" and row.name == "p_1"
    assert row.label == "Dana Levy — Herzl 12, Netanya"


def test_the_town_is_read_off_the_address_and_never_guessed():
    """Addresses are typed from paper, so the town is the part after the last
    comma and nothing else. An address with no comma has no town — a blank cell
    is honest where a guessed one sends the plan to the wrong place."""
    rows, _ = select_rows(
        [_job("p_1", "waiting", waited_days=2, address="Herzl 12, Netanya"),
         _job("p_2", "waiting", waited_days=1, address="Herzl 12")],
        QueueFilter(), now=NOW)
    assert [r.town for r in rows] == ["Netanya", ""]


def test_a_window_on_submission_excludes_the_job_that_was_never_submitted():
    """It has no submission date, so it is not inside any window — and a job
    silently inside every window would show up in a report of last week's
    intake that it had nothing to do with."""
    jobs = [_job("p_in", "waiting", waited_days=2),
            _job("p_old", "waiting", waited_days=40),
            _job("p_never", "drafting", waited_days=None)]
    rows, _ = select_rows(jobs, QueueFilter(submitted_from="2026-09-10"), now=NOW)
    assert {r.id for r in rows} == {"p_in"}


def test_free_text_searches_what_a_person_would_type():
    rows, _ = select_rows(JOBS, QueueFilter(q="mizrahi"), now=NOW)
    assert {r.id for r in rows} == {"p_c"}


# --- the five mutants that survived together ----------------------------------

def _p(pid: str, **kw) -> Project:
    base = dict(id=pid, name=pid, status="waiting",
                submitted_at="2026-09-14T08:00:00+00:00")
    return Project(**{**base, **kw})


def test_a_job_nobody_submitted_does_not_lead_the_longest_waiting():
    """The blank-placement key. Flipping `0 if p.submitted_at else 1` survived
    every test, because every fixture had a submitted date and the one job
    without one was alone in its list — so the ordering it decides was never
    observable. The failure it prevents is named in the code: every
    never-submitted job sitting at the top of the list of who has waited longest.
    """
    rows, _ = select_rows(
        [_p("blank", status="drafting", submitted_at=""),
         _p("old", submitted_at="2026-09-01T08:00:00+00:00"),
         _p("new", submitted_at="2026-09-14T08:00:00+00:00")],
        QueueFilter(bucket="open", status=("waiting", "drafting")), now=NOW)
    assert [r.id for r in rows][0] == "old", [r.id for r in rows]
    assert [r.id for r in rows][-1] == "blank", [r.id for r in rows]


def test_newest_is_the_other_direction_from_longest_waiting():
    """`sort="newest"` was never requested by any test; flipping its descending
    flag survived."""
    jobs = [_p("old", submitted_at="2026-09-01T08:00:00+00:00"),
            _p("new", submitted_at="2026-09-14T08:00:00+00:00")]
    waiting, _ = select_rows(jobs, QueueFilter(sort="waiting"), now=NOW)
    newest, _ = select_rows(jobs, QueueFilter(sort="newest"), now=NOW)
    assert [r.id for r in waiting] == ["old", "new"]
    assert [r.id for r in newest] == ["new", "old"]


def test_customer_sorts_by_the_name_a_person_would_look_for():
    """Never requested either; replacing the key with a constant survived."""
    jobs = [_p("b", job=Job(customer="Zohar")), _p("a", job=Job(customer="Abergel"))]
    rows, _ = select_rows(jobs, QueueFilter(sort="customer"), now=NOW)
    assert [r.customer for r in rows] == ["Abergel", "Zohar"]


def test_each_stored_filter_actually_filters():
    """`status`, `sold_by` and the sold-on window were all in the spec's filter
    set, all sent by the real `<select>` elements, and all survived being
    neutralised. Driven together because the failure is the same shape for each:
    a chip that looks like it did something."""
    jobs = [_p("w", status="waiting", job=Job(sold_by="Dana", sold_on="2026-09-01")),
            _p("p", status="planning", job=Job(sold_by="Ron", sold_on="2026-09-10"))]

    rows, _ = select_rows(jobs, QueueFilter(status=("waiting",)), now=NOW)
    assert [r.id for r in rows] == ["w"]

    rows, _ = select_rows(jobs, QueueFilter(sold_by="Ron"), now=NOW)
    assert [r.id for r in rows] == ["p"]

    rows, _ = select_rows(jobs, QueueFilter(sold_on_from="2026-09-05"), now=NOW)
    assert [r.id for r in rows] == ["p"]

    rows, _ = select_rows(jobs, QueueFilter(sold_on_to="2026-09-05"), now=NOW)
    assert [r.id for r in rows] == ["w"]


def test_one_unreadable_timestamp_does_not_hide_every_other_job():
    """`_waiting_seconds` guards a naive or unparseable stored time and returns
    0. Removing the guard raised inside `select_rows` — a 500 on the whole list,
    which is the failure its own docstring names: a queue that dies because one
    row's timestamp is malformed hides every other job on it."""
    jobs = [_p("naive", submitted_at="2026-09-14T08:00:00"),
            _p("junk", submitted_at="not a date"),
            _p("fine")]
    rows, _ = select_rows(jobs, QueueFilter(), now=NOW)
    assert {r.id for r in rows} == {"naive", "junk", "fine"}
    assert next(r for r in rows if r.id == "naive").waiting_seconds == 0
    assert next(r for r in rows if r.id == "junk").waiting_seconds == 0
