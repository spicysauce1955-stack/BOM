"""Loading a published snapshot over HTTP, and being refused one.

The refusal is the path with the most traffic ahead of it: the only real snapshot
in existence predates §1.1's typed `Date`, so *"refused, and here is whose move
it is"* is what the first person to use this feature meets. It has to arrive as a
sentence, not a stack trace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app

FIXTURE = (Path(__file__).resolve().parents[2]
           / "docs" / "integration-contract" / "fixtures" / "snapshot-example.json")


@pytest.fixture()
def raw() -> dict:
    return json.loads(FIXTURE.read_text())


def test_nothing_loaded_reports_a_state_not_an_error():
    with TestClient(app) as client:
        got = client.get("/api/knowledge/snapshot")
        assert got.status_code == 200
        assert got.json()["loaded"] is False


def test_loading_a_snapshot_reports_what_it_became(raw):
    """Counts a person asks about: how much came in, how much was declined, how
    many holes were reported. Not a bare 200."""
    with TestClient(app) as client:
        got = client.post("/api/knowledge/snapshot", json=raw)
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["snapshot_id"] == raw["snapshot_id"]
        assert body["versions"] >= 1
        assert body["gaps"] >= 1

        # ...and it is now the active one, with the same story
        active = client.get("/api/knowledge/snapshot").json()
        assert active["loaded"] is True
        assert active["snapshot_id"] == raw["snapshot_id"]
        assert active["admitted"] >= 1


def test_a_pre_v12_snapshot_is_refused_with_a_code_and_a_sentence(raw):
    """§3.2.3: refuse loudly at load, not silently at generate. The message names
    the amendment and says whose move the re-cut is — a person reading it should
    not have to know what a `Date` is to know what to do."""
    with TestClient(app) as client:
        got = client.post("/api/knowledge/snapshot",
                          json=dict(raw, contract_version="1.1.0"))
        assert got.status_code == 400
        detail = got.json()["detail"]
        assert detail["code"] == "contract_minor_predates_typed_date"
        assert "re-cut" in detail["message"]


def test_a_document_that_is_not_a_snapshot_says_which_fields(raw):
    """Addressed to whoever is holding the document, so it names fields rather
    than saying the request failed."""
    with TestClient(app) as client:
        got = client.post("/api/knowledge/snapshot", json={"nope": 1})
        assert got.status_code == 400
        detail = got.json()["detail"]
        assert detail["code"] == "snapshot_malformed"
        assert detail["errors"], "a malformed document names its fields"


def test_a_run_pins_the_publishers_snapshot_id(raw):
    """§3.2 obligation 1, which was not being kept: a run recorded our own digest
    of the version list and nothing that could be handed back to the publisher.

    Asserted through a real generation so the pin is proven on the path that
    actually stores runs, not on a constructed `Run`."""
    with TestClient(app) as client:
        assert client.post("/api/knowledge/snapshot", json=raw).status_code == 200

        pid = client.post("/api/projects", json={"name": "pinned"}).json()["id"]
        client.put(f"/api/projects/{pid}/topology", json={
            "revision": 1,
            "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 6000, "y_mm": 0}],
            "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
        })
        gen = client.post(f"/api/projects/{pid}/generate")
        assert gen.status_code == 200, gen.text
        run = gen.json()["result"]["run"]
        assert run["snapshot_id"] == raw["snapshot_id"]
        # our own digest is still there and still answers its own question
        assert run["snapshot_hash"]
        assert run["snapshot_hash"] != run["snapshot_id"]
