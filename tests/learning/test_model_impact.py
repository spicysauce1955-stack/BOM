"""Editing a model is a portfolio-wide change, so it has to be previewable.

`FenceModel` is catalog-side rather than a knowledge object, so it inherits none
of knowledge's versioning, review and preview machinery — and a slat gap that
silently reprices every open job is exactly what foundation §11 requires to be
exposed before it is made.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.learning.impact import (
    ImpactCase,
    hypothetical_library,
    preview_impact,
    preview_model_impact,
)
from fenceai.knowledge.model import KnowledgeVersion, SetParam
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from tests.conftest import straight_topology


# What M-SLAT's slots name. Without it every previewed job is regenerated from an
# unresolved document — no widths, no products — and every delta comes out zero.
PARTS = PartLibrary(parts=demo_parts())


def library() -> FenceModelLibrary:
    return FenceModelLibrary(models=[M_LEGACY, M_SLAT])


def case(fence_model=None, project_id="proj_1") -> ImpactCase:
    return ImpactCase(
        project_id=project_id, project_name="A job",
        topology=straight_topology(5000), fence_model=fence_model,
    )


def wider_slats(gap_mm: int):
    """The same model with one number changed — the canonical model edit."""
    edited = M_SLAT.model_copy(deep=True, update={"version": 2})
    edited.default_spec.infill.pattern[0].gap_after_mm = gap_mm
    return edited


# --- the model-version case ---------------------------------------------------

def test_widening_the_slat_gap_is_reported_as_a_change_to_the_jobs_that_use_it():
    report = preview_model_impact(
        wider_slats(60), library(), demo_knowledge(), demo_catalog(),
        [case(FenceModelChoice(model_id="M-SLAT"))], PARTS,
    )
    assert report.hypothetical_ref == "M-SLAT@v2"
    assert report.projects_checked == 1
    assert report.projects_affected == 1
    impact = report.impacts[0]
    assert impact.changed
    # wider gaps mean fewer slats, so the job gets cheaper — the direction matters
    assert impact.bom_delta_cents < 0


def test_a_job_built_to_another_model_is_checked_and_reported_unaffected():
    """Every project appears in the report with a `changed` flag; a project that
    does not use the model must read as untouched rather than be missing."""
    report = preview_model_impact(
        wider_slats(60), library(), demo_knowledge(), demo_catalog(),
        [case(FenceModelChoice(model_id="M-LEGACY"))],
    )
    assert report.projects_checked == 1
    assert report.projects_affected == 0
    assert report.impacts[0].changed is False


def test_a_project_pinned_to_the_old_version_is_unaffected():
    """That is what a pin is for. If publishing v2 moved a pinned job too, the
    pin would be decoration."""
    report = preview_model_impact(
        wider_slats(60), library(), demo_knowledge(), demo_catalog(),
        [case(FenceModelChoice(model_id="M-SLAT", version_pin=1))],
    )
    assert report.impacts[0].changed is False


def test_the_old_active_version_is_retired_in_the_hypothesis():
    """Otherwise `latest_active` could still return v1 and the preview would
    report no change to anything."""
    after = hypothetical_library(library(), wider_slats(60))
    assert after.resolve("M-SLAT", None).version == 2
    assert after.get("M-SLAT", 1).status == "retired"
    assert after.resolve("M-SLAT", 1) is not None, "a pin must still reach it"


def test_previewing_the_same_model_again_reports_nothing():
    report = preview_model_impact(
        M_SLAT.model_copy(deep=True), library(), demo_knowledge(), demo_catalog(),
        [case(FenceModelChoice(model_id="M-SLAT"))], PARTS,
    )
    assert report.projects_affected == 0


def test_the_preview_mutates_nothing():
    lib = library()
    before = lib.model_dump_json()
    preview_model_impact(wider_slats(60), lib, demo_knowledge(), demo_catalog(),
                         [case(FenceModelChoice(model_id="M-SLAT"))])
    assert lib.model_dump_json() == before


# --- the defect this round also closes ----------------------------------------

def test_a_knowledge_preview_regenerates_a_job_under_its_own_model():
    """The preview used to regenerate every project as if it had no model
    default, so a job built to M-SLAT was previewed as M-LEGACY: the report then
    showed the delta of two changes at once and attributed both to the rule."""
    kb = demo_knowledge()
    hypothetical = KnowledgeVersion(
        object_id="K-RAILS", version=2, type="fact", title="3 rails per span",
        actions=[SetParam(param="rails_per_span", value=3)],
    )
    def delta_for(choice):
        report = preview_impact(hypothetical, kb, demo_catalog(),
                                [case(choice)], library(), PARTS)
        return report.impacts[0].bom_delta_cents

    slat = delta_for(FenceModelChoice(model_id="M-SLAT"))
    legacy = delta_for(FenceModelChoice(model_id="M-LEGACY"))
    # The comparison is what makes this test non-vacuous: a third rail changes
    # the BOM under BOTH models, so "the delta is non-zero" would pass with the
    # bug intact. The two deltas differ only if each job was regenerated under
    # its OWN model — M-SLAT's screws are per_member_crossing, so a third rail
    # adds two screws per slat, while M-LEGACY's are per_panel and it adds none.
    assert slat != legacy
    assert slat and legacy
