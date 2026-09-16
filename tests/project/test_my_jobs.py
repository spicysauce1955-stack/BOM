"""A salesperson's home screen (project/queue.py: my_jobs, lifecycle.sales_status).

"The sales agent's home screen should be a list of his jobs; there he could see
comments or demands from the office on his jobs." Five words for where a job is,
folded from the office's eight, and what the office said — read off notes the
office wrote, never off notes she wrote herself.
"""

from __future__ import annotations

import pytest

from fenceai.project.lifecycle import SALES_STATUS, TRANSITIONS, sales_status
from fenceai.project.model import Annotation, Job, Project
from fenceai.project.queue import my_jobs


def _p(pid, *, by="u_dana", status="drafting", customer="", notes=()):
    return Project(id=pid, name=pid, created_by=by, status=status,
                   job=Job(customer=customer, address="1 Main St, Haifa") if customer else None,
                   annotations=[Annotation(id=f"{pid}-{i}", target_ref=ref, text=text,
                                           author=author, created_at=at)
                                for i, (ref, text, author, at) in enumerate(notes)])


def test_every_job_state_has_a_word_the_salesperson_reads():
    """A state added to the lifecycle without a sales word would raise on her
    list the day it is used — this fails first, where the state is added."""
    assert set(SALES_STATUS) == set(TRANSITIONS)
    assert set(SALES_STATUS.values()) == {"draft", "pending", "needs_info", "accepted", "rejected"}


def test_the_office_states_fold_into_the_words_she_uses():
    assert sales_status("drafting") == "draft"
    assert sales_status("waiting") == "pending"
    assert sales_status("returned") == "needs_info"
    for s in ("planning", "planned", "quoted", "delivered"):
        assert sales_status(s) == "accepted", s
    assert sales_status("cancelled") == "rejected"
    with pytest.raises(KeyError):
        sales_status("won")


def test_the_list_is_only_the_jobs_this_account_created():
    rows = my_jobs([_p("a"), _p("b", by="u_other"), _p("c", by="")], "u_dana")
    assert [r.id for r in rows] == ["a"]
    assert my_jobs([_p("a")], "") == []


def test_what_needs_her_comes_first():
    rows = my_jobs([
        _p("rej", status="cancelled", customer="Avi"),
        _p("acc", status="planning", customer="Avi"),
        _p("pen", status="waiting", customer="Avi"),
        _p("dra", status="drafting", customer="Avi"),
        _p("ask", status="returned", customer="Avi"),
    ], "u_dana")
    assert [r.sales_status for r in rows] == ["needs_info", "draft", "pending", "accepted", "rejected"]


def test_office_notes_are_counted_and_her_own_are_not():
    """Her own notes are the sale, not comments on it; a `system` note is
    nobody's comment. The latest office note is carried verbatim."""
    rows = my_jobs([_p("a", status="returned", notes=[
        ("run:r1", "keep clear of the window", "user:u_dana", "2026-09-15T08:00:00+00:00"),
        ("job", "What height by the gate?", "user:u_yossi", "2026-09-15T09:00:00+00:00"),
        ("landmark:lm1", "  Is this the street side?  ", "user:u_yossi", "2026-09-15T10:00:00+00:00"),
        ("job", "imported", "system", "2026-09-15T11:00:00+00:00"),
    ])], "u_dana")
    assert rows[0].office_notes == 2
    assert rows[0].office_latest == "  Is this the street side?  "
    assert my_jobs([_p("b")], "u_dana")[0].office_notes == 0
    assert my_jobs([_p("b")], "u_dana")[0].office_latest == ""


def test_the_latest_office_note_is_the_newest_by_time_not_by_position():
    rows = my_jobs([_p("a", status="returned", notes=[
        ("job", "newest", "user:u_yossi", "2026-09-15T12:00:00+00:00"),
        ("job", "older", "user:u_yossi", "2026-09-15T09:00:00+00:00"),
    ])], "u_dana")
    assert rows[0].office_latest == "newest"


def test_nobody_signed_in_owns_no_jobs_even_the_ones_with_no_creator():
    assert my_jobs([_p("c", by="")], "") == []


def test_ties_read_alphabetically_then_by_id():
    rows = my_jobs([_p("z2", customer="beta"), _p("z1", customer="Alpha"),
                    _p("y2", customer="Same"), _p("y1", customer="Same")], "u_dana")
    assert [r.id for r in rows] == ["z1", "z2", "y1", "y2"]


def test_an_office_question_does_not_contradict_her_no_promises():
    """A question pinned by the office is not a promise she made."""
    from fenceai.project.model import Stated
    from fenceai.report.handover import _contradiction_gaps as handover_gaps

    p = _p("a", status="returned", notes=[
        ("job", "What height by the gate?", "user:u_yossi", "2026-09-15T09:00:00+00:00")])
    p.stated = Stated(no_promises=True)
    assert "promises_contradicted" not in {g.code for g in handover_gaps(p)}
    p.annotations.append(p.annotations[0].model_copy(update={
        "id": "mine", "author": "user:u_dana", "text": "keep the tree"}))
    assert "promises_contradicted" in {g.code for g in handover_gaps(p)}
