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


# -- published parts, over HTTP (item 7) ---------------------------------------

_A_RAIL = {
    "id": "shared/not-a-real-rail",
    "status": "active",
    "type": {"key": "rail", "namespace": "shared"},
    "name_i18n": {"en": "Not a real rail"},
    "spec": [{
        "key": "nominal_length_mm", "agree": "==",
        "value": {"amount_milli": 4876800, "unit": "mm",
                  "value_raw": ["16 foot lengths"]},
        "provenance": {
            "cites": [{"id": "ref-1", "belongs_to": "FIXTURE-doc-1"}],
            "source_class": "manufacturer_installation_instruction",
            "curation_level": 0, "version_status": "unknown",
        },
    }],
}


def _with_a_part(raw: dict) -> dict:
    payload = json.loads(json.dumps(raw))
    payload["parts"] = [_A_RAIL]
    payload["source_docs"] = payload["source_docs"] + [{
        "content_hash": "FIXTURE-doc-1",
        "source_class": "manufacturer_installation_instruction",
        "version_status": "unknown",
    }]
    return payload


def test_the_snapshot_summary_counts_the_spec_values_it_judged(raw):
    """`unconsumed` used to be the only thing this route said about parts, and
    it said the honest thing at the time: nothing consumed them. Now that they
    are judged, the count of judged values is what an operator needs — with the
    reminder that a judged value is not a value in a plan."""
    with TestClient(app) as client:
        got = client.post("/api/knowledge/snapshot", json=_with_a_part(raw))
        assert got.status_code == 200, got.text
        assert got.json()["part_specs"] == 1

        active = client.get("/api/knowledge/snapshot").json()
        assert active["part_specs"] == 1
        assert active["unconsumed"] == {}


def test_a_judged_spec_value_is_inspectable_with_the_documents_behind_it(raw):
    """The reviewer's question §1.2.1 calls out — *"which documents is this
    definition built from"* — answered per VALUE rather than per definition,
    because that is the level admissibility is decided at.

    Its own route rather than a field on the summary: the summary is counts a
    person scans, and a snapshot may carry thousands of parts."""
    with TestClient(app) as client:
        client.post("/api/knowledge/snapshot", json=_with_a_part(raw))

        body = client.get("/api/knowledge/parts").json()
        assert body["loaded"] is True
        spec = body["specs"][0]
        assert spec["part_id"] == "shared/not-a-real-rail"
        assert spec["key"] == "nominal_length_mm"
        assert spec["task"] == "component_dimension"
        assert spec["admitted_by"]["rank"] == 3
        assert [d["content_hash"] for d in spec["sources"]] == ["FIXTURE-doc-1"]
        assert body["defects"] == []


def test_the_parts_route_reports_no_snapshot_as_a_state(raw):
    with TestClient(app) as client:
        body = client.get("/api/knowledge/parts").json()
        assert body["loaded"] is False
        assert body["specs"] == []
