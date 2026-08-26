"""The two read routes carry the placed warnings — `/bom` and `/structure`.

The placement itself is `tests/report/test_annexe.py`'s. What is only testable
here is the JOIN: which DOCUMENTS a run is built to. It comes off the run's own
bays (`Span.panel.model_ref`) and never off the project, because a project that
has since been pointed at another product line must not put that line's warranty
notice on a plan built to the old one — and the run stamped its refs precisely so
a reader can go back to the document it was built from.

One helper serves both routes for the same reason `_priced` does: two collections
of "which documents is this fence built to" is how the annexe on the setting-out
sheet and the notices on the BOM would come to disagree about what the
manufacturer said.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Its own database, and NOT because this test writes anything unusual.

    `seed_fence_models` is keyed on `(id, version)` and never overwrites, which
    is right — reopening a store must leave an expert's edits alone — and it
    means a store seeded before M-LEGACY carried any warnings keeps a document
    that has none. Against the ambient `fenceai.db` every assertion here would
    pass or fail on the age of a file, which is exactly the trap `test_s17_1b`
    recorded: its red was not evidence and neither was its green. Writing this
    test found the same store serving a stale document, in under a minute.
    """
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "quoted.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def _project_with_a_fence(client) -> tuple[str, str]:
    pid = client.post("/api/projects", json={"name": "quoted"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "revision": 1,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    return pid, run_id


def _placed(body) -> list[dict]:
    return body["quoted_warnings"]["placements"]


def test_the_setting_out_sheet_carries_the_annexe(client):
    """The sheet that goes to site. M-LEGACY warns that the fence is not a pool
    barrier, and that is a job-wide statement: one annexe entry, `ref` empty, and
    no bay named."""
    _, run_id = _project_with_a_fence(client)
    body = client.get(f"/api/runs/{run_id}/structure").json()
    annexe = [p for p in _placed(body) if p["where"] == "annexe"]
    assert len(annexe) == 1
    assert annexe[0]["ref"] == "" and annexe[0]["instances"] == 1
    assert "pool barrier" in annexe[0]["warning"]["text_raw"]
    assert body["quoted_warnings"]["not_in_plan"] == 0


def test_the_bom_carries_the_product_notice_for_a_sku_it_buys(client):
    """"On the BOM lines using it, once per line group" — and the ref has to be a
    sku on this bill, or the notice renders against nothing."""
    _, run_id = _project_with_a_fence(client)
    body = client.get(f"/api/runs/{run_id}/bom").json()
    product = [p for p in _placed(body) if p["where"] == "product"]
    assert len(product) == 1 and product[0]["ref"] == "RAIL-3000"
    assert "RAIL-3000" in {line["sku"] for line in body["bom"]["lines"]}


def test_both_routes_place_the_same_warnings_the_same_way(client):
    """The whole reason there is one helper. A sheet and a bill that disagreed
    about what the manufacturer said would each be defensible on its own."""
    _, run_id = _project_with_a_fence(client)
    sheet = client.get(f"/api/runs/{run_id}/structure").json()
    bill = client.get(f"/api/runs/{run_id}/bom").json()
    assert sheet["quoted_warnings"] == bill["quoted_warnings"]


def test_the_documents_come_off_the_run_and_not_off_the_project(client):
    """Pointing the PROJECT at another product line must not change what a stored
    run's plan says the manufacturer warned. The run keeps its refs; a regenerated
    run picks up the new document."""
    pid, run_id = _project_with_a_fence(client)
    before = client.get(f"/api/runs/{run_id}/structure").json()["quoted_warnings"]

    client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-VINYL"})
    after = client.get(f"/api/runs/{run_id}/structure").json()["quoted_warnings"]
    assert after == before, "a stored run's documents are the run's"

    new_run = client.post(f"/api/projects/{pid}/generate") \
        .json()["result"]["run"]["id"]
    rebuilt = client.get(f"/api/runs/{new_run}/structure").json()
    texts = " ".join(p["warning"]["text_raw"] for p in _placed(rebuilt))
    assert "frost line" in texts, "the new run is built to M-VINYL's document"
    assert "pool barrier" not in texts


def test_a_publishers_words_arrive_unedited_over_the_wire(client):
    """`text_raw`, `lang` and the publisher's `severity_lexeme`, as JSON. The
    serialisation is where a helpful normalisation would be invisible: nothing
    downstream could tell that `CAUTION` had been mapped to `warning`."""
    _, run_id = _project_with_a_fence(client)
    body = client.get(f"/api/runs/{run_id}/structure").json()
    assert _placed(body)
    for placed in _placed(body):
        warning = placed["warning"]
        assert warning["lang"] == "en"
        assert warning["severity_lexeme"] in ("WARNING", "NOTICE")
        assert "severity" not in warning
        # this legacy document was never traced to a source, and says so rather
        # than carrying an id somebody minted to fill the field
        assert warning["cites"] is None
