"""Recording an answer, and pinning a question shut.

A selection names WHAT was chosen — the widths, or the bindings — not which
generator proposed it. `fewest_posts` is defined relative to `max_span`, so
answering a footing question silently changed what that name meant.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from fenceai.api.app import app


def _project(client) -> str:
    return client.post("/api/projects", json={"name": "choices"}).json()["id"]


def test_a_selection_records_the_widths_it_chose_and_its_author():
    with TestClient(app) as client:
        pid = _project(client)
        got = client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "bay_layout", "scope": "gap:run1:0",
            "widths": [2000, 2000, 1000], "author": "bob",
        })
        assert got.status_code == 200, got.text
        stored = client.get(f"/api/projects/{pid}").json()["choices"]
        assert stored == [{"choice_set": "bay_layout", "scope": "gap:run1:0",
                            "widths": [2000, 2000, 1000], "bindings": {},
                            "asked": True, "author": "bob", "created_at": ""}]


def test_choosing_again_replaces_rather_than_accumulates():
    with TestClient(app) as client:
        pid = _project(client)
        for widths in ([2000, 2000, 1000], [1667, 1667, 1666]):
            client.put(f"/api/projects/{pid}/choices", json={
                "choice_set": "bay_layout", "scope": "gap:run1:0", "widths": widths})
        stored = client.get(f"/api/projects/{pid}").json()["choices"]
        assert [c["widths"] for c in stored] == [[1667, 1667, 1666]]


def test_two_gaps_on_one_run_are_two_separate_answers():
    """The upsert key is (set, scope) and scope is the GAP. A section-scoped key
    made one answer apply to a gap it was never measured for."""
    with TestClient(app) as client:
        pid = _project(client)
        for scope in ("gap:run1:0", "gap:run1:3000"):
            client.put(f"/api/projects/{pid}/choices", json={
                "choice_set": "bay_layout", "scope": scope, "widths": [1500, 1500]})
        assert len(client.get(f"/api/projects/{pid}").json()["choices"]) == 2


def test_a_pinned_question_is_a_selection_that_is_not_asked_again():
    with TestClient(app) as client:
        pid = _project(client)
        client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "footing_schedule", "scope": "model:M-VINYL",
            "bindings": {"footing_depth_mm": 610, "max_span_mm": 1676},
            "asked": False})
        assert client.get(f"/api/projects/{pid}").json()["choices"][0]["asked"] is False


def test_a_scope_with_a_slash_survives_the_round_trip():
    """`model:mfr/certainteed/rail` is a real scope. A path segment cannot carry
    it, which is why the scope is a query parameter on DELETE."""
    with TestClient(app) as client:
        pid = _project(client)
        scope = "model:mfr/certainteed/rail"
        client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "footing_schedule", "scope": scope, "bindings": {}})
        gone = client.delete(f"/api/projects/{pid}/choices/footing_schedule",
                              params={"scope": scope})
        assert gone.status_code == 200
        assert client.get(f"/api/projects/{pid}").json()["choices"] == []


def test_an_unknown_project_is_a_404_in_the_house_style():
    with TestClient(app) as client:
        got = client.put("/api/projects/nope/choices", json={
            "choice_set": "bay_layout", "scope": "gap:run1:0", "widths": []})
        assert got.status_code == 404
        assert "not found" in str(got.json()["detail"])
