"""The queue on the wire — and the two things only a route can answer.

`select_rows` is pure over loaded projects, so it can resolve neither "me" (it
does not know who is asking) nor a quote total (it may not reach the store).
Both are answered here, and both have a wrong answer that looks fine.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.model import User


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _account(uid: str, capacity: str) -> User:
    u = User(id=uid, name=uid, email=f"{uid}@example.com", capacity=capacity)
    state.store.save_user(u)
    return u


def _as(client, uid: str, capacity: str):
    """Become this person. No password: the identity comes from the provider,
    and the row carries only what the account may DO."""
    _account(uid, capacity)
    client.cookies.set(DEV_COOKIE, f"{uid}@example.com")


def _job(client, name: str, status: str, assignee: str | None = None):
    p = client.post("/api/projects", json={"name": name}).json()
    stored = state.store.load_project(p["id"])
    stored.status = status
    stored.assignee = assignee
    stored.submitted_at = "2026-09-15T08:00:00+00:00"
    state.store.save_project(stored)
    return p["id"]


# --- the picker did not change ------------------------------------------------

def test_the_picker_is_still_a_bare_list_of_three_fields(client):
    """Five callers read it, the project picker among them. The queue is a
    different question and got its own route rather than changing this one's
    shape underneath everybody."""
    rows = client.get("/api/projects").json()
    assert isinstance(rows, list)
    assert set(rows[0]) == {"id", "name", "label"}


# --- me -----------------------------------------------------------------------

def test_me_resolves_to_the_caller_and_never_matches_literally(client):
    """`select_rows` REFUSES the literal string, because matched as an id it
    returns an empty page that reads as "you have nothing to do" — the most
    misleading answer a queue can give. The route resolves it first."""
    _as(client, "u_yossi", "backoffice")
    mine = _job(client, "mine", "planning", assignee="u_yossi")
    _job(client, "theirs", "planning", assignee="u_maya")
    rows = client.get("/api/queue", params={"assignee": "me"}).json()["rows"]
    assert [r["id"] for r in rows] == [mine]


def test_me_is_empty_rather_than_everybody_when_nothing_is_mine(client):
    """The failure mode the resolution exists to avoid is the OPPOSITE of an
    empty page: `me` falling through to "no filter" and showing one person the
    whole office's desk. There is no anonymous caller left to test that with —
    the gate refuses one — so the case is a resolved caller with nothing
    assigned to them."""
    _as(client, "u_idle", "backoffice")
    _job(client, "someones", "planning", assignee="u_yossi")
    rows = client.get("/api/queue", params={"assignee": "me"}).json()["rows"]
    assert rows == []


def test_nobody_has_taken_it_is_a_different_question_from_mine(client):
    _as(client, "u_y2", "backoffice")
    untaken = _job(client, "untaken", "waiting")
    _job(client, "taken", "planning", assignee="u_y2")
    rows = client.get("/api/queue", params={"assignee": "none"}).json()["rows"]
    assert [r["id"] for r in rows] == [untaken]


# --- the two buckets ----------------------------------------------------------

def test_the_two_buckets_are_the_two_lists(client):
    _as(client, "u_y3", "backoffice")
    open_id = _job(client, "open one", "waiting")
    done_id = _job(client, "done one", "delivered")
    rows = client.get("/api/queue", params={"bucket": "open"}).json()["rows"]
    assert open_id in [r["id"] for r in rows]
    assert done_id not in [r["id"] for r in rows]
    rows = client.get("/api/queue", params={"bucket": "finished"}).json()["rows"]
    assert done_id in [r["id"] for r in rows]


def test_a_draft_is_the_salespersons_and_not_on_the_backoffice_queue(client):
    """A job she has not submitted is not work anybody else can pick up."""
    _as(client, "u_y4", "backoffice")
    draft = _job(client, "hers", "drafting")
    rows = client.get("/api/queue").json()["rows"]
    assert draft not in [r["id"] for r in rows]


# --- refusals -----------------------------------------------------------------

def test_an_unreadable_cursor_refuses_rather_than_starting_over(client):
    """Ignoring it would make a paging loop run for ever, quietly."""
    _as(client, "u_y5", "backoffice")
    r = client.get("/api/queue", params={"cursor": "not-a-cursor"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "queue_cursor_invalid"


def test_too_large_a_page_refuses_rather_than_clamping(client):
    """Clamping would answer a question nobody asked and look like it worked."""
    _as(client, "u_y6", "backoffice")
    r = client.get("/api/queue", params={"limit": 5000})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "queue_filter_invalid"


# --- the column a pure function could not fill --------------------------------

def test_a_page_hands_back_a_cursor_only_when_there_is_more(client):
    """The second assertion was `next_cursor is None OR len(rows) <= 2`, and the
    request used `limit=2` — so the right half was ALWAYS true and the test could
    not fail. Verified: forcing the route to return a cursor unconditionally
    still passed. The `or` was hedging against other tests' jobs polluting the
    store, and the hedge is what made it vacuous; the fix is to isolate the rows
    instead, with a status nothing else in this file uses.
    """
    _as(client, "u_y7", "backoffice")
    for i in range(3):
        _job(client, f"cursor-{i}", "returned")
    params = {"limit": 2, "status": "returned"}
    body = client.get("/api/queue", params=params).json()
    assert len(body["rows"]) == 2
    assert body["next_cursor"], "two of three rows returned and no way to the third"

    rest = client.get("/api/queue", params={**params,
                                            "cursor": body["next_cursor"]}).json()
    assert len(rest["rows"]) == 1
    assert rest["next_cursor"] is None, "a last page must not offer another"
    assert {r["id"] for r in body["rows"]} & {r["id"] for r in rest["rows"]} == set()


# --- the guards that shipped with no test at all -------------------------------

def test_a_typo_in_the_assignee_is_refused_rather_than_losing_the_job(client):
    """`_refuse_unknown_assignee` is twenty lines with a docstring explaining it
    closes the seam `commands/` deliberately left open — and deleting its body
    failed nothing. `assignee_unknown` appeared in the suite exactly once, as a
    string in the locale test, which proves a SENTENCE exists and not that
    anything emits it.

    The failure it prevents: a job on a desk nobody has, off every list at once,
    with nothing refusing and no way back but reading the database."""
    _as(client, "u_assign", "backoffice")
    job = _job(client, "typo target", "waiting")
    r = client.post(f"/api/projects/{job}/actions",
                    json={"kind": "assign_job", "payload": {"user_id": "u_typo"}})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "assignee_unknown"
    assert state.store.load_project(job).assignee is None


def test_a_deactivated_account_cannot_be_handed_a_job(client):
    """Deactivated is what a company does instead of deleting. Handing work to
    one is the same lost job as a typo."""
    _as(client, "u_assign2", "backoffice")
    gone = _account("u_gone", "backoffice")
    gone.active = False
    state.store.save_user(gone)
    job = _job(client, "to a leaver", "waiting")
    r = client.post(f"/api/projects/{job}/actions",
                    json={"kind": "assign_job", "payload": {"user_id": "u_gone"}})
    assert r.status_code == 422


def test_assigning_to_a_real_person_works(client):
    """The other half. A guard that refused everything would pass the two tests
    above and be worse than no guard."""
    _as(client, "u_assign3", "backoffice")
    _account("u_maya2", "backoffice")
    job = _job(client, "to maya", "waiting")
    r = client.post(f"/api/projects/{job}/actions",
                    json={"kind": "assign_job", "payload": {"user_id": "u_maya2"}})
    assert r.status_code == 200
    assert state.store.load_project(job).assignee == "u_maya2"


def test_the_finished_list_carries_the_quote_and_the_closing_date(client):
    """Both columns a pure function could not fill. The route's own docstring
    promised they were answered here and only `me` was tested — replacing
    `_queue_row` with a bare dump passed 327 tests."""
    _as(client, "u_q", "backoffice")
    job = _job(client, "priced", "quoted")
    stored = state.store.load_project(job)
    stored.closed_at = "2026-09-15T12:00:00+00:00"
    state.store.save_project(stored)
    row = next(r for r in client.get("/api/queue",
                                     params={"bucket": "open", "status": "quoted"}
                                     ).json()["rows"] if r["id"] == job)
    assert row["closed_at"] == "2026-09-15T12:00:00+00:00"
    assert "quote_total_cents" in row


def test_deactivating_an_account_refuses_the_very_next_request(client):
    """IAP revokes access centrally and we cannot; `active=False` is the local
    half, and it has to bite on a browser that is already open. It was unpinned
    before — dropping `and user.active` from the old `_signed_in` passed 591
    tests — so the check is asserted at the gate, which is where it lives now.
    """
    _as(client, "u_bye2", "backoffice")
    assert client.get("/api/queue").status_code == 200

    user = state.store.user("u_bye2")
    user.active = False
    state.store.save_user(user)
    r = client.get("/api/queue")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "account_deactivated"
