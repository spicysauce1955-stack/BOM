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


def test_explain_lang_param(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = result["run"]["id"]
    post_id = result["strategy"]["posts"][0]["id"]
    he = client.get(f"/api/runs/{run_id}/explain/{post_id}?lang=he").json()
    assert any("עמוד בתחנה" in line for line in he["explanation"])
    en = client.get(f"/api/runs/{run_id}/explain/{post_id}?lang=en").json()
    assert any("Post at station" in line for line in en["explanation"])
    # only en|he accepted
    assert client.get(f"/api/runs/{run_id}/explain/{post_id}?lang=fr").status_code == 422


def test_explain_units_param(client):
    """`units` is a display choice like `lang`: same decisions, same structure,
    numbers rendered in the reader's unit. The stored graph stays int mm."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = result["run"]["id"]
    post = next(p for p in result["strategy"]["posts"] if p["station_mm"])
    url = f"/api/runs/{run_id}/explain/{post['id']}"
    mm = client.get(url).json()["explanation"]                 # default
    cm = client.get(f"{url}?units=cm").json()["explanation"]
    assert len(mm) == len(cm)
    assert any(f"station {post['station_mm']} mm" in line for line in mm)
    assert any(f"station {post['station_mm'] // 10} cm" in line for line in cm)
    assert client.get(f"{url}?units=inch").status_code == 422
    # the graph itself is untouched by how it was read
    again = client.get(url).json()["explanation"]
    assert again == mm


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


def test_project_listing_and_get(client):
    pid = make_project(client, name="alpha")
    assert any(p["id"] == pid and p["name"] == "alpha" for p in client.get("/api/projects").json())
    assert client.get(f"/api/projects/{pid}").json()["name"] == "alpha"
    assert client.get("/api/projects/nope").status_code == 404
    assert client.get("/api/runs/nope").status_code == 404


def test_duplicate_topology_ids_rejected(client):
    pid = make_project(client)
    bad = {
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0}, {"id": "n1", "x_mm": 5000, "y_mm": 0}],
        "runs": [],
    }
    r = client.put(f"/api/projects/{pid}/topology", json=bad)
    assert r.status_code == 422  # corruption becomes a validation error (review #1)


def test_delete_override_and_regenerate(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    ov = client.post(
        f"/api/projects/{pid}/overrides",
        json={"id": "", "run_id": "run1", "directive": {"kind": "pin_post", "station_mm": 2000}},
    ).json()
    r1 = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert any(p["pinned"] for p in r1["strategy"]["posts"])
    client.delete(f"/api/projects/{pid}/overrides/{ov['id']}")
    r2 = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert not any(p["pinned"] for p in r2["strategy"]["posts"])
    assert client.delete(f"/api/projects/{pid}/overrides/gone").status_code == 404


def test_candidate_reject_and_scope_restrict(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]

    def correction(comment):
        client.post(
            f"/api/projects/{pid}/corrections",
            json={"generation_run_id": run["run"]["id"], "comment": comment, "author": "e"},
        )

    correction("use the existing foundation here")
    cand = client.post(f"/api/projects/{pid}/propose-knowledge").json()[0]

    # widening/retargeting disguised as restriction is rejected (review #2)
    r = client.post(
        f"/api/candidates/{cand['object_id']}/{cand['version']}/review",
        json={"action": "scope_restrict", "reviewer": "boss",
              "edited_scope": {"project_id": "other-project", "series": "X"}},
    )
    assert r.status_code == 400

    r = client.post(
        f"/api/candidates/{cand['object_id']}/{cand['version']}/review",
        json={"action": "scope_restrict", "reviewer": "boss",
              "edited_scope": {**cand["scope"], "series": "X"}},
    )
    assert r.status_code == 200
    approved = r.json()
    assert approved["status"] == "active" and approved["scope"]["series"] == "X"

    # a second candidate: reject path with reason, kept as rejected
    correction2 = client.post(
        f"/api/projects/{pid}/corrections",
        json={"generation_run_id": run["run"]["id"],
              "comment": "another foundation note", "author": "e"},
    )
    cand2 = client.post(f"/api/projects/{pid}/propose-knowledge").json()
    if cand2:
        c2 = cand2[0]
        out = client.post(
            f"/api/candidates/{c2['object_id']}/{c2['version']}/review",
            json={"action": "reject", "reviewer": "boss", "reason": "one-off"},
        ).json()
        assert out["status"] == "rejected"
    assert client.post(
        "/api/candidates/NOPE/1/review", json={"action": "approve", "reviewer": "x"}
    ).status_code == 404


def test_catalog_and_audit(client):
    catalog = client.get("/api/catalog").json()
    assert "RAIL-3000" in catalog["products"]
    new_product = {
        "sku": "POST-ALU", "name": "Aluminium post",
        "consumption": {"kind": "indivisible_discrete"}, "price_cents": 5100,
    }
    client.put("/api/catalog/products", json=new_product)
    assert "POST-ALU" in client.get("/api/catalog").json()["products"]

    entries = client.get("/api/audit").json()
    assert any(e["action"] == "save_catalog" for e in entries)


def test_bom_reports_inventory_hash(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]
    h1 = client.get(f"/api/runs/{run['run']['id']}/bom").json()["inventory_hash"]
    client.put(
        f"/api/projects/{pid}/inventory",
        json={"items": [{"id": "s1", "sku": "POST-S", "kind": "full_stock", "qty": 2}]},
    )
    h2 = client.get(f"/api/runs/{run['run']['id']}/bom").json()["inventory_hash"]
    assert h1 != h2  # a re-quoted BOM is distinguishable (review #5)
    assert any(e["action"] == "fulfill" for e in client.get("/api/audit").json())


def test_generation_failure_is_422(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    # retire the only max-span constraint -> generation must fail loudly
    client.post("/api/knowledge/K-MAXSPAN/1/retire")
    r = client.post(f"/api/projects/{pid}/generate")
    assert r.status_code == 422
    assert "max_span" in r.json()["detail"]


def test_knowledge_impact_preview(client):
    pid = make_project(client, name="impact-demo")
    put_straight_topology(client, pid)
    client.post(f"/api/projects/{pid}/generate")

    report = client.post(
        "/api/knowledge/preview-impact",
        json={
            "object_id": "K-MAXSPAN", "type": "hard_constraint",
            "title": "tighter", "author": "expert-admin",
            "actions": [{"kind": "set_param", "param": "max_span_mm", "value": 1400}],
        },
    ).json()
    assert report["projects_checked"] >= 1  # includes the seeded sample project
    impact = next(i for i in report["impacts"] if i["project_id"] == pid)
    assert impact["changed"]
    assert (impact["spans_before"], impact["spans_after"]) == (4, 5)
    assert impact["bom_delta_cents"] == -2600  # tighter cuts pack better (see impact tests)

    # preview must not have persisted anything
    versions = client.get("/api/knowledge").json()
    assert not any(v["object_id"] == "K-MAXSPAN" and v["version"] == 2 for v in versions)
    runs = client.get(f"/api/projects/{pid}/runs").json()
    assert len(runs) == 1  # preview regenerations are never saved


def test_candidate_impact_preview(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]
    client.post(
        f"/api/projects/{pid}/corrections",
        json={"generation_run_id": run["run"]["id"],
              "comment": "use existing foundations here", "author": "e"},
    )
    cand = client.post(f"/api/projects/{pid}/propose-knowledge").json()[0]
    report = client.post(
        f"/api/candidates/{cand['object_id']}/{cand['version']}/preview"
    ).json()
    assert report["projects_checked"] >= 1
    assert report["projects_affected"] == 0  # advisory AddNote: honest zero impact
    assert client.post("/api/candidates/NOPE/1/preview").status_code == 404


def test_quote_snapshot_flow(client):
    pid = make_project(client, name="quote-flow")
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = run["run"]["id"]

    q1 = client.post(f"/api/runs/{run_id}/quote", json={"label": "first offer"}).json()
    assert q1["status"] == "draft"
    assert q1["total_cents"] == q1["bom"]["total_cents"] > 0
    assert q1["knowledge_snapshot_hash"] == run["run"]["snapshot_hash"]
    total_before = q1["total_cents"]

    # inventory changes -> LIVE bom changes, but the quote document does not
    client.put(
        f"/api/projects/{pid}/inventory",
        json={"items": [{"id": "s1", "sku": "POST-S", "kind": "full_stock", "qty": 5}]},
    )
    live = client.get(f"/api/runs/{run_id}/bom").json()["bom"]
    assert live["total_cents"] != total_before
    frozen = client.get(f"/api/quotes/{q1['id']}").json()
    assert frozen["total_cents"] == total_before

    # accept; a second accepted quote supersedes the first
    assert client.post(f"/api/quotes/{q1['id']}/accept").json()["status"] == "accepted"
    q2 = client.post(f"/api/runs/{run_id}/quote", json={"label": "revised"}).json()
    client.post(f"/api/quotes/{q2['id']}/accept")
    quotes = client.get(f"/api/projects/{pid}/quotes").json()
    assert [q["status"] for q in quotes] == ["superseded", "accepted"]
    assert client.post(f"/api/quotes/{q1['id']}/accept").status_code == 400
    assert client.get("/api/quotes/none").status_code == 404


def test_impact_preview_reports_vs_accepted_quote(client):
    pid = make_project(client, name="quoted")
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]
    q = client.post(f"/api/runs/{run['run']['id']}/quote", json={}).json()
    client.post(f"/api/quotes/{q['id']}/accept")

    report = client.post(
        "/api/knowledge/preview-impact",
        json={
            "object_id": "K-MAXSPAN", "type": "hard_constraint",
            "title": "tighter", "author": "expert-admin",
            "actions": [{"kind": "set_param", "param": "max_span_mm", "value": 1400}],
        },
    ).json()
    impact = next(i for i in report["impacts"] if i["project_id"] == pid)
    assert impact["accepted_quote_cents"] == q["total_cents"]
    assert impact["vs_accepted_delta_cents"] == impact["bom_after_cents"] - q["total_cents"]


def test_fresh_database_seeds_a_sample_project(client):
    projects = client.get("/api/projects").json()
    assert len(projects) == 1
    sample = client.get(f"/api/projects/{projects[0]['id']}").json()
    assert len(sample["topology"]["runs"]) == 2  # L-shape with gate + wall section
    kinds = {e["payload"]["kind"] for r in sample["topology"]["runs"]
             for e in r["point_events"] + r["interval_events"]}
    assert {"gate", "base", "base_top"} <= kinds
    # it generates cleanly out of the box
    assert client.post(f"/api/projects/{projects[0]['id']}/generate").status_code == 200


def test_structure_endpoint_lays_out_the_run(client):
    """The structure view is derived: same run in, same document out, and every
    element it names exists in the strategy."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = result["run"]["id"]
    doc = client.get(f"/api/runs/{run_id}/structure").json()

    assert doc["run_id"] == run_id
    section = doc["sections"][0]
    assert section["tag"] == "A"
    assert [s["tag"] for s in section["setting_out"]][:2] == ["A/P1", "A/P2"]
    element_ids = {p["id"] for p in result["strategy"]["posts"]} \
        | {s["id"] for s in result["strategy"]["spans"]}
    for row in [*section["setting_out"], *section["bays"]]:
        assert row["element_id"] in element_ids
    # every bay says what it is made of
    assert all(bay["parts"] for bay in section["bays"])
    # reading it twice changes nothing
    assert client.get(f"/api/runs/{run_id}/structure").json() == doc


def test_structure_stamps_the_inventory_it_read(client):
    """The layout depends on the run alone, but a part names the BAR it is cut
    from — and that depends on what was in the yard. Two sheets that differ must
    be explainable, so the snapshot is stamped like the BOM's."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = result["run"]["id"]
    before = client.get(f"/api/runs/{run_id}/structure").json()
    assert before["inventory_hash"]

    client.put(f"/api/projects/{pid}/inventory", json={"items": [
        {"id": "inv1", "sku": "RAIL-3000", "kind": "remnant", "qty": 1, "length_mm": 2000}]})
    after = client.get(f"/api/runs/{run_id}/structure").json()
    assert after["inventory_hash"] != before["inventory_hash"]
    # the layout is untouched by what was in the yard; only the provenance moved
    strip = lambda doc: [[(r["tag"], r["station_mm"]) for r in s["setting_out"]]
                         for s in doc["sections"]]
    assert strip(after) == strip(before)
    bars = [b for s in after["sections"] for bay in s["bays"]
            for p in bay["parts"] for b in p["from_bars"]]
    assert any("inv1" in b for b in bars)


def test_structure_endpoint_404s_on_an_unknown_run(client):
    assert client.get("/api/runs/nope/structure").status_code == 404


def test_structure_refuses_a_run_that_no_longer_matches_the_drawing(client):
    """Laying a stored strategy over an edited topology invents stations for posts
    nobody placed — and that document is what goes to site."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = result["run"]["id"]
    assert client.get(f"/api/runs/{run_id}/structure").status_code == 200

    put_straight_topology(client, pid, length=9000)      # the drawing moved
    stale = client.get(f"/api/runs/{run_id}/structure")
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "topology_changed"

    # regenerating makes it current again
    again = client.post(f"/api/projects/{pid}/generate").json()["result"]
    fresh = client.get(f"/api/runs/{again['run']['id']}/structure")
    assert fresh.status_code == 200
    assert fresh.json()["sections"][0]["length_mm"] == 9000
