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


def _a_fence_that_actually_decides(client) -> tuple[str, str]:
    """A project whose rail AND slat slots have two eligible stocks each, built
    with nothing but calls a user can make.

    `tests/report/test_bom_groups.py::_with_a_real_choice` builds this shape in
    process, and in process is exactly where it stopped: every demo model names
    ONE product per slot, so no fixture anywhere put a `select_supply` decision
    on the wire, and the routes that derive those nodes from a stored run could
    be deleted with the suite still green.

    The path is the product and model editors, so no state is forced behind the
    API's back: two catalog products (`PUT /api/catalog/products`), then the
    built-in slat panel read back, its rail and slat requirements pointed at an
    eligibility of two members instead of a single part, and the result POSTed
    as a new model, published, and chosen as the project's default. A published
    model with a multi-member group is the only thing that makes `resolve_supply`
    decide rather than look up.
    """
    pid = client.post("/api/projects", json={"name": "decides"}).json()["id"]
    assert client.put(f"/api/projects/{pid}/topology", json={
        "revision": 1,
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    }).status_code == 200

    # a rival for the rail: 3050 mm stock, cheap enough that least_cost prefers
    # it over the priority-1 RAIL-3000 — so `chosen` is demonstrably NOT the
    # first member, and a test that read the priority order would not notice
    assert client.put("/api/catalog/products", json={
        "sku": "RAIL-3050", "name": "Rail stock 3050 mm",
        "consumption": {"kind": "divisible_linear", "purchase_length_mm": 3050,
                        "kerf_mm": 3, "min_reusable_remnant_mm": 300},
        "price_cents": 1850,
    }).status_code == 200
    # ...and a rival for the slat which LOSES, so the run records two decisions
    # that went opposite ways
    assert client.put("/api/catalog/products", json={
        "sku": "SLAT-105", "name": "Slat 100 mm (6000 mm stock)",
        "consumption": {"kind": "divisible_linear", "purchase_length_mm": 6000,
                        "kerf_mm": 3, "min_reusable_remnant_mm": 300},
        "price_cents": 5600,
        "attrs": {"type": "infill", "width_mm": 100},
    }).status_code == 200

    model = client.get("/api/fence-models/M-SLAT/1").json()
    model["id"] = "M-CHOICE"
    model["name_i18n"] = {"en": "Choice panel", "he": "פאנל בחירה"}
    rail = model["default_spec"]["frame"][0]["requirement"]
    rail["part_id"] = ""
    rail["role"] = "rail"
    rail["eligibility"] = {"members": [
        {"kind": "catalog_item", "sku": "RAIL-3000", "priority": 1},
        {"kind": "catalog_item", "sku": "RAIL-3050", "priority": 2}]}
    member = model["default_spec"]["infill"]["pattern"][0]
    # the width the part used to supply: a member naming no part must carry its
    # own or `fit_pattern` has no advance to lay out
    member["width_mm"] = 100
    slat = member["requirement"]
    slat["part_id"] = ""
    slat["role"] = "infill"
    slat["eligibility"] = {"members": [
        {"kind": "catalog_item", "sku": "SLAT-100", "priority": 1},
        {"kind": "catalog_item", "sku": "SLAT-105", "priority": 2}]}

    made = client.post("/api/fence-models", json=model)
    assert made.status_code == 200, made.text
    assert made.json()["invalid"] is None, made.text
    version = made.json()["model"]["version"]
    published = client.post(f"/api/fence-models/M-CHOICE/{version}/publish")
    assert published.status_code == 200, published.text
    assert client.put(f"/api/projects/{pid}/fence-model",
                      json={"model_id": "M-CHOICE"}).status_code == 200

    gen = client.post(f"/api/projects/{pid}/generate")
    assert gen.status_code == 200, gen.text
    return pid, gen.json()["result"]["run"]["id"]


def test_a_decision_is_named_the_same_thing_by_the_money_view_the_story_and_a_comment(
        isolated_client):
    """THE join, end to end, on a run that genuinely decides.

    Three surfaces name one supply decision: the grouped BOM's `decision` group,
    the `select_supply` node the section's story is told from, and the
    `decision_ref` a person's comment is anchored to. Every fixture in the suite
    priced a model with one eligible product per slot, so `select_supply` decided
    nothing, no `decision` group and no `select_supply` node ever reached the
    wire, and two independent breakages survived the whole suite:

    * deleting `with_supply_decisions` from the section route — the story loses
      every "which product was bought and why" node, silently;
    * changing the node id's prefix in `decisions/supply.py` — the money view
      and the graph go back to having two names for one decision, which is the
      exact join a whole commit was spent establishing.

    Both are killed here, and only by comparing the two surfaces' strings to each
    other. Recomputing either side's id from the same function proves only that
    the function is deterministic.
    """
    client = isolated_client
    pid, run_id = _a_fence_that_actually_decides(client)

    bom = client.get(f"/api/runs/{run_id}/bom")
    assert bom.status_code == 200, bom.text
    groups = bom.json()["grouped"]["groups"]
    decisions = [g for g in groups if g["kind"] == "decision"]
    assert len(decisions) == 2, \
        "the fixture must put TWO real supply decisions on the wire"

    story = client.get(f"/api/runs/{run_id}/sections/run1/decisions")
    assert story.status_code == 200, story.text
    supply_nodes = [d for d in story.json()["decisions"]
                    if d["action"] == "select_supply"]
    assert supply_nodes, \
        "the section's story carries no supply decision at all"

    # the same STRINGS, taken from two routes — not two calls to one id function
    assert {g["element_id"] for g in decisions} == {n["node_id"] for n in supply_nodes}

    rail = next(g for g in decisions if any(x["role"] == "rail" for x in g["lines"]))
    assert (rail["chosen"], rail["rejected"], rail["preset"]) == \
        ("RAIL-3050", ["RAIL-3000"], "least_cost"), \
        "the cheaper stock wins on cost, not the priority-1 member"
    assert all(x["sku"] == "RAIL-3050" for x in rail["lines"])
    infill = next(g for g in decisions if any(x["role"] == "infill" for x in g["lines"]))
    assert (infill["chosen"], infill["rejected"], infill["preset"]) == \
        ("SLAT-100", ["SLAT-105"], "least_cost")

    # and the story tells the same choice, in words, about the same node
    told = next(n for n in supply_nodes if n["node_id"] == rail["element_id"])
    assert "RAIL-3050" in told["sentence"] and "RAIL-3000" in told["sentence"]
    assert told["elements"], "a supply node scopes to the bays it bought for"

    # the third surface: a person arguing with that decision, read back on it
    made = client.post(f"/api/projects/{pid}/corrections", json={
        "generation_run_id": run_id, "decision_ref": rail["element_id"],
        "comment": "we always stock the 3000 — order those", "author": "expert",
    })
    assert made.status_code == 200, made.text
    assert made.json()["decision_ref"] == rail["element_id"]
    thread = client.get(f"/api/projects/{pid}/corrections"
                        f"?decision_ref={rail['element_id']}"
                        f"&generation_run_id={run_id}").json()
    assert [c["comment"] for c in thread] == ["we always stock the 3000 — order those"]
    # ...and it anchors to a decision the section view actually shows, which is
    # what makes it a conversation rather than a note filed against a string
    assert rail["element_id"] in {n["node_id"] for n in supply_nodes}
