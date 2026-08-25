"""Site conditions — the prerequisite for anything conditional.

`docs/superpowers/specs/2026-08-23-bom-engine-design.md` §2. Until a project can
say what kind of site it is, `exposure_category` is not expressible at any layer,
so every `ParameterTable` the Knowledge Platform publishes would arrive with
nothing to match against.

The acceptance criterion that design names is the second test here: **one rule on
exposure yields two span limits on two sites.**
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _exposure_rule(category: str, max_span: int) -> KnowledgeVersion:
    """A span limit that applies only on a given exposure category.

    NO `authority=` override, deliberately. It used to carry `authority=0` with
    the comment "beats the unconditioned demo maximum", and that comment was the
    bug: `specificity()` counted only bound scope dimensions, so a conditioned
    rule did not outrank an unconditioned one, they tied inside the hard band,
    and the tie was a `GenerationFailure`. The demonstration needed hand-tuned
    precedence that no real author would know to apply. Conditions count toward
    specificity now, so this is the plain authoring act it should always have
    been.
    """
    return KnowledgeVersion(
        object_id=f"K-EXPOSURE-{category}", version=1, type="hard_constraint",
        title=f"max span {max_span} on exposure {category}",
        condition=Cmp(cmp="==", left=FieldRef(path="site.exposure_category"),
                      right=Lit(value=category)),
        actions=[SetParam(param="max_span_mm", value=max_span)],
    )


def _kb() -> KnowledgeBase:
    kb = demo_knowledge()
    # 2000 and 1200, and NEITHER is 1800 — the value the unconditioned demo rule
    # already sets. The B arm used to be 1800, which made it indistinguishable
    # from "no site at all": deleting the B rule entirely left every assertion in
    # the headline test passing, so "two span limits on two sites" was really
    # testing one.
    kb.versions += [_exposure_rule("B", 2000), _exposure_rule("C", 1200)]
    return kb


# -- the binding ---------------------------------------------------------------

def test_one_rule_on_exposure_yields_two_span_limits_on_two_sites():
    """The acceptance criterion. Same fence, same rules, different site."""
    topo, kb, catalog = straight_topology(6000), _kb(), demo_catalog()

    b = generate(topo, kb, catalog, site=SiteConditions(exposure_category="B"))
    c = generate(topo, kb, catalog, site=SiteConditions(exposure_category="C"))

    # three distinct answers from one knowledge base: B, C, and the
    # unconditioned baseline (4 x 1500, asserted below in the `site=None` test).
    # If any two of the three coincided, this test could pass against an engine
    # that only ever matched one of them.
    assert [s.width_mm for s in b.strategy.spans] == [2000, 2000, 2000]
    assert [s.width_mm for s in c.strategy.spans] == [1200] * 5
    assert len(c.strategy.posts) > len(b.strategy.posts)

    # ...and each cites ITS OWN rule, so the difference is explainable and not a
    # coincidence of arithmetic
    for result, ref in ((b, "K-EXPOSURE-B@v1"), (c, "K-EXPOSURE-C@v1")):
        node = next(n for n in result.graph.nodes if n.action == "resolve_max_span")
        assert ref in {e.knowledge_ref for e in result.graph.in_edges(node.id)
                       if e.type == "governed_by"}


def test_the_governing_rule_is_cited_in_the_decision_graph():
    result = generate(straight_topology(6000), _kb(), demo_catalog(),
                      site=SiteConditions(exposure_category="C"))
    node = next(n for n in result.graph.nodes if n.action == "resolve_max_span")
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id)
            if e.type == "governed_by"}
    assert "K-EXPOSURE-C@v1" in refs


def test_an_unset_dimension_makes_the_rule_not_applicable_not_an_error():
    """`evaluator` already treats a missing context field as NOT APPLICABLE, which
    is the hook this design leans on rather than an error path to build."""
    result = generate(straight_topology(6000), _kb(), demo_catalog(), site=None)

    # neither exposure rule fired; the unconditioned demo maximum did
    assert [s.width_mm for s in result.strategy.spans] == [1500, 1500, 1500, 1500]
    node = next(n for n in result.graph.nodes if n.action == "resolve_max_span")
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id)
            if e.type == "governed_by"}
    assert refs == {"K-MAXSPAN@v1"}


def test_site_facts_reach_a_post_scoped_rule_too():
    """`site.*` is bound in EVERY evaluation context, not only the span one — a
    site fact that reached the bays and not the posts beside them would be a
    fence built to two different sites."""
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-FROST", version=1, type="hard_constraint",
        title="deep footings where it freezes",
        condition=Cmp(cmp=">=", left=FieldRef(path="site.frost_depth_mm"),
                      right=Lit(value=1000)),
        actions=[SetParam(param="post_embed_mm", value=1200)],
    ))
    result = generate(straight_topology(6000), kb, demo_catalog(),
                      site=SiteConditions(frost_depth_mm=1200))
    assert all(p.embed_mm == 1200 for p in result.strategy.posts)


# -- the warning for a dimension nobody filled in ------------------------------

def test_a_rule_that_needs_an_unset_dimension_is_reported():
    """Silence here is the failure mode: the rule simply does not fire, the fence
    is built to the unconditioned default, and nothing tells the estimator that
    the one fact deciding it was never entered."""
    result = generate(straight_topology(6000), _kb(), demo_catalog(), site=None)

    warned = [w for w in result.strategy.warnings if w.code == "site_condition_missing"]
    assert len(warned) == 1
    assert warned[0].params["dimensions"] == "exposure_category"
    assert warned[0].params["n"] == 1


def test_a_filled_dimension_is_not_reported():
    result = generate(straight_topology(6000), _kb(), demo_catalog(),
                      site=SiteConditions(exposure_category="C"))
    assert not [w for w in result.strategy.warnings if w.code == "site_condition_missing"]


def test_every_missing_dimension_is_named_once():
    """Aggregated, like every other systemic gap: a reader has a list of fields to
    go and fill, not one warning per rule that wanted one."""
    kb = _kb()
    kb.versions.append(KnowledgeVersion(
        object_id="K-HVHZ", version=1, type="company_rule",
        title="high-velocity hurricane zone",
        condition=Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=True)),
        actions=[SetParam(param="max_span_mm", value=900)],
    ))
    result = generate(straight_topology(6000), kb, demo_catalog(), site=None)
    warned = next(w for w in result.strategy.warnings
                  if w.code == "site_condition_missing")
    assert warned.params["dimensions"] == "exposure_category, hvhz"
    assert warned.params["n"] == 2


# -- the run stamps what it was generated against ------------------------------

def test_the_run_stamps_the_site_revision():
    site = SiteConditions(exposure_category="C", revision=7)
    result = generate(straight_topology(6000), _kb(), demo_catalog(), site=site)
    assert result.run.site_revision == 7


def test_a_run_generated_without_site_conditions_reads_as_revision_zero():
    """The readable-old-runs convention: every run stored before this field
    existed was generated against no site conditions, and 0 is that fact."""
    result = generate(straight_topology(6000), demo_knowledge(), demo_catalog())
    assert result.run.site_revision == 0


def test_site_conditions_change_the_run_identity():
    """Two runs of the same fence under different sites are different fences, so
    they must not share an id — `save_run` is INSERT OR IGNORE, and a shared id
    serves the first run's document for the second for ever."""
    topo, kb, catalog = straight_topology(6000), _kb(), demo_catalog()
    b = generate(topo, kb, catalog, site=SiteConditions(exposure_category="B"))
    c = generate(topo, kb, catalog, site=SiteConditions(exposure_category="C"))
    assert b.run.id != c.run.id


def test_generation_is_still_deterministic_under_site_conditions():
    """Two EQUAL-but-distinct SiteConditions, not one object passed twice —
    otherwise this proves object identity rather than value equality. The graph
    is compared too: the scenario suite's determinism check does, and a run whose
    explanation varied while its fence did not would still be non-deterministic."""
    topo, kb, catalog = straight_topology(6000), _kb(), demo_catalog()
    a = generate(topo, kb, catalog, site=SiteConditions(exposure_category="C"))
    b = generate(topo, kb, catalog, site=SiteConditions(exposure_category="C"))
    assert a.strategy.model_dump() == b.strategy.model_dump()
    assert a.graph.model_dump() == b.graph.model_dump()
    assert a.run.id == b.run.id


def test_the_run_id_does_not_move_when_only_the_revision_counter_does():
    """The CONVERSE of the identity test, and the whole reason the digest hashes
    facts rather than the counter.

    Without it, re-saving identical site conditions minted a new run id — or
    worse, kept the id and desynchronised the guard, which is exactly the defect
    that made a no-op save brick every derived view of a run permanently.
    """
    topo, kb, catalog = straight_topology(6000), _kb(), demo_catalog()
    a = generate(topo, kb, catalog, site=SiteConditions(exposure_category="C", revision=1))
    b = generate(topo, kb, catalog, site=SiteConditions(exposure_category="C", revision=9))

    assert a.run.id == b.run.id              # same fence, same site, a form re-saved
    assert a.run.site_revision != b.run.site_revision   # ...and it is still reported
    assert a.run.site_facts == b.run.site_facts == {"exposure_category": "C"}


def test_the_revision_counter_never_leaks_into_the_rule_namespace():
    """`facts()` drops `revision`. If it did not, `site.revision` would become a
    conditionable dimension AND enter the digest — the same failure by a second
    door, and one no rule author could ever mean."""
    assert "revision" not in SiteConditions(exposure_category="C", revision=4).facts()


def test_a_dimension_set_to_a_falsy_value_is_answered_not_unset():
    """`False`, `0` and `""` are where "omitted" and "falsy" diverge, and the
    whole design rests on that distinction: a site that is NOT in a hurricane
    zone has answered the question."""
    site = SiteConditions(hvhz=False, frost_depth_mm=0)
    assert site.facts() == {"hvhz": False, "frost_depth_mm": 0}

    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-NO-HVHZ", version=1, type="company_rule", authority=1,
        title="ordinary zone",
        condition=Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=False)),
        actions=[SetParam(param="max_span_mm", value=2000)]))

    result = generate(straight_topology(6000), kb, demo_catalog(), site=site)
    assert [s.width_mm for s in result.strategy.spans] == [2000, 2000, 2000]
    # ...and answering False is ANSWERING: nothing is reported missing
    assert not [w for w in result.strategy.warnings if w.code == "site_condition_missing"]


def test_a_candidate_rule_does_not_ask_for_a_site_condition():
    """Candidates are inert until approved (golden scenarios). A proposed rule
    must not make the run nag for a dimension no approved rule wants."""
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-CAND", version=1, type="candidate", status="active",
        title="proposed", condition=Cmp(cmp="==", left=FieldRef(path="site.hvhz"),
                                        right=Lit(value=True)),
        actions=[SetParam(param="max_span_mm", value=900)]))
    result = generate(straight_topology(6000), kb, demo_catalog(), site=None)
    assert not [w for w in result.strategy.warnings if w.code == "site_condition_missing"]


def test_a_retired_rule_does_not_ask_for_a_site_condition():
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-OLD", version=1, type="company_rule", status="retired",
        title="withdrawn", condition=Cmp(cmp="==", left=FieldRef(path="site.hvhz"),
                                         right=Lit(value=True)),
        actions=[SetParam(param="max_span_mm", value=900)]))
    result = generate(straight_topology(6000), kb, demo_catalog(), site=None)
    assert not [w for w in result.strategy.warnings if w.code == "site_condition_missing"]


def test_a_rule_wanting_two_dimensions_reports_only_the_unanswered_one():
    """The case where a partial-answer bug would be most invisible: a rule that
    fired on half its condition."""
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-BOTH", version=1, type="company_rule", authority=1,
        title="exposure C in a hurricane zone",
        condition=And(items=[
            Cmp(cmp="==", left=FieldRef(path="site.exposure_category"), right=Lit(value="C")),
            Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=True)),
        ]),
        actions=[SetParam(param="max_span_mm", value=900)]))

    result = generate(straight_topology(6000), kb, demo_catalog(),
                      site=SiteConditions(exposure_category="C"))
    # half-answered is NOT applicable — the fence is built to the demo maximum
    assert [s.width_mm for s in result.strategy.spans] == [1500, 1500, 1500, 1500]
    warned = next(w for w in result.strategy.warnings if w.code == "site_condition_missing")
    assert warned.params["dimensions"] == "hvhz"  # only the one nobody answered


def test_generate_does_not_mutate_the_site_conditions_it_was_given():
    """`generate()` is pure (ADR-0004) and may not touch its inputs."""
    site = SiteConditions(exposure_category="C", revision=3)
    before = site.model_dump()
    generate(straight_topology(6000), _kb(), demo_catalog(), site=site)
    assert site.model_dump() == before


# -- what belongs here, and what does not --------------------------------------

def test_the_standards_regime_is_not_a_site_condition():
    """`us_astm` vs `cn_gb` is the frame the whole rule set is written in, not a
    dimension to select between: a condition key would let a GB row and an ASTM
    row sit in one table and be chosen between, which is the silent wrong answer
    the contract's §1.2 regime guard exists to refuse."""
    assert "regime" not in SiteConditions.model_fields
    assert "standards_regime" not in SiteConditions.model_fields


def test_soil_class_is_not_here_either():
    """It varies ALONG a run, so it is an interval payload in the topology — the
    pattern `ElevationSamplePayload` and `PostTiltPayload` already establish."""
    assert "soil_class" not in SiteConditions.model_fields


@pytest.mark.parametrize("lang", ["en", "he"])
def test_the_missing_condition_node_renders_in_both_languages(lang):
    """A new decision-node action needs an entry in BOTH template tables, and the
    suite's existing coverage cannot see this one: `demo_knowledge()` mentions no
    site dimension, so the node never appears in the graph it walks."""
    from fenceai.decisions.explain import explain_node

    result = generate(straight_topology(6000), _kb(), demo_catalog(), site=None)
    node = next(n for n in result.graph.nodes if n.action == "site_condition_missing")
    line = explain_node(result.graph, node, lang=lang)
    assert line and "{" not in line and "None" not in line
    assert "exposure_category" in line


# -- one test per BINDING SITE, because prose is not coverage -------------------
#
# The commit and the design doc both claim `site.*` reaches EVERY evaluation
# context. A review mutated `"site": site` to `"site": {}` at each of the six
# contexts in turn: four mutations left all 1676 tests green. The claim was
# verified at two sites and asserted in prose at three. Each test below fails
# when its own binding site is broken.

def _site_rule(object_id: str, action, category: str = "C") -> KnowledgeVersion:
    return KnowledgeVersion(
        object_id=object_id, version=1, type="company_rule",
        title=f"{object_id} on exposure {category}",
        condition=Cmp(cmp="==", left=FieldRef(path="site.exposure_category"),
                      right=Lit(value=category)),
        actions=[action],
    )


def test_site_reaches_the_default_post_product(_post_ctx_binding=None):
    """`_post_ctx` — feeds FOUR resolvers, and was covered by none."""
    from fenceai.knowledge.model import DefaultComponent

    kb = demo_knowledge()
    kb.versions.append(_site_rule(
        "K-SITE-POST", DefaultComponent(role="post_ground", sku="POST-S-HD")))
    kb.versions[-1].authority = 1  # beat the demo default (a fact at tier 3)

    on = generate(straight_topology(6000), kb, demo_catalog(),
                  site=SiteConditions(exposure_category="C"))
    off = generate(straight_topology(6000), kb, demo_catalog(),
                   site=SiteConditions(exposure_category="B"))
    assert {p.sku for p in on.strategy.posts} == {"POST-S-HD"}
    assert {p.sku for p in off.strategy.posts} == {"POST-S"}


def test_site_reaches_the_demand_products():
    """`_post_ctx` again, through `_resolve_demand_skus` — a different role."""
    from fenceai.knowledge.model import DefaultComponent

    kb = demo_knowledge()
    kb.versions.append(_site_rule(
        "K-SITE-RAIL", DefaultComponent(role="rail", sku="RAIL-V-3600")))
    kb.versions[-1].authority = 1

    on = generate(straight_topology(6000), kb, demo_catalog(),
                  site=SiteConditions(exposure_category="C"))
    off = generate(straight_topology(6000), kb, demo_catalog(),
                   site=SiteConditions(exposure_category="B"))
    assert on.run.demand_skus["rail_sku"] == "RAIL-V-3600"
    assert off.run.demand_skus["rail_sku"] != "RAIL-V-3600"


def test_site_reaches_the_gate_reinforcement_rule():
    """`_post_ctx` with a gate context — the case this feature most exists for,
    and doubly uncovered before: the binding site had no test and neither did
    the gate path through it."""
    from fenceai.knowledge.model import RequirePostReinforcement
    from fenceai.topology.model import GatePayload
    from tests.conftest import add_point_event

    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-GATE-REINF"]
    kb.versions.append(_site_rule(
        "K-SITE-GATE", RequirePostReinforcement(context="gate", sku="POST-S-HD")))

    def run(category):
        topo = straight_topology(5000)
        add_point_event(topo, "run1", "g", 2000,
                        GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
        return generate(topo, kb, demo_catalog(),
                        site=SiteConditions(exposure_category=category))

    assert any(p.reinforced for p in run("C").strategy.posts)
    assert not any(p.reinforced for p in run("B").strategy.posts)


def test_site_reaches_the_mounting_rule():
    """`_post_ctx` with a masonry base — the third resolver behind that one
    context."""
    from fenceai.knowledge.model import RequireMounting
    from fenceai.topology.model import BasePayload
    from tests.conftest import add_interval_event

    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MASONRY"]
    kb.versions.append(_site_rule(
        "K-SITE-MOUNT",
        RequireMounting(surface="masonry_wall", mounting="masonry", sku="POST-M")))

    def run(category):
        topo = straight_topology(7000)
        add_interval_event(topo, "run1", "base", 4000, 7000,
                           BasePayload(surface="masonry_wall"))
        return generate(topo, kb, demo_catalog(),
                        site=SiteConditions(exposure_category=category))

    assert any(p.mounting == "masonry" for p in run("C").strategy.posts)
    assert not any(p.mounting == "masonry" for p in run("B").strategy.posts)


def test_site_reaches_the_vertical_mode_preference():
    """The vertical-mode context. A site-conditioned choice between level,
    stepped and raked stopped applying silently when this binding broke."""
    from fenceai.knowledge.model import PreferVertical
    from fenceai.topology.model import ElevationSamplePayload
    from tests.conftest import add_point_event

    kb = demo_knowledge()
    kb.versions.append(_site_rule("K-SITE-VERT", PreferVertical(mode="raked", weight=99)))
    kb.versions[-1].authority = 1

    def run(category):
        topo = straight_topology(6000)
        add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
        add_point_event(topo, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))
        return generate(topo, kb, demo_catalog(),
                        site=SiteConditions(exposure_category=category))

    assert {s.vertical for s in run("C").strategy.spans} == {"raked"}
    assert "raked" not in {s.vertical for s in run("B").strategy.spans}


def test_site_reaches_the_panel_safety_limits():
    """The panel-safety context — where a site-conditioned HARD limit was being
    dropped in silence, which is the golden-scenarios invariant "hard constraints
    are never silently overridden".

    Built to M-SLAT, not the compatibility model: `clear_gap_exceeded` measures
    the openings between INFILL members, and M-LEGACY has none — so against it
    this check has nothing to measure and the test could never fail for the right
    reason."""
    from fenceai.fencemodel.demo import demo_models
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.fencemodel.selection import FenceModelChoice
    from fenceai.parts.demo import demo_parts
    from fenceai.parts.model import PartLibrary

    kb = demo_knowledge()
    rule = _site_rule("K-SITE-GAP", SetParam(param="max_clear_gap_mm", value=1))
    rule.authority = 1
    kb.versions.append(rule)
    kw = dict(models=FenceModelLibrary(models=list(demo_models().values())),
              parts=PartLibrary(parts=demo_parts()),
              default_model=FenceModelChoice(model_id="M-SLAT"))

    on = generate(straight_topology(6000), kb, demo_catalog(),
                  site=SiteConditions(exposure_category="C"), **kw)
    off = generate(straight_topology(6000), kb, demo_catalog(),
                   site=SiteConditions(exposure_category="B"), **kw)
    assert [w.code for w in on.strategy.warnings if w.code == "clear_gap_exceeded"]
    assert not [w.code for w in off.strategy.warnings if w.code == "clear_gap_exceeded"]


def test_a_rule_that_could_never_apply_here_does_not_nag():
    """A rule scoped to another project, or to a product line this fence is not
    built from, cannot fire — so asking the estimator to fill in the dimension it
    wants is an item they cannot clear. Entering a value changes nothing."""
    kb = demo_knowledge()
    for object_id, scope in (("K-OTHER-PROJECT", {"project_id": "someone-else"}),
                             ("K-OTHER-SERIES", {"series": "M-DOES-NOT-EXIST"})):
        kb.versions.append(KnowledgeVersion(
            object_id=object_id, version=1, type="company_rule", scope=scope,
            title="unreachable here",
            condition=Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=True)),
            actions=[SetParam(param="max_span_mm", value=900)]))

    result = generate(straight_topology(6000), kb, demo_catalog(),
                      site=None, project_id="mine")
    assert not [w for w in result.strategy.warnings if w.code == "site_condition_missing"]


def test_an_unevaluable_HARD_constraint_is_an_error_not_a_note():
    """"Hard constraint is not preference" is a foundation rule, and it should
    reach the report rather than stopping at the resolver: a safety limit that
    could not be evaluated is a different event from a preference not firing."""
    def run(rule_type):
        kb = demo_knowledge()
        kb.versions.append(KnowledgeVersion(
            object_id="K-WANTS", version=1, type=rule_type, title="wants a site fact",
            condition=Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=True)),
            actions=[SetParam(param="max_span_mm", value=900)]))
        result = generate(straight_topology(6000), kb, demo_catalog(), site=None)
        return next(w for w in result.strategy.warnings
                    if w.code == "site_condition_missing")

    assert run("hard_constraint").severity == "error"
    assert run("preference").severity == "warning"
