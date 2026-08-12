"""Why THAT product was bought.

`resolve_supply` has recorded its reasoning since phase 1 and nothing consumed
it: the record reached no decision-graph node, so `/explain` could not say why
one eligible product was bought instead of another. It stayed invisible only
because every shipped model had one eligible member per slot — the gap
`docs/v1-known-limitations.md` records, with the trigger that has now fired.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app
from fenceai.catalog.model import Catalog, DivisibleLinear, Product
from fenceai.decisions.graph import DecisionGraph
from fenceai.decisions.supply import with_supply_decisions
from fenceai.fulfillment.supply import Candidate, SupplyDecision


def decision(**kw) -> SupplyDecision:
    base = dict(
        requirement_ids=["req0001"], pegs=["span@run1:0-1500"], slot_key="rail",
        role="rail", chosen="RAIL-3050", preset="least_cost",
        candidates=[
            Candidate(sku="RAIL-3050", priority=2, cost_cents=3700, waste_mm=100),
            Candidate(sku="RAIL-3000", priority=1, cost_cents=4000, waste_mm=900),
        ],
    )
    return SupplyDecision(**{**base, **kw})


# --- the derived graph --------------------------------------------------------

def test_reading_a_run_never_mutates_its_graph():
    """The whole design rests on this. These nodes are derived at read time
    because selection runs in fulfillment, which has no graph builder; a derived
    read model that wrote back into the stored document would make a run's
    explanation depend on who had looked at it."""
    stored = DecisionGraph()
    before = stored.model_dump_json()
    with_supply_decisions(stored, [decision()])
    assert stored.model_dump_json() == before


def test_a_node_is_scoped_to_the_elements_its_lines_peg_to():
    graph = with_supply_decisions(DecisionGraph(), [decision()])
    node = graph.nodes[-1]
    assert node.action == "select_supply"
    assert node.kind == "selection"
    assert graph.nodes_for_element("span@run1:0-1500") == [node]


def test_ordinals_continue_past_the_stored_graph():
    """Edges may only point from earlier ordinals to later ones. An appended node
    that reused an ordinal would break the acyclicity the builder guarantees
    during generation."""
    from fenceai.decisions.graph import GraphBuilder
    builder = GraphBuilder()
    builder.add("input_fact", "run_geometry", payload={})
    stored = builder.build()
    graph = with_supply_decisions(stored, [decision()])
    assert graph.nodes[-1].ordinal > max(n.ordinal for n in stored.nodes)


def test_the_order_is_deterministic():
    two = [decision(slot_key="slat", chosen="SLAT-A"), decision()]
    a = with_supply_decisions(DecisionGraph(), two)
    b = with_supply_decisions(DecisionGraph(), list(reversed(two)))
    assert [n.payload["chosen"] for n in a.nodes] == [n.payload["chosen"] for n in b.nodes]


# --- the sentence -------------------------------------------------------------

def explain_one(lang="en", **kw) -> str:
    from fenceai.decisions.explain import explain_node
    graph = with_supply_decisions(DecisionGraph(), [decision(**kw)])
    return explain_node(graph, graph.nodes[-1], lang, "mm")


def test_the_sentence_names_the_runner_up_and_the_gap():
    """"Cheaper than the others" is not an explanation; "cheaper than THAT one,
    by this much" is."""
    text = explain_one()
    assert "RAIL-3050" in text and "RAIL-3000" in text
    assert "3700" in text and "4000" in text
    assert "least_cost" in text


def test_hebrew_renders_and_keeps_the_skus_latin():
    text = explain_one(lang="he")
    assert "RAIL-3050" in text
    assert any("֐" <= ch <= "ת" for ch in text), "no Hebrew in the sentence"


def test_an_unbuildable_candidate_is_named_as_such_not_costed_at_zero():
    """A candidate nothing was planned for has no cost. Rendering a zero there
    would read as 'free', which is the opposite of what happened."""
    text = explain_one(candidates=[
        Candidate(sku="GOOD", priority=1),
        Candidate(sku="SHORT", priority=2, feasible=False),
    ])
    assert "SHORT" in text
    assert "0c" not in text


# --- end to end ---------------------------------------------------------------

TWO_RAILS = Catalog.of(
    Product(sku="RAIL-3000", name="Rail 3000",
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3),
            price_cents=1000),
    Product(sku="RAIL-3050", name="Rail 3050",
            consumption=DivisibleLinear(purchase_length_mm=3050, kerf_mm=3),
            price_cents=1050),
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def test_explaining_a_bay_says_which_product_was_bought_and_why(client):
    """The end the whole mechanism exists for: a two-member group, carried
    through generation and storage, explained to a person clicking a bay."""
    model = {
        "id": "M-TWO", "version": 1, "name_i18n": {"en": "Two rails", "he": "שתי מסילות"},
        "default_spec": {"frame": [{
            "key": "rail", "orientation": "horizontal",
            "placement": {"kind": "distributed", "count": 2},
            "requirement": {
                "role": "rail", "qty": 1, "length_rule": "centre_to_centre",
                "eligibility": {"members": [
                    {"kind": "catalog_item", "sku": "RAIL-3000", "priority": 1},
                    {"kind": "catalog_item", "sku": "RAIL-3050", "priority": 2},
                ]},
            },
        }]},
    }
    for sku, product in TWO_RAILS.products.items():
        assert client.put("/api/catalog/products",
                          json=product.model_dump()).status_code == 200, sku
    created = client.post("/api/fence-models", json=model).json()
    assert created["invalid"] is None, created["invalid"]
    client.post(f"/api/fence-models/M-TWO/{created['model']['version']}/publish")

    pid = client.post("/api/projects", json={"name": "two"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-TWO"})
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = result["run"]["id"]
    span_id = result["strategy"]["spans"][0]["id"]

    body = client.get(f"/api/runs/{run_id}/explain/{span_id}").json()
    text = " ".join(body["explanation"])
    assert "RAIL-3000" in text and "RAIL-3050" in text, \
        "the bay's explanation does not name the products that were weighed"
    assert "least_cost" in text


def test_the_stored_run_document_is_unchanged_by_being_explained(client):
    pid = client.post("/api/projects", json={"name": "plain"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 3000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    result = client.post(f"/api/projects/{pid}/generate").json()["result"]
    run_id = result["run"]["id"]
    before = client.get(f"/api/runs/{run_id}").json()
    client.get(f"/api/runs/{run_id}/explain/{result['strategy']['spans'][0]['id']}")
    assert client.get(f"/api/runs/{run_id}").json() == before
