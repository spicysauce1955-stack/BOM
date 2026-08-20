"""The two routes the picker needs, and nothing more.

No eligibility endpoint: `PreviewPart.eligible_skus` already carries the candidate
set per slot and `/api/fence-models/preview` already takes an unsaved document, so
the list the editor wants is already arriving in the browser and simply is not
displayed.
"""

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app


# A fixture, not a module-level `client = TestClient(app)`: the store lives on
# `state.store` and is only populated inside `app`'s lifespan, which a bare
# TestClient never enters. Matches the `client(tmp_path, monkeypatch)` fixture
# every other file in this directory uses, so each test also gets its own
# scratch DB instead of writing into the repo's `fenceai.db`.
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def test_the_library_is_listed_with_the_spec_each_part_declares(client):
    body = client.get("/api/parts").json()
    parts = {p["id"]: p for p in body["parts"]}
    assert "rail-rail-3000" in parts
    rail = parts["rail-rail-3000"]
    assert rail["type"] == "rail"
    assert rail["status"] == "active"
    assert rail["version"] >= 1
    # the spec travels: an author choosing a part should see WHY it is that part,
    # not only its name
    assert any(f["key"] == "sku" for f in rail["spec"])


def test_a_spec_field_keeps_its_three_parts(client):
    body = client.get("/api/parts").json()
    rail = next(p for p in body["parts"] if p["id"] == "rail-rail-3000")
    sku_field = next(f for f in rail["spec"] if f["key"] == "sku")
    assert sku_field["agree"] == "among"
    assert sku_field["value"] == ["RAIL-3000"]


def test_a_multi_candidate_part_is_offered_too(client):
    """`rail-38-vinyl` is specified by width and material rather than by sku. It is
    the case the whole entity exists for, and a picker that only ever showed
    sku-list parts would render the feature invisible."""
    ids = {p["id"] for p in client.get("/api/parts").json()["parts"]}
    assert "rail-38-vinyl" in ids


def test_the_types_in_use_are_offered_with_labels(client):
    body = client.get("/api/part-types").json()
    keys = {t["key"] for t in body["types"]}
    assert {"rail", "infill", "screw"} <= keys
    rail = next(t for t in body["types"] if t["key"] == "rail")
    assert rail["label_i18n"]["en"]
    assert rail["label_i18n"]["he"]


def test_types_are_derived_from_the_library_not_invented(client):
    """Nothing instantiates PartType, so a route over stored type data would return
    an empty list. These come from the parts that exist."""
    parts = client.get("/api/parts").json()["parts"]
    types = {t["key"] for t in client.get("/api/part-types").json()["types"]}
    assert types == {p["type"] for p in parts}


def test_the_types_are_sorted_so_the_picker_does_not_reshuffle(client):
    keys = [t["key"] for t in client.get("/api/part-types").json()["types"]]
    assert keys == sorted(keys)
