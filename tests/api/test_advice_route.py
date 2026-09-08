"""The advice route. It reads; it changes nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app

# 5000mm against the demo knowledge's `max_span_mm = 1800` (tests/strategy/
# test_choice_generation.py) leaves `bay_layout` with more than one admissible
# answer — an equal split and a fewest-posts alternative — so a run generated
# over it is exactly the "open question" case this route exists to answer.
_LENGTH_MM = 5000

# Exactly one max span and nothing to split: at this length `generate()` never
# logs a gap with more than one admissible layout, so `choice_sets` comes back
# empty — not "no question survived", but no slice for the task to read at
# all. That is `run_task`'s vacuous case: `evaluated=False`, which must stay
# distinguishable from an empty `proposals` list on an evaluated run.
_UNEVALUATED_LENGTH_MM = 1800


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project_id(client) -> str:
    return client.post("/api/projects", json={"name": "advice"}).json()["id"]


def _put_topology(client, project_id: str, length_mm: int = _LENGTH_MM) -> None:
    r = client.put(f"/api/projects/{project_id}/topology", json={
        "revision": 1,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": length_mm, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    assert r.status_code == 200, r.text


@pytest.fixture()
def seeded_run(client, project_id) -> str:
    _put_topology(client, project_id)
    gen = client.post(f"/api/projects/{project_id}/generate")
    assert gen.status_code == 200, gen.text
    return gen.json()["result"]["run"]["id"]


@pytest.fixture()
def seeded_run_no_question(client, project_id) -> str:
    """A run with no gap that has more than one admissible layout at all —
    `choice_sets` comes back empty, so `RANK_CHOICE_SET`'s only `reads` slice
    is absent and `run_task` reports `evaluated=False` before the runner is
    ever asked to look (`agent/run.py`'s vacuous-green rule)."""
    _put_topology(client, project_id, _UNEVALUATED_LENGTH_MM)
    gen = client.post(f"/api/projects/{project_id}/generate")
    assert gen.status_code == 200, gen.text
    return gen.json()["result"]["run"]["id"]


@pytest.fixture()
def moved_topology(client, project_id, seeded_run) -> None:
    """Bumps the project's topology revision past the one the run was
    generated from, by PUTting it again — `PUT` always assigns
    `project.topology.revision + 1` (`app.py`'s `put_topology`), so a second
    PUT after `seeded_run` already moves it."""
    _put_topology(client, project_id)


def test_advice_on_a_run_with_an_open_question(client, seeded_run):
    r = client.get(f"/api/runs/{seeded_run}/advice")
    assert r.status_code == 200
    body = r.json()
    assert body["evaluated"] is True
    assert body["task_id"] == "rank_choice_set"
    # The count first: a `for` loop over an empty list passes on nothing, and
    # that vacuous green is exactly the failure this test exists to catch
    # (spec §8b — "the stub's tests must assert that a proposal was actually
    # produced").
    assert len(body["proposals"]) == 1, body
    for proposal in body["proposals"]:
        assert proposal["source_class"] == "ai_proposal"
        assert proposal["claims"], "a proposal with no rationale is not a proposal"


def test_advice_never_mutates_the_project(client, seeded_run, project_id):
    before = client.get(f"/api/projects/{project_id}").json()
    client.get(f"/api/runs/{seeded_run}/advice")
    assert client.get(f"/api/projects/{project_id}").json() == before


def test_advice_is_the_same_on_two_calls(client, seeded_run):
    a = client.get(f"/api/runs/{seeded_run}/advice").json()
    b = client.get(f"/api/runs/{seeded_run}/advice").json()
    ids = [p["id"] for p in a["proposals"]]
    # `[] == []` passes without proving anything replayed identically — pin a
    # non-empty list first, same reasoning as the open-question test above.
    assert ids, a
    assert ids == [p["id"] for p in b["proposals"]]


def test_advice_refuses_a_run_whose_topology_moved(client, seeded_run, moved_topology):
    r = client.get(f"/api/runs/{seeded_run}/advice")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "topology_changed"


# -- the wire contract Task 10's UI is about to build on ----------------------

def test_advice_carries_produced_dropped_and_claims_refused_as_distinct_counters(
    client, seeded_run,
):
    """Task 7 made `produced`, `dropped` and `claims_refused` three separate
    counters on purpose (`agent/proposal.py`'s `TaskResult`) — a flattening
    regression (folding one into another, or dropping one from the response)
    would be invisible to every other test here, which only reads
    `proposals`."""
    body = client.get(f"/api/runs/{seeded_run}/advice").json()
    for key in ("produced", "dropped", "claims_refused"):
        assert key in body, body
        assert isinstance(body[key], int) and not isinstance(body[key], bool), body
    assert body["produced"] == 1
    assert body["dropped"] == 0
    assert body["claims_refused"] == 0


def test_advice_reports_evaluated_false_when_the_task_had_nothing_to_read(
    client, seeded_run_no_question,
):
    """"I did not look" must stay distinguishable from "I looked and found
    nothing" — `evaluated: false`, not an empty `proposals` list standing in
    for it (`agent/run.py`'s vacuous-green rule)."""
    r = client.get(f"/api/runs/{seeded_run_no_question}/advice")
    assert r.status_code == 200
    body = r.json()
    assert body["evaluated"] is False
    assert body["proposals"] == []


def test_advice_on_an_unknown_run_is_a_404(client):
    r = client.get("/api/runs/nope/advice")
    assert r.status_code == 404
    assert "not found" in str(r.json()["detail"])
