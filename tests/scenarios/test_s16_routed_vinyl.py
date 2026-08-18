"""S16 — a routed vinyl line: the post is part of the panel.

The case a panel-only model cannot express. A screwed panel sits BETWEEN two
posts and the posts are the company's business; a routed vinyl fence's rails go
THROUGH the post, into holes punched at the factory, so which post can be used
at all depends on where this bay puts its rails — a number no author knows.

The whole file is one walk down the resolution DAG:

    height -> rail positions -> post -> clear width -> infill fit

and every test below pins one arrow of it.

The post arrow has TWO inputs, and the second one is not on that line at all: the
factory also decides which FACES to cut, and it decides that from where the post
will stand. So a run is 2 end posts + n line posts + a corner at every turn, not
n+1 of one SKU — which is why a manufacturer asks for the layout before it will
quote. `post.kind` comes from the topology rather than from the panel, so it
joins the post's facts without joining the cycle.

See docs/scenarios/golden-scenarios.md §S16 for the numbers and where they come
from.
"""

from __future__ import annotations

import pytest

from fenceai.demand.derive import derive_requirements
from fenceai.fencemodel.demo import M_VINYL
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.core.errors import GenerationFailure
from fenceai.strategy.generator import generate
from fenceai.topology.model import Node, Run, Topology
from tests.conftest import straight_topology

LIBRARY = FenceModelLibrary(models=[M_VINYL])
PARTS = PartLibrary(parts=demo_parts())
VINYL = FenceModelChoice(model_id="M-VINYL")


def _run(knowledge, catalog, *, height_mm: int | None = None):
    return generate(
        straight_topology(6000), knowledge, catalog,
        policy={"default_height_mm": height_mm} if height_mm else None,
        models=LIBRARY, parts=PARTS, default_model=VINYL,
    )


@pytest.fixture
def vinyl(knowledge, catalog):
    return _run(knowledge, catalog), catalog


def test_the_panel_puts_its_rails_where_the_height_says(vinyl):
    """Arrow one and two: the bay is 1800 tall, and two rails inset 150 mm top
    and bottom therefore sit at 150 and 1650. Nothing about the post yet."""
    result, _ = vinyl
    assert [sp.width_mm for sp in result.strategy.spans] == [1500] * 4
    rails = [slot for sp in result.strategy.spans for slot in sp.panel.slots
             if slot.slot_key == "rail"]
    assert rails and all(slot.positions_mm == [150, 1650] for slot in rails)
    assert all(sp.height_mm == 1800 for sp in result.strategy.spans)


def test_the_post_is_the_one_routed_for_those_rails(vinyl):
    """Arrow three, and the reason the arc exists. POST-V-2100 is not a worse
    buy — its holes are punched 300 mm from where this panel wants them, so it
    is a fence that cannot be assembled. The requirement lives in the post's
    SPEC, so it never becomes a candidate at all."""
    result, catalog = vinyl
    assert len(result.strategy.posts) == 5
    assert {p.sku for p in result.strategy.posts} <= {
        "POST-V-1800", "POST-V-1800-END"}
    assert "POST-V-2100" in catalog.products   # it was available and not chosen


def test_the_ends_and_the_middle_of_one_run_are_not_the_same_post(vinyl):
    """Arrow three's second half, and the whole reason a manufacturer asks for
    the layout before it will quote: the factory cuts the holes, so WHICH FACES
    are cut is decided by where the post stands. Two ends routed on one face,
    three line posts routed on two opposite faces — one run, one height, two
    products.

    Kills: `post_panel_facts` dropping `post.kind`, and M-VINYL dropping the
    routed-faces term. Either one puts all 5 stations on POST-V-1800 — a run
    whose two end posts are ordered with a hole cut through the outside face,
    which is the bug this arrow exists to prevent.
    """
    result, _ = vinyl
    by_station = {p.station_mm: (p.kind, p.sku) for p in result.strategy.posts
                  if p.run_ref == "run1"}
    by_station.update({0 if p.id.endswith("n1") else 6000: (p.kind, p.sku)
                       for p in result.strategy.posts
                       if p.run_ref.startswith("node:")})
    assert by_station == {
        0: ("end", "POST-V-1800-END"),
        1500: ("line", "POST-V-1800"),
        3000: ("line", "POST-V-1800"),
        4500: ("line", "POST-V-1800"),
        6000: ("end", "POST-V-1800-END"),
    }


def test_a_corner_turns_the_routing_ninety_degrees(knowledge, catalog):
    """The third position, and the one no straight run can show. A corner post is
    routed on two ADJACENT faces because a bay lands on each of them at 90 deg;
    an end post on one, a line post on two opposite. One topology, one model, one
    height, three products.

    Kills: any mapping of `post.kind` that collapses corner into line (including
    "supply the kind but only distinguish end") — a corner post cut at 180 deg
    has both its holes facing down the wrong runs and cannot be assembled.
    """
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0),
               Node(id="n2", x_mm=4000, y_mm=0),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")],
    )
    result = generate(topo, knowledge, catalog, models=LIBRARY, parts=PARTS, default_model=VINYL)
    # BY STATION, not as a set of kinds. Asked as a set, this assertion passes on
    # a fence that never turns — a straight line drawn with an intermediate click
    # also yields one end/corner/line of each, and the test named "a corner turns
    # the routing ninety degrees" would be green on it.
    at = {post.id: (post.kind, post.sku) for post in result.strategy.posts}
    assert at["post@node:n1"] == ("end", "POST-V-1800-END")
    assert at["post@node:n2"] == ("corner", "POST-V-1800-CORNER"), (
        "the post where the fence actually turns")
    assert at["post@node:n3"] == ("end", "POST-V-1800-END")
    assert all(v == ("line", "POST-V-1800")
               for k, v in at.items() if not k.startswith("post@node:"))


def test_the_cap_is_matched_against_the_post_already_chosen(vinyl):
    """Arrow four. The chosen post's face is 90 mm and CAP-V-90 declares it fits
    one — answerable only because the post was resolved first, which is the whole
    reason `cap` nests inside `PostSlot`."""
    result, _ = vinyl
    assert {p.cap_sku for p in result.strategy.posts} == {"CAP-V-90"}


def test_the_opening_is_measured_to_the_faces_of_those_posts(vinyl):
    """Arrow five, and the cycle rule paid off: the clear opening is known only
    AFTER the post is, because it is measured to its faces. 1500 − 90."""
    result, _ = vinyl
    assert all(sp.clear_width_mm == 1410 for sp in result.strategy.spans)


def test_the_slats_are_cut_to_what_the_two_channels_leave(vinyl):
    """Arrow six. (1650 − 150) − (30 + 30) + 15 + 15 = 1470, starting at 165:
    the rails' centrelines, less half of each 60 mm face, plus what seats into
    each 18 mm channel. Nine of them fill 1350 of the 1410 opening."""
    result, _ = vinyl
    slats = [slot for sp in result.strategy.spans for slot in sp.panel.slots
             if slot.slot_key == "slat"]
    assert slats and all(s.qty == 9 and s.length_mm == 1470 and s.span_start_mm == 165
                         for s in slats)


def test_the_residual_goes_to_the_edges_and_never_between_the_boards(vinyl):
    """A privacy fence with eight 7 mm slots between its boards is not a privacy
    fence. `truncate` leaves the 60 mm residual whole and `center` halves it into
    the two edges, where the post's own routed channel takes it up."""
    result, _ = vinyl
    fits = [slot.fit for sp in result.strategy.spans for slot in sp.panel.slots
            if slot.slot_key == "slat"]
    assert fits and all(f.gaps_mm == [0] * 8 for f in fits)
    assert all((f.edge_margin_start_mm, f.edge_margin_end_mm) == (30, 30) for f in fits)


def test_the_bom_buys_the_line_and_not_one_screw(vinyl):
    """A board held in a channel top and bottom is not fixed. A model carrying a
    fixing rule for symmetry would put real money on a real BOM.

    The bar counts are cut-planning answers, not divisions: two 1503 mm pieces
    need 3006 mm against a 3003 mm capacity, so a 3000 mm rail bar yields ONE
    1500 mm cut — the S15 arithmetic, on a second product."""
    result, catalog = vinyl
    bom = price_strategy(result.strategy, catalog,
                         demand_skus=result.run.demand_skus).bom
    assert {line.sku: line.purchase_qty for line in bom.lines} == {
        "POST-V-1800": 3, "POST-V-1800-END": 2, "CAP-V-90": 5, "CONC-25": 3,
        "RAIL-V-3000": 8, "SLAT-V-150": 9,
    }
    assert bom.total_cents == 119_300


def test_a_taller_fence_orders_a_differently_routed_post(knowledge, catalog):
    """What makes the post an ANSWER rather than a lookup: the same model and the
    same catalog, 300 mm taller, and every arrow of the DAG moves with it."""
    result = _run(knowledge, catalog, height_mm=2100)
    rails = [slot for sp in result.strategy.spans for slot in sp.panel.slots
             if slot.slot_key == "rail"]
    assert all(slot.positions_mm == [150, 1950] for slot in rails)
    assert {p.kind: p.sku for p in result.strategy.posts} == {
        "end": "POST-V-2100-END", "line": "POST-V-2100"}
    slats = [slot for sp in result.strategy.spans for slot in sp.panel.slots
             if slot.slot_key == "slat"]
    assert all(s.length_mm == 1770 for s in slats)


def test_every_product_the_line_named_is_recorded_on_the_run(vinyl):
    """`catalog_skus` is what `catalog_hash` narrows to, so a product the run
    bought and did not record could be repriced with nobody refused. The CAP is
    the one that had to be added: knowledge's `post_cap` rides in `demand_skus`,
    a model's cap does not."""
    result, _ = vinyl
    assert {"POST-V-1800", "POST-V-1800-END", "CAP-V-90", "RAIL-V-3000",
            "SLAT-V-150"} <= set(result.run.catalog_skus)


def test_the_parts_of_a_bay_trace_back_to_the_products_that_were_matched(vinyl):
    """The choice stays explainable where a post's choice always has been: the
    demand line carries the eligibility that was frozen into the run, so "why
    this post" is answerable from the stored document alone."""
    result, catalog = vinyl
    lines = derive_requirements(result.strategy, catalog,
                                policy=result.run.demand_skus)
    # every post line, not the last one: the run buys two products for one role
    # now, and a dict keyed by role would hide whichever came first.
    posts = [[m.sku for m in line.eligibility.members]
             for line in lines if line.role == "post"]
    assert sorted(posts) == [["POST-V-1800"]] * 3 + [["POST-V-1800-END"]] * 2
    caps = {m.sku for line in lines if line.role == "cap"
            for m in line.eligibility.members}
    assert caps == {"CAP-V-90"}


# --- the two refusals ---------------------------------------------------------
# They stay distinct because the ROUTING term and the POSITION term are separate
# conjuncts of the post predicate: `sole_excluding_term` names the one term that
# excluded everybody, and only a routing term can name two position sets.

def test_a_height_nothing_is_routed_for_still_names_both_position_sets(
    knowledge, catalog,
):
    """The routing diagnostic, unchanged by the position term beside it. 2000 mm
    puts the rails at 150 and 1850 and no post in the line is punched there, so
    this is a fence that cannot be assembled rather than a worse buy.

    Kills: folding the position mapping INTO the routing conjunct. That makes one
    term the sole discriminator for both failures, and `sole_excluding_term`
    would then answer this one by reading `item.routed_faces` and `item.material`
    into the routed-position sentence — "your posts are routed at vinyl, single,
    150, 1650". A merged term is a merged diagnostic.
    """
    with pytest.raises(GenerationFailure) as exc:
        _run(knowledge, catalog, height_mm=2000)
    assert exc.value.code == "post_routing_mismatch"
    assert exc.value.params["wanted"] == "150, 1850"
    assert exc.value.params["routed"] == "150, 1650; 150, 1950"


def test_a_junction_is_refused_generically_and_not_as_a_routing_problem(
    knowledge, catalog,
):
    """Three runs meeting needs a post cut on three faces, and this line does not
    make one. The refusal is the generic `no_item_covers_part_spec`, NOT a
    routing sentence — the heights are not the problem and saying they were would
    send the reader to the wrong catalogue page.

    This is also the deliberate gap in M-VINYL's mapping being visible: a junction
    is refused by name rather than quietly standing a two-face post where three
    panels have to land.

    Kills: mapping `junction` to a routed variant "to be safe", and folding the
    position term into the routing term (which would answer `post_routing_mismatch`
    here).
    """
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0),
               Node(id="n2", x_mm=4000, y_mm=0, kind="junction"),
               Node(id="n3", x_mm=4000, y_mm=3000),
               Node(id="n4", x_mm=8000, y_mm=0)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3"),
              Run(id="runC", start_node_id="n2", end_node_id="n4")],
    )
    with pytest.raises(GenerationFailure) as exc:
        generate(topo, knowledge, catalog, models=LIBRARY, parts=PARTS, default_model=VINYL)
    assert exc.value.code == "no_item_covers_part_spec"
    assert exc.value.params["station_mm"] == 4000
    assert exc.value.params["slot_key"] == "post"


# --- a node is a corner only if the fence turns there --------------------------
#
# `finishDraft` makes ONE RUN PER DRAWN SEGMENT, so every intermediate click on a
# straight line is a two-run node. While `kind` was a label that cost nothing;
# it is a PART NUMBER now, and a vinyl corner post is routed on two ADJACENT
# faces — so a straight node called a corner buys a post that physically cannot
# receive both its rails, priced and on the BOM.


def _two_run_topology(bend_to: tuple[int, int]):
    """Two runs meeting at n2: straight through, or turning to `bend_to`."""
    return Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=3000, y_mm=0),
               Node(id="n3", x_mm=bend_to[0], y_mm=bend_to[1])],
        runs=[Run(id="r1", start_node_id="n1", end_node_id="n2"),
              Run(id="r2", start_node_id="n2", end_node_id="n3")],
    )


def _node_post(result, node_id="n2"):
    return next(p for p in result.strategy.posts if p.id == f"post@node:{node_id}")


def test_a_straight_line_drawn_as_two_clicks_buys_no_corner_post(knowledge, catalog):
    """The ordinary drawing gesture. Two collinear runs meet at 180 degrees, so
    the post between them is a LINE post — routed on two opposite faces, which is
    what two panels arriving from opposite directions need."""
    result = generate(_two_run_topology((6000, 0)), knowledge, catalog,
                      models=LIBRARY, parts=PARTS, default_model=VINYL)
    post = _node_post(result)
    assert post.kind == "line"
    assert post.sku == "POST-V-1800", "a straight node must not buy a corner post"


def test_a_node_that_really_turns_is_still_a_corner(knowledge, catalog):
    """The contrast, so the fix above cannot be 'call every node a line post'."""
    result = generate(_two_run_topology((3000, 3000)), knowledge, catalog,
                      models=LIBRARY, parts=PARTS, default_model=VINYL)
    post = _node_post(result)
    assert post.kind == "corner"
    assert post.sku == "POST-V-1800-CORNER"


def test_the_turn_threshold_is_the_one_interior_vertices_already_use(knowledge, catalog):
    """A node and an interior vertex are the same geometry in two shapes, and two
    thresholds would make the same bend a corner on one and not the other."""
    import math

    from fenceai.topology.station import CORNER_ANGLE_DEG

    # a bend just inside the threshold reads as straight; just outside, a corner
    for turn_deg, expected in ((CORNER_ANGLE_DEG - 5, "line"),
                               (CORNER_ANGLE_DEG + 5, "corner")):
        rad = math.radians(turn_deg)
        far = (3000 + round(3000 * math.cos(rad)), round(3000 * math.sin(rad)))
        result = generate(_two_run_topology(far), knowledge, catalog,
                          models=LIBRARY, parts=PARTS, default_model=VINYL)
        assert _node_post(result).kind == expected, turn_deg


def test_a_gate_post_takes_the_single_face_variant(knowledge, catalog):
    """`gate` is mapped to `single` deliberately — a gate post meets ONE panel
    through one routed face, and the leaf hangs on hardware. The mapping is
    argued at length in the demo and in the doc, and nothing exercised it: with
    `gate` unmapped the run fails generation with the SAME refusal S16 uses to
    prove the junction gap is deliberate, so the doc's distinction between
    "mapped" and "deliberately unmapped" was unverifiable.

    Kills: dropping "gate" from the end arm of M-VINYL's position mapping.
    """
    from fenceai.topology.model import GatePayload

    from tests.conftest import add_point_event

    topo = straight_topology(6000)
    add_point_event(topo, "run1", "gate1", 3000,
                    GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    # It generates AT ALL — that is the load-bearing part. `_model_post_skus`
    # evaluates the model's post predicate at every station including a gate's,
    # and raises before `_make_post` gets to apply its precedence. So with `gate`
    # unmapped the predicate admits nothing there and the whole run dies with
    # `post_routing_mismatch`.
    result = generate(topo, knowledge, catalog, models=LIBRARY, parts=PARTS, default_model=VINYL)
    gates = [p for p in result.strategy.posts if p.kind == "gate"]
    assert gates, "the gate must place its own posts"
    # ... and what it actually STANDS is the reinforced post knowledge supplies:
    # gate reinforcement outranks the model's post, which is why the mapping's
    # job here is admitting a candidate rather than choosing the final sku.
    assert {p.sku for p in gates} == {"POST-S-HD"}
