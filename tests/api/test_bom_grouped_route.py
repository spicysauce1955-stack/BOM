"""/bom carries the grouped view, and stays readable when the drawing moves on.

The second half is the point of putting it here rather than on /structure: the
setting-out sheet REFUSES a run whose topology has changed (409
`topology_changed`), because a station measured on the wrong drawing goes to
site. A BOM is a working view — the fence you priced is still the fence you
priced — so grouping it must not borrow that refusal.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


def _project_with_a_fence(client) -> tuple[str, str]:
    project = client.post("/api/projects", json={"name": "grouped"}).json()
    pid = project["id"]
    topology = {
        "revision": 1,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    }
    client.put(f"/api/projects/{pid}/topology", json=topology)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    return pid, run_id


def test_the_bom_route_groups_by_section_and_bay():
    with TestClient(app) as client:
        _, run_id = _project_with_a_fence(client)
        body = client.get(f"/api/runs/{run_id}/bom").json()
        assert "grouped" in body, "the flat list is not the only shape asked for"
        kinds = [g["kind"] for g in body["grouped"]["groups"]]
        # named exactly, because "is a subset" hid that this fixture produces NO
        # decision group at all — every demo model names one product per slot, so
        # `resolve_supply` never has a choice to record. The unit suite covers
        # the decision kind on a fixture with two eligible stocks.
        assert sorted(set(kinds)) == ["bay", "node", "section"]
        assert kinds.count("node") == 2 and kinds.count("section") == 1
        section = next(g for g in body["grouped"]["groups"] if g["kind"] == "section")
        assert section["element_id"] == "run1"
        assert section["lines"]


def test_grouping_never_prices_a_group():
    """The refusal this view is built on, held at the wire: a purchase is pooled
    per sku across the run, so a per-section price would be an apportionment
    nothing measured — arriving with the authority of a BOM."""
    with TestClient(app) as client:
        _, run_id = _project_with_a_fence(client)
        grouped = client.get(f"/api/runs/{run_id}/bom").json()["grouped"]
        for group in grouped["groups"]:
            assert not any("cent" in k or "price" in k for k in group)
            for line in group["lines"]:
                assert not any("cent" in k or "price" in k for k in line)


def test_the_grouped_bom_survives_a_topology_the_run_was_not_generated_from():
    """/structure answers 409 here and must; /bom answers, because what the run
    bought did not change when somebody moved a line on the drawing."""
    with TestClient(app) as client:
        pid, run_id = _project_with_a_fence(client)
        moved = client.get(f"/api/projects/{pid}").json()["topology"]
        moved["nodes"][1]["x_mm"] = 9000
        moved["revision"] = 2
        client.put(f"/api/projects/{pid}/topology", json=moved)

        assert client.get(f"/api/runs/{run_id}/structure").status_code == 409
        bom = client.get(f"/api/runs/{run_id}/bom")
        assert bom.status_code == 200
        assert bom.json()["grouped"]["groups"]


@pytest.fixture()
def isolated_client(tmp_path, monkeypatch):
    """Own database, because the test below EDITS the catalog and the knowledge
    base — a product with an 800 mm stock length left in the shared demo store
    would change what every later test priced."""
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "grouped.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def test_the_grouped_view_carries_the_lines_nothing_could_supply(isolated_client):
    """`GroupedBom.unresolved` is the fifth argument `/bom` passes to `group_bom`,
    and nothing at the wire asserted it arrived: the renderer's own tests build a
    document by hand, so dropping the argument here left the whole suite green
    while the grouped panel read as a COMPLETE bill of materials for a fence
    missing every rail. A section that silently omits what it could not buy is
    worse than one that refuses.

    Provoked the way `test_a_rail_default_pointing_at_short_stock_reads_as_unsupplied`
    provokes it — two calls a user can make from the product's own editors, a
    catalog product whose stock is shorter than the piece and a DefaultComponent
    aiming the rail role at it — so no state is forced behind the API's back.
    """
    client = isolated_client
    pid, _ = _project_with_a_fence(client)
    assert client.put("/api/catalog/products", json={
        "sku": "RAIL-SHORT", "name": "Short rail",
        "consumption": {"kind": "divisible_linear", "purchase_length_mm": 800},
        "price_cents": 1000,
    }).status_code == 200
    assert client.post("/api/knowledge", json={
        "object_id": "K-RAIL-SHORT", "type": "fact", "title": "short rail default",
        "actions": [{"kind": "default_component", "role": "rail",
                     "sku": "RAIL-SHORT"}],
    }).status_code == 200

    gen = client.post(f"/api/projects/{pid}/generate")
    assert gen.status_code == 200, gen.text
    run_id = gen.json()["result"]["run"]["id"]
    spans = [s["id"] for s in gen.json()["result"]["strategy"]["spans"]]

    resp = client.get(f"/api/runs/{run_id}/bom")
    assert resp.status_code == 200, resp.text
    grouped = resp.json()["grouped"]
    unresolved = grouped["unresolved"]
    assert unresolved, "the grouped view must carry what could not be supplied"
    # the same gap the flat view reports, at the same size — one rail line per
    # bay, each still asking for the two rails that bay needs
    assert [(r["role"], r["slot_key"], r["engineering_qty"]) for r in unresolved] == \
        [("rail", "rail", 2)] * len(spans)
    assert sorted(peg for r in unresolved for peg in r["pegs"]) == sorted(spans)
    # and never a product: an unresolved line is one that never got one
    assert all("sku" not in r for r in unresolved)
    # no group bought a rail either, so the panel cannot read as complete
    assert not any(line["role"] == "rail"
                   for g in grouped["groups"] for line in g["lines"])
