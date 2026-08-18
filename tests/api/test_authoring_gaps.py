"""The four gaps the authoring round left open, each with the failure it caused.

Reported honestly rather than patched at the time, on the grounds that each
needed a product decision rather than a fix. These are the decisions.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app
from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_SLAT
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import validate_model
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import DefaultComponent, KnowledgeVersion
from fenceai.learning.impact import ImpactCase, preview_model_impact
from fenceai.parts.demo import demo_parts
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
    there, and the moment they can say it is while they are authoring.

    The rule SPLIT when a slot started naming a part. This body names no part and
    lists no member, so it is still refused here — that is the half `validate_model`
    kept. The other half, a slot that names a part no product covers, moved to
    `validate_part`; the test below is the one that follows it there."""
    body = draft_body()
    body["default_spec"]["frame"][0]["requirement"]["eligibility"]["members"] = []
    created = client.post("/api/fence-models", json=body).json()
    assert created["invalid"]["code"] == "fence_model_invalid"

    r = client.post(f"/api/fence-models/M-GAP/{created['model']['version']}/publish")
    assert r.status_code == 422


def test_the_refusal_followed_the_spec_onto_the_part_and_names_it():
    """WHERE this rule lives moved, and the old assertion would re-assert a rule
    the design retired.

    `validate_model` no longer refuses a slot with an empty member list: members
    are a MATCHING-time artifact and `parts.resolve` does not populate them, so
    that rule could not pass for any migrated model — it would refuse the whole
    portfolio for a list that is empty by design. The equivalent refusal is now
    `validate_part`'s "no product in the catalog covers this spec", raised over the
    object that actually says what may supply the slot, at the same moment and in
    the same voice.

    What is lost is the SLOT's name, and it is not lost: `validate_model` runs
    `validate_part` for every part its model names, so an author reading the model's
    errors still sees it — named by the part, which is where the fix has to be made.
    A part backing four slots is one fact about the library, and an author cannot
    fix it four times.
    """
    from fenceai.parts.model import Part, PartLibrary, SpecField
    from fenceai.parts.validate import validate_part

    # the part M-SLAT's rail slot names, republished as a spec nothing stocks
    unfillable = Part(id="rail-rail-3000", version=1, type="rail",
                      spec=[SpecField(key="sku", value=["NO-SUCH-RAIL"],
                                      agree="among")])
    assert any("no product in the catalog covers this spec" in e
               for e in validate_part(unfillable, demo_catalog()))

    # by NAME, not by position: `demo_parts()[1:]` meant reordering the demo library
    # silently changed which part this test replaced and which it left alone
    library = PartLibrary(parts=[unfillable, *(p for p in demo_parts()
                                               if p.id != "rail-rail-3000")])
    errors = validate_model(M_SLAT, demo_catalog(), library)
    assert any("rail-rail-3000@v1" in e and "no product in the catalog covers" in e
               for e in errors), errors
    # and the slot that names it is still buildable the moment the PART is fixed
    assert validate_model(M_SLAT, demo_catalog(),
                          PartLibrary(parts=demo_parts())) == []


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
