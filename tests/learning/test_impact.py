"""Rule impact preview tests (learning/impact.py)."""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fulfillment.fulfill import Inventory
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import AddNote, KnowledgeVersion, SetParam
from fenceai.learning.impact import (
    ImpactCase,
    activated_copy,
    hypothetical_kb,
    preview_impact,
)
from tests.conftest import straight_topology


def _cases():
    return [
        ImpactCase(project_id="p1", project_name="six", topology=straight_topology(6000)),
        ImpactCase(project_id="p2", project_name="three", topology=straight_topology(3000)),
        ImpactCase(project_id="p3", project_name="empty", topology=straight_topology(6000).model_copy(update={"runs": [], "nodes": []})),
    ]


def hypo_max_span(value: int) -> KnowledgeVersion:
    return KnowledgeVersion(
        object_id="K-MAXSPAN", version=2, type="hard_constraint",
        title=f"max span {value}",
        actions=[SetParam(param="max_span_mm", value=value)],
        status="draft",
    )


def test_tightened_max_span_affects_projects():
    report = preview_impact(hypo_max_span(1400), demo_knowledge(), demo_catalog(), _cases())
    assert report.projects_checked == 2  # empty project skipped
    assert report.projects_affected == 2  # 6000: 4->5 spans; 3000: 2->3 spans
    p1 = next(i for i in report.impacts if i.project_id == "p1")
    assert p1.changed
    assert (p1.spans_before, p1.spans_after) == (4, 5)
    assert p1.posts_added == 4  # line posts move: 1500/3000/4500 -> 1200/2400/3600/4800
    assert p1.posts_removed == 3
    # counter-intuitive but correct: 1200 mm cuts pair on 3000 mm stock (2403 <= 3000)
    # while 1500 mm cuts cannot (3003 > 3000) — the tighter rule SAVES money here.
    # Exactly the non-obvious insight impact preview exists to surface.
    assert p1.bom_delta_cents == -2600
    assert p1.bom_after_cents == p1.bom_before_cents + p1.bom_delta_cents


def test_identical_rule_version_changes_nothing():
    report = preview_impact(hypo_max_span(1800), demo_knowledge(), demo_catalog(), _cases())
    assert report.projects_affected == 0
    assert all(not i.changed for i in report.impacts)
    assert all(i.bom_delta_cents == 0 for i in report.impacts)


def test_advisory_candidate_shows_no_structural_impact():
    """AddNote candidates (the stub proposer's output) change nothing structurally —
    the preview must say so honestly."""
    candidate = KnowledgeVersion(
        object_id="K-CAND-X", version=1, type="candidate",
        actions=[AddNote(text="prefer existing foundations")],
        scope={"project_id": "p1"}, status="proposed",
    )
    report = preview_impact(
        activated_copy(candidate), demo_knowledge(), demo_catalog(), _cases()
    )
    assert report.projects_affected == 0


def test_breaking_change_reported_as_generation_failure():
    """Retiring the only max-span source: preview surfaces the failure per project
    instead of crashing."""
    hypo = KnowledgeVersion(
        object_id="K-MAXSPAN", version=2, type="hard_constraint",
        title="broken: no param action", actions=[AddNote(text="oops")], status="draft",
    )
    report = preview_impact(hypo, demo_knowledge(), demo_catalog(), _cases())
    assert report.projects_affected == 2
    assert all(i.generation_failed for i in report.impacts)


def test_activated_copy_mirrors_review_promotion():
    cand = KnowledgeVersion(
        object_id="K-C", version=3, type="candidate",
        actions=[AddNote(text="x")], status="proposed",
    )
    active = activated_copy(cand)
    assert (active.version, active.type, active.status) == (4, "heuristic", "active")
    assert cand.status == "proposed"  # original untouched


def test_hypothetical_kb_retires_current_active():
    kb = demo_knowledge()
    kb2 = hypothetical_kb(kb, hypo_max_span(1400))
    actives = [v for v in kb2.versions if v.object_id == "K-MAXSPAN" and v.status == "active"]
    assert len(actives) == 1 and actives[0].version == 2
    # original KB untouched (pure)
    assert any(
        v.object_id == "K-MAXSPAN" and v.status == "active" and v.version == 1
        for v in kb.versions
    )


def test_preview_is_deterministic():
    r1 = preview_impact(hypo_max_span(1400), demo_knowledge(), demo_catalog(), _cases())
    r2 = preview_impact(hypo_max_span(1400), demo_knowledge(), demo_catalog(), _cases())
    assert r1.model_dump() == r2.model_dump()


def test_inventory_participates_in_bom_diff():
    """A remnant that only fits the AFTER cut lengths changes the BOM delta."""
    inv = Inventory.model_validate(
        {"items": [{"id": "r1", "sku": "RAIL-3000", "kind": "remnant", "length_mm": 1600, "qty": 1}]}
    )
    cases = [ImpactCase(project_id="p1", topology=straight_topology(6000), inventory=inv)]
    # asymmetric remnant: 1600 holds one BEFORE-side 1500 cut (saves a bar there)
    # but saves nothing on the AFTER side (one 1200 leaves 9 cuts -> still 5 bars),
    # so the delta must shift versus the no-inventory case
    report = preview_impact(hypo_max_span(1400), demo_knowledge(), demo_catalog(), cases)
    impact = report.impacts[0]
    assert impact.changed
    no_inv = preview_impact(
        hypo_max_span(1400), demo_knowledge(), demo_catalog(),
        [ImpactCase(project_id="p1", topology=straight_topology(6000))],
    ).impacts[0]
    assert impact.bom_before_cents == no_inv.bom_before_cents - 1800  # remnant saved a bar
    assert impact.bom_delta_cents == no_inv.bom_delta_cents + 1800
