"""S17 — a section is asked why, and answered; then argued with.

Roadmap step 5. The property spans the whole spine, which is why it is a
scenario and not a unit test: the decision graph decides, the TOPOLOGY defines
what a section is, the learning store keeps what a person said about it, and the
boundary between the two must hold — a comment is evidence and never an edit.

See docs/scenarios/golden-scenarios.md §S17.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from fenceai.api.app import app

L_SHAPE = {
    "revision": 1,
    "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
              {"id": "n2", "x_mm": 4000, "y_mm": 0},
              {"id": "n3", "x_mm": 4000, "y_mm": 3000}],
    "runs": [{"id": "runA", "start_node_id": "n1", "end_node_id": "n2"},
             {"id": "runB", "start_node_id": "n2", "end_node_id": "n3"}],
}
STRAIGHT = {
    "revision": 1,
    "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
              {"id": "n2", "x_mm": 6000, "y_mm": 0}],
    "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
}


def _fence(client, topology) -> tuple[str, str]:
    pid = client.post("/api/projects", json={"name": "s17"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json=topology)
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    return pid, run_id


def _decisions(client, run_id, section, **q):
    query = "".join(f"&{k}={v}" for k, v in q.items())
    return client.get(
        f"/api/runs/{run_id}/sections/{section}/decisions?lang=en{query}").json()


def test_s17_1_only_this_sections_decisions_come_back():
    with TestClient(app) as client:
        _, run_id = _fence(client, L_SHAPE)
        a = _decisions(client, run_id, "runA")
        assert a["decisions"]
        assert not any("@runB" in e
                       for d in a["decisions"] for e in d["elements"])


def test_s17_2_the_run_level_decisions_are_there():
    """They name no element and are what a person asks about a section first."""
    with TestClient(app) as client:
        _, run_id = _fence(client, STRAIGHT)
        actions = {d["action"] for d in _decisions(client, run_id, "run1")["decisions"]}
        assert {"run_geometry", "choose_vertical_mode"} <= actions


def test_s17_3_a_shared_corner_post_reaches_both_sections():
    with TestClient(app) as client:
        _, run_id = _fence(client, L_SHAPE)
        shared = "post@node:n2"
        for section in ("runA", "runB"):
            got = _decisions(client, run_id, section)
            assert any(shared in d["elements"] for d in got["decisions"]), section


def test_s17_4_the_story_is_told_in_the_order_it_happened():
    with TestClient(app) as client:
        _, run_id = _fence(client, STRAIGHT)
        ordinals = [d["ordinal"] for d in _decisions(client, run_id, "run1")["decisions"]]
        assert ordinals == sorted(ordinals) and len(set(ordinals)) == len(ordinals)


def test_s17_5_a_moved_drawing_is_refused_here_and_not_on_an_element():
    """The asymmetry is deliberate: a section is a topology object, an element
    id is self-identifying."""
    with TestClient(app) as client:
        pid, run_id = _fence(client, STRAIGHT)
        element = next(e for d in _decisions(client, run_id, "run1")["decisions"]
                       for e in d["elements"])
        moved = {**STRAIGHT, "revision": 2,
                 "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                           {"id": "n2", "x_mm": 9000, "y_mm": 0}]}
        client.put(f"/api/projects/{pid}/topology", json=moved)

        refused = client.get(f"/api/runs/{run_id}/sections/run1/decisions")
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "topology_changed"
        still = client.get(f"/api/runs/{run_id}/explain/{element}")
        assert still.status_code == 200


def test_s17_6_7_8_a_conversation_is_kept_verbatim_in_order_and_changes_nothing():
    said = ["why is this bay 1500?", "the closing bay should absorb the odd one"]
    with TestClient(app) as client:
        pid, run_id = _fence(client, STRAIGHT)
        node_id = _decisions(client, run_id, "run1")["decisions"][0]["node_id"]
        before = client.get(f"/api/runs/{run_id}").json()

        for text in said:
            posted = client.post(f"/api/projects/{pid}/corrections", json={
                "generation_run_id": run_id, "decision_ref": node_id,
                "comment": text, "author": "expert"})
            assert posted.status_code == 200
            assert posted.json()["decision_ref"] == node_id

        thread = client.get(
            f"/api/projects/{pid}/corrections?decision_ref={node_id}").json()
        # 6 + 7: verbatim, against that decision, in the order it was said
        assert [c["comment"] for c in thread] == said
        assert all(c["created_at"] for c in thread)
        assert all(c["generation_run_id"] == run_id for c in thread)
        # 8: the fence is untouched. A comment is evidence, never an edit.
        assert client.get(f"/api/runs/{run_id}").json() == before
