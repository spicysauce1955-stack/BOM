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


def test_bom_refuses_a_run_read_against_a_different_catalog(client):
    """Stamping is not checking. /bom recomputes against today's catalog, so it
    must refuse rather than quietly serve a different answer (task 10)."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]

    product = client.get("/api/catalog").json()["products"]["RAIL-3000"]
    product["price_cents"] = 9999
    client.put("/api/catalog/products", json=product)

    response = client.get(f"/api/runs/{run_id}/bom")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "catalog_changed"


def test_quote_refuses_a_run_read_against_a_different_catalog(client):
    """The divergence four copies of one pipeline actually caused.

    `create_quote` called `state.store.load_catalog()` directly while /bom and
    /structure went through `_fresh_catalog`, so the ONE endpoint that freezes an
    immutable commercial document was the only one exempt from the staleness
    check — verified before the fix as BOM 409, structure 409, quote 200. All
    four sites now share one helper, so a quote cannot be the odd one out."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]

    product = client.get("/api/catalog").json()["products"]["RAIL-3000"]
    product["price_cents"] = 9999
    client.put("/api/catalog/products", json=product)

    response = client.post(f"/api/runs/{run_id}/quote", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "catalog_changed"


def test_a_quote_records_the_catalog_that_priced_it(client):
    """Provenance beside knowledge_snapshot_hash: the two inputs that decide
    what the customer was quoted."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]
    quote = client.post(f"/api/runs/{run['run']['id']}/quote", json={}).json()
    assert quote["catalog_hash"]
    assert quote["catalog_hash"] == run["run"]["catalog_hash"]


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


def test_unresolved_supply_is_visible_on_working_views_and_refused_on_a_quote(client):
    """No fence model in the demo catalog currently produces an unresolvable slot
    (every eligibility group has exactly one auto-approved member), so this test
    forces the state directly: persist a run whose panel has had a slot's
    eligibility emptied out, exactly what `resolve_supply` sees as
    `no_eligible_item`. /bom and /structure are working views and must still
    report the gap rather than going silent; a quote is a commercial document and
    must refuse rather than freeze one that's silently missing a part."""
    from fenceai.api.app import state
    from fenceai.fencemodel.model import Eligibility

    pid = make_project(client, name="unresolvable")
    put_straight_topology(client, pid)
    run = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = run["run"]["id"]

    result = state.store.load_run(run_id)
    slot = result.strategy.spans[0].panel.slots[0]
    assert slot.role == "rail"
    slot.eligibility = Eligibility()  # no member can supply it
    # generation_runs is append-only (ADR-0004: a run is immutable once
    # generated) — save_run() INSERT OR IGNOREs, so a second call is a no-op.
    # Overwrite the row directly; this is a test-only way to force the state,
    # not a path the product exposes.
    state.store._conn.execute(
        "UPDATE generation_runs SET doc=? WHERE id=?",
        (result.model_dump_json(), run_id),
    )
    state.store._conn.commit()

    bom_doc = client.get(f"/api/runs/{run_id}/bom").json()
    assert bom_doc["unresolved"], "the emptied-out slot must surface, not vanish"
    assert bom_doc["unresolved"][0]["role"] == "rail"
    assert bom_doc["unresolved"][0]["sku"] == ""
    assert bom_doc["bom"]["warnings"][0]["code"] == "no_eligible_item"

    structure_doc = client.get(f"/api/runs/{run_id}/structure").json()
    assert structure_doc["unresolved"]
    assert structure_doc["unresolved"][0]["role"] == "rail"
    assert structure_doc["warnings"][0]["code"] == "no_eligible_item"

    quote_resp = client.post(f"/api/runs/{run_id}/quote", json={})
    assert quote_resp.status_code == 400
    body = quote_resp.json()["detail"]
    assert body["code"] == "unresolved_supply"
    assert body["unresolved"][0]["role"] == "rail"


def _run_with_an_unsuppliable_rail(client) -> str:
    """A persisted run whose first rail slot has no eligible member.

    Forced directly, because no fence model in the demo catalog produces an
    unresolvable slot — every eligibility group has exactly one auto-approved
    member. Mirrors the setup in
    test_unresolved_supply_is_visible_on_working_views_and_refused_on_a_quote.
    """
    from fenceai.api.app import state
    from fenceai.fencemodel.model import Eligibility

    pid = make_project(client, name="blank-sku-guard")
    put_straight_topology(client, pid)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    result = state.store.load_run(run_id)
    result.strategy.spans[0].panel.slots[0].eligibility = Eligibility()
    state.store._conn.execute(
        "UPDATE generation_runs SET doc=? WHERE id=?",
        (result.model_dump_json(), run_id),
    )
    state.store._conn.commit()
    return run_id


def test_no_blank_sku_ever_appears_in_a_bom_response(client):
    """The "no blank SKU reaches the ledger" guarantee used to rest on caller
    discipline that nothing enforced: a reviewer reintroduced the defect at all
    three routes with a three-word edit (`priced.requirements +
    priced.unresolved`) and got zero failures. `fulfill()` now refuses a blank
    sku outright, and these assertions cover what fulfill() never sees — the
    lines the RESPONSE puts under `requirements`."""
    run_id = _run_with_an_unsuppliable_rail(client)
    doc = client.get(f"/api/runs/{run_id}/bom").json()

    assert doc["unresolved"], "the gap must be reported, not hidden"
    assert all(r["sku"] for r in doc["requirements"]), \
        "an unresolved line must never be folded back into `requirements`"
    assert all(l["sku"] for l in doc["bom"]["lines"])


def test_no_blank_sku_ever_appears_on_the_structure_sheet(client):
    """A blank sku in the ledger reports one demand as unassigned AND from stock
    at once and prints an empty SKU column on a document that goes to site."""
    run_id = _run_with_an_unsuppliable_rail(client)
    doc = client.get(f"/api/runs/{run_id}/structure").json()

    assert doc["unresolved"], "the gap must be reported, not hidden"
    totals = doc["totals"]
    for bucket in ("per_sku", "unassigned", "from_stock"):
        assert all(t["sku"] for t in totals[bucket]), (bucket, totals[bucket])
    for section in doc["sections"]:
        for bay in section["bays"]:
            assert all(p["sku"] for p in bay["parts"]), bay["tag"]
        for station in section["setting_out"]:
            assert all(p["sku"] for p in station["parts"]), station["tag"]


def test_fulfill_refuses_a_blank_sku_rather_than_trusting_its_caller(client):
    """The guarantee is structural now, not a convention. This is the unit-level
    statement of it; the two route tests above cover the response shapes
    fulfill() never gets to see."""
    import pytest

    from fenceai.catalog.demo import demo_catalog
    from fenceai.demand.derive import RequirementLine
    from fenceai.fulfillment.fulfill import fulfill

    with pytest.raises(ValueError, match="no sku"):
        fulfill([RequirementLine(id="req0001", engineering_qty=2, unit="cut",
                                 cut_length_mm=1500, role="rail")], demo_catalog())


def test_a_run_generated_before_fence_models_refuses_with_a_code_not_english(client):
    """v1-known-limitations (4): runs stored before this branch cannot be read.
    That is a real, permanent state — but it surfaced as a raw English
    ValueError sentence in a Hebrew-first UI, and on the structure tab as "no
    structure yet", which is false. It carries `code + params` now, with entries
    in both locale bundles."""
    from fenceai.api.app import state

    pid = make_project(client, name="legacy-run")
    put_straight_topology(client, pid)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    result = state.store.load_run(run_id)
    for span in result.strategy.spans:
        span.panel = None                       # what a pre-branch run looks like
    state.store._conn.execute(
        "UPDATE generation_runs SET doc=? WHERE id=?",
        (result.model_dump_json(), run_id),
    )
    state.store._conn.commit()

    for path in (f"/api/runs/{run_id}/bom", f"/api/runs/{run_id}/structure"):
        response = client.get(path)
        assert response.status_code == 400, path
        detail = response.json()["detail"]
        assert detail["code"] == "run_predates_fence_model", path
        assert detail["params"]["span_id"].startswith("span@"), path

    quote = client.post(f"/api/runs/{run_id}/quote", json={})
    assert quote.status_code == 400
    assert quote.json()["detail"]["code"] == "run_predates_fence_model"


def test_a_run_with_an_unrecognised_preset_refuses_rather_than_repricing_silently(client):
    """objective_preset is stored as a plain str, so a run generated under an
    older DEFAULT_POLICY (or any bad data) can carry a value outside
    fulfillment.supply.Preset. resolve_supply now refuses it loudly instead of
    resolve_supply._choose silently treating it as least-cost (task 10 fix
    round 1, finding 3) — this proves the refusal reaches the HTTP layer as a
    clean 400, not an unhandled 500."""
    from fenceai.api.app import state

    pid = make_project(client, name="bad-preset")
    put_straight_topology(client, pid)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]

    result = state.store.load_run(run_id)
    result.run.objective_preset = "fewest_new_stock"   # the vestigial, unimplemented name
    state.store._conn.execute(
        "UPDATE generation_runs SET doc=? WHERE id=?",
        (result.model_dump_json(), run_id),
    )
    state.store._conn.commit()

    bom_resp = client.get(f"/api/runs/{run_id}/bom")
    assert bom_resp.status_code == 400
    assert "fewest_new_stock" in bom_resp.json()["detail"]

    structure_resp = client.get(f"/api/runs/{run_id}/structure")
    assert structure_resp.status_code == 400
    assert "fewest_new_stock" in structure_resp.json()["detail"]


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
    assert doc["warnings"] == []  # additive field; empty in the normal, resolved case
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


# test_structure_surfaces_supply_resolution_warnings was deleted here: it
# assigned `report.warnings` and then asserted the value it had just assigned,
# which tests Pydantic, not this system. Its only non-vacuous line was the
# empty-by-default check, and the behaviour it claimed to cover — the ROUTE
# stamping resolution warnings onto the report — is genuinely covered by
# test_unresolved_supply_is_visible_on_working_views_and_refused_on_a_quote,
# which drives it through /structure with a real unresolvable slot.


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


def test_structure_refuses_a_run_read_against_a_different_catalog(client):
    """Stamping is not checking. /structure recomputes against today's catalog,
    so it must refuse rather than quietly serve a different answer."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]

    product = client.get("/api/catalog").json()["products"]["RAIL-3000"]
    product["price_cents"] = 9999
    client.put("/api/catalog/products", json=product)

    response = client.get(f"/api/runs/{run_id}/structure")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "catalog_changed"
