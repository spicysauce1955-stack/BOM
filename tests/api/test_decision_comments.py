"""Commenting on a decision, and reading the conversation back.

The roadmap asks to *"focus on specific sections of the fence and get only the
decisions related to the selected section. change, comment or start a
conversation about it!"* The comment half existed as a write with no read: the
inspector posted a `Correction` and alerted, and nothing in the app could ever
show it again — so there was no conversation, only a suggestion box.

The boundary this must not cross is stated in `plan/open-work.md`: a comment
becomes an interpretation, an interpretation becomes a PROPOSAL, and only a
human confirms. AI never decides. So commenting stores VERBATIM text and changes
no fence.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from fenceai.api.app import app


def _fence(client) -> tuple[str, str, str]:
    """(project id, generation run id, a decision node id of section run1)."""
    pid = client.post("/api/projects", json={"name": "talk"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "revision": 1,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
    decisions = client.get(
        f"/api/runs/{run_id}/sections/run1/decisions").json()["decisions"]
    return pid, run_id, decisions[0]["node_id"]


def test_a_section_serves_only_its_own_decisions():
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        body = client.get(f"/api/runs/{run_id}/sections/run1/decisions").json()
        assert body["section_id"] == "run1"
        assert body["decisions"]
        assert all(d["sentence"] for d in body["decisions"])


def test_the_section_view_refuses_a_drawing_it_was_not_generated_from():
    """A section is a TOPOLOGY object, so "the decisions for section A" stops
    being true the moment A may no longer be that stretch — the same refusal
    /structure makes, for the same reason. /explain is per element and needs no
    topology, which is why it does not refuse."""
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        moved = client.get(f"/api/projects/{pid}").json()["topology"]
        moved["nodes"][1]["x_mm"] = 9000
        moved["revision"] = 2
        client.put(f"/api/projects/{pid}/topology", json=moved)
        refused = client.get(f"/api/runs/{run_id}/sections/run1/decisions")
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "topology_changed"


def test_a_comment_on_a_decision_is_stored_against_that_decision():
    """`Correction.decision_ref` has existed since the learning model was
    written and nothing has ever populated it — the inspector sent only
    `element_ref`. A comment on a DECISION is what it is for."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        made = client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "why is this bay 1500?", "author": "expert",
        })
        assert made.status_code == 200
        assert made.json()["decision_ref"] == node_id


def test_the_conversation_can_be_read_back_at_all():
    """The half that did not exist. There was no GET for corrections anywhere —
    `Store.list_corrections` was called only by the knowledge proposer — so a
    comment went in and was never seen again by any surface."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        for text in ("first thought", "second thought"):
            client.post(f"/api/projects/{pid}/corrections", json={
                "generation_run_id": run_id, "decision_ref": node_id,
                "comment": text, "author": "expert"})
        got = client.get(f"/api/projects/{pid}/corrections").json()
        assert [c["comment"] for c in got] == ["first thought", "second thought"]
        assert all(c["created_at"] for c in got)


def test_a_conversation_can_be_asked_for_by_decision():
    """A thread is about one thing. Asking for a decision's conversation must
    not return the comments left on every other decision of the fence."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        others = client.get(
            f"/api/runs/{run_id}/sections/run1/decisions").json()["decisions"]
        other_id = next(d["node_id"] for d in others if d["node_id"] != node_id)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "about this one", "author": "expert"})
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": other_id,
            "comment": "about the other", "author": "expert"})
        mine = client.get(
            f"/api/projects/{pid}/corrections"
            f"?decision_ref={node_id}&generation_run_id={run_id}").json()
        assert [c["comment"] for c in mine] == ["about this one"]


def test_asking_for_a_decision_across_runs_is_refused():
    """A decision node id is POSITIONAL — `d0007` is the seventh node the builder
    emitted, and one new gate event renumbers everything after it. A
    `decision_ref` without the run it was made in therefore names different
    decisions in different runs, and the route refuses rather than quietly
    returning a mixture."""
    with TestClient(app) as client:
        pid, _, node_id = _fence(client)
        refused = client.get(
            f"/api/projects/{pid}/corrections?decision_ref={node_id}")
        assert refused.status_code == 422
        assert refused.json()["detail"]["code"] == "decision_ref_needs_run"


def test_commenting_changes_no_fence():
    """The boundary, held at the wire: a comment is evidence, not an edit. Only
    a human confirming a candidate ever changes what is built, and this route
    does not go near that."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        before = client.get(f"/api/runs/{run_id}").json()
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "this is wrong", "author": "expert"})
        after = client.get(f"/api/runs/{run_id}").json()
        assert after == before


def test_regenerating_the_same_drawing_keeps_the_conversation():
    """A run id is a digest of what the run MEANS, so regenerating an unchanged
    drawing returns the same run — and the thread is still there. This is the
    ordinary case and it must not be mistaken for the one below."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "still relevant", "author": "expert"})
        again = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
        assert again == run_id
        thread = client.get(f"/api/projects/{pid}/corrections"
                            f"?decision_ref={node_id}&generation_run_id={again}").json()
        assert [c["comment"] for c in thread] == ["still relevant"]


def test_a_comment_does_not_follow_its_decision_into_a_NEW_run():
    """The honest half. A decision id is positional, so after the drawing moves
    the same string names a different decision. The comment is not destroyed —
    evidence never is — it simply is not claimed by the new run, and the panel
    says so at the level where the statement is true."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "about the old fence", "author": "expert"})
        moved = client.get(f"/api/projects/{pid}").json()["topology"]
        moved["nodes"][1]["x_mm"] = 9000
        moved["revision"] = 2
        client.put(f"/api/projects/{pid}/topology", json=moved)
        new_run = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
        assert new_run != run_id

        assert client.get(f"/api/projects/{pid}/corrections"
                          f"?decision_ref={node_id}&generation_run_id={new_run}").json() == []
        kept = client.get(f"/api/projects/{pid}/corrections").json()
        assert [c["comment"] for c in kept] == ["about the old fence"]


def test_commenting_leaves_the_knowledge_base_alone():
    """The boundary, checked where it could actually break. Comparing the RUN
    would still pass if posting a comment had quietly run the proposer — and a
    knowledge candidate appearing because somebody typed a sentence is exactly
    the "inert until approved" invariant, broken at the surface this slice adds."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        before = (client.get("/api/knowledge").json(),
                  client.get("/api/candidates").json())
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "always use existing foundations", "author": "expert"})
        assert (client.get("/api/knowledge").json(),
                client.get("/api/candidates").json()) == before


def test_a_comment_on_a_decision_the_run_does_not_have_is_kept_as_evidence():
    """Deliberate, not an oversight. Refusing would mean the store had to know
    the shape of every run's graph, and a comment is EVIDENCE — the one thing
    this system never throws away. It simply appears on no section, which is
    visible rather than silent: the project's conversation still lists it."""
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        made = client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": "d9999",
            "comment": "about nothing", "author": "expert"})
        assert made.status_code == 200
        assert any(c["comment"] == "about nothing"
                   for c in client.get(f"/api/projects/{pid}/corrections").json())


def test_an_unknown_section_is_empty_rather_than_missing():
    """A section nothing was decided about is an ordinary state. So is a node id
    typed where a run id belongs."""
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        for section in ("nope", "n2"):
            got = client.get(f"/api/runs/{run_id}/sections/{section}/decisions")
            assert got.status_code == 200
            # `admitted` is empty rather than absent, for the same reason
            # `decisions` is: a surface forced to branch on a missing key
            # branches wrongly the first time it is missing for a
            # different reason.
            assert got.json() == {
                "section_id": section, "decisions": [], "admitted": {}}


def test_the_same_question_gets_the_same_answer_twice():
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        a = client.get(f"/api/runs/{run_id}/sections/run1/decisions")
        b = client.get(f"/api/runs/{run_id}/sections/run1/decisions")
        assert a.text == b.text


def test_the_comment_is_kept_verbatim():
    """Verbatim human text is immutable (foundation §15). Punctuation, case and
    a right-to-left sentence come back exactly as typed."""
    said = '  למה הבַּיִת הזה 1500?  "ככה"  '
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": said, "author": "expert"})
        [got] = client.get(f"/api/projects/{pid}/corrections").json()
        assert got["comment"] == said


# --- a comment becomes a PROPOSAL, and a human confirms -----------------------

def test_a_conversation_can_become_a_candidate_rule_that_is_inert():
    """The boundary walked end to end, which is the whole of roadmap step 5: a
    comment becomes an interpretation, an interpretation becomes a PROPOSAL, and
    only a human confirms. The candidate must arrive INERT — proposed, invisible
    to generation, and outside the run's knowledge snapshot."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "always use existing foundations when within 300 mm",
            "author": "expert"})
        made = client.post(f"/api/projects/{pid}/propose-knowledge").json()
        assert made, "the demo proposer reads this vocabulary; nothing was proposed"
        assert all(c["status"] == "proposed" for c in made)
        assert all(c["type"] == "candidate" for c in made)

        # inert: generation cannot see it
        before = client.get(f"/api/runs/{run_id}").json()
        again = client.post(f"/api/projects/{pid}/generate").json()["result"]
        assert again["run"]["id"] == before["run"]["id"], \
            "a proposed candidate changed the fence, which is the one thing it may not do"
        # the snapshot is (object_id, version) pairs: a candidate must be in none
        assert made[0]["object_id"] not in {
            pair[0] for pair in again["run"]["knowledge_snapshot"]}


def test_the_same_conversation_does_not_propose_the_same_rule_twice():
    """Pressing the button again is an ordinary thing to do. A candidate already
    handled — or already sitting in the queue — is never re-proposed."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "always use existing foundations", "author": "expert"})
        first = client.post(f"/api/projects/{pid}/propose-knowledge").json()
        second = client.post(f"/api/projects/{pid}/propose-knowledge").json()
        assert first and second == []


def test_a_conversation_that_suggests_no_rule_proposes_nothing_rather_than_something():
    """The ordinary answer. The proposer reads a narrow vocabulary on purpose
    (it must not become a second rule engine), so most comments yield nothing —
    and inventing a rule from a question would be the AI deciding."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "why is this bay 1500?", "author": "expert"})
        assert client.post(f"/api/projects/{pid}/propose-knowledge").json() == []


def test_a_candidate_remembers_which_decision_was_argued_with():
    """The evidence chain, joined at the one place it was broken. A candidate
    born from an argument about a decision kept only the sentence — and the
    decision graph is the natural evidence for a proposed rule. The ref carries
    its RUN, because a decision id means nothing outside the run that made it."""
    with TestClient(app) as client:
        pid, run_id, node_id = _fence(client)
        client.post(f"/api/projects/{pid}/corrections", json={
            "generation_run_id": run_id, "decision_ref": node_id,
            "comment": "always use existing foundations", "author": "expert"})
        [candidate] = client.post(f"/api/projects/{pid}/propose-knowledge").json()
        assert f"{run_id}#{node_id}" in candidate["derived_from"]
        assert any(d.startswith("corr_") for d in candidate["derived_from"]), \
            "the correction itself is still cited"
