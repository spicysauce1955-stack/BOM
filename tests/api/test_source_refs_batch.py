"""`POST /api/source-refs:batch` — the evidence viewer's one data route.

Fixture-backed (frontend design §3): the real Knowledge Platform Discovery API
does not exist yet, so this resolves against a vendored copy of fence-rag's own
`source-ref-examples.json` — seven records built from real rows in their store,
covering every kind and every degrade case. This file exercises three of them:
a normal quoted paragraph, a record with no quote at all (the scanned NOA page,
where the whole page IS the evidence), and the derived record with no document
and no image at all. None of those three is an error case — the design doc is
explicit that all three are first-class results.
"""

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app

REF_1 = "sref_00000000000000000000000000000001"  # element_quote, no pre-cut crop
REF_3 = "sref_00000000000000000000000000000003"  # page, no quote at all
REF_4 = "sref_00000000000000000000000000000004"  # visual_reading, agent reader
REF_7 = "sref_00000000000000000000000000000007"  # derived, no document, no image


# Same fixture pattern as tests/api/test_parts_routes.py: the store only exists
# inside the app's lifespan, and each test gets its own scratch DB.
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def test_a_normal_quoted_paragraph_resolves_with_document_and_locus(client):
    body = client.post("/api/source-refs:batch", json={"ids": [REF_1]}).json()
    assert body["not_found"] == []
    rec = body["resolved"][0]
    assert rec["source_ref_id"] == REF_1
    assert rec["kind"] == "element_quote"
    assert rec["document"]["manufacturer"] == "CertainTeed"
    assert rec["document"]["status"]["version_status"] == "unknown"
    assert "30\" deep" in rec["text"]["quote"]
    assert rec["locus"]["page_no"] == 5
    assert rec["image"]["status"] == "available"
    # a paragraph with a bbox and no pre-cut crop — the crop is still described
    assert rec["image"]["crop"]["bbox_px"] == [322, 750, 745, 820]
    codes = {w["code"] for w in rec["warnings"]}
    assert "SOURCE_VERSION_STATUS_UNKNOWN" in codes


def test_the_scanned_page_case_has_no_quote_and_no_bbox_but_is_not_an_error(client):
    """The case the design doc calls out as the one an interface is most likely
    to get wrong: no quote, no element, no bbox — the whole page is the
    evidence. A valid, non-error, first-class result."""
    body = client.post("/api/source-refs:batch", json={"ids": [REF_3]}).json()
    rec = body["resolved"][0]
    assert rec["kind"] == "page"
    assert rec["text"]["quote"] is None
    assert rec["text"]["quote_absent_reason"]
    assert rec["locus"]["bbox_pt"] is None
    assert rec["image"]["status"] == "available"
    assert rec["image"]["crop"] is None
    assert rec["image"]["page"]["width_px"] == 3400  # landscape sheet


def test_the_derived_record_has_no_document_and_no_image_and_is_not_an_error(client):
    """A hand-researched dataset assertion: no document, no page, no pixels at
    all. The design doc's other hard case — a broken thumbnail or a 404 here
    would be dishonest; `image.status: not_applicable` with a reason is the
    correct, valid answer."""
    body = client.post("/api/source-refs:batch", json={"ids": [REF_7]}).json()
    rec = body["resolved"][0]
    assert rec["kind"] == "derived"
    assert rec["document"] is None
    assert rec["locus"] is None
    assert rec["text"]["quote"] is None
    assert rec["image"]["status"] == "not_applicable"
    assert rec["image"]["reason"]
    assert rec["image"]["crop"] is None and rec["image"]["page"] is None
    assert rec["derived_from"]["dataset_path"].endswith(".json")
    codes = {w["code"] for w in rec["warnings"]}
    assert "SOURCE_NO_IMAGE_AVAILABLE" in codes
    assert "SOURCE_DERIVED_NOT_ACCEPTABLE" in codes


def test_the_visual_reading_carries_the_readers_identity_and_no_cell_box(client):
    """`visual_reading` is stronger than `page` and must not look like it: a
    named reader read this cell, at these crop pixels — but the current corpus
    records row/column labels only, with no cell box in crop pixels."""
    body = client.post("/api/source-refs:batch", json={"ids": [REF_4]}).json()
    rec = body["resolved"][0]
    assert rec["kind"] == "visual_reading"
    assert rec["reading"]["reader"] == "calibration-A"
    assert rec["reading"]["reader_kind"] == "agent"
    assert rec["reading"]["value_raw"] == '97"'
    assert rec["reading"]["cell_bbox_px"] is None
    assert rec["reading"]["cell_bbox_absent_reason"]


def test_batch_resolves_several_ids_in_one_call(client):
    body = client.post(
        "/api/source-refs:batch",
        json={"ids": [REF_1, REF_3, REF_7]},
    ).json()
    assert body["not_found"] == []
    assert {r["source_ref_id"] for r in body["resolved"]} == {REF_1, REF_3, REF_7}


def test_an_id_the_fixture_does_not_carry_is_reported_not_failed(client):
    """A queue resolving fifty citations cannot afford one miss to fail the
    other forty-nine — an unrecognized opaque id is an honest 'not found',
    never a 404 that aborts the whole batch."""
    body = client.post(
        "/api/source-refs:batch",
        json={"ids": [REF_1, "sref_does_not_exist"]},
    ).json()
    assert len(body["resolved"]) == 1
    assert body["resolved"][0]["source_ref_id"] == REF_1
    assert body["not_found"] == ["sref_does_not_exist"]


def test_an_empty_batch_is_a_valid_empty_result(client):
    body = client.post("/api/source-refs:batch", json={"ids": []}).json()
    assert body == {"resolved": [], "not_found": []}
