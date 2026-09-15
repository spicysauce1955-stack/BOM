"""The one new domain concept: somebody says they have read something.

Two steps of the office road ask for a fact no code can derive — *did you read
her promise?* and *did you read the warning?* Counting open warnings instead
would be worse: a 6 % slope at a gate is a fact, not a fault, so the step would
never go green and the map would train its reader to ignore it.

`Stated` in spirit — a named fact, never a step key — and `Override` in
mechanism: anchored to what it is about, and dead when the anchor moves.
"""

from __future__ import annotations

import pytest

from fenceai.commands.run import perform
from fenceai.project.model import Annotation, Project
from fenceai.report.readiness import SALE_READ, WARNINGS_REVIEWED, readiness, sale_anchor

NOW = "2026-09-15T09:00:00+00:00"


def _note(nid: str) -> Annotation:
    return Annotation(id=nid, target_ref="job", text="a promise", author="user:u_dana")


def _codes(project: Project, **kw) -> set[str]:
    return {i.code for i in readiness(project, **kw)}


def _ack(project: Project, kind: str, payload: dict | None = None,
         actor: str = "user:u_yossi") -> Project:
    return perform(kind, payload or {}, project,
                   actor=actor, capacity="backoffice", now=NOW)


# --- reading the sale ---------------------------------------------------------

def test_reading_the_sale_answers_the_step_nothing_can_check():
    p = Project(id="p", name="x", annotations=[_note("a1")])
    assert "sale_unread" in _codes(p)
    p = _ack(p, "acknowledge_sale")
    assert "sale_unread" not in _codes(p)


def test_it_stops_being_true_the_moment_a_note_arrives():
    """Anchored to the SET of annotation ids. A promise added after somebody read
    the job is a promise nobody has read, and being covered by having read the
    earlier ones is exactly the silence this concept exists to break."""
    p = Project(id="p", name="x", annotations=[_note("a1")])
    p = _ack(p, "acknowledge_sale")
    assert "sale_unread" not in _codes(p)

    p.annotations.append(_note("a2"))
    assert "sale_unread" in _codes(p)


def test_the_order_of_the_notes_is_nobody_s_decision():
    """Sorted, so two notes swapping places does not un-read a sale — the office
    person would never learn what they had done to deserve it."""
    p = Project(id="p", name="x", annotations=[_note("a1"), _note("a2")])
    p = _ack(p, "acknowledge_sale")
    p.annotations.reverse()
    assert "sale_unread" not in _codes(p)


# --- reviewing the warnings ---------------------------------------------------

def test_reviewing_warnings_dies_with_the_run_it_was_about():
    """Anchored to `run_id`, and orphaned the way an override is when the station
    under it moves. A new run means new warnings nobody has read — which is the
    loop the office works in, not an edge case."""
    p = Project(id="p", name="x")
    p = _ack(p, "acknowledge_warnings", {"run_id": "run_1"})
    acks = [a for a in p.acknowledgements if a.kind == WARNINGS_REVIEWED]
    assert acks and acks[-1].anchor == "run_1"


# --- what an acknowledgement is -----------------------------------------------

def test_an_acknowledgement_names_who_made_it():
    """"Somebody read this" is worth nothing without a name against it. That is
    the whole reason the concept is stored rather than derived."""
    p = _ack(Project(id="p", name="x"), "acknowledge_sale", actor="user:u_yossi")
    assert p.acknowledgements[-1].by == "user:u_yossi"
    assert p.acknowledgements[-1].at == NOW


def test_acknowledging_twice_replaces_rather_than_accumulating():
    """One answer per question. A list that grows every time somebody presses the
    button is a list nothing can read, and the newest answer is the only one that
    was ever true."""
    p = Project(id="p", name="x")
    p = _ack(p, "acknowledge_sale", actor="user:u_a")
    p = _ack(p, "acknowledge_sale", actor="user:u_b")
    sale = [a for a in p.acknowledgements if a.kind == SALE_READ]
    assert len(sale) == 1
    assert sale[0].by == "user:u_b"


def test_a_different_run_gets_its_own_row_rather_than_replacing():
    """Two runs are two questions. Replacing would mean reviewing run 2 claimed
    you had read run 1, and a regenerate-heavy day would quietly lose them all."""
    p = Project(id="p", name="x")
    p = _ack(p, "acknowledge_warnings", {"run_id": "run_1"})
    p = _ack(p, "acknowledge_warnings", {"run_id": "run_2"})
    anchors = {a.anchor for a in p.acknowledgements if a.kind == WARNINGS_REVIEWED}
    assert anchors == {"run_1", "run_2"}


def test_a_project_stored_before_this_existed_still_loads():
    """Every field has a default. ~3000 tests and every row in the database
    predate the concept."""
    assert Project(id="p", name="x").acknowledgements == []


# --- the anchor is the read model's, not the command's ------------------------

def test_the_command_writes_the_anchor_the_read_model_reads():
    """Two spellings of "what was this read against" is how an acknowledgement
    silently stops matching. The command calls `sale_anchor` rather than
    rebuilding it."""
    p = Project(id="p", name="x", annotations=[_note("a2"), _note("a1")])
    p = _ack(p, "acknowledge_sale")
    assert p.acknowledgements[-1].anchor == sale_anchor(p)


# --- capacity -----------------------------------------------------------------

def test_a_salesperson_does_not_acknowledge_the_office_s_reading():
    """It is the office's record of having read her work. Her pressing it would
    make the one fact nobody can derive also the one nobody can trust."""
    from fenceai.commands.model import CommandRefused

    with pytest.raises(CommandRefused):
        perform("acknowledge_sale", {}, Project(id="p", name="x"),
                actor="user:u_dana", capacity="sales", now=NOW)
