"""API integration tests: full scenario workflows over HTTP (plan/tasks/09-store-api.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def make_project(client, name="demo") -> str:
    return client.post("/api/projects", json={"name": name}).json()["id"]


def put_straight_topology(client, project_id: str, length=6000):
    topology = {
        "nodes": [
            {"id": "n1", "x_mm": 0, "y_mm": 0},
            {"id": "n2", "x_mm": length, "y_mm": 0},
        ],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    }
    r = client.put(f"/api/projects/{project_id}/topology", json=topology)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_reports_stub(client):
    r = client.get("/api/health")
    assert r.json() == {"ok": True, "interpreter": "stub"}


def test_full_generation_flow(client):
    pid = make_project(client)
    put_straight_topology(client, pid)

    r = client.post(f"/api/projects/{pid}/generate")
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert len(result["strategy"]["spans"]) == 4
    assert len(result["strategy"]["posts"]) == 5
    run_id = result["run"]["id"]
    assert result["run"]["knowledge_snapshot"]  # snapshot stamped

    # runs are persisted and listable
    runs = client.get(f"/api/projects/{pid}/runs").json()
    assert [r["id"] for r in runs] == [run_id]

    # BOM from the persisted run
    bom = client.get(f"/api/runs/{run_id}/bom").json()["bom"]
    skus = {l["sku"] for l in bom["lines"]}
    assert {"POST-S", "RAIL-3000", "SCREW-S10", "CONC-25"} <= skus

    # explanation for a generated post
    post_id = result["strategy"]["posts"][0]["id"]
    exp = client.get(f"/api/runs/{run_id}/explain/{post_id}").json()
    assert any("Post at station" in line for line in exp["explanation"])

    # impact analysis: decisions depending on K-MAXSPAN
    impact = client.get(f"/api/runs/{run_id}/impact/K-MAXSPAN").json()
    assert impact["decisions"]


def test_annotation_interpret_confirm_flow(client):
    pid = make_project(client)
    put_straight_topology(client, pid, length=3000)

    ann = client.post(
        f"/api/projects/{pid}/annotations",
        json={"target_ref": "run:run1", "text": "keep the top aligned with the neighbour (approx. 1750)"},
    ).json()
    record = client.post(f"/api/projects/{pid}/annotations/{ann['id']}/interpret").json()
    assert record["interpreter"] == "stub"
    assert len(record["candidates"]) == 1
    intent = record["candidates"][0]
    assert intent["status"] == "proposed"

    # before confirmation: default heights
    r1 = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert all(s["height_mm"] == 1800 for s in r1["strategy"]["spans"])

    conf = client.post(
        f"/api/projects/{pid}/intents/{intent['id']}/confirm",
        json={"annotation_id": ann["id"], "run_id": "run1"},
    )
    assert conf.status_code == 200, conf.text

    r2 = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert all(s["height_mm"] == 1750 for s in r2["strategy"]["spans"])
    # different topology revision -> different run identity
    assert r2["run"]["id"] != r1["run"]["id"]
    assert r2["run"]["topology_revision"] > r1["run"]["topology_revision"]


def test_override_flow(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    ov = client.post(
        f"/api/projects/{pid}/overrides",
        json={"id": "", "run_id": "run1", "directive": {"kind": "pin_post", "station_mm": 2000}},
    ).json()
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    pinned = [p for p in result["strategy"]["posts"] if p["pinned"]]
    assert len(pinned) == 1 and pinned[0]["station_mm"] == 2000
    assert ov["id"] in result["run"]["overrides_applied"]


def test_correction_candidate_review_flow(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]

    client.post(
        f"/api/projects/{pid}/corrections",
        json={
            "generation_run_id": run["run"]["id"],
            "element_ref": "post@run1:1500",
            "before": {"station_mm": 1500},
            "after": {"station_mm": 1450},
            "comment": "always use existing foundations when within 300 mm",
            "author": "expert-jane",
        },
    )
    proposals = client.post(f"/api/projects/{pid}/propose-knowledge").json()
    assert len(proposals) == 1
    cand = proposals[0]
    assert cand["status"] == "proposed"

    # candidate listed for review; generation unaffected while proposed
    assert len(client.get("/api/candidates").json()) == 1
    r_with_cand = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert r_with_cand["strategy"] == run["strategy"]

    outcome = client.post(
        f"/api/candidates/{cand['object_id']}/{cand['version']}/review",
        json={"action": "approve", "reviewer": "expert-admin"},
    ).json()
    assert outcome["status"] == "active"
    assert outcome["version"] == cand["version"] + 1
    assert client.get("/api/candidates").json() == []

    # re-proposal of the same correction is suppressed
    assert client.post(f"/api/projects/{pid}/propose-knowledge").json() == []


def test_knowledge_versioning_flow(client):
    v = client.post(
        "/api/knowledge",
        json={
            "object_id": "K-MAXSPAN",
            "type": "hard_constraint",
            "title": "Tightened max span",
            "actions": [{"kind": "set_param", "param": "max_span_mm", "value": 1500}],
            "author": "expert-admin",
        },
    ).json()
    assert v["version"] == 2
    versions = client.get("/api/knowledge").json()
    v1 = next(x for x in versions if x["object_id"] == "K-MAXSPAN" and x["version"] == 1)
    assert v1["status"] == "retired"

    # the new rule version changes generation and is stamped in the snapshot
    pid = make_project(client)
    put_straight_topology(client, pid)  # 6000 with max 1500 -> 4 spans of 1500 still,
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert ["K-MAXSPAN", 2] in result["run"]["knowledge_snapshot"]
    assert ["K-MAXSPAN", 1] not in result["run"]["knowledge_snapshot"]


def test_inventory_flow(client):
    pid = make_project(client)
    put_straight_topology(client, pid, length=1200)
    client.put(
        f"/api/projects/{pid}/inventory",
        json={"items": [{"id": "rem1", "sku": "RAIL-3000", "kind": "remnant", "length_mm": 1250, "qty": 1}]},
    )
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]
    bom = client.get(f"/api/runs/{run['run']['id']}/bom").json()["bom"]
    assert bom["cut_plans"]["RAIL-3000"]["new_bar_count"] == 1
    assert any(a["inventory_item_id"] == "rem1" for a in bom["allocations"])


def test_generation_failure_is_422(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    # retire the only max-span constraint -> generation must fail loudly
    client.post("/api/knowledge/K-MAXSPAN/1/retire")
    r = client.post(f"/api/projects/{pid}/generate")
    assert r.status_code == 422
    assert "max_span" in r.json()["detail"]
