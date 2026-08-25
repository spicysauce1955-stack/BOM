"""S17 — a section is asked why, and answered; then argued with.

Roadmap step 5. The property spans the whole spine, which is why it is a
scenario and not a unit test: the decision graph decides, the TOPOLOGY defines
what a section is, the learning store keeps what a person said about it, and the
boundary between the two must hold — a comment is evidence and never an edit.

See docs/scenarios/golden-scenarios.md §S17.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """This file is the ONLY one in the release gate that drives the API without
    pinning its own database, so it inherited whatever `FENCEAI_DB` the ambient
    environment happened to carry — a developer's local db, or one a browser
    smoke run had just populated.

    Two agents working in separate worktrees independently reported this file
    failing and spent time proving it was not their change. Neither failure
    reproduces here under any condition I could construct, so the cause is still
    unidentified — which is exactly why the gate should not be reading a database
    it did not create. A release gate that depends on ambient state is one whose
    red is not evidence.
    """
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "s17.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")

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
# an 8000 mm run with a 1000 mm gate asked for at station 3000
GATED = {
    "revision": 1,
    "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
              {"id": "n2", "x_mm": 8000, "y_mm": 0}],
    "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2",
              "point_events": [{"id": "ev_gate",
                                "anchor": {"segment_index": 0, "offset_mm": 3000,
                                           "seg_len_at_authoring_mm": 8000},
                                "payload": {"kind": "gate", "width_mm": 1000,
                                            "kit_sku": "GATE-KIT-1000"}}]}],
}


def _max_span(client, value_mm: int) -> None:
    """Establish the max span this scenario is written against.

    S17's documented numbers — three 2000 mm bays, and the sentence naming the
    rejected alternative `[2438, 2438, 1124]` — are a fence built under
    **K-MAXSPAN@v2**, which the golden-scenarios doc names explicitly. The seed
    ships v1 at 1800 mm, under which 2000 mm bays are not merely different, they
    are ILLEGAL.

    The scenario never created v2. It passed because some other test in the same
    session did, and this file was the only one in the release gate that drove the
    API without pinning its own database — so it read whatever knowledge the
    ambient one happened to hold. Given a clean database it fails, and it has
    failed that way since long before the current branch (verified at 42598c5).

    A gate that only passes on state another test left behind is not testing what
    it says. It establishes its own precondition now.
    """
    assert client.post("/api/knowledge", json={
        "object_id": "K-MAXSPAN", "type": "hard_constraint",
        "title": f"Manufacturer max span {value_mm} mm",
        "actions": [{"kind": "set_param", "param": "max_span_mm", "value": value_mm}],
    }).status_code == 200


def _fence(client, topology) -> tuple[str, str]:
    _max_span(client, 2438)
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


def test_s17_1b_the_section_says_WHAT_was_decided_not_merely_that_something_was():
    """A scenario that asserts non-emptiness is a slower unit test. These are the
    numbers a 6000 mm run on the demo knowledge actually produces — three equal
    bays beating the max-span alternative, four posts, and the rule that decided
    it named in the sentence."""
    with TestClient(app) as client:
        _, run_id = _fence(client, STRAIGHT)
        got = _decisions(client, run_id, "run1")["decisions"]
        assert [d["elements"] for d in got if d["action"] == "create_span"] == [
            ["span@run1:0-2000"], ["span@run1:2000-4000"], ["span@run1:4000-6000"]]
        assert sorted({e for d in got for e in d["elements"]
                       if e.startswith("post@")}) == [
            "post@node:n1", "post@node:n2", "post@run1:2000", "post@run1:4000"]
        layout = next(d for d in got if d["action"] == "layout_spans")
        assert layout["sentence"] == (
            "Segment [0, 6000] divided into spans [2000, 2000, 2000]. "
            "Alternative [2438, 2438, 1124] was rejected because of K-EQUAL@v1. "
            "Governed by K-EQUAL@v1, K-MAXSPAN@v2.")


def test_s17_9_the_section_explains_exactly_what_the_structure_sheet_lays_on_it():
    """The spine, joined. Two independent read models over one run — the setting
    out and the decision trail — must name the same elements, or one of them is
    describing a fence the other did not build."""
    with TestClient(app) as client:
        _, run_id = _fence(client, STRAIGHT)
        explained = {e for d in _decisions(client, run_id, "run1")["decisions"]
                     for e in d["elements"]}
        report = client.get(f"/api/runs/{run_id}/structure").json()
        section = next(s for s in report["sections"] if s["run_id"] == "run1")
        laid_out = {row["element_id"]
                    for row in [*section["setting_out"], *section["bays"]]}
        assert laid_out <= explained, \
            f"laid out but never explained: {sorted(laid_out - explained)}"


def test_s17_2_the_run_level_decisions_are_there():
    """They name no element and are what a person asks about a section first."""
    with TestClient(app) as client:
        _, run_id = _fence(client, STRAIGHT)
        actions = {d["action"] for d in _decisions(client, run_id, "run1")["decisions"]}
        assert {"run_geometry", "choose_vertical_mode"} <= actions


def test_s17_2b_a_gated_sections_story_states_the_gate_that_caused_it():
    """A gate fact is run-level too. It names no element — the posts it forced
    do — so it reaches its section through `run_id` in its payload or not at
    all, exactly like `run_geometry` and `choose_vertical_mode`. Without it the
    section's story has two gate posts and a `place_gate` and never says a gate
    was asked for: the cause is missing from the account of its own effects."""
    with TestClient(app) as client:
        _, run_id = _fence(client, GATED)
        got = _decisions(client, run_id, "run1")["decisions"]
        caused = [d for d in got if d["action"] == "place_post"
                  and d["elements"] in (["post@run1:3000"], ["post@run1:4000"])]
        assert len(caused) == 2, "fixture stopped producing the flanking gate posts"
        assert any(d["action"] == "place_gate" for d in got)
        facts = [d for d in got if d["action"] == "gate_event"]
        assert facts, (
            "the gate is absent from the story of the section it reshaped: "
            f"{sorted({d['action'] for d in got})}")
        assert facts[0]["sentence"] == (
            "A gate was asked for between 3000 mm and 4000 mm.")
        # and it is told BEFORE the posts it explains — causal order, by ordinal
        assert facts[0]["ordinal"] < min(d["ordinal"] for d in caused)


def test_s17_2c_a_facts_sentence_is_grammatical_in_the_readers_language():
    """The section view answers in the reader's language, and a count inside a
    sentence is grammar, not a number. English can hide behind "section(s)";
    Hebrew cannot — an END node, where ONE section stops, is the common case and
    the plural reads as broken Hebrew there."""
    with TestClient(app) as client:
        _, straight = _fence(client, STRAIGHT)
        he = client.get(
            f"/api/runs/{straight}/sections/run1/decisions?lang=he").json()["decisions"]
        ends = [d["sentence"] for d in he if d["action"] == "topology_node"]
        assert ends == ["צומת n1 בשרטוט, שבו מסתיים קטע אחד.",
                        "צומת n2 בשרטוט, שבו מסתיים קטע אחד."]

        _, corner = _fence(client, L_SHAPE)
        he_l = client.get(
            f"/api/runs/{corner}/sections/runA/decisions?lang=he").json()["decisions"]
        shared = [d["sentence"] for d in he_l if d["action"] == "topology_node"
                  and "n2" in d["sentence"]]
        # two really do meet at the corner, and there the plural is correct
        assert shared == ["צומת n2 בשרטוט, שבו נפגשים 2 קטעים."]


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
            f"/api/projects/{pid}/corrections"
            f"?decision_ref={node_id}&generation_run_id={run_id}").json()
        # 6 + 7: verbatim, against that decision, in the order it was said
        assert [c["comment"] for c in thread] == said
        assert all(c["created_at"] for c in thread)
        assert all(c["generation_run_id"] == run_id for c in thread)
        # 8: the fence is untouched. A comment is evidence, never an edit.
        assert client.get(f"/api/runs/{run_id}").json() == before
