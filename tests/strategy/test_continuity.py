"""The continuity derivation on its own — `strategy/continuity.py` is pure.

S18 walks the whole spine and pins the obligation's own numbers. This file pins
the arithmetic and the edges, which a spine test reaches only by building a
topology for each of them: the three length-rule joins, every fact that ends a
chain, and the branch a validated model cannot reach.
"""

from __future__ import annotations

import pytest

from fenceai.fencemodel.lengths import CONTINUITY_JOINS
from fenceai.fencemodel.resolve import clear_opening_mm
from fenceai.strategy.continuity import (
    BayFacts, SlotFacts, derive_member_runs,
)

FACE = 80


def bay(n: int, *, width=2400, z0=0, z1=0, height=1800, kind="line",
        panel="M#0", last=False) -> BayFacts:
    return BayFacts(
        span_id=f"span{n}", width_mm=width, vertical="level", height_mm=height,
        bottom_z_start_mm=z0, bottom_z_end_mm=z1, panel_key=panel,
        start_face_mm=FACE, end_face_mm=FACE,
        through_post_id=None if last else f"post{n}",
        through_post_kind="" if last else kind,
    )


def rail(*, rule="centre_to_centre", post_joint="through", continuity="derived",
         length=2400, qty=2, elig="RAIL") -> SlotFacts:
    return SlotFacts(
        slot_key="rail", role="rail", qty=qty, length_mm=length,
        length_rule=rule, slot_kind="frame", orientation="horizontal",
        post_joint=post_joint, continuity=continuity, eligibility_key=elig,
    )


def derive(bays, slot_for=None, stock=4877, elig="RAIL"):
    slot_for = slot_for or (lambda i: rail())
    slots = {b.span_id: {"rail": slot_for(i)} for i, b in enumerate(bays)}
    return derive_member_runs(bays, slots, {elig: stock})


def straight(n: int, **kw):
    return [bay(i, last=(i == n - 1), **kw) for i in range(n)]


def test_a_piece_is_extended_while_the_stock_can_still_make_it():
    """Two 2400 mm bays are 4800 mm and a third is 7200 mm, so 4877 mm stock
    stops at two — and the leftover bay is its own piece, not a short one bolted
    onto the first."""
    runs, notes = derive(straight(4))
    assert notes == []
    assert [(r.length_mm, r.span_ids) for r in runs] == [
        (4800, ["span0", "span1"]), (4800, ["span2", "span3"])]
    assert all(r.qty == 2 for r in runs)      # two rails, NOT two per bay


def test_one_bay_short_of_the_stock_is_never_recorded():
    """A member confined to its own bay is what the per-bay path already buys.
    Recording it would give demand two places to read the same line."""
    runs, notes = derive(straight(3), stock=3000)
    assert runs == [] and notes == []


def test_an_odd_bay_at_the_end_is_left_per_bay():
    runs, _ = derive(straight(3))
    assert [r.span_ids for r in runs] == [["span0", "span1"]]


@pytest.mark.parametrize("kind", ["end", "corner", "gate", "junction", "transition"])
def test_only_a_line_post_can_be_run_through(kind):
    """`end`, `corner`, `gate`, `junction` and `transition` all stop a member:
    the fence turns, opens, or hands over to another run there. All five, because
    the docstring naming five while the parametrize covered two is how a mapping
    that collapses `transition` into `line` ships green."""
    bays = [bay(0, kind=kind), bay(1, last=True)]
    runs, _ = derive(bays)
    assert runs == [], kind


def test_a_line_post_is_the_one_that_does_not_stop_it():
    """The positive half of the test above — five negatives and no positive
    would pass with continuity switched off entirely."""
    runs, _ = derive([bay(0, kind="line"), bay(1, last=True)])
    assert [r.span_ids for r in runs] == [["span0", "span1"]]


def test_a_piece_exactly_as_long_as_its_stock_is_made_not_refused():
    """The boundary `plan_cuts` uses: a piece costs `length + kerf` against
    `stock + kerf`, so a piece EQUAL to the stock fits. `> stock` and `>= stock`
    differ only here, and nothing else in the suite sits on the line."""
    runs, _ = derive(straight(2), stock=4800)      # two 2400 mm bays, exactly
    assert [r.length_mm for r in runs] == [4800]
    one_short = derive(straight(2), stock=4799)[0]
    assert one_short == []


def test_no_post_at_all_is_not_a_post_to_run_through():
    bays = [bay(0, kind=""), bay(1, last=True)]
    bays[0].through_post_id = None
    runs, _ = derive(bays)
    assert runs == []


def test_a_graded_bay_is_cut_per_bay_and_its_level_neighbours_are_not():
    """Obligation 14's second case. Bays 0 and 1 are flat, 2 and 3 climb; the
    flat pair is one piece and the climbing pair is two."""
    bays = [bay(0), bay(1), bay(2, z0=0, z1=400), bay(3, z0=400, z1=800, last=True)]
    runs, _ = derive(bays)
    assert [r.span_ids for r in runs] == [["span0", "span1"]]


def test_a_step_at_the_post_ends_the_chain_even_between_two_flat_bays():
    """Both bays are level in themselves and the member still cannot cross: it
    would have to jump 400 mm at the post."""
    bays = [bay(0, z0=0, z1=0), bay(1, z0=400, z1=400, last=True)]
    runs, _ = derive(bays)
    assert runs == []


@pytest.mark.parametrize("field,value", [
    ("height_mm", 2100),
    ("panel_key", "OTHER#0"),
])
def test_a_bay_built_to_a_different_panel_is_a_different_piece(field, value):
    bays = straight(2)
    setattr(bays[1], field, value)
    runs, _ = derive(bays)
    assert runs == []


def test_two_bays_offered_different_shelves_do_not_share_a_piece():
    """Which product fills the slot is fulfilment's answer; two bays whose
    candidate sets differ have not been offered the same piece to share."""
    bays = straight(2)
    slots = {"span0": {"rail": rail(elig="A")}, "span1": {"rail": rail(elig="B")}}
    runs, _ = derive_member_runs(bays, slots, {"A": 4877, "B": 4877})
    assert runs == []


def test_a_member_that_lands_on_its_post_is_never_derived_continuous():
    """`post_joint` is the authored CAPABILITY. Without it there is nothing for the
    stock length to be measured against."""
    runs, notes = derive(straight(4), slot_for=lambda i: rail(post_joint="lands"))
    assert runs == [] and notes == []


def test_a_vertical_or_infill_slot_is_not_a_candidate():
    bays = straight(2)
    for slot in (SlotFacts(slot_key="rail", qty=2, length_mm=2400,
                           length_rule="centre_to_centre", slot_kind="frame",
                           orientation="vertical", post_joint="through",
                           eligibility_key="RAIL"),
                 SlotFacts(slot_key="rail", qty=2, length_mm=2400,
                           length_rule="centre_to_centre", slot_kind="infill",
                           orientation="horizontal", post_joint="through",
                           eligibility_key="RAIL")):
        runs, _ = derive_member_runs(
            bays, {b.span_id: {"rail": slot} for b in bays}, {"RAIL": 4877})
        assert runs == []


def test_a_rule_with_no_registered_join_is_not_continuable():
    """`panel_height` measures a vertical member and `between_frame` measures
    inside one panel's own frame. Neither has a join, and a member built to one
    stays per bay rather than being handed an invented length."""
    assert "panel_height" not in CONTINUITY_JOINS
    assert "between_frame" not in CONTINUITY_JOINS
    runs, _ = derive(straight(2), slot_for=lambda i: rail(rule="panel_height"))
    assert runs == []


# --- the three joins, which are what a piece is MEASURED as ------------------

def test_clear_between_posts_gives_back_the_posts_it_no_longer_stops_at():
    """Each bay's opening gave up half of each of its two posts' faces. A member
    passing through the interior post crosses the whole of it; the two END posts
    still take theirs — which is `clear_opening_mm` over the group, exactly."""
    per_bay = clear_opening_mm(2400, FACE, FACE)
    runs, _ = derive(straight(2), slot_for=lambda i: rail(
        rule="clear_between_posts", length=per_bay))
    assert [r.length_mm for r in runs] == [clear_opening_mm(4800, FACE, FACE)]
    assert runs[0].length_mm == 2 * per_bay + FACE


def test_an_odd_face_width_is_not_recomposed_from_the_openings():
    """Recomposing from the bays' own openings is right to within the integer
    half of an odd face, and a millimetre invented in a cut list is the class of
    number this system refuses. The join goes through `clear_opening_mm` itself.
    """
    bays = straight(2)
    bays[0].start_face_mm, bays[0].end_face_mm = 80, 81
    bays[1].start_face_mm, bays[1].end_face_mm = 81, 80
    per_bay = [clear_opening_mm(2400, 80, 81), clear_opening_mm(2400, 81, 80)]
    slots = {b.span_id: {"rail": rail(rule="clear_between_posts", length=per_bay[i])}
             for i, b in enumerate(bays)}
    runs, _ = derive_member_runs(bays, slots, {"RAIL": 4877})
    assert runs[0].length_mm == clear_opening_mm(4800, 80, 80)
    assert runs[0].length_mm != sum(per_bay) + 81   # the recomposition, off by one


def test_an_overlap_is_spent_once_over_the_whole_piece():
    """It is a run-out past the ends, not a per-bay addition."""
    runs, _ = derive(straight(2), slot_for=lambda i: rail(rule="overlap", length=2450))
    assert [r.length_mm for r in runs] == [4850]      # 4800 centre-to-centre + 50


# --- the authored override --------------------------------------------------

def test_an_authored_per_bay_wins_and_reports_the_disagreement():
    runs, notes = derive(straight(2), slot_for=lambda i: rail(continuity="per_bay"))
    assert runs == []
    assert [n.code for n in notes] == ["continuity_override_disagrees"]
    assert notes[0].params["derived_bays"] == 2 and notes[0].params["built_bays"] == 1


def test_an_authored_per_bay_that_agrees_says_nothing():
    """The author wrote down what the engine would have decided. There is
    nothing to tell anyone, and a warning here would train readers to skip them.
    """
    runs, notes = derive(straight(2), stock=3000,
                         slot_for=lambda i: rail(continuity="per_bay"))
    assert runs == [] and notes == []


def test_a_per_bay_chain_is_reported_once_not_once_per_bay():
    runs, notes = derive(straight(4), slot_for=lambda i: rail(continuity="per_bay"))
    assert runs == [] and len(notes) == 1


def test_an_authored_continuous_carries_a_member_the_post_joint_would_not():
    """The case the contract keeps the override FOR: a guide states the
    behaviour outright."""
    runs, notes = derive(straight(2),
                         slot_for=lambda i: rail(post_joint="lands", continuity="continuous"))
    assert [r.length_mm for r in runs] == [4800]
    assert runs[0].basis == "authored"
    assert [n.code for n in notes] == ["continuity_override_disagrees"]
    assert notes[0].params["derived_bays"] == 1


def test_an_override_cannot_order_a_piece_longer_than_the_bar():
    """Not the override losing to a preference — to the length of a bar."""
    runs, notes = derive(straight(2), stock=3000,
                         slot_for=lambda i: rail(continuity="continuous"))
    assert runs == []
    assert [n.code for n in notes] == ["continuity_override_unbuildable"]
    assert notes[0].params["stock_length_mm"] == 3000


def test_an_authored_continuous_with_no_stated_stock_length_runs_the_chain():
    """Obligation 14's own wording: the assertion survives for the case where a
    guide states the behaviour outright AND GIVES NO LENGTH. With nothing to
    measure against, the piece is the chain — and it SAYS SO, because nothing
    bounded it. An unbounded piece over a fifty-bay chain is one 120 m rail on
    the cut list, and `_piece_too_long` only guards divisible stock, so silence
    here is a five-fold under-order nothing downstream would catch."""
    runs, notes = derive(straight(3), stock=None,
                         slot_for=lambda i: rail(continuity="continuous"))
    assert [r.span_ids for r in runs] == [["span0", "span1", "span2"]]
    assert runs[0].stock_length_mm is None and runs[0].basis == "authored"
    assert [n.code for n in notes] == ["continuity_stock_length_unknown"]
    assert notes[0].params["built_bays"] == 3


def test_an_authored_per_bay_with_no_stock_length_says_nothing():
    """The author bounded it, so a missing stock length changed nothing and
    there is nothing to report. The warning above is about an extent NOBODY
    chose."""
    runs, notes = derive(straight(3), stock=None,
                         slot_for=lambda i: rail(continuity="per_bay"))
    assert runs == [] and notes == []


def test_a_member_that_lands_on_its_post_never_asks_about_stock():
    """`lands` is an answer, so the derivation is not waiting on a length and a
    missing one is not a hole in anything."""
    runs, notes = derive(straight(3), stock=None,
                         slot_for=lambda i: rail(post_joint="lands"))
    assert runs == [] and notes == []


def test_unstated_and_lands_build_the_same_fence_and_stay_different_words():
    """`unstated` resolves to per bay — what every fence authored before this
    was built and priced to — but it is not the same CLAIM as `lands`, and the
    schema keeps them apart so closing the silence is an audit rather than a
    change of meaning under everyone's feet."""
    for value in ("unstated", "lands"):
        runs, notes = derive(straight(4),
                             slot_for=lambda i, v=value: rail(post_joint=v))
        assert runs == [] and notes == [], value


def test_no_stock_length_and_nothing_authored_is_per_bay_and_warned():
    """Not knowing is not "as far as it will go". Per bay plus a warning, the
    way an uncovered `max_span_mm` is a fallback plus a warning."""
    runs, notes = derive(straight(2), stock=None)
    assert runs == []
    assert [n.code for n in notes] == ["continuity_stock_length_unknown"]


def test_a_wide_bay_refusing_to_pair_says_nothing_about_the_bays_after_it():
    """The advance rule, and the reason it is one bay rather than the chain: a
    4000 mm bay cannot pair with its 1000 mm neighbour inside 4877 mm stock, and
    the two 1000 mm bays after it certainly can."""
    bays = [bay(0, width=4000), bay(1, width=1000), bay(2, width=1000, last=True)]
    slots = {b.span_id: {"rail": rail(length=b.width_mm)} for b in bays}
    runs, _ = derive_member_runs(bays, slots, {"RAIL": 4877})
    assert [(r.span_ids, r.length_mm) for r in runs] == [(["span1", "span2"], 2000)]


def test_the_unknown_stock_length_sentence_renders_in_both_languages():
    """S18 renders the other three through a real run. This one cannot be
    reached through a validated model (`validate_model` refuses a length rule
    backed by a product that states no length), and a template nothing renders
    is a template nobody notices is broken."""
    from fenceai.decisions.graph import DecisionNode, DecisionGraph
    from fenceai.decisions.explain import explain_node

    node = DecisionNode(
        id="d1", ordinal=1, kind="conflict",
        action="continuity_stock_length_unknown",
        payload={"slot": "rail", "run_id": "run1", "built_bays": 3})
    rendered = {}
    for lang in ("en", "he"):
        line = explain_node(DecisionGraph(nodes=[node]), node, lang=lang)
        assert line and "{" not in line, (lang, line)
        assert "3" in line, (lang, line)      # the extent it settled on
        rendered[lang] = line
    # a Hebrew template that is a copy of the English one renders fine and says
    # nothing to a Hebrew reader, so identity is the failure to check for
    assert rendered["he"] != rendered["en"]


def test_the_shortest_candidate_binds_and_the_arithmetic_still_gets_the_credit():
    """`basis` names what actually FIXED the extent. An author who merely agreed
    with the arithmetic did not decide it — crediting them would drop the stock
    length from the explanation of a number the stock length chose."""
    agreeing = derive(straight(2),
                      slot_for=lambda i: rail(continuity="continuous"))[0]
    assert agreeing[0].basis == "stock_length"     # derived 2, authored 2
    overriding = derive(straight(2), stock=3000,
                        slot_for=lambda i: rail(post_joint="lands",
                                                continuity="continuous"))[0]
    assert overriding == []                        # 3000 cannot make 4800


def test_the_disagreement_note_names_every_bay_it_settled():
    """`element_refs` is what highlights bays in the UI, and an authored
    `per_bay` over four bays is applied to four of them, not to the two the
    derivation would have joined."""
    _, notes = derive(straight(4), slot_for=lambda i: rail(continuity="per_bay"))
    assert len(notes) == 1
    assert notes[0].span_ids == ["span0", "span1", "span2", "span3"]
