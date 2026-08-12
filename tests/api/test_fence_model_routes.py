"""The routes that make a fence model something a user can see and choose.

Until these existed, `FenceModel` was persisted nowhere and the generator minted
the one instance in the system per call — so there was nothing to list, nothing
to pick, and no way for a project to say what it builds.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app
from fenceai.fencemodel.demo import demo_models


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
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": length, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    }
    assert client.put(f"/api/projects/{project_id}/topology", json=topology).status_code == 200


def other_model_id() -> str:
    ids = sorted(m for m in demo_models() if m != "M-LEGACY")
    assert ids, "there must be a second built-in model to choose"
    return ids[0]


# --- listing and reading ------------------------------------------------------

def test_a_fresh_database_already_offers_the_built_in_models(client):
    rows = client.get("/api/fence-models").json()
    assert {r["id"] for r in rows} == set(demo_models())
    assert all(r["active_version"] == 1 for r in rows)
    # a chooser needs a name in the reader's language, not a SKU-like id
    assert all(r["name_i18n"].get("he") for r in rows)


def test_one_model_reads_back_whole(client):
    model = client.get("/api/fence-models/M-LEGACY/1").json()
    assert model["id"] == "M-LEGACY"
    assert model["default_spec"]["frame"], "the panel structure must survive the round trip"


def test_an_unknown_model_is_a_404(client):
    assert client.get("/api/fence-models/M-NOPE/1").status_code == 404


# --- the project default ------------------------------------------------------

def test_setting_the_project_default_changes_what_generation_builds(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    chosen = other_model_id()

    before = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert [u["model_id"] for u in before["run"]["model_snapshot"]] == ["M-LEGACY"]

    r = client.put(f"/api/projects/{pid}/fence-model", json={"model_id": chosen})
    assert r.status_code == 200, r.text
    assert r.json()["fence_model"]["model_id"] == chosen

    after = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert [u["model_id"] for u in after["run"]["model_snapshot"]] == [chosen]
    assert after["run"]["id"] != before["run"]["id"]


def test_a_default_naming_an_unknown_model_is_refused_at_the_boundary(client):
    """Not at generation: a typo that only fails when Generate is pressed has
    already cost the user the strategy they were working on."""
    pid = make_project(client)
    r = client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-NOPE"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "fence_model_not_found"


def test_clearing_the_default_returns_to_the_compatibility_model(client):
    pid = make_project(client)
    put_straight_topology(client, pid)
    client.put(f"/api/projects/{pid}/fence-model", json={"model_id": other_model_id()})
    assert client.put(f"/api/projects/{pid}/fence-model").status_code == 200
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert [u["model_id"] for u in result["run"]["model_snapshot"]] == ["M-LEGACY"]


# --- the interval event, over HTTP --------------------------------------------

def test_a_fence_model_event_survives_the_topology_round_trip(client):
    pid = make_project(client)
    chosen = other_model_id()
    topology = {
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0}, {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{
            "id": "run1", "start_node_id": "n1", "end_node_id": "n2",
            "interval_events": [{
                "id": "ev_m",
                "start_anchor": {"segment_index": 0, "offset_mm": 0,
                                 "seg_len_at_authoring_mm": 6000},
                "end_anchor": {"segment_index": 0, "offset_mm": 3000,
                               "seg_len_at_authoring_mm": 6000},
                "payload": {"kind": "fence_model", "model_id": chosen},
            }],
        }],
    }
    assert client.put(f"/api/projects/{pid}/topology", json=topology).status_code == 200

    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert {u["model_id"] for u in result["run"]["model_snapshot"]} == {chosen, "M-LEGACY"}
    # the change is a structural boundary, so a post stands on it
    assert 3000 in {p["station_mm"] for p in result["strategy"]["posts"]}


# --- authoring ----------------------------------------------------------------

def draft_body(model_id="M-TEST"):
    return {
        "id": model_id, "version": 1, "name_i18n": {"en": "Test", "he": "בדיקה"},
        "default_spec": {"frame": [{
            "key": "rail", "orientation": "horizontal",
            "placement": {"kind": "distributed", "count": 2},
            "requirement": {"role": "rail", "qty": 1, "length_rule": "centre_to_centre",
                            "eligibility": {"members": [{"kind": "catalog_item", "sku": "RAIL-3000"}]}},
        }]},
    }


def test_a_new_model_arrives_as_a_draft_and_is_not_yet_selectable(client):
    r = client.post("/api/fence-models", json=draft_body())
    assert r.status_code == 200, r.text
    assert r.json()["model"]["status"] == "draft"
    assert r.json()["invalid"] is None

    row = next(x for x in client.get("/api/fence-models").json() if x["id"] == "M-TEST")
    assert row["active_version"] is None and row["has_draft"] is True

    pid = make_project(client)
    assert client.put(f"/api/projects/{pid}/fence-model",
                      json={"model_id": "M-TEST"}).status_code == 422


def test_a_draft_may_be_saved_invalid_and_says_so(client):
    """Authoring is iterative: a save that refuses until the whole panel is
    coherent is a save nobody can use. The gate is publish."""
    body = draft_body()
    body["default_spec"]["frame"][0]["requirement"]["eligibility"]["members"] = [
        {"kind": "catalog_item", "sku": "NOT-IN-CATALOG"}
    ]
    r = client.post("/api/fence-models", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["invalid"]["code"] == "fence_model_unknown_sku"
    assert "NOT-IN-CATALOG" in r.json()["invalid"]["params"]["skus"]


def test_publishing_an_invalid_draft_is_refused(client):
    body = draft_body()
    body["default_spec"]["frame"][0]["requirement"]["eligibility"]["members"] = [
        {"kind": "catalog_item", "sku": "NOT-IN-CATALOG"}
    ]
    created = client.post("/api/fence-models", json=body).json()["model"]
    r = client.post(f"/api/fence-models/M-TEST/{created['version']}/publish")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "fence_model_unknown_sku"


def test_publish_then_select_then_generate(client):
    created = client.post("/api/fence-models", json=draft_body()).json()["model"]
    published = client.post(
        f"/api/fence-models/M-TEST/{created['version']}/publish").json()
    assert published["status"] == "active"

    pid = make_project(client)
    put_straight_topology(client, pid)
    assert client.put(f"/api/projects/{pid}/fence-model",
                      json={"model_id": "M-TEST"}).status_code == 200
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    assert [u["model_id"] for u in result["run"]["model_snapshot"]] == ["M-TEST"]


def test_a_published_version_cannot_be_rewritten_through_the_draft_route(client):
    """The immutability invariant lives in the store, so no route can talk past
    it — an accepted quote's model must mean the same thing tomorrow."""
    created = client.post("/api/fence-models", json=draft_body()).json()["model"]
    client.post(f"/api/fence-models/M-TEST/{created['version']}/publish")

    changed = draft_body()
    changed["name_i18n"]["en"] = "Rewritten"
    r = client.put("/api/fence-models/M-TEST/draft", json=changed)
    assert r.status_code == 200, r.text
    # it became the NEXT version as a draft, and the published one is untouched
    assert r.json()["model"]["version"] == created["version"] + 1
    assert client.get(f"/api/fence-models/M-TEST/{created['version']}").json(
        )["name_i18n"]["en"] == "Test"


def test_retiring_a_version_removes_it_from_the_unpinned_path(client):
    created = client.post("/api/fence-models", json=draft_body()).json()["model"]
    client.post(f"/api/fence-models/M-TEST/{created['version']}/publish")
    r = client.post(
        f"/api/fence-models/M-TEST/{created['version']}/status?status=retired")
    assert r.status_code == 200, r.text

    row = next(x for x in client.get("/api/fence-models").json() if x["id"] == "M-TEST")
    assert row["active_version"] is None
    pid = make_project(client)
    assert client.put(f"/api/projects/{pid}/fence-model",
                      json={"model_id": "M-TEST"}).status_code == 422
    # but a pin still resolves it, or retiring would rewrite what stored runs meant
    assert client.put(f"/api/projects/{pid}/fence-model",
                      json={"model_id": "M-TEST",
                            "version_pin": created["version"]}).status_code == 200


# --- the whole point: the model reaches the money ------------------------------

def test_choosing_the_slat_model_puts_slats_in_the_bom(client):
    """The claim the feature makes — model -> panel -> materials, sizes and
    structure — asserted at the far end of the pipeline rather than at the
    resolver. A slat that reaches no BOM line is the failure this pins."""
    pid = make_project(client)
    put_straight_topology(client, pid)

    legacy = client.post(f"/api/projects/{pid}/generate").json()["result"]
    legacy_bom = client.get(f"/api/runs/{legacy['run']['id']}/bom").json()["bom"]
    assert "SLAT-100" not in {line["sku"] for line in legacy_bom["lines"]}

    client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-SLAT"})
    slat = client.post(f"/api/projects/{pid}/generate").json()["result"]
    body = client.get(f"/api/runs/{slat['run']['id']}/bom").json()
    lines = {line["sku"]: line for line in body["bom"]["lines"]}

    assert "SLAT-100" in lines, "choosing the slat model bought no slats"
    assert lines["SLAT-100"]["total_cents"] > 0
    assert not body["unresolved"]
    # the slats are cut to the panel height, not to the bay width
    cut = [r for r in body["requirements"] if r["sku"] == "SLAT-100"]
    assert cut and {r["cut_length_mm"] for r in cut} == {1800}


def test_the_structure_sheet_accounts_for_every_slat(client):
    """Sigma(parts) == BOM in both directions, over a panel with dozens of members
    rather than two rails. A slat with no cut length used to land in `from_stock`,
    which balances the ledger while buying nothing."""
    pid = make_project(client)
    put_straight_topology(client, pid)
    client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-SLAT"})
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]

    report = client.get(f"/api/runs/{run_id}/structure").json()
    totals = report["totals"]
    assert report["unresolved"] == []
    assert not any(t["sku"] == "SLAT-100" for t in totals["unassigned"])
    assert not any(t["sku"] == "SLAT-100" for t in totals["from_stock"])

    parts = [p for section in report["sections"] for bay in section["bays"]
             for p in bay["parts"]]
    slat_parts = [p for p in parts if p["sku"] == "SLAT-100"]
    assert slat_parts, "no bay claims a slat"
    # every slat a bay asked for is on the purchased side, sku for sku
    asked = sum(p["qty"] for p in slat_parts)
    bought = next(t["qty"] for t in totals["per_sku"] if t["sku"] == "SLAT-100")
    assert asked == bought


# --- seeing the panel before the strategy -------------------------------------

def test_the_panel_previews_without_a_project_or_a_topology(client):
    """The point of the endpoint: decide whether to build a model before drawing
    anything. It stores nothing and it is not a run."""
    before = client.get("/api/projects").json()
    r = client.post("/api/fence-models/M-SLAT/1/preview",
                    json={"height_mm": 1800, "width_mm": 2500})
    assert r.status_code == 200, r.text
    body = r.json()
    parts = {p["slot_key"]: p for p in body["parts"]}
    assert set(parts) == {"rail", "slat", "screw"}
    assert parts["slat"]["length_mm"] == 1800
    assert parts["slat"]["sku"] == "SLAT-100"
    assert body["total_cents"] > 0
    assert body["model_ref"] == "M-SLAT@v1"
    # nothing was persisted: no project appeared and no run was recorded
    assert client.get("/api/projects").json() == before
    assert all(not client.get(f"/api/projects/{p['id']}/runs").json() for p in before)


def test_a_draft_can_be_previewed_before_it_is_published(client):
    """Deciding whether a model is worth publishing is exactly when its panel
    most needs looking at."""
    created = client.post("/api/fence-models", json=draft_body()).json()["model"]
    r = client.post(f"/api/fence-models/M-TEST/{created['version']}/preview",
                    json={"height_mm": 1800, "width_mm": 1500})
    assert r.status_code == 200, r.text
    assert [p["slot_key"] for p in r.json()["parts"]] == ["rail"]


def test_previewing_an_unknown_model_is_a_404(client):
    assert client.post("/api/fence-models/M-NOPE/1/preview", json={}).status_code == 404


def test_two_models_can_be_compared_at_the_same_bay(client):
    """What a picker is for."""
    body = {"height_mm": 1800, "width_mm": 2500}
    legacy = client.post("/api/fence-models/M-LEGACY/1/preview", json=body).json()
    slat = client.post("/api/fence-models/M-SLAT/1/preview", json=body).json()
    assert slat["total_cents"] > legacy["total_cents"]
    assert len(slat["parts"]) > len(legacy["parts"])
