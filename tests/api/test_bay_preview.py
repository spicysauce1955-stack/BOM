"""Previewing a bay of a fence that already exists.

The drawer used to price a bay of a stored run by asking the MODEL-scoped
preview route for a panel of the same model at the same height and width. That
is a different question, and it was answered with different inputs: the default
objective preset, `length_basis="width"`, the model's authored rail count, no
options, and today's catalog instead of the one the run was frozen against.

Each test below is one of the ways those two questions came apart. The first is
the governing one: an empty body must reproduce the run's own numbers, asserted
against the RUN — never against another preview, which would only prove the two
previews agree with each other.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app, state


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


# --- fixtures -----------------------------------------------------------------

def make_project(client, name="job", nodes=None) -> str:
    pid = client.post("/api/projects", json={"name": name}).json()["id"]
    nodes = nodes or [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 6000, "y_mm": 0}]
    r = client.put(f"/api/projects/{pid}/topology", json={
        "nodes": nodes,
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}],
    })
    assert r.status_code == 200, r.text
    return pid


def generate(client, pid: str) -> dict:
    r = client.post(f"/api/projects/{pid}/generate")
    assert r.status_code == 200, r.text
    return r.json()["result"]


def set_preset(pid: str, preset: str) -> None:
    """No route sets a project's policy yet — the preset is a company setting,
    not a per-request one — so the fixture writes it where the generator reads
    it from."""
    project = state.store.load_project(pid)
    project.policy = {**project.policy, "objective_preset": preset}
    state.store.save_project(project)


def bay_preview(client, run_id: str, element_id: str, **body):
    return client.post(
        f"/api/runs/{run_id}/bays/{element_id}/panel-preview", json=body)


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def run_lines(client, run_id: str, element_id: str) -> dict:
    """What the RUN bought for one bay, by slot — the answer every preview here
    is measured against."""
    body = ok(client.get(f"/api/runs/{run_id}/bom"))
    return {line["slot_key"]: line for line in body["requirements"]
            if element_id in line["pegs"]}


def two_rail_catalog(client) -> None:
    """S15's two stock lengths: the 3000 is the company's first choice and the
    3050 is the cheaper cut (a 1500 piece fits twice in it, once in the 3000)."""
    rail = ok(client.get("/api/catalog"))["products"]["RAIL-3000"]
    alt = {**rail, "sku": "RAIL-3050", "price_cents": 1850,
           "consumption": {**rail["consumption"], "purchase_length_mm": 3050}}
    assert client.put("/api/catalog/products", json=alt).status_code == 200


def rivals_model(client, model_id="M-RIVALS") -> None:
    """A model whose rail slot has both stock lengths eligible, in the company's
    stated order."""
    model = {
        "id": model_id, "version": 1,
        "name_i18n": {"en": "Rivals", "he": "מתחרים"},
        "default_spec": {"frame": [{
            "key": "rail", "orientation": "horizontal",
            "placement": {"kind": "distributed", "count": 2,
                          "count_param": "rails_per_span"},
            "requirement": {"role": "rail", "qty": 1,
                            "length_rule": "centre_to_centre",
                            "eligibility": {"members": [
                                {"kind": "catalog_item", "sku": "RAIL-3000", "priority": 1},
                                {"kind": "catalog_item", "sku": "RAIL-3050", "priority": 2}]}},
        }]},
    }
    created = ok(client.post("/api/fence-models", json=model))["model"]
    ok(client.post(f"/api/fence-models/{model_id}/{created['version']}/publish"))


# --- the governing property ----------------------------------------------------

def test_an_empty_body_reproduces_the_runs_own_numbers_for_that_bay(client):
    pid = make_project(client)
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    bought = run_lines(client, result["run"]["id"], span["id"])

    preview = ok(bay_preview(client, result["run"]["id"], span["id"]))
    parts = {p["slot_key"]: p for p in preview["parts"]}

    assert set(parts) == set(bought), "the same slots, no more and no fewer"
    for slot, line in bought.items():
        assert parts[slot]["sku"] == line["sku"], slot
        assert parts[slot]["length_mm"] == line["cut_length_mm"], slot
        assert parts[slot]["qty"] == line["engineering_qty"], slot
    assert preview["height_mm"] == span["height_mm"]
    assert preview["width_mm"] == span["width_mm"]


def test_the_preview_resolves_the_model_the_run_stamped_for_the_bay(client):
    pid = make_project(client)
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    preview = ok(bay_preview(client, result["run"]["id"], span["id"]))
    assert preview["model_ref"] == span["panel"]["model_ref"]


def test_a_later_model_version_does_not_change_a_stored_bay(client):
    """`latest_active` is what a chooser wants and the opposite of what a stored
    run wants: the bay was built to the version the run stamped."""
    pid = make_project(client)
    ok(client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-SLAT"}))
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    ref = span["panel"]["model_ref"]
    model_id, version = ref.rsplit("@v", 1)
    assert model_id == "M-SLAT"

    newer = ok(client.get(f"/api/fence-models/{model_id}/{version}"))
    newer["version"] = int(version) + 1
    newer["status"] = "draft"
    newer["default_spec"]["frame"][0]["placement"]["count"] = 5
    created = ok(client.post("/api/fence-models", json=newer))["model"]
    ok(client.post(f"/api/fence-models/{model_id}/{created['version']}/publish"))

    preview = ok(bay_preview(client, result["run"]["id"], span["id"]))
    assert preview["model_ref"] == ref


# --- the preset: the reviewer's S15 case ---------------------------------------

def test_a_bay_of_an_honour_priority_run_previews_what_the_run_bought(client):
    """The blocker, end to end. The run buys its first-choice stock length; the
    model-scoped route, hardcoded to `least_cost`, calls the other one chosen."""
    two_rail_catalog(client)
    rivals_model(client)
    pid = make_project(client)
    ok(client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-RIVALS"}))
    set_preset(pid, "honour_priority")
    result = generate(client, pid)
    run_id = result["run"]["id"]
    assert result["run"]["objective_preset"] == "honour_priority"
    span = result["strategy"]["spans"][0]
    assert run_lines(client, run_id, span["id"])["rail"]["sku"] == "RAIL-3000"

    preview = ok(bay_preview(client, run_id, span["id"]))
    rail = next(p for p in preview["parts"] if p["slot_key"] == "rail")
    assert rail["sku"] == "RAIL-3000"
    assert set(rail["eligible_skus"]) == {"RAIL-3000", "RAIL-3050"}, (
        "both were in the running — the preset is what decided")

    # and the route it replaced disagrees, which is why it was replaced
    old = ok(client.post("/api/fence-models/M-RIVALS/1/preview",
                         json={"height_mm": span["height_mm"],
                               "width_mm": span["width_mm"]}))
    assert next(p for p in old["parts"] if p["slot_key"] == "rail")["sku"] == "RAIL-3050"


# --- the bay's own geometry ----------------------------------------------------

def sloped_project(client) -> str:
    return make_project(client, name="slope", nodes=[
        {"id": "n1", "x_mm": 0, "y_mm": 0},
        {"id": "n2", "x_mm": 6000, "y_mm": 0, "z_mm": 300},
    ])


def test_a_raked_bays_rails_are_cut_on_the_slope_in_the_preview_too(client):
    """S04/S06: a raked bay's rails are cut on the slope length, and
    `length_basis` was not expressible through the model-scoped request at all —
    so that preview drew and priced a level bay of the same width."""
    pid = sloped_project(client)
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    assert span["vertical"] == "raked" and span["rail_cut_basis"] == "slope"
    assert span["slope_len_mm"] > span["width_mm"]
    bought = run_lines(client, result["run"]["id"], span["id"])

    preview = ok(bay_preview(client, result["run"]["id"], span["id"]))
    rail = next(p for p in preview["parts"] if p["slot_key"] == "rail")
    assert rail["length_mm"] == bought["rail"]["cut_length_mm"]
    assert rail["length_mm"] == span["slope_len_mm"], "cut on the grade, not the plan"

    level = ok(client.post(
        f"/api/fence-models/{preview['model_ref'].replace('@v', '/')}/preview",
        json={"height_mm": span["height_mm"], "width_mm": span["width_mm"]}))
    assert next(p for p in level["parts"] if p["slot_key"] == "rail")["length_mm"] \
        == span["width_mm"], "the old route could only ever answer for a level bay"


def test_a_wider_what_if_on_a_raked_bay_keeps_the_grade(client):
    """A what-if changes the width; the ground it stands on is unchanged, so the
    slope length is recomputed from the bay's own rise rather than carried over
    from a width nobody asked about."""
    pid = sloped_project(client)
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    wider = span["width_mm"] + 200

    preview = ok(bay_preview(client, result["run"]["id"], span["id"], width_mm=wider))
    rail = next(p for p in preview["parts"] if p["slot_key"] == "rail")
    rise = span["bottom_z_end_mm"] - span["bottom_z_start_mm"]
    assert rail["length_mm"] > wider, "still cut on the slope"
    assert rail["length_mm"] == round((wider ** 2 + rise ** 2) ** 0.5)


def test_a_company_rail_count_changes_the_previewed_frame_the_way_it_changed_the_run(client):
    """`rails_per_span` is knowledge, and the preview cannot resolve knowledge —
    it has no project to bind a scope to. So the span's own resolved quantity is
    what it is given. The demo hides this because K-RAILS says 2, which is also
    the model's authored default."""
    ok(client.post("/api/knowledge", json={
        "object_id": "K-RAILS", "type": "fact", "title": "3 rails per span",
        "actions": [{"kind": "set_param", "param": "rails_per_span", "value": 3}],
    }))
    pid = make_project(client)
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    assert span["rail_count"] == 3
    bought = run_lines(client, result["run"]["id"], span["id"])

    preview = ok(bay_preview(client, result["run"]["id"], span["id"]))
    rail = next(p for p in preview["parts"] if p["slot_key"] == "rail")
    assert rail["qty"] == bought["rail"]["engineering_qty"] == 3
    assert len(next(s for s in preview["panel"]["slots"]
                    if s["slot_key"] == "rail")["positions_mm"]) == 3, (
        "the frame is drawn with the members the run bought")
    screw = next(p for p in preview["parts"] if p["slot_key"] == "screw")
    assert screw["qty"] == bought["screw"]["engineering_qty"]

    ref = preview["model_ref"].replace("@v", "/")
    old = ok(client.post(f"/api/fence-models/{ref}/preview",
                         json={"height_mm": span["height_mm"],
                               "width_mm": span["width_mm"]}))
    assert next(p for p in old["parts"] if p["slot_key"] == "rail")["qty"] == 2, (
        "the model-scoped route can only answer with the model's own default")


def finish_model(client, model_id="M-FINISH") -> None:
    """One rail slot, two eligible products, and an option axis that names one of
    them per value — the shape an option narrowing needs to be visible."""
    two_rail_catalog(client)
    model = {
        "id": model_id, "version": 1,
        "name_i18n": {"en": "Finish", "he": "גימור"},
        "option_axes": [{"key": "finish", "kind": "enum", "values": [
            {"key": "plain", "label_i18n": {"en": "Plain"}},
            {"key": "long", "label_i18n": {"en": "Long"}}]}],
        "default_spec": {"frame": [{
            "key": "rail", "orientation": "horizontal",
            "placement": {"kind": "distributed", "count": 2,
                          "count_param": "rails_per_span"},
            "requirement": {"role": "rail", "qty": 1,
                            "length_rule": "centre_to_centre",
                            "option_axis": "finish",
                            "sku_by_option": {"plain": "RAIL-3000", "long": "RAIL-3050"},
                            "eligibility": {"members": [
                                {"kind": "catalog_item", "sku": "RAIL-3000", "priority": 1},
                                {"kind": "catalog_item", "sku": "RAIL-3050", "priority": 2}]}},
        }]},
    }
    created = ok(client.post("/api/fence-models", json=model))["model"]
    ok(client.post(f"/api/fence-models/{model_id}/{created['version']}/publish"))


def test_each_bay_previews_under_the_options_that_bay_was_built_with(client):
    """Two stretches of one fence, the same model version, different options.

    `model_snapshot` names that model twice and cannot say which bay is which;
    the decision graph can, because `select_model` records the effective choice
    and every bay's `resolve_panel` takes that node as an input. Reading the
    options off the snapshot would price half this fence in the other finish.
    """
    finish_model(client)
    pid = client.post("/api/projects", json={"name": "two finishes"}).json()["id"]
    anchor = {"segment_index": 0, "offset_mm": 0, "seg_len_at_authoring_mm": 6000}
    ok(client.put(f"/api/projects/{pid}/topology", json={
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 6000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2",
                  "interval_events": [{
                      "id": "ev_finish",
                      "start_anchor": anchor,
                      "end_anchor": {**anchor, "offset_mm": 3000},
                      "payload": {"kind": "fence_model", "model_id": "M-FINISH",
                                  "options": {"finish": "long"}},
                  }]}],
    }))
    ok(client.put(f"/api/projects/{pid}/fence-model",
                  json={"model_id": "M-FINISH", "options": {"finish": "plain"}}))
    result = generate(client, pid)
    run_id = result["run"]["id"]
    spans = result["strategy"]["spans"]
    first, last = spans[0], spans[-1]
    uses = result["run"]["model_snapshot"]
    assert len(uses) == 2 and {u["model_id"] for u in uses} == {"M-FINISH"}, (
        "one model, two option sets — the snapshot alone is ambiguous")

    for span in (first, last):
        bought = run_lines(client, run_id, span["id"])["rail"]["sku"]
        preview = ok(bay_preview(client, run_id, span["id"]))
        rail = next(p for p in preview["parts"] if p["slot_key"] == "rail")
        assert rail["eligible_skus"] == [bought], span["id"]
        assert rail["sku"] == bought, span["id"]
    assert run_lines(client, run_id, first["id"])["rail"]["sku"] != \
        run_lines(client, run_id, last["id"])["rail"]["sku"], "the fixture must differ"


# --- what-ifs and refusals -----------------------------------------------------

def test_a_named_product_still_narrows_the_slot(client):
    two_rail_catalog(client)
    rivals_model(client, "M-PICK")
    pid = make_project(client)
    ok(client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-PICK"}))
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]

    preview = ok(bay_preview(client, result["run"]["id"], span["id"],
                             slot_skus={"rail": "RAIL-3000"}))
    rail = next(p for p in preview["parts"] if p["slot_key"] == "rail")
    assert rail["sku"] == "RAIL-3000" and rail["eligible_skus"] == ["RAIL-3000"]


def test_a_product_the_slot_cannot_be_supplied_by_is_a_coded_422(client):
    pid = make_project(client)
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    r = bay_preview(client, result["run"]["id"], span["id"],
                    slot_skus={"rail": "POST-S"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "sku_not_eligible"


def test_a_taller_what_if_is_priced_as_asked(client):
    pid = make_project(client)
    result = generate(client, pid)
    span = result["strategy"]["spans"][0]
    taller = ok(bay_preview(client, result["run"]["id"], span["id"],
                            height_mm=span["height_mm"] + 400))
    assert taller["height_mm"] == span["height_mm"] + 400
    assert taller["width_mm"] == span["width_mm"], "only what was asked changes"


def test_an_unknown_run_is_a_404(client):
    assert bay_preview(client, "run_nope", "span@x:0-1").status_code == 404


def test_an_element_that_is_not_a_bay_of_this_run_is_a_404(client):
    pid = make_project(client)
    result = generate(client, pid)
    post_id = result["strategy"]["posts"][0]["id"]
    assert bay_preview(client, result["run"]["id"], post_id).status_code == 404
    assert bay_preview(client, result["run"]["id"], "span@other:0-1").status_code == 404


def test_a_moved_catalog_refuses_here_exactly_as_it_does_on_the_bom(client):
    """A stored run re-priced against a catalog it was not generated from is the
    same lie whether it is the whole BOM or one bay of it."""
    pid = make_project(client)
    result = generate(client, pid)
    run_id, span = result["run"]["id"], result["strategy"]["spans"][0]
    assert bay_preview(client, run_id, span["id"]).status_code == 200

    rail = ok(client.get("/api/catalog"))["products"]["RAIL-3000"]
    ok(client.put("/api/catalog/products", json={**rail, "price_cents": 9999}))

    assert client.get(f"/api/runs/{run_id}/bom").status_code == 409
    r = bay_preview(client, run_id, span["id"])
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "catalog_changed"
