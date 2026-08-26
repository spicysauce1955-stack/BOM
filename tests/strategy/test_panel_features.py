"""The model features W3 turns on, as a run actually experiences them.

Each of these was a named refusal in `_unsupported_features` until the resolver
honoured it. The unit-level rules live in `tests/fencemodel/`; what is pinned
here is the wiring — that a variant condition is evaluated per bay, that an
option value reaches the eligibility of the slot it governs, that an unsupported
height is reported once per section, and that a model's layout policy enters the
same evaluator as everything else and can lose there.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.decisions.explain import explain_node
from fenceai.demand.derive import derive_requirements
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Axis, Continuous, Discrete, Distributed, Eligibility, EligibleItem, FenceModel,
    FrameSlot, OptionValue, PanelSpec, PartRequirement, PolicyContribution, Variant,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeVersion, SetParam
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    ElevationSamplePayload, FenceModelPayload, HeightIntentPayload, TopLinePayload,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology

MODEL_ID = "M-TEST"


def _rail_req(sku: str = "RAIL-3000", **kw) -> PartRequirement:
    return PartRequirement(
        role="rail", qty=1, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku=sku, priority=1)]),
        **kw,
    )


def _spec(count: int, requirement: PartRequirement | None = None,
          count_param: str | None = None) -> PanelSpec:
    """One rail slot. `count_param` is left OFF by default so a spec's rail count
    identifies the spec: these tests distinguish two variants by counting rails,
    and a knowledge-owned count would give both the same answer."""
    return PanelSpec(frame=[FrameSlot(
        key="rail", orientation="horizontal",
        placement=Distributed(count=count, count_param=count_param),
        requirement=requirement or _rail_req(),
    )])


def _model(**kw) -> FenceModel:
    return FenceModel(id=MODEL_ID, version=1, name_i18n={"en": "Test"},
                      default_spec=kw.pop("default_spec", _spec(2)), **kw)


def _generate(model: FenceModel, topo=None, kb=None, options=None, site=None):
    return generate(
        topo if topo is not None else straight_topology(3000),
        kb if kb is not None else demo_knowledge(),
        demo_catalog(),
        models=FenceModelLibrary(models=[model]),
        default_model=FenceModelChoice(model_id=MODEL_ID, options=options or {}),
        site=site,
    )


def _rail_qty(span) -> int:
    return next(s.qty for s in span.panel.slots if s.role == "rail")


# --- 1 · variants -------------------------------------------------------------

SHORT = Cmp(cmp="<", left=FieldRef(path="panel.height_mm"), right=Lit(value=1200))
LEVEL = Cmp(cmp="==", left=FieldRef(path="panel.vertical"), right=Lit(value="level"))
MISSING = Cmp(cmp="==", left=FieldRef(path="panel.colour"), right=Lit(value="black"))


def _height(topo, height_mm: int) -> None:
    add_interval_event(topo, "run1", "ev_h", 0, 3000,
                       HeightIntentPayload(height_mm=height_mm))


def _level_top_over_a_slope(length_mm: int = 6000, rise_mm: int = 2000,
                            top_z_mm: int = 2400):
    """S06's shape: the top line is pinned to one elevation while the ground
    climbs, so every bay has a different panel height."""
    topo = straight_topology(length_mm)
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", length_mm, ElevationSamplePayload(z_mm=rise_mm))
    add_interval_event(topo, "run1", "ev_top", 0, length_mm,
                       TopLinePayload(mode="level", z_mm=top_z_mm))
    return topo


def test_a_variant_condition_is_evaluated_per_bay_and_builds_its_own_spec():
    model = _model(variants=[Variant(condition=SHORT, spec=_spec(5))])
    topo = straight_topology(3000)
    _height(topo, 1000)
    result = _generate(model, topo)
    assert result.strategy.spans
    for span in result.strategy.spans:
        assert span.panel.variant_index == 0
        assert _rail_qty(span) == 5


def test_a_bay_the_condition_misses_falls_back_to_the_default_spec():
    model = _model(variants=[Variant(condition=SHORT, spec=_spec(5))])
    topo = straight_topology(3000)
    _height(topo, 1800)
    result = _generate(model, topo)
    for span in result.strategy.spans:
        assert span.panel.variant_index is None
        assert _rail_qty(span) == 2


def test_two_bays_of_one_run_can_resolve_to_different_variants():
    """The condition is a property of the BAY, not of the run: a level top over a
    slope gives every bay a different height (S06), and the variant follows it."""
    model = _model(variants=[Variant(condition=SHORT, spec=_spec(5))])
    topo = _level_top_over_a_slope()
    result = _generate(model, topo)
    heights = {s.height_mm for s in result.strategy.spans}
    assert len(heights) > 1, "fixture no longer produces differing bay heights"
    for span in result.strategy.spans:
        expected = 0 if span.height_mm < 1200 else None
        assert span.panel.variant_index == expected


def test_the_select_variant_node_records_the_winner_and_the_conditions_that_failed():
    model = _model(variants=[
        Variant(condition=MISSING, spec=_spec(9)),
        Variant(condition=SHORT, spec=_spec(5)),
        Variant(condition=LEVEL, spec=_spec(7)),
    ])
    topo = straight_topology(3000)
    _height(topo, 1000)
    result = _generate(model, topo)
    nodes = [n for n in result.graph.nodes if n.action == "select_variant"]
    assert len(nodes) == len(result.strategy.spans)
    payload = nodes[0].payload
    assert payload["variant_index"] == 1
    assert payload["failed"] == [0]
    # authored order, first satisfied wins: variant 2 was never asked, and the
    # graph must not claim its condition failed
    assert payload["not_reached"] == [2]


def test_a_variant_is_product_structure_and_carries_no_defeated_edge():
    """Deliberate, and the reason it is asserted: a variant is evaluated OUTSIDE
    the knowledge evaluator, so there is no losing knowledge version to cite.
    Someone will look for the edge; this says it was never going to exist."""
    model = _model(variants=[
        Variant(condition=SHORT, spec=_spec(5)),
        Variant(condition=LEVEL, spec=_spec(7)),
    ])
    topo = straight_topology(3000)
    _height(topo, 1000)
    result = _generate(model, topo)
    node = next(n for n in result.graph.nodes if n.action == "select_variant")
    edges = result.graph.in_edges(node.id)
    assert edges, "the node must still be anchored to what produced it"
    assert not [e for e in edges if e.type in ("defeated", "governed_by")]


def test_a_model_without_variants_emits_no_variant_node():
    """The graph is the explanation: a node per bay describing a choice with one
    candidate would be noise in every run that exists today."""
    result = _generate(_model())
    assert not [n for n in result.graph.nodes if n.action == "select_variant"]


# --- 1b · variants conditioned on the SITE ------------------------------------
#
# `site.*` was bound into every KNOWLEDGE evaluation context and into no fence-
# model one, so a variant conditioned on the site came back `MissingField`,
# read as "not applicable", and fell through to the default spec with nothing
# said. These pin the binding and the two ways it is allowed to be silent.

HVHZ = Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=True))
FROST = Cmp(cmp=">=", left=FieldRef(path="site.frost_depth_mm"),
            right=Lit(value=1000))


def test_a_variant_conditioned_on_the_site_selects():
    """The defect, from the other side. Site conditions exist so that a fence can
    be conditioned on the site; a hurricane-zone variant that could not be
    reached made the whole capability decorative."""
    model = _model(variants=[Variant(condition=HVHZ, spec=_spec(5))])
    result = _generate(model, site=SiteConditions(hvhz=True))
    assert result.strategy.spans
    for span in result.strategy.spans:
        assert span.panel.variant_index == 0
        assert _rail_qty(span) == 5


def test_the_same_model_on_a_site_that_answered_NO_builds_the_default():
    """`False` is an ANSWER, and the run must not warn about it: the estimator
    said this is not a hurricane zone, which is exactly what the condition was
    asked to distinguish."""
    model = _model(variants=[Variant(condition=HVHZ, spec=_spec(5))])
    result = _generate(model, site=SiteConditions(hvhz=False))
    assert result.strategy.spans, "fixture built no bays"
    for span in result.strategy.spans:
        assert span.panel.variant_index is None
        assert _rail_qty(span) == 2
    assert not [w for w in result.strategy.warnings
                if w.code == "site_condition_missing"]


def test_a_site_the_project_never_answered_is_REPORTED_not_silent():
    """The silent fall-through, named. The variant still does not fire — that is
    the `MissingField` behaviour the whole design leans on — but the run now says
    which dimension decided it, through the code that already existed for a
    knowledge rule in exactly this position.

    Kills: binding `site` into the context and leaving the report reading only
    `kb.active()`, which would trade a silent wrong panel for a silent right one
    and leave the estimator no way to learn the fence was decided by a blank
    field.
    """
    model = _model(variants=[Variant(condition=HVHZ, spec=_spec(5))])
    result = _generate(model, site=None)
    assert result.strategy.spans, "fixture built no bays"
    for span in result.strategy.spans:
        assert span.panel.variant_index is None       # not applicable, as designed
    warned = next(w for w in result.strategy.warnings
                  if w.code == "site_condition_missing")
    assert warned.params["dimensions"] == "hvhz"
    assert warned.params["n"] == 1
    # a variant is product structure, not a limit — so this is a warning and not
    # the error a missing HARD constraint dimension raises
    assert warned.severity == "warning"
    # ...and it is anchored in the graph, because the graph is the explanation
    # (foundation §15): a warning with no node is a claim nothing traces to.
    node = next(n for n in result.graph.nodes
                if n.action == "site_condition_missing")
    assert node.kind == "gap"
    assert warned.decision_ref == node.id


def test_a_rule_and_a_variant_wanting_DIFFERENT_dimensions_aggregate_into_one():
    """One warning, both dimensions, and the RULE's severity kept.

    The dimensions differ deliberately. When a rule and a variant want the SAME
    one, every assertion here is already true before the model side exists — so
    that version of the test passed at base and could not tell aggregation from
    its absence. Splitting them is what makes each half observable:

      * `frost_depth_mm` is in the list ONLY because the model asked;
      * `hvhz` is there because the rule did, and it is a hard constraint, so
        the whole warning is an `error` — a hard constraint that could not be
        evaluated is not the same event as a variant that did not fire, and the
        model's want must not dilute it.

    Kills: dropping the `model_wanted` merge in `_report_missing_site_conditions`
    (loses `frost_depth_mm`), and letting the model's want overwrite the rule's
    type with `setdefault` -> plain assignment (downgrades `error` to `warning`).
    """
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-HVHZ", version=1, type="hard_constraint",
        title="hurricane zone spans",
        condition=HVHZ, actions=[SetParam(param="max_span_mm", value=900)]))
    model = _model(variants=[Variant(condition=FROST, spec=_spec(5))])

    result = _generate(model, kb=kb, site=None)
    warned = [w for w in result.strategy.warnings
              if w.code == "site_condition_missing"]
    assert len(warned) == 1, "two askers must not mean two work items"
    assert warned[0].params["dimensions"] == "frost_depth_mm, hvhz"
    assert warned[0].params["n"] == 2
    assert warned[0].severity == "error"      # the rule's claim, not the variant's


def test_a_variant_alone_does_not_promote_the_warning_to_an_error():
    """The other side of that severity rule: with no hard constraint involved, a
    variant that did not fire is a warning. A variant is product structure, so
    its condition losing is a different panel and not a violated limit."""
    model = _model(variants=[Variant(condition=FROST, spec=_spec(5))])
    result = _generate(model, site=None)
    warned = next(w for w in result.strategy.warnings
                  if w.code == "site_condition_missing")
    assert warned.severity == "warning"


def test_a_variant_on_a_dimension_nobody_asked_about_reports_only_its_own():
    """Read off the DOCUMENTS this run drew from, so a model that asks about
    frost depth nags about frost depth and about nothing else."""
    model = _model(variants=[Variant(condition=FROST, spec=_spec(5))])
    result = _generate(model, site=SiteConditions(hvhz=True))
    warned = next(w for w in result.strategy.warnings
                  if w.code == "site_condition_missing")
    assert warned.params["dimensions"] == "frost_depth_mm"


def test_an_eligibility_predicate_may_read_the_site():
    """The second half of the binding. "This rail only where it freezes" is an
    item-against-SITE relation, and without the namespace the predicate came back
    `MissingField`, `_covers` read that as "has not covered the requirement", and
    the slot admitted NOTHING — a panel that silently loses a member rather than
    one that visibly asks for the wrong one.
    """
    covered = And(items=[
        Cmp(cmp="==", left=FieldRef(path="item.sku"), right=Lit(value="RAIL-3000")),
        HVHZ,
    ])
    req = _rail_req()
    req.eligibility = Eligibility(predicate=covered)
    model = _model(default_spec=_spec(2, req))

    on_site = _generate(model, site=SiteConditions(hvhz=True))
    assert on_site.strategy.spans, "fixture built no bays"
    for span in on_site.strategy.spans:
        assert _rail_members(span) == ["RAIL-3000"]

    # ...and where the site answered NO the predicate is simply not satisfied,
    # so the slot has nothing eligible.
    off_site = _generate(model, site=SiteConditions(hvhz=False))
    assert off_site.strategy.spans, "fixture built no bays"
    for span in off_site.strategy.spans:
        assert _rail_members(span) == []


def test_where_an_unsatisfied_predicate_IS_reported_and_where_it_is_not():
    """Written because the test above once claimed "a run that says so" and the
    run said nothing: `result.strategy.warnings` is EMPTY for a bay whose rail
    slot admitted no product.

    That is not a defect this slice introduced — it is where the reporting for an
    unsatisfiable predicate has always lived — but the boundary is worth pinning
    rather than mis-stating, because the two silences look identical from the
    strategy and are not the same thing:

      * the SITE never answered -> `site_condition_missing` on the strategy, and
        that is the silence this whole slice exists to break;
      * the site answered NO -> nothing on the strategy, and `no_eligible_item`
        at the SUPPLY stage, per bay, where a slot's emptiness is priced.

    Kills: a future "tidy-up" that reports the second case on the strategy too,
    which would nag on every correctly-not-applicable bay of every job.
    """
    covered = And(items=[
        Cmp(cmp="==", left=FieldRef(path="item.sku"), right=Lit(value="RAIL-3000")),
        HVHZ,
    ])
    req = _rail_req()
    req.eligibility = Eligibility(predicate=covered)
    model = _model(default_spec=_spec(2, req))

    answered_no = _generate(model, site=SiteConditions(hvhz=False))
    assert [w.code for w in answered_no.strategy.warnings] == []
    # ...and the emptiness surfaces where emptiness is priced
    lines = derive_requirements(answered_no.strategy, demo_catalog(),
                               policy=answered_no.run.demand_skus)
    rails = [line for line in lines if line.role == "rail"]
    assert rails, "the requirement is still derived for the slot"
    assert all(not line.eligibility.members for line in rails)

    # the site NEVER answered: same empty slot, and the run names the field
    never_answered = _generate(model, site=None)
    assert [w.code for w in never_answered.strategy.warnings] == [
        "site_condition_missing"]


def test_the_site_reaches_a_post_at_its_own_station_too():
    """A site fact that reached the bays and not the posts beside them would be a
    fence built to two different sites — the argument the knowledge binding
    already makes, and it holds harder here: the spec a post is MATCHED against
    must be the spec its bay is BUILT to.

    Kills: binding `site` into `PanelContext.condition_ctx` and not into
    `_PostFacts.at`, which would leave a site-conditioned variant picking the
    variant's rails in the bay and the DEFAULT spec's rails at the post.
    """
    tall = _spec(9)
    model = _model(variants=[Variant(condition=HVHZ, spec=tall)])
    result = _generate(model, site=SiteConditions(hvhz=True))
    node = next(n for n in result.graph.nodes if n.action == "select_variant")
    assert node.payload["variant_index"] == 0
    for span in result.strategy.spans:
        assert _rail_qty(span) == 9


# --- 2 · option axes ----------------------------------------------------------

FINISH = Axis(key="frame_finish", kind="enum", values=[
    OptionValue(key="black", label_i18n={"en": "Black"}, swatch="#101010"),
    OptionValue(key="grey", label_i18n={"en": "Grey"}, swatch="#9a9a9a"),
])


def _two_member_model() -> FenceModel:
    """One slot, two eligible rails, and an axis that names one of them per
    option value. RAIL-ALT is added to the catalog by `_catalog_with_alt`."""
    req = _rail_req(option_axis="frame_finish",
                    sku_by_option={"black": "RAIL-3000", "grey": "RAIL-ALT"})
    req.eligibility = Eligibility(members=[
        EligibleItem(sku="RAIL-3000", priority=1),
        EligibleItem(sku="RAIL-ALT", priority=2),
    ])
    return _model(default_spec=_spec(2, req), option_axes=[FINISH])


def _catalog_with_alt():
    catalog = demo_catalog()
    catalog.products["RAIL-ALT"] = catalog.products["RAIL-3000"].model_copy(
        update={"sku": "RAIL-ALT"})
    return catalog


def _generate_with_alt(model: FenceModel, options: dict):
    return generate(
        straight_topology(3000), demo_knowledge(), _catalog_with_alt(),
        models=FenceModelLibrary(models=[model]),
        default_model=FenceModelChoice(model_id=MODEL_ID, options=options),
    )


def _rail_members(span) -> list[str]:
    slot = next(s for s in span.panel.slots if s.role == "rail")
    return [m.sku for m in slot.eligibility.members]


def test_an_option_narrows_the_eligibility_set_to_the_member_it_names():
    result = _generate_with_alt(_two_member_model(), {"frame_finish": "grey"})
    assert result.strategy.spans
    for span in result.strategy.spans:
        assert _rail_members(span) == ["RAIL-ALT"]


def test_the_other_option_value_narrows_to_the_other_member():
    result = _generate_with_alt(_two_member_model(), {"frame_finish": "black"})
    for span in result.strategy.spans:
        assert _rail_members(span) == ["RAIL-3000"]


def test_no_option_chosen_leaves_the_whole_eligibility_set_intact():
    """An axis is a question; an unanswered question narrows nothing. Priority
    order and the selection objective then decide, as they do today."""
    result = _generate_with_alt(_two_member_model(), {})
    for span in result.strategy.spans:
        assert _rail_members(span) == ["RAIL-3000", "RAIL-ALT"]


def test_the_chosen_option_reaches_the_bom_and_not_just_the_panel():
    """The point of the feature: pick a colour and the purchased product changes."""
    from fenceai.fulfillment.pipeline import price_strategy

    catalog = _catalog_with_alt()
    result = generate(straight_topology(3000), demo_knowledge(), catalog,
                      models=FenceModelLibrary(models=[_two_member_model()]),
                      default_model=FenceModelChoice(
                          model_id=MODEL_ID, options={"frame_finish": "grey"}))
    priced = price_strategy(result.strategy, catalog,
                            demand_skus=result.run.demand_skus,
                            preset=result.run.objective_preset)
    assert "RAIL-ALT" in {line.sku for line in priced.bom.lines}
    assert "RAIL-3000" not in {line.sku for line in priced.bom.lines}


def test_the_select_product_node_names_the_option_that_governed_the_slot():
    result = _generate_with_alt(_two_member_model(), {"frame_finish": "grey"})
    nodes = [n for n in result.graph.nodes if n.action == "select_product"]
    assert len(nodes) == len(result.strategy.spans)
    payload = nodes[0].payload
    assert payload["slot"] == "rail"
    assert payload["axis"] == "frame_finish"
    assert payload["value"] == "grey"
    assert payload["sku"] == "RAIL-ALT"


def test_a_slot_no_option_governs_emits_no_select_product_node():
    result = _generate_with_alt(_model(), {"frame_finish": "grey"})
    assert not [n for n in result.graph.nodes if n.action == "select_product"]


# --- 3 · height_support -------------------------------------------------------

def _warnings(result, code: str):
    return [w for w in result.strategy.warnings if w.code == code]


def test_a_discrete_ladder_warns_once_per_section_not_once_per_bay():
    """`top_line: level` over a slope gives every bay its own height (S06). One
    warning per bay would be four warnings saying the same thing, and on a real
    fence it would drown every other warning in the list."""
    model = _model(height_support=Discrete(heights_mm=[1800, 2000]))
    result = _generate(model, _level_top_over_a_slope())
    heights = sorted({s.height_mm for s in result.strategy.spans})
    assert len(heights) > 1, "fixture no longer produces differing bay heights"
    warnings = _warnings(result, "height_not_supported")
    assert len(warnings) == 1
    assert warnings[0].params["n"] == len(heights)
    assert warnings[0].params["model_ref"] == f"{MODEL_ID}@v1"
    # every offending height is in the params (pre-joined, as `contenders` and
    # `surfaces` are — a warning param is a `str | int`), and the decision node
    # carries them as the int millimetres they are
    assert warnings[0].params["heights_mm"] == ", ".join(str(h) for h in heights)
    assert warnings[0].params["min_mm"] == heights[0]
    assert warnings[0].params["max_mm"] == heights[-1]
    assert result.graph.node(warnings[0].decision_ref).payload["heights_mm"] == heights


def test_the_warning_points_at_every_bay_it_is_about():
    model = _model(height_support=Discrete(heights_mm=[1800, 2000]))
    result = _generate(model, _level_top_over_a_slope())
    warning = _warnings(result, "height_not_supported")[0]
    assert set(warning.element_refs) == {s.id for s in result.strategy.spans}
    node = result.graph.node(warning.decision_ref)
    assert node.action == "height_not_supported"


def test_a_height_on_the_ladder_does_not_warn():
    model = _model(height_support=Discrete(heights_mm=[1800, 2000]))
    result = _generate(model)  # policy default height, 1800
    assert {s.height_mm for s in result.strategy.spans} == {1800}
    assert not _warnings(result, "height_not_supported")


def test_two_sections_each_report_their_own_heights():
    """Per SECTION means per section: two runs of one topology are two warnings,
    or the second one's heights would ride on the first one's message."""
    from fenceai.topology.model import Node, Run, Topology

    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=3000, y_mm=0),
               Node(id="n3", x_mm=3000, y_mm=3000)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2"),
              Run(id="run2", start_node_id="n2", end_node_id="n3")],
    )
    add_interval_event(topo, "run1", "h1", 0, 3000, HeightIntentPayload(height_mm=1500))
    add_interval_event(topo, "run2", "h2", 0, 3000, HeightIntentPayload(height_mm=1600))
    model = _model(height_support=Discrete(heights_mm=[1800]))
    result = _generate(model, topo)
    warnings = _warnings(result, "height_not_supported")
    assert len(warnings) == 2
    assert sorted(w.params["heights_mm"] for w in warnings) == ["1500", "1600"]
    assert {w.params["run_id"] for w in warnings} == {"run1", "run2"}


def test_a_continuous_band_refuses_a_height_outside_it():
    model = _model(height_support=Continuous(min_mm=1000, max_mm=1500, step_mm=1))
    result = _generate(model)  # 1800, above the band
    assert _warnings(result, "height_not_supported")[0].params["heights_mm"] == "1800"


# --- 4 · layout_policy --------------------------------------------------------

def _series_rule(param: str, value: int, type_: str) -> KnowledgeVersion:
    """A company rule about this model's product line — the thing a model's own
    contribution has to fight, at the specificity that makes it a fair fight."""
    return KnowledgeVersion(
        object_id=f"K-CO-{param}", version=1, type=type_,  # type: ignore[arg-type]
        title=f"company {param} for {MODEL_ID}",
        scope={"series": MODEL_ID},
        actions=[SetParam(param=param, value=value)],
    )


def _policy_model(param: str, value: int, knowledge_type: str) -> FenceModel:
    # the rail slot defers its count to knowledge, as a real model's does: the
    # structure is the model's and the count remains knowledge's, which is the
    # whole reason a contribution has to fight for it
    return _model(
        default_spec=_spec(2, count_param="rails_per_span"),
        layout_policy=[PolicyContribution(
            param=param, value=value,
            knowledge_type=knowledge_type)],  # type: ignore[arg-type]
    )


def test_a_hard_constraint_contribution_beats_a_company_rule():
    """Authority is per CONTRIBUTION: a manufacturer's limit is a hard
    constraint, and one authority for the whole policy would make it beatable."""
    kb = demo_knowledge()
    kb.versions.append(_series_rule("rails_per_span", 3, "company_rule"))
    result = _generate(_policy_model("rails_per_span", 5, "hard_constraint"), kb=kb)
    assert {s.rail_count for s in result.strategy.spans} == {5}
    # and it reaches the PANEL, not only the span's legacy field
    assert {_rail_qty(s) for s in result.strategy.spans} == {5}


def test_a_preference_contribution_loses_to_a_company_rule():
    """The same field, the other authority: a nominal panel width is a
    preference, and a company rule outranks it. Emitting the whole policy at one
    authority would have given one of these two the wrong answer."""
    kb = demo_knowledge()
    kb.versions.append(_series_rule("rails_per_span", 3, "company_rule"))
    result = _generate(_policy_model("rails_per_span", 5, "preference"), kb=kb)
    assert {s.rail_count for s in result.strategy.spans} == {3}


def test_a_contribution_enters_the_evaluator_and_is_cited_by_ref():
    """It is knowledge-shaped, not a private channel: the winning contribution
    governs the node exactly as a knowledge version does, and the loser is a
    `defeated` edge — because this one IS resolved by the evaluator."""
    kb = demo_knowledge()
    kb.versions.append(_series_rule("max_span_mm", 1200, "company_rule"))
    result = _generate(_policy_model("max_span_mm", 1000, "hard_constraint"), kb=kb)
    node = next(n for n in result.graph.nodes if n.action == "resolve_max_span")
    governed = [e.knowledge_ref for e in result.graph.in_edges(node.id)
                if e.type == "governed_by"]
    defeated = [e.knowledge_ref for e in result.graph.in_edges(node.id)
                if e.type == "defeated"]
    assert governed == [f"{MODEL_ID}#max_span_mm@v1"]
    assert "K-CO-max_span_mm@v1" in defeated
    assert max(s.width_mm for s in result.strategy.spans) <= 1000


def test_a_contribution_is_scoped_to_its_own_series():
    """`series=<model_id>`, so a second model on the same run keeps its own
    numbers — a model's policy must not leak past the fence it describes."""
    other = FenceModel(id="M-OTHER", version=1, default_spec=_spec(2))
    topo = straight_topology(5000)
    add_interval_event(topo, "run1", "ev_m", 0, 2500,
                       FenceModelPayload(model_id=MODEL_ID))
    result = generate(
        topo, demo_knowledge(), demo_catalog(),
        models=FenceModelLibrary(models=[
            _policy_model("max_span_mm", 1000, "hard_constraint"), other]),
        default_model=FenceModelChoice(model_id="M-OTHER"),
    )
    left = [s for s in result.strategy.spans if s.end_station_mm <= 2500]
    right = [s for s in result.strategy.spans if s.start_station_mm >= 2500]
    assert left and right
    assert max(s.width_mm for s in left) <= 1000
    assert max(s.width_mm for s in right) > 1000


def test_a_contribution_cannot_reach_a_param_generation_never_resolves_by_series():
    """The refusal that keeps the rest of this honest: `post_embed_mm` is
    resolved once for the whole topology, before any model is chosen, so a
    contribution naming it would be accepted and never seen."""
    from fenceai.core.errors import GenerationFailure
    from fenceai.fencemodel.model import validate_model

    model = _policy_model("post_embed_mm", 900, "hard_constraint")
    errs = validate_model(model, demo_catalog())
    assert any("post_embed_mm" in e and "not yet supported" in e for e in errs)
    with pytest.raises(GenerationFailure) as exc:
        _generate(model)
    assert exc.value.code == "fence_model_invalid"


@pytest.mark.parametrize("param,value", [("max_span_mm", 1000),
                                         ("rails_per_span", 4),
                                         ("screws_per_span", 12)])
def test_every_param_the_table_allows_is_actually_resolved_under_the_model_scope(
        param, value):
    """The allow-list in `fencemodel/model.py` is a claim about the generator.
    This is the claim, checked: contribute each one and watch the fence change."""
    base = _generate(_model())
    changed = _generate(_policy_model(param, value, "hard_constraint"))
    assert base.strategy.model_dump() != changed.strategy.model_dump(), param


def test_editing_a_models_policy_changes_the_run_id():
    """The contributions are never stored as knowledge, so the run's knowledge
    snapshot cannot record them. What makes a policy edit reproducible is the
    model's content hash, which is already in the digest — checked here, because
    that is the only thing standing between an edited policy and `INSERT OR
    IGNORE` serving the old document under a reused run id."""
    a = _generate(_policy_model("max_span_mm", 1500, "hard_constraint"))
    b = _generate(_policy_model("max_span_mm", 1200, "hard_constraint"))
    assert a.run.id != b.run.id


def test_the_run_is_reproducible_and_deterministic_with_every_feature_on():
    """Purity, over the whole set: same inputs, same run id, same strategy."""
    model = FenceModel(
        id=MODEL_ID, version=1,
        height_support=Discrete(heights_mm=[1800]),
        option_axes=[FINISH],
        layout_policy=[PolicyContribution(param="max_span_mm", value=1500,
                                          knowledge_type="hard_constraint")],
        default_spec=_spec(2, _rail_req(option_axis="frame_finish",
                                        sku_by_option={"black": "RAIL-3000"})),
        variants=[Variant(condition=LEVEL, spec=_spec(3))],
    )
    runs = [_generate(model, options={"frame_finish": "black"}) for _ in range(2)]
    assert runs[0].run.id == runs[1].run.id
    assert runs[0].strategy.model_dump() == runs[1].strategy.model_dump()
    assert runs[0].graph.model_dump() == runs[1].graph.model_dump()


def test_the_new_decision_nodes_render_in_both_languages():
    """A new node kind needs key-identical en/he TEMPLATES entries, or the
    /explain endpoint raises a KeyError in one language only."""
    from fenceai.decisions.explain import explain_node

    optioned = _rail_req(option_axis="frame_finish",
                         sku_by_option={"black": "RAIL-3000"})
    model = FenceModel(
        id=MODEL_ID, version=1,
        height_support=Discrete(heights_mm=[1000]),   # 1800 is off the ladder
        option_axes=[FINISH],
        default_spec=_spec(2),
        # the winner is the middle one: an earlier condition that cannot be
        # evaluated, and a later one that is never asked
        variants=[Variant(condition=MISSING, spec=_spec(4)),
                  Variant(condition=LEVEL, spec=_spec(3, optioned)),
                  Variant(condition=SHORT, spec=_spec(9))],
    )
    result = _generate(model, options={"frame_finish": "black"})
    # input facts embed their raw payload dict verbatim, braces and all
    raw = {"topology_node", "run_geometry", "gate_event", "knowledge_version"}
    seen = set()
    for node in result.graph.nodes:
        for lang in ("en", "he"):
            line = explain_node(result.graph, node, lang=lang)
            assert line, (node.action, lang)
            if node.action not in raw:
                assert "{" not in line, (node.action, lang, line)
        seen.add(node.action)
    assert {"select_variant", "select_product", "height_not_supported"} <= seen


def test_the_default_variant_sentence_renders_when_no_variant_applies():
    from fenceai.decisions.explain import explain_node

    model = _model(variants=[Variant(condition=SHORT, spec=_spec(9))])
    result = _generate(model)  # 1800 high: the condition misses
    node = next(n for n in result.graph.nodes if n.action == "select_variant")
    assert "no variant" in explain_node(result.graph, node, lang="en").lower()
    assert "{" not in explain_node(result.graph, node, lang="he")


# --- 5 · a length the bay cannot resolve --------------------------------------

def _jointed_spec(count: int = 2) -> PanelSpec:
    """A rail set with slats measured between its outermost two members — the
    shape M-SLAT@v2 has, reduced to what this section is about."""
    from fenceai.fencemodel.model import InfillSpec, Member

    return PanelSpec(
        frame=[FrameSlot(
            key="rail", orientation="horizontal", thickness_mm=40,
            placement=Distributed(count=count),
            requirement=_rail_req(),
        )],
        infill=InfillSpec(orientation="vertical", pattern=[Member(
            key="slat", width_mm=100, gap_after_mm=20,
            base_ref="rail", top_ref="rail",
            requirement=PartRequirement(
                role="infill", qty=1, length_rule="between_frame",
                eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")]),
            ),
        )]),
    )


def test_a_bay_that_cannot_measure_its_members_says_so_instead_of_pricing_none():
    """One rail, and the slats are measured between the outermost two members of
    that set — which is the same rail, so the two datums coincide and the face
    correction takes what is left. The quiet failure this guards is not a wrong
    length: it is NO length, and a divisible product asked for without one plans
    no bars, prices at nothing, and reads to the parts ledger as demand covered
    from stock — a quote missing a line rather than visibly wrong on one. Hence
    `severity="error"`, alone among the panel checks.
    """
    result = _generate(_model(default_spec=_jointed_spec(count=1)))

    slats = [s for span in result.strategy.spans for s in span.panel.slots
             if s.slot_key == "slat"]
    assert slats and all(s.length_mm is None for s in slats)

    (warning,) = _warnings(result, "panel_length_unresolved")
    assert warning.severity == "error"
    assert warning.params["slot"] == "slat"
    assert warning.params["model_ref"] == f"{MODEL_ID}@v1"
    assert warning.params["n"] == len(result.strategy.spans)
    assert set(warning.element_refs) == {s.id for s in result.strategy.spans}
    node = result.graph.node(warning.decision_ref)
    assert node.action == "panel_length_unresolved"
    from fenceai.decisions.explain import explain_node
    for lang in ("en", "he"):
        line = explain_node(result.graph, node, lang=lang)
        assert line and "{" not in line, (lang, line)


def test_a_bay_that_measures_cleanly_files_no_such_warning():
    """One warning per (model, slot) means the ordinary panel must produce
    none — otherwise every jointed job would ship an error it has no cause for."""
    result = _generate(_model(default_spec=_jointed_spec()))
    slats = [s for span in result.strategy.spans for s in span.panel.slots
             if s.slot_key == "slat"]
    assert slats and all(s.length_mm and s.length_mm > 0 for s in slats)
    assert not _warnings(result, "panel_length_unresolved")


def test_the_gap_node_records_WHICH_asker_was_silenced():
    """The graph is the explanation, and "a rule did not fire" and "a bay was
    built to the default spec" are different diagnoses with the same repair. A
    reader cannot recover which from a list of dimensions, so the node carries it.

    Kills: dropping `asked_by`, which leaves the aggregated warning unable to say
    whether a knowledge rule, a fence model, or both were silenced — the shape of
    under-explanation the split warning was supposed to avoid.
    """
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-HVHZ", version=1, type="company_rule", authority=1,
        title="hurricane zone spans",
        condition=HVHZ, actions=[SetParam(param="max_span_mm", value=900)]))

    only_model = _generate(_model(variants=[Variant(condition=FROST, spec=_spec(5))]),
                           site=None)
    only_rule = _generate(_model(), kb=kb, site=None)
    both = _generate(_model(variants=[Variant(condition=FROST, spec=_spec(5))]),
                     kb=kb, site=None)

    def asked_by(result):
        node = next(n for n in result.graph.nodes
                    if n.action == "site_condition_missing")
        warned = next(w for w in result.strategy.warnings
                      if w.code == "site_condition_missing")
        # the node and the warning must agree — they are one fact rendered twice
        assert node.payload["asked_by"] == warned.params["asked_by"]
        return warned.params["asked_by"]

    assert asked_by(only_model) == "model"
    assert asked_by(only_rule) == "rule"
    assert asked_by(both) == "both"


def test_the_sentence_no_longer_claims_only_rules_were_silenced():
    """It said "rules needing them did not apply" in both bundles. For a
    model-only want that is false — no rule wanted the dimension and no rule
    failed to apply — and the en/he parity check cannot see a sentence that is
    wrong in both languages."""
    result = _generate(_model(variants=[Variant(condition=FROST, spec=_spec(5))]),
                       site=None)
    warned = next(w for w in result.strategy.warnings
                  if w.code == "site_condition_missing")
    assert warned.params["asked_by"] == "model"
    for lang in ("en", "he"):
        node = next(n for n in result.graph.nodes
                    if n.action == "site_condition_missing")
        sentence = explain_node(result.graph, node, lang=lang)
        assert sentence
        assert "rules needing them did not apply" not in sentence

