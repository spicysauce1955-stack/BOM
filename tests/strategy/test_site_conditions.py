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
from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _exposure_rule(category: str, max_span: int) -> KnowledgeVersion:
    """A span limit that applies only on a given exposure category."""
    return KnowledgeVersion(
        object_id=f"K-EXPOSURE-{category}", version=1, type="hard_constraint",
        authority=0,  # beats the unconditioned demo maximum
        title=f"max span {max_span} on exposure {category}",
        condition=Cmp(cmp="==", left=FieldRef(path="site.exposure_category"),
                      right=Lit(value=category)),
        actions=[SetParam(param="max_span_mm", value=max_span)],
    )


def _kb() -> KnowledgeBase:
    kb = demo_knowledge()
    kb.versions += [_exposure_rule("B", 1800), _exposure_rule("C", 1200)]
    return kb


# -- the binding ---------------------------------------------------------------

def test_one_rule_on_exposure_yields_two_span_limits_on_two_sites():
    """The acceptance criterion. Same fence, same rules, different site."""
    topo, kb, catalog = straight_topology(6000), _kb(), demo_catalog()

    b = generate(topo, kb, catalog, site=SiteConditions(exposure_category="B"))
    c = generate(topo, kb, catalog, site=SiteConditions(exposure_category="C"))

    assert [s.width_mm for s in b.strategy.spans] == [1500, 1500, 1500, 1500]
    assert [s.width_mm for s in c.strategy.spans] == [1200] * 5
    # ...and they are genuinely different fences, not the same one relabelled
    assert len(c.strategy.posts) > len(b.strategy.posts)


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
    topo, kb, catalog = straight_topology(6000), _kb(), demo_catalog()
    site = SiteConditions(exposure_category="C")
    a = generate(topo, kb, catalog, site=site)
    b = generate(topo, kb, catalog, site=site)
    assert a.strategy.model_dump() == b.strategy.model_dump()
    assert a.run.id == b.run.id


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
