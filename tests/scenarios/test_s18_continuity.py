"""S18 — the same rail, continuous in one colour and per-bay in another.

Boundary contract obligation 14. Whether a member runs continuously through an
intermediate post is **derived** — from the product's manufactured stock length
against the RESOLVED bay spacing — and never authored. The obligation gives its
own case and this file is that case, in millimetres:

    97 in maximum spacing  ->  2464 mm, four 2400 mm bays over 9600 mm
    16 ft White            ->  4877 mm stock  ->  4800 mm piece fits: TWO bays
    12 ft Blend            ->  3658 mm stock  ->  4800 mm does not: ONE bay

One model, one topology, one authored panel. The colour is an option, the option
narrows the slot to one product, and the product's stock length is the whole of
the difference. Nothing in the document says "continuous".

See docs/scenarios/golden-scenarios.md §S18.
"""

from __future__ import annotations

import pytest

from fenceai.demand.derive import derive_requirements
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Eligibility, EligibleItem, PartRequirement, validate_model,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.topology.model import ElevationSamplePayload
from tests.conftest import add_point_event, straight_topology
from tests.scenarios.continuity_fixture import (
    MAX_SPAN_MM, RUN_MM, STOCK_12FT_MM, STOCK_16FT_MM,
    board_model, catalog_with_two_colours, rail_product,
)

_rail = rail_product


def _generate(colour: str, *, topo=None, model=None, catalog=None):
    model = model or board_model()
    catalog = catalog or catalog_with_two_colours()
    return generate(
        topo if topo is not None else straight_topology(RUN_MM),
        demo_knowledge(), catalog,
        models=FenceModelLibrary(models=[model]),
        default_model=FenceModelChoice(model_id="M-BOARD", options={"colour": colour}),
    ), catalog


@pytest.fixture
def white():
    return _generate("white")


@pytest.fixture
def blend():
    return _generate("blend")


def test_the_layout_is_the_obligations_own_layout(white):
    """Four 2400 mm bays under a 97 in maximum. Everything below is measured
    against these numbers, so pin them before pinning anything derived."""
    result, _ = white
    assert [s.width_mm for s in result.strategy.spans] == [2400] * 4
    assert all(s.vertical == "level" for s in result.strategy.spans)
    line_posts = [p for p in result.strategy.posts if p.kind == "line"]
    assert len(line_posts) == 3      # three intermediate posts to run through


def test_sixteen_foot_white_runs_through_one_post_and_stops(white):
    """4800 mm out of 4877 mm fits and 7200 mm does not, so a piece covers TWO
    bays — and the two runs tile the four bays without overlapping."""
    result, _ = white
    runs = result.strategy.member_runs
    assert [r.length_mm for r in runs] == [4800, 4800]
    assert [len(r.span_ids) for r in runs] == [2, 2]
    assert [r.stock_length_mm for r in runs] == [STOCK_16FT_MM] * 2
    assert all(r.basis == "stock_length" and r.authored == "derived" for r in runs)
    # each run threads exactly one intermediate post, and never the same one
    threaded = [p for r in runs for p in r.through_post_ids]
    assert len(threaded) == 2 and len(set(threaded)) == 2
    covered = [sid for r in runs for sid in r.span_ids]
    assert covered == [s.id for s in result.strategy.spans]


def test_twelve_foot_blend_is_per_bay_on_the_identical_panel(blend):
    """The SAME authored slot, the same spacing, the same `post_joint="through"`.
    Only the stock length differs, and it is the whole of the difference."""
    result, _ = blend
    assert result.strategy.member_runs == []


def test_the_bill_of_materials_is_where_it_shows(white, blend):
    """The point of deriving it at all. Per bay, four bays of two rails is eight
    pieces and eight bars, because a 2400 mm piece and its kerf cannot be paired
    inside 3658 mm. Continuous, it is four 4800 mm pieces and four bars.

    The engineering QUANTITY halves too — a rail crossing two bays is one piece
    bought once, not two — which is the over-ordering the obligation is about.
    """
    (w_result, w_catalog), (b_result, b_catalog) = white, blend
    w = price_strategy(w_result.strategy, w_catalog, [],
                       demand_skus=w_result.run.demand_skus)
    b = price_strategy(b_result.strategy, b_catalog, [],
                       demand_skus=b_result.run.demand_skus)

    def rails(priced):
        return [r for r in priced.requirements if r.role == "rail"]

    assert [(r.engineering_qty, r.cut_length_mm) for r in rails(w)] == [(2, 4800)] * 2
    assert [(r.engineering_qty, r.cut_length_mm) for r in rails(b)] == [(2, 2400)] * 4

    def bars(priced, sku):
        return priced.bom.cut_plans[sku].new_bar_count

    assert bars(w, "RAIL-16FT-WHITE") == 4
    assert bars(b, "RAIL-12FT-BLEND") == 8
    # and the piece count itself, which is what "bought once, not twice" means
    assert sum(r.engineering_qty for r in rails(w)) == 4
    assert sum(r.engineering_qty for r in rails(b)) == 8


def test_every_rail_still_traces_to_the_bays_it_crosses(white):
    """A member run belongs to no bay (contract §3.1.12), so it pegs to all of
    them: the traceability chain the invariant suite enforces must survive a line
    that answers for two elements at once."""
    result, catalog = white
    reqs = derive_requirements(result.strategy, catalog)
    rails = [r for r in reqs if r.role == "rail"]
    assert [len(r.pegs) for r in rails] == [2, 2]
    elements = set(result.strategy.element_ids())
    for r in reqs:
        assert r.pegs and all(peg in elements for peg in r.pegs)
        for peg in r.pegs:
            assert result.graph.nodes_for_element(peg)


def test_the_decision_graph_says_why_it_is_one_piece(white):
    """`derive_continuity` carries both inputs — the stock length and the bays —
    because "why is this one piece" is asked of the cut list, and prose is
    rendered from the graph rather than stored beside it."""
    result, _ = white
    nodes = [n for n in result.graph.nodes if n.action == "derive_continuity"]
    assert len(nodes) == 2
    assert all(n.payload["stock_length_mm"] == STOCK_16FT_MM
               and n.payload["bays"] == 2
               and n.payload["length_mm"] == 4800
               and n.payload["basis"] == "stock_length" for n in nodes)


def test_the_node_is_wired_to_every_bay_it_crosses():
    """The design's own claim about `derive_continuity`, asserted rather than
    described: it is SCOPED to the member run and to each bay (so
    `/explain/{element}` answers for all of them) and takes each bay's
    `create_span` node as an INPUT (which is the whole reason `span_nodes` is
    threaded through `_generate_run`). Both survived mutation while only the
    payload was checked."""
    result, _ = _generate("white")
    graph = result.graph
    node = next(n for n in graph.nodes if n.action == "derive_continuity")
    member = result.strategy.member_runs[0]

    assert node.scope_refs == [member.id, *member.span_ids]
    for element in (member.id, *member.span_ids):
        assert graph.nodes_for_element(element), element

    spans = {n.id for n in graph.nodes
             if n.action == "create_span" and set(n.scope_refs) & set(member.span_ids)}
    incoming = {e.from_id for e in graph.edges if e.to_id == node.id}
    assert len(spans) == 2 and spans <= incoming

    # and the member run is an element the strategy admits to having
    assert member.id in result.strategy.element_ids()


def test_a_continuous_rail_and_a_per_bay_one_do_not_merge_in_the_sheet():
    """`_merge_parts` keys on `shared_with` as well as sku/unit/cut length. Two
    2400 mm rails that are one shared piece and two that are not are different
    facts about a bay, and merging them would report a count nobody decided."""
    from fenceai.report.structure import Part, _merge_parts

    shared = Part(sku="R", qty=2, unit="cut", role="rail", slot_key="rail",
                  cut_length_mm=2400, shared_with=["span@run1:2400-4800"])
    alone = Part(sku="R", qty=2, unit="cut", role="rail", slot_key="rail",
                 cut_length_mm=2400)
    assert len(_merge_parts([shared, alone])) == 2
    assert len(_merge_parts([alone, alone.model_copy(deep=True)])) == 1


def test_a_run_with_continuous_members_regenerates_identically():
    """Determinism, over the shape the invariant battery's own `test_determinism`
    never sees: a strategy containing member runs. Greedy extension, dict
    ordering and the eligibility key are all places a set could leak in."""
    first, _ = _generate("white")
    second, _ = _generate("white")
    assert first.strategy.model_dump() == second.strategy.model_dump()
    assert first.graph.model_dump() == second.graph.model_dump()
    assert first.run.id == second.run.id


def test_continuity_on_an_infill_member_is_refused_at_authoring():
    """The third refusal, and the one called "THE SEAM, named rather than left
    as a silent no-op" — which nothing tested, so it was the one that could
    silently become a no-op. An infill member is placed by `fit_pattern` against
    ONE bay's opening; a continuous one needs a group-scoped fit."""
    from fenceai.fencemodel.model import InfillSpec, Member

    model = board_model()
    model.default_spec.infill = InfillSpec(
        orientation="horizontal",
        pattern=[Member(key="board", continuity="continuous",
                        requirement=PartRequirement(
                            role="infill", qty=1, length_rule="centre_to_centre",
                            eligibility=Eligibility(members=[
                                EligibleItem(sku="RAIL-16FT-WHITE")])))])
    errors = validate_model(model, catalog_with_two_colours())
    assert any("continuity is not yet supported (phase 2) on infill" in e
               for e in errors), errors


# --- the obligation's second case: rolling terrain --------------------------

def _rolling():
    """Level for the first half, climbing for the second: 0 mm at 0 and 4800,
    800 mm at 9600. One run, one model, two kinds of bay."""
    topo = straight_topology(RUN_MM)
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "zmid", 4800, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", RUN_MM, ElevationSamplePayload(z_mm=800))
    return topo


def test_a_rail_cut_for_rolling_terrain_is_per_bay_on_the_graded_bays_only():
    """Obligation 14's other case, and it is not a special rule: a graded bay
    changes the member's elevation or angle at the post, so one straight piece
    cannot be the same piece on both sides of it. The level bays keep their
    continuity; only the graded ones are cut per bay."""
    result, catalog = _generate("white", topo=_rolling())
    spans = result.strategy.spans
    # the MODE is resolved per run, so it labels every bay the same; which bays
    # are actually graded is in the elevations, which is what continuity reads
    graded = [s.id for s in spans if s.bottom_z_start_mm != s.bottom_z_end_mm]
    assert graded, "the fixture must actually grade some bays"
    level = [s.id for s in spans if s.bottom_z_start_mm == s.bottom_z_end_mm]
    assert level, "and must leave some level, or it pins nothing"

    # The PARTITION, pinned positively. Asserting only "no graded bay is covered"
    # is vacuous the moment nothing is covered at all — with the derivation
    # deleted this test passed, which made obligation 14's second documented case
    # the one test in the file that proved nothing.
    assert len(level) == 2 and len(graded) == 2
    assert [r.span_ids for r in result.strategy.member_runs] == [level]
    covered = {sid for r in result.strategy.member_runs for sid in r.span_ids}
    assert covered == set(level)
    assert not covered & set(graded)
    # and the piece really is two bays long, not a one-bay run recorded by mistake
    assert [r.length_mm for r in result.strategy.member_runs] == [4800]


# --- the authored override, which never decides in silence ------------------

def test_an_authored_per_bay_beats_the_derivation_and_says_so():
    """`Member.continuity` survives as an override (obligation 14) and it WINS —
    but a plan that quietly contradicts its own arithmetic is a plan nobody can
    check, so the disagreement is reported with both answers in it."""
    result, catalog = _generate("white", model=board_model(continuity="per_bay"))
    assert result.strategy.member_runs == []
    notes = [w for w in result.strategy.warnings
             if w.code == "continuity_override_disagrees"]
    assert len(notes) == 1
    assert notes[0].params["authored"] == "per_bay"
    assert notes[0].params["derived_bays"] == 2
    assert notes[0].params["built_bays"] == 1
    assert notes[0].params["stock_length_mm"] == STOCK_16FT_MM


def test_an_authored_continuous_carries_a_rail_a_landing_joint_would_not():
    """The case the contract keeps the override FOR: a guide states the behaviour
    outright. The joint says nothing, the derivation therefore says one bay, and
    the authored answer is built — with the disagreement on the record."""
    result, catalog = _generate(
        "white", model=board_model(post_joint="lands", continuity="continuous"))
    runs = result.strategy.member_runs
    assert [r.length_mm for r in runs] == [4800, 4800]
    assert all(r.basis == "authored" for r in runs)
    notes = [w for w in result.strategy.warnings
             if w.code == "continuity_override_disagrees"]
    assert len(notes) == 2 and all(n.params["derived_bays"] == 1 for n in notes)


def test_an_override_cannot_order_a_piece_longer_than_the_bar():
    """The one thing the override cannot win: 12 ft stock will not reach past the
    first 2400 mm bay however the guide is worded, so it is cut per bay and
    `continuity_override_unbuildable` says which of the two gave way."""
    result, catalog = _generate(
        "blend", model=board_model(post_joint="lands", continuity="continuous"))
    assert result.strategy.member_runs == []
    notes = [w for w in result.strategy.warnings
             if w.code == "continuity_override_unbuildable"]
    assert len(notes) == 1
    assert notes[0].params["stock_length_mm"] == STOCK_12FT_MM
    assert notes[0].params["span_mm"] == 2400


# --- what the model refuses at authoring ------------------------------------

def test_a_vertical_member_cannot_be_authored_continuous():
    """A member runs through an INTERMEDIATE POST, and a vertical frame member
    meets none. Refused at load rather than carried and never read."""
    model = board_model()
    model.default_spec.frame[0].orientation = "vertical"
    errors = validate_model(model, catalog_with_two_colours())
    assert any("continuity on an orientation='vertical'" in e for e in errors)


def test_continuity_on_a_rule_with_no_join_is_refused():
    """The rule decides what the piece measures, so it decides how two bays' worth
    combine. `panel_height` has no join registered, so nothing could say how long
    one piece across two bays is."""
    model = board_model()
    model.default_spec.frame[0].requirement.length_rule = "panel_height"
    errors = validate_model(model, catalog_with_two_colours())
    assert any("no continuity join is registered" in e for e in errors)


def test_the_structure_sheet_says_one_piece_rather_than_one_per_bay():
    """The read-model half of the same obligation. A continuous rail appears in
    every bay it crosses — the crew meets it in each — and a bay table that said
    only "2 × rail" four times would add up to eight where the BOM buys four.

    Nothing is recomputed to say so: `shared_with` is the demand line's own pegs,
    inverted, which is the only thing `report/` is allowed to do with them.
    """
    from fenceai.report.structure import build_structure

    result, catalog = _generate("white")
    priced = price_strategy(result.strategy, catalog, [],
                            demand_skus=result.run.demand_skus)
    report = build_structure(straight_topology(RUN_MM), result.strategy,
                             priced.requirements, priced.bom, catalog=catalog)
    bays = [b for s in report.sections for b in s.bays]
    rails = [(b.tag, p) for b in bays for p in b.parts if p.role == "rail"]
    assert len(rails) == 4
    assert all(p.shared_with and len(p.shared_with) == 1 for _, p in rails)
    # the drawing and the bill agree about how many pieces were bought
    total = next(t for t in report.totals.per_sku if t.sku == "RAIL-16FT-WHITE")
    assert total.qty == 4
    assert sum(line.engineering_qty for line in priced.requirements
               if line.role == "rail") == 4
    # and the screws, which are per bay, carry no such claim
    screws = [p for b in bays for p in b.parts if p.role == "screw"]
    assert screws and not any(p.shared_with for p in screws)


def test_every_continuity_node_renders_in_both_languages():
    """The decision graph is the explanation and the prose comes from
    per-language templates. A new node kind with no entry falls through to the
    generic payload dump — a Hebrew reader shown an English dict — so every one
    of them is rendered here, in both, and checked for unsubstituted braces.
    """
    from fenceai.decisions.explain import explain_node

    seen = set()
    # WHITE for the authored case, not blend: 12 ft stock cannot make a piece at
    # all, so blend emits `continuity_override_unbuildable` and NO member run —
    # and the `derive_continuity_authored` sentence was rendered by nothing.
    for model, colour in ((board_model(), "white"),
                          (board_model(continuity="per_bay"), "white"),
                          (board_model(post_joint="lands", continuity="continuous"), "white"),
                          (board_model(post_joint="lands", continuity="continuous"), "blend")):
        result, _ = _generate(colour, model=model)
        for node in result.graph.nodes:
            if not node.action.startswith(("derive_continuity", "continuity_")):
                continue
            seen.add(node.action)
            for lang in ("en", "he"):
                line = explain_node(result.graph, node, lang=lang)
                assert line and "{" not in line, (node.action, lang, line)
    assert seen == {"derive_continuity", "continuity_override_disagrees",
                    "continuity_override_unbuildable"}


def test_the_two_continuity_sentences_say_different_things():
    """`derive_continuity` has two branches and they are two different answers:
    a piece the stock length fixed, and one the model asserted. Rendering is not
    enough to tell them apart — inverting the branch left the suite green while a
    stock-derived rail was explained as "because the model says so" and an
    authored one quoted a stock length of 0."""
    from fenceai.decisions.explain import explain_node

    derived, _ = _generate("white")
    asserted, _ = _generate(
        "white", model=board_model(post_joint="lands", continuity="continuous"))

    def sentence(result):
        node = next(n for n in result.graph.nodes
                    if n.action == "derive_continuity")
        return node.payload["basis"], explain_node(result.graph, node, lang="en")

    derived_basis, derived_line = sentence(derived)
    asserted_basis, asserted_line = sentence(asserted)
    assert derived_basis == "stock_length" and asserted_basis == "authored"
    assert derived_line != asserted_line
    # the derived sentence spends the number that decided it; the authored one
    # credits the model and must not quote a stock length it never used
    assert str(STOCK_16FT_MM) in derived_line
    assert str(STOCK_16FT_MM) not in asserted_line
    assert "says so" in asserted_line


def test_the_shortest_candidate_binds_when_no_option_narrows_the_slot():
    """The rule `_shortest_stock_mm` exists for, asserted where it can fail.

    Every other test here answers the colour axis, which narrows eligibility to
    ONE product — so `min` over a one-element list is `max` over it, and swapping
    them left the suite green. Here both rails stay on the table: 16 ft and 12 ft
    both eligible, nothing chosen. Which product fills the slot is
    `resolve_supply`'s answer, so the run is planned against the shorter — the
    longer one would plan a 4800 mm piece that the 3658 mm candidate cannot cut,
    and `resolve_supply` would then find NO feasible product for the line.
    """
    model = board_model()
    # drop the axis binding; both members stay eligible and unnarrowed
    model.default_spec.frame[0].requirement.option_axis = None
    model.default_spec.frame[0].requirement.sku_by_option = {}
    result, _ = _generate("white", model=model)

    assert result.strategy.member_runs == [], (
        "the 12 ft candidate cannot make a 4800 mm piece, so nothing may be "
        "planned continuous while it is still on the table")
    # and the node that WOULD have been written is absent for the same reason
    assert not [n for n in result.graph.nodes if n.action == "derive_continuity"]


def test_the_longest_candidate_is_recorded_even_though_it_did_not_decide():
    """The spread, where the two genuinely differ. A reader shown one number
    cannot tell a longer bar was on the table — nor that adding a SHORT one to
    the catalog is what would shorten every piece on the next run."""
    catalog = catalog_with_two_colours()
    # a second white rail, longer, also eligible: the shorter still binds
    catalog.products["RAIL-20FT-WHITE"] = _rail("RAIL-20FT-WHITE", 6096)
    model = board_model()
    model.default_spec.frame[0].requirement.eligibility.members.append(
        EligibleItem(sku="RAIL-20FT-WHITE", priority=3))
    model.default_spec.frame[0].requirement.sku_by_option = {
        "white": "RAIL-16FT-WHITE", "blend": "RAIL-12FT-BLEND"}
    result, _ = _generate("white", model=model, catalog=catalog)
    node = next(n for n in result.graph.nodes if n.action == "derive_continuity")
    # the colour still narrows to the 16 ft rail, so that is what bound it
    assert node.payload["stock_length_mm"] == STOCK_16FT_MM
    assert node.payload["longest_candidate_mm"] == STOCK_16FT_MM


def test_the_node_records_the_candidate_that_did_not_decide():
    """Continuity is fixed by the SHORTEST stock every candidate can be bought
    in, because which product fills the slot is fulfilment's answer. A reader
    shown one number cannot tell that a longer bar was on the table — nor that
    adding a short one to the catalog is what would shorten every piece on the
    next run. Both lengths ride on the node."""
    result, _ = _generate("white")
    nodes = [n for n in result.graph.nodes if n.action == "derive_continuity"]
    assert nodes
    for node in nodes:
        # the colour narrowed the slot to one product, so the two agree here —
        # and the field exists so that they can disagree visibly when they do
        assert node.payload["stock_length_mm"] == STOCK_16FT_MM
        assert node.payload["longest_candidate_mm"] == STOCK_16FT_MM
