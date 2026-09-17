"""Committing a plan (backoffice design §7).

Generating is cheap and repeated; committing is the decision. The command moves
the job to `planned` and records WHICH run people build from — and because
somebody else reads that later and builds from it, the route takes the strict
staleness guards `create_quote` takes rather than the permissive ones the
working views take.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.model import User


@pytest.fixture()
def client(dsn, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", dsn)
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def _as(client, uid: str, capacity: str):
    """Become this person. No password: the identity comes from the provider,
    and the row carries only what the account may DO."""
    u = User(id=uid, name=uid, email=f"{uid}@example.com", capacity=capacity)
    state.store.save_user(u)
    client.cookies.set(DEV_COOKIE, u.email)


TOPOLOGY = {
    "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0}, {"id": "n2", "x_mm": 6000, "y_mm": 0}],
    "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
}


def _planning_job(client) -> tuple[str, str]:
    """A job on the office's desk with one run on it."""
    _as(client, "u_dana", "sales")
    pid = client.post("/api/projects", json={"name": "job"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json=TOPOLOGY)
    client.post(f"/api/projects/{pid}/actions", json={"kind": "submit_job", "payload": {}})
    _as(client, "u_yossi", "backoffice")
    client.post(f"/api/projects/{pid}/actions", json={"kind": "claim_job", "payload": {}})
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    return pid, run_id


def _commit(client, pid: str, run_id: str):
    return client.post(f"/api/projects/{pid}/actions",
                       json={"kind": "commit_plan", "payload": {"run_id": run_id}})


def _codes(client, pid: str) -> set[str]:
    return {i["code"] for i in client.get(f"/api/projects/{pid}/readiness").json()["items"]}


def test_committing_names_the_run_and_moves_the_job_to_planned(client):
    pid, run_id = _planning_job(client)
    assert "no_plan_committed" in _codes(client, pid)

    assert _commit(client, pid, run_id).status_code == 200
    stored = state.store.load_project(pid)
    assert stored.committed_run_id == run_id
    assert stored.status == "planned"
    assert "no_plan_committed" not in _codes(client, pid)


def test_a_salesperson_may_not_commit_a_plan(client):
    pid, run_id = _planning_job(client)
    _as(client, "u_dana", "sales")
    r = _commit(client, pid, run_id)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "command_not_permitted"
    assert state.store.load_project(pid).committed_run_id == ""


def test_committing_twice_is_refused_by_the_state_it_left(client):
    """Changing the answer goes back through `planning`, so a plan somebody may
    be building from cannot be swapped underneath them by one click."""
    pid, run_id = _planning_job(client)
    assert _commit(client, pid, run_id).status_code == 200
    again = _commit(client, pid, run_id)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "command_wrong_state"


def test_a_run_from_another_job_is_refused(client):
    """The payload names a run explicitly — so it can name somebody else's."""
    pid, _ = _planning_job(client)
    _, other_run = _planning_job(client)
    r = _commit(client, pid, other_run)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "run_not_on_this_job"
    assert state.store.load_project(pid).committed_run_id == ""


def test_a_moved_drawing_refuses_the_commit(client):
    """A working view renders something stale and somebody re-reads it. A
    committed plan is read later by somebody who builds from it."""
    pid, run_id = _planning_job(client)
    moved = dict(TOPOLOGY)
    moved["nodes"] = [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 9000, "y_mm": 0}]
    client.put(f"/api/projects/{pid}/topology", json=moved)
    r = _commit(client, pid, run_id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "topology_changed"
    assert state.store.load_project(pid).status == "planning"


def test_moved_site_conditions_refuse_the_commit(client):
    pid, run_id = _planning_job(client)
    client.put(f"/api/projects/{pid}/site", json={"exposure_category": "D"})
    r = _commit(client, pid, run_id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "site_conditions_changed"


def test_a_repriced_product_the_run_bought_refuses_the_commit(client):
    pid, run_id = _planning_job(client)
    product = client.get("/api/catalog").json()["products"]["RAIL-3000"]
    product["price_cents"] = 9999
    client.put("/api/catalog/products", json=product)
    r = _commit(client, pid, run_id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "catalog_changed"


def test_a_plan_committed_before_the_drawing_moved_reads_stale(client):
    """The office may edit the drawing, and should: a plan committed against the
    revision before that edit describes a different fence."""
    pid, run_id = _planning_job(client)
    assert _commit(client, pid, run_id).status_code == 200
    moved = dict(TOPOLOGY)
    moved["nodes"] = [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 9000, "y_mm": 0}]
    client.put(f"/api/projects/{pid}/topology", json=moved)
    assert "plan_stale" in _codes(client, pid)


MOVED = {
    "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0}, {"id": "n2", "x_mm": 9000, "y_mm": 0}],
    "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
}


def test_a_blank_run_id_is_not_a_commit(client):
    """It committed nothing, moved the job to `planned` and stranded it there —
    and a blank short-circuited every staleness guard on the way."""
    pid, _ = _planning_job(client)
    r = client.post(f"/api/projects/{pid}/actions",
                    json={"kind": "commit_plan", "payload": {"run_id": ""}})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "command_payload_invalid"
    stored = state.store.load_project(pid)
    assert stored.status == "planning" and stored.committed_run_id == ""


def test_a_salesperson_is_told_about_her_account_and_nothing_about_our_runs(client):
    """Capacity is asked first, so a door that should only ever say "not your
    account" cannot be used to enumerate run ids or read how far a job has got."""
    pid, run_id = _planning_job(client)
    client.put(f"/api/projects/{pid}/topology", json=MOVED)     # the run is now stale
    _as(client, "u_dana", "sales")

    stale = _commit(client, pid, run_id)
    assert stale.status_code == 403
    assert stale.json()["detail"]["code"] == "command_not_permitted"

    ghost = client.post(f"/api/projects/{pid}/actions",
                        json={"kind": "commit_plan", "payload": {"run_id": "ghost"}})
    assert ghost.status_code == 403
    assert ghost.json()["detail"]["code"] == "command_not_permitted"


def test_a_run_nobody_stored_is_refused_in_words_the_office_can_read(client):
    """`_run`'s bare 404 reached the screen as "the action failed". A run that
    does not exist and one belonging to another job are one fact from here."""
    pid, _ = _planning_job(client)
    r = client.post(f"/api/projects/{pid}/actions",
                    json={"kind": "commit_plan", "payload": {"run_id": "ghost"}})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "run_not_on_this_job"


def test_a_job_in_the_wrong_state_is_told_that_before_any_staleness(client):
    """Both answers are true of a committed job whose drawing then moved. The
    state is the one the office can act on, and the precondition is asked after
    it."""
    pid, run_id = _planning_job(client)
    assert _commit(client, pid, run_id).status_code == 200
    client.put(f"/api/projects/{pid}/topology", json=MOVED)
    again = _commit(client, pid, run_id)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "command_wrong_state"


def test_the_plan_can_be_taken_back_and_committed_again(client):
    """`planned` was a one-way door: nothing performed `planned -> planning`, so
    a plan that went stale could only be corrected by REJECTING the job, which
    the salesperson reads as rejected for an office decision."""
    pid, run_id = _planning_job(client)
    assert _commit(client, pid, run_id).status_code == 200
    back = client.post(f"/api/projects/{pid}/actions",
                       json={"kind": "revise_plan", "payload": {}})
    assert back.status_code == 200
    stored = state.store.load_project(pid)
    assert stored.status == "planning" and stored.committed_run_id == ""
    assert "no_plan_committed" in _codes(client, pid)
    assert _commit(client, pid, run_id).status_code == 200


def test_a_job_that_leaves_the_office_forgets_the_plan_it_named(client):
    """Reject and reopen is the other way out of `planned`, and a job coming
    back must not still name a run committed in a previous life — step 6 would
    read green for a job nobody has re-planned."""
    pid, run_id = _planning_job(client)
    _commit(client, pid, run_id)
    client.post(f"/api/projects/{pid}/actions", json={"kind": "cancel_job", "payload": {}})
    client.post(f"/api/projects/{pid}/actions", json={"kind": "reopen_job", "payload": {}})
    stored = state.store.load_project(pid)
    assert stored.status == "waiting" and stored.committed_run_id == ""


def test_a_committed_id_this_job_has_no_run_for_reads_as_nothing_committed(client):
    """Not silence: a plan nobody can open is not a plan, and step 6 read done
    on the strength of a string."""
    pid, _ = _planning_job(client)
    stored = state.store.load_project(pid)
    stored.committed_run_id = "ghost-run"
    state.store.save_project(stored)
    r = client.get(f"/api/projects/{pid}/readiness")
    assert r.status_code == 200
    assert "no_plan_committed" in {i["code"] for i in r.json()["items"]}


def test_committing_changes_no_run_id(client):
    """`committed_run_id` is not an input to generation and must never enter the
    run digest — committing a plan would otherwise change the id of the run it
    commits."""
    pid, run_id = _planning_job(client)
    _commit(client, pid, run_id)
    client.post(f"/api/projects/{pid}/actions", json={"kind": "revise_plan", "payload": {}})
    again = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    assert again == run_id


def test_the_road_is_told_what_the_yard_can_fill(client):
    """Step 5 asks what supply could not resolve, and the route did not resolve
    it — so every job with a run reported `supply_unknown` ("nobody worked it
    out") and the materials step could never read done."""
    pid, _ = _planning_job(client)
    assert "supply_unknown" not in _codes(client, pid)


def test_a_run_too_stale_to_price_reports_that_nobody_could_work_it_out(client):
    """A moved CATALOG is what stops a stored run being priced (a moved drawing
    does not: supply is about the demand this run already recorded). Reported,
    not raised — the road is the screen somebody opens to find out what is wrong
    with a job, and it must not refuse to render because something is."""
    pid, _ = _planning_job(client)
    product = client.get("/api/catalog").json()["products"]["RAIL-3000"]
    product["price_cents"] = 4242
    client.put("/api/catalog/products", json=product)
    r = client.get(f"/api/projects/{pid}/readiness")
    assert r.status_code == 200
    assert "supply_unknown" in {i["code"] for i in r.json()["items"]}


def test_moved_site_conditions_stop_the_road_claiming_the_yard_can_fill_it(client):
    """Step 5 read green while step 7's quote door would refuse the same run on
    `site_conditions_changed` — the road saying go and the next door saying no."""
    pid, _ = _planning_job(client)
    assert "supply_unknown" not in _codes(client, pid)
    client.put(f"/api/projects/{pid}/site", json={"frost_depth_mm": 900})
    r = client.get(f"/api/projects/{pid}/readiness")
    assert r.status_code == 200
    assert "supply_unknown" in {i["code"] for i in r.json()["items"]}
