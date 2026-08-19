"""/bom carries the grouped view, and stays readable when the drawing moves on.

The second half is the point of putting it here rather than on /structure: the
setting-out sheet REFUSES a run whose topology has changed (409
`topology_changed`), because a station measured on the wrong drawing goes to
site. A BOM is a working view — the fence you priced is still the fence you
priced — so grouping it must not borrow that refusal.
"""

from __future__ import annotations

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


def test_the_bom_route_groups_by_section_bay_and_decision():
    with TestClient(app) as client:
        _, run_id = _project_with_a_fence(client)
        body = client.get(f"/api/runs/{run_id}/bom").json()
        assert "grouped" in body, "the flat list is not the only shape asked for"
        kinds = {g["kind"] for g in body["grouped"]["groups"]}
        assert {"section", "bay"} <= kinds
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
