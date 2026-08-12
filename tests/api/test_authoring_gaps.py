"""The four gaps the authoring round left open, each with the failure it caused.

Reported honestly rather than patched at the time, on the grounds that each
needed a product decision rather than a fix. These are the decisions.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app
from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_SLAT, slat_model
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import Eligibility, validate_model
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import DefaultComponent, KnowledgeVersion
from fenceai.learning.impact import ImpactCase, preview_model_impact
from tests.conftest import straight_topology


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


def draft_body(model_id="M-GAP", count=2):
    return {
        "id": model_id, "version": 1, "name_i18n": {"en": "Gap", "he": "פער"},
        "default_spec": {"frame": [{
            "key": "rail", "orientation": "horizontal",
            "placement": {"kind": "distributed", "count": count},
            "requirement": {"role": "rail", "qty": 1, "length_rule": "centre_to_centre",
                            "eligibility": {"members": [
                                {"kind": "catalog_item", "sku": "RAIL-3000"}]}},
        }]},
    }


# --- 1: a slot nothing can supply published cleanly ---------------------------

def test_a_slot_with_no_eligible_product_cannot_be_published(client):
    """It used to publish fine and then report `no_eligible_item` on every bay of
    every job built to it. The author is the only person who can say what belongs
    there, and the moment they can say it is while they are authoring."""
    body = draft_body()
    body["default_spec"]["frame"][0]["requirement"]["eligibility"]["members"] = []
    created = client.post("/api/fence-models", json=body).json()
    assert created["invalid"]["code"] == "fence_model_invalid"

    r = client.post(f"/api/fence-models/M-GAP/{created['model']['version']}/publish")
    assert r.status_code == 422


def test_the_error_names_the_slot_so_it_can_be_found():
    model = slat_model().model_copy(deep=True)
    model.default_spec.frame[0].requirement.eligibility = Eligibility(members=[])
    errors = validate_model(model, demo_catalog())
    assert any("rail" in e and "no eligible product" in e for e in errors)


# --- 2: one broken project took the whole portfolio preview down --------------

def test_a_project_that_cannot_generate_does_not_break_the_preview():
    """The "before" spine ran outside the try, so one unbuildable job 500'd the
    answer to "what would this change affect" — at the moment a user most needs
    an answer."""
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-BROKEN", version=1, type="company_rule", title="a missing rail",
        actions=[DefaultComponent(role="rail", sku="SKU-THAT-DOES-NOT-EXIST")]))

    # the broken one is on the compatibility model, whose eligibility is seeded
    # from the resolved demand SKUs — so the missing rail reaches it and
    # `_validate_resolved_model` refuses. M-SLAT names its own rail, so the other
    # project is untouched by the same rule.
    cases = [
        ImpactCase(project_id="broken", project_name="broken",
                   topology=straight_topology(6000)),
        ImpactCase(project_id="fine", project_name="fine",
                   topology=straight_topology(6000),
                   fence_model=FenceModelChoice(model_id="M-SLAT")),
    ]
    edited = M_SLAT.model_copy(deep=True, update={"version": 2})
    edited.default_spec.infill.pattern[0].gap_after_mm = 60

    report = preview_model_impact(edited, FenceModelLibrary(models=[M_SLAT]),
                                  kb, demo_catalog(), cases)

    rows = {r.project_id: r for r in report.impacts}
    assert set(rows) == {"broken", "fine"}, "a project vanished from the report"
    assert rows["broken"].baseline_failed is True
    assert rows["broken"].generation_failure is not None
    # and it is NOT counted as affected: it was already broken, so this change
    # is not evidence about it
    assert rows["broken"].changed is False


# --- 3: two drafts, and the write went to the one nobody was editing ----------

def test_saving_a_draft_writes_the_version_the_listing_reports(client):
    """`listing()` reports the HIGHEST draft — the one the editor shows — while
    the save took the first it found. With two drafts they disagreed silently,
    and the user's edits landed in a version they were not looking at."""
    first = client.post("/api/fence-models", json=draft_body()).json()["model"]
    client.post(f"/api/fence-models/M-GAP/{first['version']}/publish")
    second = client.put("/api/fence-models/M-GAP/draft",
                        json=draft_body(count=3)).json()["model"]
    assert second["version"] > first["version"]

    row = next(x for x in client.get("/api/fence-models").json() if x["id"] == "M-GAP")
    saved = client.put("/api/fence-models/M-GAP/draft",
                       json=draft_body(count=4)).json()["model"]
    assert saved["version"] == second["version"]
    assert row.get("draft_version", second["version"]) == saved["version"]
    assert client.get(
        f"/api/fence-models/M-GAP/{saved['version']}"
    ).json()["default_spec"]["frame"][0]["placement"]["count"] == 4


# --- 4: an abandoned draft stayed for ever ------------------------------------

def test_a_draft_can_be_discarded(client):
    created = client.post("/api/fence-models", json=draft_body()).json()["model"]
    r = client.delete(f"/api/fence-models/M-GAP/{created['version']}")
    assert r.status_code == 200, r.text
    assert client.get(f"/api/fence-models/M-GAP/{created['version']}").status_code == 404
    assert not [x for x in client.get("/api/fence-models").json() if x["id"] == "M-GAP"]


def test_a_published_version_cannot_be_discarded(client):
    """A stored run or an accepted quote may name it; deleting one would make an
    immutable commercial document refer to nothing."""
    created = client.post("/api/fence-models", json=draft_body()).json()["model"]
    client.post(f"/api/fence-models/M-GAP/{created['version']}/publish")
    r = client.delete(f"/api/fence-models/M-GAP/{created['version']}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "fence_model_not_a_draft"


def test_the_compatibility_model_cannot_be_discarded_either(client):
    assert client.delete("/api/fence-models/M-LEGACY/1").status_code == 409
    assert client.get("/api/fence-models/M-LEGACY/1").status_code == 200
