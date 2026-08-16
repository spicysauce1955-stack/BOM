"""Which catalog edits a stored run should refuse to be re-read against.

`catalog_hash` used to cover the WHOLE catalog, so adding an unrelated gate kit
made every previously generated run's working views 409 — "the first user who
edits a catalog price and finds their existing quotes' working views all refuse"
(docs/v1-known-limitations.md). The refusal is right in kind and was far too
broad in scope.
"""

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


def generated(client) -> str:
    pid = client.post("/api/projects", json={"name": "job"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    return client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]


def put_product(client, sku: str, **changes):
    product = client.get("/api/catalog").json()["products"].get(sku)
    if product is None:
        product = {"sku": sku, "name": sku,
                   "consumption": {"kind": "indivisible_discrete"}, "price_cents": 100}
    product.update(changes)
    r = client.put("/api/catalog/products", json=product)
    assert r.status_code == 200, r.text


# --- what must still refuse ---------------------------------------------------

def test_repricing_a_product_the_run_bought_still_refuses(client):
    """Stamping is not checking: re-reading against a moved catalog would quietly
    reprice a stored run."""
    run_id = generated(client)
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 200
    put_product(client, "RAIL-3000", price_cents=9999)
    r = client.get(f"/api/runs/{run_id}/bom")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "catalog_changed"


def test_changing_a_stock_length_the_run_cut_from_refuses(client):
    """Not just the price — a purchase length changes the cut plan."""
    run_id = generated(client)
    rail = client.get("/api/catalog").json()["products"]["RAIL-3000"]
    rail["consumption"]["purchase_length_mm"] = 2500
    assert client.put("/api/catalog/products", json=rail).status_code == 200
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 409


def test_every_money_view_refuses_together(client):
    run_id = generated(client)
    put_product(client, "POST-S", price_cents=9999)
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 409
    assert client.get(f"/api/runs/{run_id}/structure").status_code == 409
    assert client.post(f"/api/runs/{run_id}/quote", json={}).status_code == 409


# --- what must now be tolerated ------------------------------------------------

def test_adding_an_unrelated_product_no_longer_refuses(client):
    """The narrowing. Safe because eligibility is FROZEN into the run: a product
    that did not exist when it was generated can never change what it means."""
    run_id = generated(client)
    put_product(client, "GATE-KIT-2000", price_cents=25000,
                attrs={"category": "gate"}, capabilities={"opening_width_mm": 2000})
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 200
    assert client.get(f"/api/runs/{run_id}/structure").status_code == 200


def test_repricing_a_product_this_run_never_named_no_longer_refuses(client):
    run_id = generated(client)
    bought = {line["sku"] for line in client.get(f"/api/runs/{run_id}/bom").json()
              ["bom"]["lines"]}
    assert "POST-M" not in bought, "the fixture must not use the product it edits"
    put_product(client, "POST-M", price_cents=9999)
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 200


def test_the_run_records_which_products_it_depends_on(client):
    run_id = generated(client)
    run = client.get(f"/api/runs/{run_id}").json()
    skus = run["run"]["catalog_skus"]
    assert "RAIL-3000" in skus and "POST-S" in skus
    assert "POST-M" not in skus
    assert skus == sorted(skus), "a stamped set must be deterministic"


def test_a_kits_components_count_as_dependencies(client):
    """A BOM line's notes read a kit's component list, so changing one changes
    what the stored run says."""
    pid = client.post("/api/projects", json={"name": "gated"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2",
                  "point_events": [{
                      "id": "ev_g",
                      "anchor": {"segment_index": 0, "offset_mm": 3000,
                                 "seg_len_at_authoring_mm": 6000},
                      "payload": {"kind": "gate", "width_mm": 1000,
                                  "kit_sku": "GATE-KIT-1000"},
                  }]}],
    })
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 200
    put_product(client, "HINGE-SET", price_cents=9999)   # a kit COMPONENT
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 409


def test_an_eligibility_rival_counts_even_though_it_was_not_bought(client):
    """The choice among members is made at READ time, so a rival's price changing
    is exactly a reason to re-check rather than silently keep the old answer."""
    for sku, price in (("RAIL-ALT", 100), ("RAIL-3000", 1800)):
        rail = client.get("/api/catalog").json()["products"]["RAIL-3000"]
        rail = {**rail, "sku": sku, "price_cents": price}
        client.put("/api/catalog/products", json=rail)
    model = {
        "id": "M-RIVALS", "version": 1, "name_i18n": {"en": "Rivals", "he": "מתחרים"},
        "default_spec": {"frame": [{
            "key": "rail", "orientation": "horizontal",
            "placement": {"kind": "distributed", "count": 2},
            "requirement": {"role": "rail", "qty": 1, "length_rule": "centre_to_centre",
                            "eligibility": {"members": [
                                {"kind": "catalog_item", "sku": "RAIL-3000"},
                                {"kind": "catalog_item", "sku": "RAIL-ALT"}]}},
        }]},
    }
    created = client.post("/api/fence-models", json=model).json()["model"]
    client.post(f"/api/fence-models/M-RIVALS/{created['version']}/publish")

    pid = client.post("/api/projects", json={"name": "rivals"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-RIVALS"})
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    body = client.get(f"/api/runs/{run_id}/bom").json()
    assert "RAIL-ALT" in {line["sku"] for line in body["bom"]["lines"]}

    put_product(client, "RAIL-3000", price_cents=1)   # the LOSER gets cheaper
    assert client.get(f"/api/runs/{run_id}/bom").status_code == 409


def test_a_run_stamped_before_the_catalog_schema_moved_says_so(client, monkeypatch):
    """The deliberate migration, made legible.

    Adding a field to `Product` changes every product's content hash, so every
    run generated beforehand refuses. `catalog_changed` would be a LIE about
    that: nothing was repriced and no product moved — the schema did. A reader
    who is told the catalog changed goes looking for a price edit that never
    happened."""
    from fenceai.api import app as app_module

    run_id = generated(client)
    # the migration as it actually happens: the run is stamped with the shape
    # that was current when it was generated, and then Product gains a field
    monkeypatch.setattr(app_module, "CATALOG_SCHEMA_VERSION", "capabilities-v2-future")

    r = client.get(f"/api/runs/{run_id}/bom")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "catalog_schema_changed"
