"""`GET /api/projects/{id}/flags` — every problem on a job, placed.

The screen's second route. Its defining property, like `/sections`, is a
refusal it does NOT make: flags are how somebody finds out that the drawing
moved, so refusing to list them because the drawing moved is the wrong way
round.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _topology(revision: int = 0, length_mm: int = 8000) -> dict:
    return {
        "revision": revision,
        "nodes": [
            {"id": "n1", "x_mm": 0, "y_mm": 0},
            {"id": "n2", "x_mm": length_mm, "y_mm": 0},
        ],
        "runs": [{"id": "r1", "start_node_id": "n1", "end_node_id": "n2"}],
    }


def _drawn(client, revision: int = 0, length_mm: int = 8000) -> str:
    pid = client.post("/api/projects", json={"name": "bob"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/topology",
                   json=_topology(revision, length_mm))
    assert r.status_code == 200, r.text
    return pid


def _codes(body: dict) -> set[str]:
    return {f["code"] for f in body["flags"]}


def _triples(body: dict) -> set[tuple[str, str, str]]:
    return {(f["source"], f["code"], f["severity"]) for f in body["flags"]}

def _stepped(revision: int = 0) -> dict:
    """A run whose wall STEPS UP 1120 mm halfway along.

    The demo job's own shape, and the only fixture here that makes the route
    emit a `strategy` flag at all. Without one, every assertion about the run's
    own warnings passes on a job that has none — which is how the `warnings=`
    wiring of this route went unexercised end to end.
    """
    anchor = lambda mm: {"segment_index": 0, "offset_mm": mm,
                         "seg_len_at_authoring_mm": 8000,
                         "reanchor": "proportional"}
    return {
        "revision": revision,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 8000, "y_mm": 0}],
        "runs": [{
            "id": "r1", "start_node_id": "n1", "end_node_id": "n2",
            "interval_events": [
                {"id": "ev-base", "start_anchor": anchor(0), "end_anchor": anchor(8000),
                 "payload": {"kind": "base", "surface": "masonry_wall"}},
                {"id": "ev-top", "start_anchor": anchor(0), "end_anchor": anchor(8000),
                 "payload": {"kind": "base_top", "points": [
                     {"pos_permille": 0, "z_mm": 940, "lock": "level"},
                     {"pos_permille": 500, "z_mm": 940, "lock": "step"},
                     {"pos_permille": 500, "z_mm": 2060, "lock": "level"},
                     {"pos_permille": 1000, "z_mm": 2060, "lock": None}]}},
            ],
        }],
    }


def _stepped_job(client) -> str:
    pid = client.post("/api/projects", json={"name": "stepped"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/topology", json=_stepped())
    assert r.status_code == 200, r.text
    assert client.post(f"/api/projects/{pid}/generate").status_code == 200
    return pid



def test_with_no_run_it_answers_handover_flags_and_says_there_is_no_run(client):
    """A normal 200, not an error and not an empty list.

    Before generation there are no posts, no bays and no warnings — but there
    is plenty wrong with a job nobody measured, and that is exactly what the
    office opens the screen to see.
    """
    pid = _drawn(client)
    body = client.get(f"/api/projects/{pid}/flags").json()
    assert body["run_id"] == ""
    # NAMED, not merely non-empty. `assert _codes(body)` passed with every
    # handover gap deleted from the route, because the readiness source alone
    # contributes four codes — so the eight findings this screen exists for,
    # including the only blocking one, could vanish with the suite green.
    assert ("handover", "no_model_chosen", "blocking") in _triples(body)
    assert "height_assumed" in _codes(body)
    assert all(f["source"] != "strategy" for f in body["flags"])


def test_after_generating_it_carries_the_runs_own_warnings_too(client):
    """The route's `warnings=` wiring, end to end, on a job that HAS one.

    This assertion used to be a disjunction — "strategy OR readiness findings" —
    over a fixture that produced no strategy flags at all, so the left side was
    always false, the right always true, and deleting the warnings from the
    route changed nothing. A test named after a behaviour has to fail when that
    behaviour is removed.
    """
    pid = _stepped_job(client)
    body = client.get(f"/api/projects/{pid}/flags").json()
    assert body["run_id"], "the answer names the run it read"

    strategy = [f for f in body["flags"] if f["source"] == "strategy"]
    assert strategy, "a 1120 mm step is a finding the RUN makes, not the sheet"

    step = [f for f in strategy if f["code"] == "excessive_step"]
    assert step, [f["code"] for f in strategy]
    assert step[0]["severity"] == "blocking"
    # And it is placed where the step IS, which is the whole point of the model:
    # the middle of the stretch would be a mark at a spot nothing is wrong with.
    assert {"kind": "element", "element_id": "post@r1:4000", "run_id": "r1",
            "station_mm": 4000, "node_id": ""} in step[0]["places"]
    # The English fallback rides along for a code no bundle has registered yet —
    # codes are an open registry, so a miss is the expected case.
    assert step[0]["message"], "a strategy flag carries its own sentence"


def test_every_flag_carries_at_least_one_place(client):
    """The whole point of the model: a finding with nowhere to go is a finding
    somebody scrolls past."""
    pid = _drawn(client)
    client.post(f"/api/projects/{pid}/generate")
    body = client.get(f"/api/projects/{pid}/flags").json()
    assert body["flags"]
    for flag in body["flags"]:
        assert flag["places"], f"{flag['code']} has nowhere to be drawn"


def test_a_run_from_another_job_is_refused_rather_than_answered(client):
    mine = _drawn(client)
    theirs = _drawn(client)
    client.post(f"/api/projects/{theirs}/generate")
    other_run = client.get(f"/api/projects/{theirs}/runs").json()[-1]["id"]

    r = client.get(f"/api/projects/{mine}/flags", params={"run_id": other_run})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "run_not_on_this_job"


def test_a_moved_drawing_is_still_answered(client):
    """Flags are how you find out something moved.

    `/structure` refuses a stale run with 409 `topology_changed` and is right
    to — it describes a fence laid out against a drawing that has changed. This
    route is the screen that TELLS somebody that happened, so refusing here
    would hide the answer behind the problem it is reporting.
    """
    pid = _drawn(client)
    client.post(f"/api/projects/{pid}/generate")
    assert client.put(f"/api/projects/{pid}/topology",
                      json=_topology(revision=1, length_mm=9000)).status_code == 200

    r = client.get(f"/api/projects/{pid}/flags")
    assert r.status_code == 200
    assert r.json()["flags"]


def test_an_unknown_project_is_a_404(client):
    assert client.get("/api/projects/proj_nope/flags").status_code == 404


def test_the_answer_says_which_drawing_the_run_was_laid_out_against(client):
    """The pair of revisions that lets the reader tell a live mark from a lie.

    A `strategy` flag's place is a STATION minted against the run's topology.
    Move a node and those stations describe a fence that no longer exists — a
    red `!` at station 4000 of a run that is now 3000 mm long, drawn
    confidently at a spot that is not there.

    The route must not 409 (it is how somebody finds out the drawing moved), so
    it carries both revisions instead and lets the screen draw its own
    conclusion. `readiness`'s `plan_stale` does NOT cover this: it is a claim
    about the COMMITTED run only, so in the ordinary loop — generate, edit,
    nothing committed — nothing else in the answer mentions it.
    """
    pid = _stepped_job(client)
    fresh = client.get(f"/api/projects/{pid}/flags").json()
    assert fresh["run_topology_revision"] == fresh["topology_revision"], \
        "a run just generated describes the drawing it was generated from"

    shrunk = _stepped(revision=1)
    shrunk["nodes"][1]["x_mm"] = 3000
    assert client.put(f"/api/projects/{pid}/topology",
                      json=shrunk).status_code == 200

    moved = client.get(f"/api/projects/{pid}/flags").json()
    assert moved["run_topology_revision"] != moved["topology_revision"], \
        "the reader must be able to tell the run is not about this drawing"
    assert moved["run_id"], "and which run it was, so the screen can say so"

    # And the thing that makes it matter, asserted on a job that genuinely has
    # one: a station out of range of the run as it NOW stands. `or not stations`
    # here was the same vacuous shape as the disjunction above — this fixture
    # emitted no strategy flags, so the escape clause was always taken.
    stations = [p["station_mm"] for f in moved["flags"] if f["source"] == "strategy"
                for p in f["places"] if p.get("station_mm") is not None]
    assert stations, "the fixture must emit a stationed strategy flag or this proves nothing"
    assert any(s > 3000 for s in stations), \
        "a surviving strategy station belongs to the OLD drawing, and the " \
        "revisions above are the only thing telling the screen not to trust it"


def test_a_job_with_no_run_reports_no_run_revision(client):
    """Zero, and `run_id` empty — not the project's own revision, which would
    read as "generated against this exact drawing" on a job nobody generated."""
    pid = _drawn(client)
    body = client.get(f"/api/projects/{pid}/flags").json()
    assert body["run_id"] == ""
    assert body["run_topology_revision"] == 0
    # The project's OWN revision, read back rather than assumed: the topology
    # PUT bumps it server-side (a client that set its own would make a stale
    # document look current), so a literal here would pin the wrong fact.
    live = client.get(f"/api/projects/{pid}").json()["topology"]["revision"]
    assert body["topology_revision"] == live
    assert body["run_topology_revision"] != live, \
        "0 must not accidentally equal a real revision and read as fresh"


def test_a_run_of_this_job_is_answered_and_named(client):
    """The other half of the ownership check. Without it a route that refused
    EVERY `run_id`, including the caller's own, would pass the refusal test."""
    pid = _stepped_job(client)
    mine = client.get(f"/api/projects/{pid}/runs").json()[-1]["id"]
    r = client.get(f"/api/projects/{pid}/flags", params={"run_id": mine})
    assert r.status_code == 200
    assert r.json()["run_id"] == mine
    assert any(f["source"] == "strategy" for f in r.json()["flags"])
