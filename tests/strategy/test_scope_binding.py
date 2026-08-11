"""Rule scope binds to the facts of the thing being generated (persona-lab run 2, B2).

`KnowledgeVersion.scope` is a dict of bound dimensions and `specificity()` is the
second precedence key after authority. The generator used to hand the evaluator
`{"scope": {}}` at every call site, so **any** rule with a non-empty scope was
silently inert — including every rule the review queue produces via restricted
approval, and every candidate the stub proposer emits (it defaults to
`scope={"project_id": ...}`).

Dimensions are bound generically from facts present in the generation context —
nothing here is specific to a catalog, a SKU or to fences.
"""

from __future__ import annotations

from fenceai.knowledge.model import (
    DefaultComponent,
    KnowledgeBase,
    KnowledgeVersion,
    RequirePostReinforcement,
    SetParam,
)
from fenceai.learning.model import ReviewAction
from fenceai.learning.review import apply_review
from fenceai.strategy.generator import generate
from fenceai.topology.model import BasePayload, GatePayload
from tests.conftest import add_interval_event, add_point_event, straight_topology


def _rails_rule(scope: dict[str, str]) -> KnowledgeVersion:
    """Same tier as the demo K-RAILS fact — only specificity can decide."""
    return KnowledgeVersion(
        object_id="K-RAILS-PROJECT", version=1, type="fact",
        title="Three rails per span on this project",
        scope=scope,
        actions=[SetParam(param="rails_per_span", value=3)],
    )


def test_project_scoped_rule_fires_for_its_own_project(knowledge, catalog):
    knowledge.versions.append(_rails_rule({"project_id": "p1"}))
    result = generate(straight_topology(6000), knowledge, catalog, project_id="p1")
    assert {s.rail_count for s in result.strategy.spans} == {3}


def test_project_scoped_rule_stays_inert_on_another_project(knowledge, catalog):
    knowledge.versions.append(_rails_rule({"project_id": "p1"}))
    result = generate(straight_topology(6000), knowledge, catalog, project_id="p2")
    assert {s.rail_count for s in result.strategy.spans} == {2}  # demo K-RAILS


def test_surface_scoped_rule_beats_the_general_rule_at_equal_authority(knowledge, catalog):
    """`surface` binds from the base under the post; the demo default-post rule is
    the same tier (fact), so the win is specificity and nothing else."""
    knowledge.versions.append(
        KnowledgeVersion(
            object_id="K-POST-CONCRETE", version=1, type="fact",
            title="Concrete bases take the heavy-duty post",
            scope={"surface": "concrete"},
            actions=[DefaultComponent(role="post_ground", sku="POST-S-HD")],
        )
    )
    on_soil = generate(straight_topology(6000), knowledge, catalog, project_id="p1")
    assert {p.sku for p in on_soil.strategy.posts} == {"POST-S"}

    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "ev_base", 0, 6000, BasePayload(surface="concrete"))
    on_concrete = generate(topo, knowledge, catalog, project_id="p1")
    assert {p.sku for p in on_concrete.strategy.posts} == {"POST-S-HD"}


def _gated_topology():
    topo = straight_topology(6000)
    add_point_event(topo, "run1", "ev_gate", 2000, GatePayload(width_mm=1000,
                                                              kit_sku="GATE-KIT-1000"))
    return topo


def test_context_scoped_rule_discriminates_on_the_bound_context(knowledge, catalog):
    """The gate-reinforcement slot resolves in context "gate": a rule scoped to it
    wins on specificity, a rule scoped to any other context never fires."""
    gate_scoped = KnowledgeVersion(
        object_id="K-GATE-ALT", version=1, type="company_rule",
        title="Gate posts are wall brackets here",
        scope={"context": "gate"},
        actions=[RequirePostReinforcement(context="gate", sku="POST-M")],
    )
    kb_hit = KnowledgeBase(versions=knowledge.versions + [gate_scoped])
    hit = generate(_gated_topology(), kb_hit, catalog, project_id="p1")
    assert {p.sku for p in hit.strategy.posts if p.kind == "gate"} == {"POST-M"}

    elsewhere = gate_scoped.model_copy(
        update={"object_id": "K-GATE-OTHER", "scope": {"context": "line"}}
    )
    kb_miss = KnowledgeBase(versions=knowledge.versions + [elsewhere])
    miss = generate(_gated_topology(), kb_miss, catalog, project_id="p1")
    assert {p.sku for p in miss.strategy.posts if p.kind == "gate"} == {"POST-S-HD"}


def test_restricted_approval_produces_a_rule_that_actually_fires(catalog):
    """`learning/review.apply_review` scope-restriction ("אישור בתחולה מצומצמת") is
    only meaningful if the added dimension is bound at generation time."""
    candidate = KnowledgeVersion(
        object_id="K-CAND-1", version=1, type="candidate", status="proposed",
        title="Heavy-duty ground posts (candidate)",
        scope={"project_id": "p1"},
        actions=[DefaultComponent(role="post_ground", sku="POST-S-HD")],
    )
    approved = apply_review(
        candidate,
        ReviewAction(action="scope_restrict", reviewer="expert",
                     edited_scope={"project_id": "p1", "surface": "soil"}),
    )
    assert approved.status == "active" and approved.specificity() == 2

    kb = KnowledgeBase(versions=[
        KnowledgeVersion(object_id="K-MAXSPAN", version=1, type="hard_constraint",
                         title="Max span", actions=[SetParam(param="max_span_mm", value=1800)]),
        KnowledgeVersion(object_id="K-POST-BASE", version=1, type="heuristic",
                         title="Default ground post",
                         actions=[DefaultComponent(role="post_ground", sku="POST-S")]),
        approved,
    ])
    inside = generate(straight_topology(6000), kb, catalog, project_id="p1")
    assert {p.sku for p in inside.strategy.posts} == {"POST-S-HD"}

    outside = generate(straight_topology(6000), kb, catalog, project_id="p2")
    assert {p.sku for p in outside.strategy.posts} == {"POST-S"}


def test_impact_preview_scopes_each_case_to_its_own_project(knowledge, catalog):
    """The preview regenerates each case; a project-scoped rule must affect exactly
    the project it is scoped to, or the preview lies about what approval will do."""
    from fenceai.learning.impact import ImpactCase, preview_impact

    report = preview_impact(
        _rails_rule({"project_id": "p1"}),
        knowledge, catalog,
        [ImpactCase(project_id="p1", topology=straight_topology(6000)),
         ImpactCase(project_id="p2", topology=straight_topology(6000))],
    )
    affected = {i.project_id for i in report.impacts if i.changed}
    assert affected == {"p1"}
