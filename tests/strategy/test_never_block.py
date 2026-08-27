"""A run never fails over a GAP — contract §3.2.4, and boundary delta item 1.

The distinction this suite pins is not "generate never raises". It is *what*
generate is allowed to raise over: a violated hard constraint and invalid
authored data still refuse, while a hole in the knowledge — a parameter no row
covers, a default nobody stated — produces a plan with the hole NAMED.

See docs/reviews/generation-failure-audit-2026-08-25.md for the site-by-site
verdicts these tests hold in place.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.errors import GenerationFailure
from fenceai.core.gaps import Gap
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.evaluator import resolve_param
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.strategy.generator import (
    DEFAULT_RAILS_PER_SPAN, DEFAULT_SCREWS_PER_SPAN, FALLBACK_MAX_SPAN_MM, generate,
)
from tests.conftest import straight_topology


def _without(kb: KnowledgeBase, *object_ids: str) -> KnowledgeBase:
    return KnowledgeBase(versions=[v for v in kb.versions if v.object_id not in object_ids])


def _gaps(result, kind: str) -> list[Gap]:
    return [g for g in result.strategy.gaps if g.kind == kind]


# -- an uncovered parameter (generator.py, the max_span site) -------------------

def test_the_fallback_is_never_wider_than_a_stated_maximum():
    """The safety property the whole choice of 1800 rests on.

    `docs/reviews/generation-failure-audit-2026-08-25.md` argues the fallback is
    acceptable because it "errs toward standing up": a fallback that guessed
    WIDER could plan a fence that falls down. Nothing tested that. Raising the
    constant to 5000 — planning five-metre bays — left the entire suite green,
    because every assertion about it compared the code against itself.
    """
    assert FALLBACK_MAX_SPAN_MM == 1800  # the literal, so a change is a decision

    stated = [a.value for v in demo_knowledge().versions
              for a in v.actions
              if a.kind == "set_param" and a.param == "max_span_mm"]
    assert stated, "the demo base must state one, or this proves nothing"
    assert FALLBACK_MAX_SPAN_MM <= min(stated)


def test_uncovered_max_span_produces_a_plan_not_a_failure():
    """The declared defect: an uncovered exposure category used to produce no
    plan at all, on the single most important parameter in the system."""
    kb = _without(demo_knowledge(), "K-MAXSPAN")
    result = generate(straight_topology(6000), kb, demo_catalog())

    # the CONCRETE plan, not merely a non-empty one: 6000 over a 1800 basis is
    # four equal bays and the five posts that carry them
    assert [s.width_mm for s in result.strategy.spans] == [1500, 1500, 1500, 1500]
    assert len(result.strategy.posts) == 5


def test_uncovered_max_span_names_the_gap():
    kb = _without(demo_knowledge(), "K-MAXSPAN")
    result = generate(straight_topology(6000), kb, demo_catalog())

    gaps = _gaps(result, "uncovered_condition")
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.subject.kind == "param"
    assert gap.subject.id == "max_span_mm"
    assert gap.closes_by == "knowledge"
    assert gap.severity == "warns_line"
    # BINDING: a gap that only says something is missing sends a curator hunting.
    # "max_span_mm is missing" satisfies a substring check and is verbatim the
    # sentence the contract calls useless, so assert the parts that make it a
    # WORK ITEM: the parameter AND the condition coordinate it is missing on.
    assert "max_span_mm" in gap.would_close
    assert "M-LEGACY@v1" in gap.would_close
    # ...and never a run id: §3.1.13 bans a published condition naming a run, so
    # a sentence asking for one asks for a row nobody may author
    assert "run1" not in gap.would_close


def test_uncovered_max_span_warns_every_bay_it_laid_out():
    """Warned, named, unfulfilled — not a silent default."""
    kb = _without(demo_knowledge(), "K-MAXSPAN")
    result = generate(straight_topology(6000), kb, demo_catalog())

    warned = [w for w in result.strategy.warnings if w.code == "uncovered_max_span"]
    assert len(warned) == 1
    assert warned[0].severity == "warning"
    assert warned[0].params["value_mm"] == FALLBACK_MAX_SPAN_MM
    # the bays laid out on an assumed basis are the ones it points at
    assert set(warned[0].element_refs) == {s.id for s in result.strategy.spans}


def test_uncovered_max_span_is_traceable_in_the_decision_graph():
    kb = _without(demo_knowledge(), "K-MAXSPAN")
    result = generate(straight_topology(6000), kb, demo_catalog())

    gap_nodes = [n for n in result.graph.nodes if n.kind == "gap"]
    assert [n.action for n in gap_nodes] == ["uncovered_param"]
    assert gap_nodes[0].confidence == "uncertain"
    assert gap_nodes[0].payload["param"] == "max_span_mm"
    assert gap_nodes[0].payload["value"] == FALLBACK_MAX_SPAN_MM
    # Nothing governs it — that is the point, and it has to be read off the
    # IN-edges: `GraphBuilder._edge` writes governed_by FROM the knowledge node
    # TO the decision node, so the out-edge set is vacuously empty for every
    # decision node in every graph. Asserted the wrong way round, a gap node
    # citing `K-INVENTED@v1` passed the whole suite.
    in_edges = result.graph.in_edges(gap_nodes[0].id)
    assert not [e for e in in_edges if e.type == "governed_by"]
    assert {e.type for e in in_edges} == {"input_from"}  # connected, just ungoverned


def test_covered_max_span_produces_no_gap_and_no_assumption():
    """The regression guard: the demo base covers it, so nothing changes."""
    result = generate(straight_topology(6000), demo_knowledge(), demo_catalog())
    assert result.strategy.gaps == []
    assert not [n for n in result.graph.nodes if n.kind == "gap"]
    assert not [w for w in result.strategy.warnings if w.code == "uncovered_max_span"]


# -- an unstated default (generator.py, the post_ground site) -------------------

def test_missing_default_post_produces_a_plan_with_an_unfilled_post():
    kb = _without(demo_knowledge(), "K-POST-DEFAULT")
    result = generate(straight_topology(6000), kb, demo_catalog())

    assert result.strategy.posts
    # the post EXISTS and stands where it stands; only its product is unknown,
    # which is what an unresolved demand line is for
    assert all(p.sku == "" for p in result.strategy.posts)

    # ONE gap and ONE warning for the run — the docstring's claim that "sixty
    # posts are one work item". An `any`-shaped assertion passes a regression
    # that files one per post, which is the stated anti-goal.
    gaps = _gaps(result, "missing_value")
    assert len(gaps) == 1
    assert gaps[0].subject.id == "post_ground"
    assert gaps[0].subject.kind == "slot"  # a role, not a parameter key
    assert gaps[0].closes_by == "knowledge"

    warned = [w for w in result.strategy.warnings if w.code == "no_default_post"]
    assert len(warned) == 1
    # its consequence downstream is one `no_eligible_item` ERROR per post, so
    # the cause may not be quieter than the consequence
    assert warned[0].severity == "error"
    assert set(warned[0].element_refs) == {p.id for p in result.strategy.posts}
    # and the warning's decision_ref actually resolves, to the gap node
    assert result.graph.node(warned[0].decision_ref).kind == "gap"


def test_missing_default_post_reaches_demand_as_an_unresolved_line():
    from fenceai.demand.derive import derive_requirements

    kb = _without(demo_knowledge(), "K-POST-DEFAULT")
    result = generate(straight_topology(6000), kb, demo_catalog())
    lines = derive_requirements(result.strategy, demo_catalog())

    posts = [line for line in lines if line.role == "post"]
    assert posts
    assert all(m.sku == "" for line in posts for m in line.eligibility.members)


def test_an_unfilled_post_survives_the_WHOLE_spine():
    """The regression this suite originally missed by one call.

    The first version of the test above stopped at `derive_requirements`, and the
    bug was in the step after it: a blank sku is not the "deleted product" case,
    so `resolve_supply` sent it to `_resolved`, `ResolvedSupplyLine.sku` refused
    it (`min_length=1`), and the `ValidationError` surfaced from `_priced()` as a
    raw 400 on /bom, /structure and /quote. Generation stopped refusing and the
    FIRST READ AFTER IT refused instead, in an untranslated pydantic sentence —
    strictly worse than the behaviour §3.2.4 removed.

    So this walks the spine to a priced BOM, which is the only place the property
    is actually observable."""
    from fenceai.demand.derive import derive_requirements
    from fenceai.fulfillment.fulfill import fulfill
    from fenceai.fulfillment.supply import resolve_supply

    kb = _without(demo_knowledge(), "K-POST-DEFAULT")
    catalog = demo_catalog()
    result = generate(straight_topology(6000), kb, catalog)

    priced = resolve_supply(derive_requirements(result.strategy, catalog), catalog, None)

    # the post lines are UNFULFILLED and named, never resolved and never dropped
    assert len(priced.unresolved) == len(result.strategy.posts)
    assert all(line.role == "post" for line in priced.unresolved)
    assert [w.code for w in priced.warnings if w.code == "no_eligible_item"]
    # a blank sku never reaches the ledger
    assert all(r.sku for r in priced.requirements)

    # and the BOM still prices everything that CAN be bought
    bom = fulfill(priced.requirements, catalog, None)
    assert bom.lines
    assert all(line.sku for line in bom.lines)


# -- unstated per-span COUNTS (generator.py, the _resolve_quantity sites) -------
#
# The same shape as the max-span site and, until this change, missing the same
# thing: `DEFAULT_RAILS_PER_SPAN = 2` and `DEFAULT_SCREWS_PER_SPAN = 8` answered
# a question nobody had answered and said nothing about it.

def test_the_count_defaults_keep_their_values():
    """The decision this change did NOT make, pinned so it cannot drift.

    Closing the hole means REPORTING the number, never changing it: every fence
    this engine has quoted was built with 2 rails and 8 screws a bay, and moving
    either would silently reprice every job that relied on the default. The
    literals, so a change is a decision rather than a diff nobody reads."""
    assert DEFAULT_RAILS_PER_SPAN == 2
    assert DEFAULT_SCREWS_PER_SPAN == 8

    # ...and the demo base states exactly these, so retiring its rows changes
    # what the run SAYS and not what it builds. If these ever disagree, the
    # cost-invariance test below is testing nothing.
    stated = {a.param: a.value for v in demo_knowledge().versions for a in v.actions
              if a.kind == "set_param" and a.param.endswith("_per_span")}
    assert stated == {"rails_per_span": DEFAULT_RAILS_PER_SPAN,
                      "screws_per_span": DEFAULT_SCREWS_PER_SPAN}


@pytest.mark.parametrize(("dropped", "code", "param", "value"), [
    ("K-RAILS", "uncovered_rails_per_span", "rails_per_span", DEFAULT_RAILS_PER_SPAN),
    ("K-SCREWS", "uncovered_screws_per_span", "screws_per_span", DEFAULT_SCREWS_PER_SPAN),
])
def test_an_unstated_count_is_a_named_gap_not_a_silent_default(dropped, code, param, value):
    kb = _without(demo_knowledge(), dropped)
    result = generate(straight_topology(6000), kb, demo_catalog())

    gaps = [g for g in result.strategy.gaps if g.because.code == code]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.kind == "uncovered_condition"
    assert gap.subject.kind == "param" and gap.subject.id == param
    assert gap.closes_by == "knowledge" and gap.severity == "warns_line"
    # BINDING (§1.2.1): a work item names the row AND the coordinate it is
    # missing on, so a curator reads what to author. `param in would_close`
    # alone is satisfied by "rails_per_span is missing", the sentence the
    # contract calls useless.
    assert param in gap.would_close
    assert "M-LEGACY@v1" in gap.would_close
    # ...and never a run id: §3.1.13 bans a published condition naming a run
    assert "run1" not in gap.would_close

    # `value`, NOT `value_mm`. A count is not a length, and `unitParams`
    # converts every `*_mm` key to the reader's display unit — the suffix would
    # render "0.2 cm rails" to anyone whose preference is centimetres.
    assert gap.because.params["value"] == value
    assert not [k for k in gap.because.params if k.endswith("_mm")]


@pytest.mark.parametrize(("dropped", "code"), [
    ("K-RAILS", "uncovered_rails_per_span"),
    ("K-SCREWS", "uncovered_screws_per_span"),
])
def test_a_forty_bay_fence_files_ONE_warning_and_names_every_bay(dropped, code):
    """The aggregation, and the reason this was its own change.

    Both counts resolve PER SEGMENT (two call sites: `segment_model` and the
    post facts beside it), so the naive conversion emits one warning per bay —
    forty identical sentences naming no bay between them, which is verbatim the
    failure `warnings.js` records for element refs. One per section and model
    line, because the row that would close it is one row.

    An `any`-shaped assertion passes the regression that files forty, which is
    the stated anti-goal, so this counts.
    """
    kb = _without(demo_knowledge(), dropped)
    result = generate(straight_topology(75000), kb, demo_catalog())
    assert len(result.strategy.spans) >= 40, "or this proves nothing"

    warned = [w for w in result.strategy.warnings if w.code == code]
    assert len(warned) == 1
    assert warned[0].severity == "warning"
    # ONE warning, and "which bays" still has an answer: every one of them
    assert set(warned[0].element_refs) == {s.id for s in result.strategy.spans}
    assert warned[0].params["n"] == len(result.strategy.spans)
    # ...and one gap, not forty
    assert len([g for g in result.strategy.gaps if g.because.code == code]) == 1


@pytest.mark.parametrize("dropped", ["K-RAILS", "K-SCREWS"])
def test_an_unstated_count_is_traceable_in_the_decision_graph(dropped):
    """A bay's rail count has to walk back to "nobody stated this".

    Without the gap node in the quantity node's INPUTS the trail dead-ends at a
    `resolve_span_quantities` node with an empty `governed_by` — a number on the
    drawing with nothing behind it, which is the state this change removes.
    """
    kb = _without(demo_knowledge(), dropped)
    result = generate(straight_topology(6000), kb, demo_catalog())

    nodes = [n for n in result.graph.nodes
             if n.kind == "gap" and n.action == "uncovered_quantity"]
    assert len(nodes) == 1
    assert nodes[0].confidence == "uncertain"
    # nothing governs it, read off the IN-edges (`GraphBuilder._edge` writes
    # governed_by FROM the knowledge node, so out-edges are vacuously empty)
    in_edges = result.graph.in_edges(nodes[0].id)
    assert not [e for e in in_edges if e.type == "governed_by"]
    assert {e.type for e in in_edges} == {"input_from"}

    # the warning points AT it, and the quantity node hangs OFF it
    warned = next(w for w in result.strategy.warnings
                  if w.code.startswith("uncovered_") and w.code.endswith("_per_span"))
    assert warned.decision_ref == nodes[0].id
    quantity = [n for n in result.graph.nodes if n.action == "resolve_span_quantities"]
    assert quantity
    assert all(nodes[0].id in {e.from_id for e in result.graph.in_edges(q.id)}
               for q in quantity)


def test_reporting_the_count_moved_no_quantity_and_no_price():
    """The claim the commit makes, made executable.

    The whole point of keeping 2 and 8 is that a run whose knowledge stopped
    stating them builds and costs EXACTLY what it built and cost before. Compared
    against the run that DOES state them rather than against a remembered number,
    because a fixture of expected totals is a comparison of the code with itself.
    """
    from fenceai.demand.derive import derive_requirements
    from fenceai.fulfillment.fulfill import fulfill
    from fenceai.fulfillment.supply import resolve_supply

    catalog, topo = demo_catalog(), straight_topology(20000)

    def priced_bom(kb):
        result = generate(topo, kb, catalog)
        supply = resolve_supply(derive_requirements(result.strategy, catalog), catalog, None)
        return result, fulfill(supply.requirements, catalog, None)

    stated, stated_bom = priced_bom(demo_knowledge())
    assumed, assumed_bom = priced_bom(_without(demo_knowledge(), "K-RAILS", "K-SCREWS"))

    assert ([s.rail_count for s in assumed.strategy.spans]
            == [s.rail_count for s in stated.strategy.spans])
    assert ([s.screws_count for s in assumed.strategy.spans]
            == [s.screws_count for s in stated.strategy.spans])
    assert assumed_bom.total_cents == stated_bom.total_cents
    assert ([(line.sku, line.purchase_qty, line.engineering_qty, line.total_cents)
             for line in assumed_bom.lines]
            == [(line.sku, line.purchase_qty, line.engineering_qty, line.total_cents)
                for line in stated_bom.lines])

    # ...and the ONLY difference is what the run says about itself
    assert {g.because.code for g in assumed.strategy.gaps} == {
        "uncovered_rails_per_span", "uncovered_screws_per_span"}
    assert stated.strategy.gaps == []


def test_two_models_on_one_section_file_one_gap_each():
    """The case the per-MODEL half of the aggregation exists for.

    A section can be built to two model lines (a `fence_model` interval event),
    and these params resolve under the segment's model scope — so a
    `rails_per_span` row authored for one line closes nothing for the other. Two
    work items, each naming its own bays, and NOT one gap that would send a
    curator to author half a fix.

    The mirror of `_report_uncovered_max_span`'s "two segments of one run can
    name the same model" note, from the other side: same model twice is one gap,
    different models is two.
    """
    from fenceai.fencemodel.demo import demo_models
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.topology.model import FenceModelPayload
    from tests.conftest import add_interval_event

    models = demo_models()
    library = FenceModelLibrary(models=[models["M-LEGACY"], models["M-SLAT"]])
    topo = straight_topology(12000)
    add_interval_event(topo, "run1", "mA", 0, 6000,
                       FenceModelPayload(model_id="M-LEGACY"))
    add_interval_event(topo, "run1", "mB", 6000, 12000,
                       FenceModelPayload(model_id="M-SLAT"))

    kb = _without(demo_knowledge(), "K-RAILS")
    result = generate(topo, kb, demo_catalog(), models=library)

    gaps = [g for g in result.strategy.gaps if g.because.code == "uncovered_rails_per_span"]
    assert len(gaps) == 2, [g.id for g in gaps]
    # one work item per product LINE, each naming its own line and nobody else's
    assert {g.would_close for g in gaps} == {
        "a rails_per_span row for series M-LEGACY@v1",
        "a rails_per_span row for series M-SLAT@v1",
    }
    assert len({g.id for g in gaps}) == 2  # and two ids, not one overwritten

    warned = [w for w in result.strategy.warnings
              if w.code == "uncovered_rails_per_span"]
    assert len(warned) == 2
    # every bay is accounted for exactly once: the two element_ref sets partition
    # the section, so neither warning claims bays the other model built
    refs = [set(w.element_refs) for w in warned]
    assert not refs[0] & refs[1]
    assert refs[0] | refs[1] == {s.id for s in result.strategy.spans}


def test_a_stated_count_produces_no_gap_and_no_node():
    """The regression guard: the demo base states both, so nothing changes."""
    result = generate(straight_topology(6000), demo_knowledge(), demo_catalog())
    assert result.strategy.gaps == []
    assert not [n for n in result.graph.nodes if n.action == "uncovered_quantity"]
    assert not [w for w in result.strategy.warnings if w.code.endswith("_per_span")]


# -- what still refuses ---------------------------------------------------------

def test_an_unknown_model_pin_still_refuses():
    """§3.2.4 covers gaps, not invalid input. A pin naming a model that does not
    exist is not a hole in the knowledge — it is an instruction that cannot be
    carried out, and silently building something else is the failure mode the
    refusal exists to prevent."""
    with pytest.raises(GenerationFailure) as excinfo:
        generate(straight_topology(6000), demo_knowledge(), demo_catalog(),
                 default_model=FenceModelChoice(model_id="M-NOPE"))
    assert excinfo.value.code == "fence_model_not_found"


# -- a disagreeing tie: authored vs published ----------------------------------

def _rule(object_id: str, value: int, origin: str) -> KnowledgeVersion:
    return KnowledgeVersion(
        object_id=object_id, version=1, type="company_rule", origin=origin,
        title=f"{object_id} = {value}",
        actions=[SetParam(param="max_span_mm", value=value)],
    )


def test_two_authored_rules_that_tie_and_disagree_stay_a_build_error():
    """Two rules WE wrote cannot both be right; that is our bug to fix."""
    kb = KnowledgeBase(versions=[
        _rule("R1", 1800, "authored"), _rule("R2", 1500, "authored"),
    ])
    with pytest.raises(GenerationFailure):
        resolve_param(kb, {"scope": {}}, "max_span_mm")


@pytest.mark.parametrize("origins", [("published", "authored"),
                                     ("authored", "published"),
                                     ("published", "published")])
def test_a_published_contender_turns_the_tie_into_a_conflict(origins):
    """The exposure that scales with adoption: our expansion puts published rows
    at authority 1 or 3, so both branches sat inside the raise band."""
    kb = KnowledgeBase(versions=[
        _rule("R1", 1800, origins[0]), _rule("R2", 1500, origins[1]),
    ])
    res = resolve_param(kb, {"scope": {}}, "max_span_mm")

    assert res.winner is not None, "generation continues with the flagged pick"
    assert len(res.conflicts) == 1
    assert set(res.conflicts[0].contenders) == {"R1@v1", "R2@v1"}


def test_origin_defaults_to_authored():
    """Every rule already in the codebase was written by us; nothing published
    has arrived yet. The default is the one that keeps today's build errors."""
    assert KnowledgeVersion(object_id="X", version=1, type="fact").origin == "authored"


# -- both gaps render, in both languages ---------------------------------------

@pytest.mark.parametrize("dropped",
                         ["K-MAXSPAN", "K-POST-DEFAULT", "K-RAILS", "K-SCREWS"])
@pytest.mark.parametrize("lang", ["en", "he"])
def test_a_gap_node_renders_in_both_languages(dropped, lang):
    """A gap the reader cannot read is a gap that was not reported. Same rule as
    every other node: both bundles, no placeholder left unresolved."""
    from fenceai.decisions.explain import explain_node

    kb = _without(demo_knowledge(), dropped)
    result = generate(straight_topology(6000), kb, demo_catalog())
    nodes = [n for n in result.graph.nodes if n.kind == "gap"]
    assert nodes

    for node in nodes:
        line = explain_node(result.graph, node, lang=lang)
        assert line and "{" not in line
        # ...and no placeholder resolved to None. `_fmt` renders a missing
        # payload key as the string "None" with no braces left over, so the
        # brace check alone passes a sentence reading "for section None; laid
        # out to a fallback of None mm" — which is the entire explanation of the
        # number, naming neither the section nor the number.
        assert "None" not in line


# -- the property, not the three known holes -----------------------------------

def test_leave_one_out_no_knowledge_object_is_load_bearing():
    """The audit's central claim, made executable.

    `docs/reviews/generation-failure-audit-2026-08-25.md` concludes that after
    the three conversions "the engine has no refusal left that a curator could
    close". Asserting the three holes we happen to know about cannot show that:
    a fourteenth `raise` on a knowledge-absence path added next month is a
    green-suite change. So retire each knowledge object in turn and require a
    plan every time.

    This is the test that would have caught all three original defects without
    anyone having found them first.
    """
    catalog = demo_catalog()
    topo = straight_topology(6000)
    for victim in [v.object_id for v in demo_knowledge().versions]:
        kb = _without(demo_knowledge(), victim)
        result = generate(topo, kb, catalog)  # must not raise
        assert result.strategy.spans, f"retiring {victim} produced no plan"


def test_an_empty_knowledge_base_still_plans_every_shape():
    """The strongest form: nothing is known at all."""
    catalog = demo_catalog()
    empty = KnowledgeBase(versions=[])
    for length in (1200, 6000, 20000):
        result = generate(straight_topology(length), empty, catalog)
        assert result.strategy.spans
        # exactly the four holes, named — not a silent plan
        assert {g.because.code for g in result.strategy.gaps} == {
            "uncovered_max_span", "no_default_post",
            "uncovered_rails_per_span", "uncovered_screws_per_span"}


def test_gaps_are_deterministic():
    """`generate()` is pure (ADR-0004): the same inputs give the same gaps, in
    the same order, with the same ids."""
    kb, catalog, topo = KnowledgeBase(versions=[]), demo_catalog(), straight_topology(6000)
    a = generate(topo, kb, catalog)
    b = generate(topo, kb, catalog)
    assert [g.model_dump() for g in a.strategy.gaps] == [g.model_dump() for g in b.strategy.gaps]
    assert a.strategy.model_dump() == b.strategy.model_dump()


def test_gaps_survive_a_store_round_trip():
    """A stored run is re-read with `model_validate_json`, which re-runs every
    `Gap` invariant. A schema slip would surface as a run that cannot be loaded
    at all, so this is the assertion that keeps a gap from making a run
    unreadable."""
    from fenceai.strategy.model import GenerationResult

    result = generate(straight_topology(6000), KnowledgeBase(versions=[]), demo_catalog())
    assert result.strategy.gaps
    reread = GenerationResult.model_validate_json(result.model_dump_json())
    assert reread.strategy.gaps == result.strategy.gaps


def test_an_override_neither_suppresses_nor_duplicates_a_gap():
    """A user patch changes the fence, not what knowledge failed to say."""
    from fenceai.strategy.overrides import Override, PinPost

    kb, catalog = _without(demo_knowledge(), "K-MAXSPAN"), demo_catalog()
    ov = [Override(id="ov1", run_id="run1", directive=PinPost(station_mm=1000))]
    result = generate(straight_topology(6000), kb, catalog, overrides=ov)

    assert [p for p in result.strategy.posts if p.pinned]
    assert len(_gaps(result, "uncovered_condition")) == 1


# -- a published contradiction, all the way through generate() -----------------

def _published(object_id: str, value: int) -> KnowledgeVersion:
    return KnowledgeVersion(
        object_id=object_id, version=1, type="hard_constraint", origin="published",
        title=f"{object_id} max span {value}",
        actions=[SetParam(param="max_span_mm", value=value)],
    )


@pytest.mark.parametrize("order", [("P-AAA", 2400, "P-ZZZ", 1200),
                                   ("P-AAA", 1200, "P-ZZZ", 2400)])
def test_two_published_maxima_that_disagree_build_to_the_RESTRICTIVE_one(order):
    """The alphabet must never decide a safety limit.

    `applicable_firings` tie-breaks on `object_id` last, so before this the same
    two rows built 2000 mm bays or 1200 mm bays depending on what they were
    NAMED — and the 2000 mm answer exceeded a maximum one of them stated. Never
    blocking the run does not license picking the looser number: both orderings
    must land on the tightest figure every contender could live with.
    """
    a_id, a_val, b_id, b_val = order
    kb = _without(demo_knowledge(), "K-MAXSPAN")
    kb.versions += [_published(a_id, a_val), _published(b_id, b_val)]

    result = generate(straight_topology(6000), kb, demo_catalog())
    assert max(s.width_mm for s in result.strategy.spans) <= min(a_val, b_val)


def test_a_published_contradiction_is_reported_BACK_as_a_disputed_gap():
    """Only the publisher can fix two of their own rows contradicting each other,
    so a `StrategyWarning` alone leaves the finding inside this repo, rendered on
    our drawing, reaching nobody who can act on it."""
    kb = _without(demo_knowledge(), "K-MAXSPAN")
    kb.versions += [_published("P-AAA", 2400), _published("P-ZZZ", 1200)]
    result = generate(straight_topology(6000), kb, demo_catalog())

    disputed = _gaps(result, "disputed")
    assert len(disputed) == 1
    assert disputed[0].on == "value"  # they agree on WHEN, not on the number
    assert disputed[0].closes_by == "knowledge"
    assert "P-AAA@v1" in disputed[0].would_close and "P-ZZZ@v1" in disputed[0].would_close
    # and it is an error on the drawing, not a note: a stated maximum is in play
    conflict = next(w for w in result.strategy.warnings if w.code == "knowledge_conflict")
    assert conflict.severity == "error"


def test_a_manufactured_width_beats_an_invented_maximum():
    """When nobody states a maximum but the model declares the width its line
    ships in, that number is authored and the fallback is not.

    Before this, the run laid out 1800 mm bays for 2400 mm panels and reported,
    at ERROR severity, that the panels exceeded "the 1800 mm maximum span" — a
    limit nobody set, on a plan that could not be built."""
    kb = _without(demo_knowledge(), "K-MAXSPAN")
    kb.versions.append(KnowledgeVersion(
        object_id="K-EXACT", version=1, type="hard_constraint",
        title="manufactured in 2400 mm bays",
        actions=[SetParam(param="exact_span_mm", value=2400)],
    ))
    result = generate(straight_topology(7200), kb, demo_catalog())

    assert [s.width_mm for s in result.strategy.spans] == [2400, 2400, 2400]
    assert not [w for w in result.strategy.warnings if w.code == "exact_span_over_max"]
    # the gap still stands — no rule covers the parameter — but it must not call
    # the manufacturer's own number a fallback
    gap = _gaps(result, "uncovered_condition")[0]
    assert gap.because.params["basis"] == "manufactured_width"


# -- a Conflict cannot be silently dropped -------------------------------------

def _published_mounting(object_id: str, sku: str) -> KnowledgeVersion:
    from fenceai.knowledge.model import RequireMounting

    return KnowledgeVersion(
        object_id=object_id, version=1, type="company_rule", origin="published",
        title=f"{object_id} mounting",
        actions=[RequireMounting(surface="masonry_wall", mounting="masonry", sku=sku)],
    )


def test_a_published_tie_at_a_NON_span_site_is_still_surfaced():
    """Conflicts were surfaced at three of the ~13 resolution sites and dropped at
    the rest — which was survivable only while every hard-band tie RAISED.

    Once a tie touching a published row became a flagged pick (§3.2.4), a
    published `require_mounting` disagreeing with an authored one picked a winner
    by tie-break order and reported NOTHING: ground versus masonry, decided
    silently, on a run nobody warned. `_resolve_mounting` is one of the ten that
    dropped them.
    """
    from fenceai.topology.model import BasePayload
    from tests.conftest import add_interval_event

    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MASONRY"]
    kb.versions += [_published_mounting("P-MOUNT-A", "POST-M"),
                    _published_mounting("P-MOUNT-B", "POST-S")]

    topo = straight_topology(7000)
    add_interval_event(topo, "run1", "base", 4000, 7000,
                       BasePayload(surface="masonry_wall"))
    result = generate(topo, kb, demo_catalog())

    surfaced = [w for w in result.strategy.warnings if w.code == "knowledge_conflict"]
    assert surfaced, "a published tie on mounting was resolved and never reported"
    assert "P-MOUNT-A@v1" in surfaced[0].params["contenders"]
    # ...and it is traceable, like every other conflict
    assert result.graph.node(surfaced[0].decision_ref).action == "knowledge_conflict"


def test_a_published_tie_on_a_QUANTITY_is_still_surfaced():
    """`_resolve_quantity` served rails, screws, step thresholds and embedment —
    four params through one helper that threw its conflicts away."""
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-RAILS"]
    for object_id, value in (("P-RAILS-A", 2), ("P-RAILS-B", 3)):
        kb.versions.append(KnowledgeVersion(
            object_id=object_id, version=1, type="fact", origin="published",
            title=object_id, actions=[SetParam(param="rails_per_span", value=value)]))

    result = generate(straight_topology(6000), kb, demo_catalog())
    surfaced = [w for w in result.strategy.warnings if w.code == "knowledge_conflict"]
    assert any("rails_per_span" in w.params["slot"] for w in surfaced)


def test_every_conflict_is_surfaced_exactly_once():
    """The sink is drained in one place, so a conflict recorded by a memoised
    resolution cannot be reported twice — a run claiming two disagreements where
    there is one is its own wrong answer."""
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-RAILS"]
    for object_id, value in (("P-RAILS-A", 2), ("P-RAILS-B", 3)):
        kb.versions.append(KnowledgeVersion(
            object_id=object_id, version=1, type="fact", origin="published",
            title=object_id, actions=[SetParam(param="rails_per_span", value=value)]))

    # A TWO-RUN topology, deliberately: the same slot is resolved once per run,
    # so a single-run fence proves nothing here. It reported the identical
    # disagreement twice before the drain deduped.
    from fenceai.topology.model import Node, Run, Topology

    lshape = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=4000, y_mm=0),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")])
    result = generate(lshape, kb, demo_catalog())
    rails = [w for w in result.strategy.warnings
             if w.code == "knowledge_conflict" and "rails_per_span" in w.params["slot"]]
    assert len(rails) == 1, "one disagreement, reported once per place we looked"


def _resolutions_that_go_nowhere(path) -> list[str]:
    """Every resolution in `path` that neither records its conflicts nor hands the
    `Resolution` back. Shared with the self-test below, which is what keeps this
    from being a check that only ever passes."""
    import ast

    tree = ast.parse(path.read_text())
    RESOLVERS = {"resolve_param", "resolve_actions", "evaluator_resolve", "resolve"}
    lost = []

    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for stmt in ast.walk(fn):
            if not isinstance(stmt, ast.Assign):
                continue
            call = stmt.value
            if not (isinstance(call, ast.Call)
                    and getattr(call.func, "id", None) in RESOLVERS):
                continue
            name = getattr(stmt.targets[0], "id", None)
            if name is None:
                continue

            # recorded: `<sink>.extend(<name>.conflicts)` or
            # `_surface_conflicts(<name>.conflicts, …)` anywhere in this function
            recorded = any(
                isinstance(n, ast.Attribute) and n.attr == "conflicts"
                and getattr(n.value, "id", None) == name
                for n in ast.walk(fn)
            )
            # handed back: the Resolution ITSELF is returned, not something read
            # off it. `return later.winner` is not handing it back — that was the
            # hole the first version of this check had.
            def bare(node) -> bool:
                """`res` handed back, as opposed to something READ off it.

                An Attribute subtree is not bare by definition: `return
                res.winner` gives the caller a value, not the Resolution, so it
                cannot record the conflicts. Set subtraction gets this wrong when
                one name appears BOTH ways — `return res.winner, res` does hand it
                back."""
                if isinstance(node, ast.Name):
                    return node.id == name
                if isinstance(node, ast.Attribute):
                    return False
                return any(bare(c) for c in ast.iter_child_nodes(node))

            handed_back = any(
                bare(r) for r in ast.walk(fn) if isinstance(r, ast.Return))
            if not (recorded or handed_back):
                lost.append(f"{fn.name}() line {stmt.lineno}: {name}")
    return lost


def test_no_resolution_in_the_generator_drops_its_conflicts():
    """The guard against the NEXT call site, not this one.

    Every resolution in the generator must have its `Resolution.conflicts` reach
    the sink, or a disagreement is decided by tie-break order and reported to
    nobody. Thirteen sites are fine today; the one that matters is the
    fourteenth. `test_backend_code_list_is_current` guards new warning codes the
    same way and for the same reason.

    Parsed rather than line-windowed: the max-span site records 67 lines below
    the call, past the comment explaining the never-block change, and
    `_vertical_mode` legitimately hands its `Resolution` back for the caller to
    record. A proximity heuristic calls both of those bugs.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "strategy" / "generator.py"
    lost = _resolutions_that_go_nowhere(src)
    assert not lost, (
        "these resolutions neither record their conflicts into the sink nor hand "
        "the Resolution back to a caller that does — a published tie there is "
        "decided by tie-break order and reported to nobody:\n  "
        + "\n  ".join(lost)
    )


def test_that_guard_actually_catches_a_dropped_conflict(tmp_path):
    """The guard's own test. The first version of it passed a function that read
    `.winner` off the resolution and threw the conflicts away, because "the name
    appears in a return statement" is not the same claim as "the Resolution was
    handed back" — so the check that was supposed to catch the fourteenth site
    would have waved it through."""
    forgetful = tmp_path / "forgetful.py"
    forgetful.write_text(
        "def newcomer(kb, ctx):\n"
        "    later = resolve_param(kb, ctx, 'p')\n"
        "    return 1 if later.winner else 0\n"
    )
    assert _resolutions_that_go_nowhere(forgetful) == ["newcomer() line 2: later"]

    careful = tmp_path / "careful.py"
    careful.write_text(
        "def newcomer(kb, ctx, sink):\n"
        "    later = resolve_param(kb, ctx, 'p')\n"
        "    sink.extend(later.conflicts)\n"
        "    return 1 if later.winner else 0\n"
    )
    assert _resolutions_that_go_nowhere(careful) == []

    handing_back = tmp_path / "handing_back.py"
    handing_back.write_text(
        "def helper(kb, ctx):\n"
        "    res = resolve_param(kb, ctx, 'p')\n"
        "    return res.winner, res\n"
    )
    assert _resolutions_that_go_nowhere(handing_back) == []
