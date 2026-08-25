"""Whether a member runs continuously through an intermediate post — DERIVED.

Boundary contract obligation 14. The property is derived from the product's
manufactured `stock_length` against the **resolved** bay spacing, and it is
derived exactly once, here, during generation:

  * it cannot be a property of the part, because it needs the spacing, and the
    spacing is not known until the run is laid out;
  * it cannot be recomputed downstream, because a read model that recomputed it
    could disagree with the bill of materials about whether a rail is one piece
    or three — and `foundation §15` says a read model never recomputes a
    quantity. The answer is recorded on the strategy as `MemberRun`s, and demand,
    the cut plan and the structure sheet all read that one record.

The obligation's own cases, and where each is decided below:

  * *the same rail is continuous in one colour and per-bay in another — 16 ft
    White against 12 ft Blend, at a 97" maximum spacing.* The colour is an option
    that narrows the slot's eligibility to one product, so the generator's
    `_shortest_stock_mm` answers 4877 mm or 3658 mm for the identical authored
    slot, and `_greedy_extent` turns that into two bays or one.
  * *a rail cut for rolling terrain is per-bay on the graded bays only.* A graded
    bay's member changes angle or elevation at the post, and one straight piece
    cannot do both, so `_chain_break` stops there and the level bays of the same
    run keep their continuity. Read off the bay's ELEVATIONS, never off
    `Span.vertical` — see `_flat`, where the "only" is won or lost.
  * *`Member.continuity` survives as an authored override.* `_apply_override`,
    which never decides in silence: an authored answer that differs from the
    derived one is reported.

**What is authored and what is derived.** The model authors a *capability* —
`joint="through"`, the member is detailed to pass what it lands on rather than
stop at it — and the engine derives the *behaviour*. That distinction is the
whole of the obligation's rationale: v0.4 made continuity an authored boolean and
"that flattened a derived property into a fact". A `through` rail with 12 ft
stock at 97" spacing is still cut per bay, and no author can say otherwise
without the engine reporting that they did.

Pure: no catalog, no strategy objects, no decision graph. The generator gathers
the facts, this decides, and the generator records.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.fencemodel.lengths import CONTINUITY_JOINS


class BayFacts(BaseModel):
    """One bay, as continuity sees it: its geometry and the post at each end."""

    span_id: str
    width_mm: Mm
    vertical: str                # level | stepped | raked
    height_mm: Mm
    bottom_z_start_mm: Mm
    bottom_z_end_mm: Mm
    # The panel this bay was built to. Two bays cannot share a piece unless they
    # share the detail that piece is cut to, and `(model_ref, variant_index)` is
    # what says so — a variant switching at a height change is a different panel
    # even under one model.
    panel_key: str
    start_face_mm: Mm            # face width of the post this bay starts at
    end_face_mm: Mm
    # The post at this bay's END, if the next bay starts at the same station. A
    # member runs through an INTERMEDIATE post, so `None` (a run end, a gate
    # opening, a suppressed post) ends the chain: there is nothing to run
    # through, and two bays with no post between them are not two bays a piece is
    # threaded across — they are a hole in the fence.
    through_post_id: str | None = None
    through_post_kind: str = ""


class SlotFacts(BaseModel):
    """One slot of one bay, as continuity sees it."""

    slot_key: str
    role: str = ""
    qty: int
    length_mm: Mm | None = None
    length_rule: str = ""
    slot_kind: str = ""
    orientation: str = ""
    joint: str = "butt"
    continuity: str = "derived"
    post_joint: str = "unstated"
    length_basis: str = "width"
    # The candidate products, as one comparable string. Two bays whose slot could
    # be filled from different shelves are not two bays one piece crosses.
    eligibility_key: str = ""


class MemberRunPlan(BaseModel):
    """One physical piece, and the bays it covers. `len(span_ids) == 1` is never
    emitted: a member confined to its own bay is what the per-bay path already
    buys, and recording it would give demand two places to read the same line."""

    slot_key: str
    role: str = ""
    span_ids: list[str]
    through_post_ids: list[str]
    length_mm: Mm
    qty: int
    length_rule: str
    length_basis: str = "width"
    basis: Literal["stock_length", "authored"]
    stock_length_mm: Mm | None = None
    authored: str = "derived"


class ContinuityNote(BaseModel):
    """Something a person has to be told. `code` + `params`, never prose — the
    English message is assembled by the generator as the fallback it is."""

    code: str
    slot_key: str
    span_ids: list[str]
    params: dict[str, str | int] = {}


def _flat(bay: "BayFacts") -> bool:
    """Does this bay's member run level from one post to the next?

    Asked of the bay's GEOMETRY, not of `Span.vertical`. The mode is resolved for
    a whole run — one `prefer_vertical` rule settles it for every bay at once —
    so a run with a hump in the middle is labelled `stepped` end to end, and a
    reader of the label alone would put the flat half in with the graded half.
    Obligation 14 says the rail is cut per bay on the graded bays **only**, and
    only the elevations know which those are.

    **A known narrowing.** The physical impossibility is a CHANGE of gradient at
    the post, not a gradient: a uniformly raked run is straight across its
    intermediate posts and one piece would make it. This asks the stricter
    question and so cuts a constant slope per bay. Obligation 14's wording ("per
    bay on the graded bays only") makes that the safe reading, and generalizing
    it is not free — collinearity has to be tested by integer cross-multiplication
    (`dz_a * width_b == dz_b * width_a`, never a ratio), and
    `_join_centre_to_centre` sums per-bay lengths that are only additive once
    collinearity holds.
    """
    return bay.bottom_z_start_mm == bay.bottom_z_end_mm


def _wants_continuity(slot: SlotFacts) -> bool:
    """Is this member even a candidate to pass a post?

    `post_joint="through"` is a CAPABILITY — how the member is detailed where it
    meets the post — and `continuity="continuous"` is the authored assertion the
    contract keeps for a guide that states the behaviour and gives no length.
    Neither is the answer; both merely put the member on the table.

    `unstated` (the default) and `lands` both stay off it, and today they produce
    the same fence. They are not the same claim, and `PostJoint` explains why the
    difference is kept.
    """
    return slot.post_joint == "through" or slot.continuity == "continuous"


def _continuable(slot: SlotFacts) -> bool:
    return (
        slot.slot_kind == "frame"
        and slot.orientation == "horizontal"
        and slot.length_mm is not None
        and slot.length_rule in CONTINUITY_JOINS
    )


def _chain_break(a: BayFacts, b: BayFacts, sa: SlotFacts, sb: SlotFacts) -> bool:
    """Is the piece crossing from bay `a` to bay `b` the SAME piece?

    Everything here is a fact that would make it two pieces however long the
    stock is. Stock length is asked afterwards and only ever shortens a chain.
    """
    if a.through_post_id is None or a.through_post_kind != "line":
        # end, corner, gate, junction and transition posts all stop a member: the
        # fence changes direction, opens, or hands over to another run there.
        return True
    if not _flat(a) or not _flat(b):
        # a bay that climbs turns the member through an angle at the post, and
        # one straight piece cannot be at two angles: "per bay on the graded bays
        # only" is not a special case, it is this question answered honestly
        return True
    if a.bottom_z_end_mm != b.bottom_z_start_mm or a.height_mm != b.height_mm:
        # a step at the post moves the member up or down as it crosses
        return True
    if a.panel_key != b.panel_key:
        return True
    if not _continuable(sb):
        # the next bay's slot cannot be part of a piece at all. Unreachable while
        # both bays share a `panel_key` — the same spec resolves the same way —
        # and checked anyway, because the alternative is summing a `None` length
        # into a cut list.
        return True
    return (
        sa.slot_key != sb.slot_key
        or sa.qty != sb.qty
        or sa.length_rule != sb.length_rule
        or sa.joint != sb.joint
        or sa.post_joint != sb.post_joint
        or sa.continuity != sb.continuity
        or sa.eligibility_key != sb.eligibility_key
    )


def _piece_length(bays: list[BayFacts], slots: list[SlotFacts]) -> Mm:
    """How long ONE piece covering these bays is, through the rule's own join."""
    join = CONTINUITY_JOINS.get(slots[0].length_rule)
    faces = [bays[0].start_face_mm] + [b.end_face_mm for b in bays]
    return join([s.length_mm for s in slots], [b.width_mm for b in bays], faces)


def _greedy_extent(
    bays: list[BayFacts], slots: list[SlotFacts], stock_mm: Mm | None
) -> int:
    """How many of these bays one piece covers, starting at the first.

    Longest-first and deterministic: a piece is extended while the stock it is
    cut from can still make it, and stops at the first bay it cannot. With no
    stock length known the whole chain is one piece — which is only reachable
    from an authored override, because the derived path needs a length to derive
    from.
    """
    if stock_mm is None:
        return len(bays)
    n = 1
    while n < len(bays):
        if _piece_length(bays[: n + 1], slots[: n + 1]) > stock_mm:
            break
        n += 1
    return n


def _apply_override(
    authored: str, derived_n: int | None, override_n: int
) -> tuple[int, str | None]:
    """The authored answer wins; a real disagreement is reported. Returns the
    extent to build and the code of the note that must go with it, if any.

    `derived_n is None` is the derivation ABSTAINING — the member is detailed to
    pass the post and nothing states how long a piece can be bought — which is
    exactly the case obligation 14 keeps the override for: *"a guide states the
    behaviour outright and gives no length"*. Nothing was derived, so nothing can
    disagree, and reporting one there would put a warning on the one use the
    contract explicitly blesses.

    The outcomes that stay silent are the two that should: nothing authored, and
    an author who wrote down what the engine would have decided anyway. What is
    never silent is a genuine disagreement — a plan that quietly contradicts its
    own arithmetic is a plan nobody can check.

    The one thing an override cannot do is order a piece longer than the stock it
    would be cut from. `continuity_override_unbuildable` is that case: not the
    override losing to a preference, but to the length of a bar.
    """
    if authored == "derived":
        return derived_n or 1, None
    if authored == "per_bay":
        disagrees = derived_n is not None and derived_n > 1
        return 1, "disagrees" if disagrees else None
    # authored == "continuous"
    if override_n == 1:
        return 1, "unbuildable"
    if derived_n is not None and override_n != derived_n:
        return override_n, "disagrees"
    return override_n, None


def derive_member_runs(
    bays: list[BayFacts],
    slots_by_span: dict[str, dict[str, SlotFacts]],
    stock_lengths: dict[str, Mm | None],
) -> tuple[list[MemberRunPlan], list[ContinuityNote]]:
    """The whole derivation, for one run's bays in station order.

    `slots_by_span` is span id -> slot key -> facts; `stock_lengths` is keyed by
    `SlotFacts.eligibility_key` — the shortest stock length every candidate
    product in that set can be bought in, or None where any of them declares
    none. Keyed by the candidate SET rather than by the slot key because one slot
    key can be filled from different shelves in two segments of one run, and the
    piece is planned inside a chain where the set is the same by construction.

    **Why the SHORTEST.** Which product fills the slot is fulfilment's answer,
    not generation's, so a slot with several candidates has not decided its own
    stock length yet. Claiming continuity on the longest would plan a piece a
    cheaper candidate cannot cut; the shortest claims it only where every
    candidate can make it, and per-bay is what the engine already did. Where an
    option HAS narrowed the slot to one product — the colour in obligation 14's
    own example — there is one candidate and the shortest is simply its length.
    """
    runs: list[MemberRunPlan] = []
    notes: list[ContinuityNote] = []
    slot_keys: list[str] = []
    seen: set[str] = set()
    for bay in bays:
        for key in slots_by_span.get(bay.span_id, {}):
            if key not in seen:
                seen.add(key)
                slot_keys.append(key)

    for slot_key in slot_keys:
        i = 0
        while i < len(bays):
            slot = slots_by_span.get(bays[i].span_id, {}).get(slot_key)
            if slot is None or not _continuable(slot) or not _wants_continuity(slot):
                i += 1
                continue
            # the maximal chain of bays this piece COULD cross if stock allowed
            j = i
            while j + 1 < len(bays):
                nxt = slots_by_span.get(bays[j + 1].span_id, {}).get(slot_key)
                if nxt is None or _chain_break(bays[j], bays[j + 1], slot, nxt):
                    break
                j += 1
            chain = bays[i : j + 1]
            chain_slots = [slots_by_span[b.span_id][slot_key] for b in chain]
            stock = stock_lengths.get(slot.eligibility_key)

            capable = slot.post_joint == "through"
            # THE DERIVATION, and the only place it happens. No stock length is
            # not "as far as it will go" — it is not knowing, and not knowing is
            # reported rather than guessed, the way an uncovered `max_span_mm` is
            # a fallback plus a warning rather than a number wearing certainty.
            derived_n: int | None
            if not capable:
                # `lands` says so and `unstated` has not said; both are cut per
                # bay today and `PostJoint` records why that difference is kept
                derived_n = 1
            elif stock is None:
                derived_n = None       # nothing to measure against: an ABSTENTION
            else:
                derived_n = _greedy_extent(chain, chain_slots, stock)
            # What an authored `continuous` asks for: as far as one piece can be
            # cut, and — for the contract's own case, a guide that states the
            # behaviour and gives no length — the whole chain when nothing says
            # how long a piece can be.
            override_n = _greedy_extent(chain, chain_slots, stock)
            n, disagreement = _apply_override(
                slot.continuity, derived_n, override_n)

            if stock is None and slot.continuity != "per_bay":
                # Nothing states how long a piece of this can be bought, so
                # nothing BOUNDS the answer — and that is true whether the
                # derivation was asking (it abstains, and the member is cut per
                # bay) or an authored `continuous` was (it runs the whole chain).
                # Reported in both cases, because the second is the one that
                # invents a number: an unbounded piece over a fifty-bay chain is
                # one 120 m rail on the cut list, and `_piece_too_long` only
                # guards divisible stock, so nothing downstream would catch it.
                # The chain is still a real bound — a corner, a gate or a grade
                # ends it — but it is not a bound anybody chose. Not reported
                # under an authored `per_bay`: there the author bounded it, and
                # a missing stock length changed nothing.
                #
                # An AUTHORED slot cannot arrive here — `validate_model` refuses a
                # length rule backed by a product that declares no length, and
                # that is the same test as this one (`match.stock_length_mm`).
                # The open door is the seam M-LEGACY uses: an eligibility rebuilt
                # at generation from the run's resolved `demand_skus`, which is
                # never seen by the validator. That is a real path, so this is a
                # warning rather than an assertion.
                notes.append(ContinuityNote(
                    code="continuity_stock_length_unknown", slot_key=slot_key,
                    span_ids=[b.span_id for b in chain],
                    params={"slot": slot_key, "element": chain[0].span_id,
                            "role": slot.role, "built_bays": n},
                ))
            if disagreement is not None:
                # the WHOLE chain: an authored `per_bay` over four bays is
                # applied to four, and `element_refs` is what highlights them
                where = [b.span_id for b in chain]
                params: dict[str, str | int] = {
                    "slot": slot_key,
                    "element": chain[0].span_id,
                    "authored": slot.continuity,
                    "derived_bays": derived_n or 0,
                    "built_bays": n,
                    "stock_length_mm": stock if stock is not None else 0,
                    "span_mm": chain[0].width_mm,
                }
                # the two codes as LITERALS, for the locale guard's sake
                if disagreement == "unbuildable":
                    notes.append(ContinuityNote(
                        code="continuity_override_unbuildable",
                        slot_key=slot_key, span_ids=where, params=params))
                else:
                    notes.append(ContinuityNote(
                        code="continuity_override_disagrees",
                        slot_key=slot_key, span_ids=where, params=params))
            if n > 1:
                runs.append(MemberRunPlan(
                    slot_key=slot_key, role=slot.role,
                    span_ids=[b.span_id for b in chain[:n]],
                    through_post_ids=[b.through_post_id for b in chain[: n - 1]
                                      if b.through_post_id],
                    length_mm=_piece_length(chain[:n], chain_slots[:n]),
                    qty=slot.qty, length_rule=slot.length_rule,
                    length_basis=slot.length_basis,
                    # What actually FIXED this extent. An author who merely
                    # agreed with the arithmetic did not decide it, and a
                    # sentence saying "because the model says so" would drop the
                    # stock length that did.
                    basis="stock_length" if derived_n == n else "authored",
                    stock_length_mm=stock, authored=slot.continuity,
                ))
            # How far to move on. A piece that was made covers its own bays and
            # the next question starts after it. A chain settled UNIFORMLY —
            # an override that put it per bay, or a derivation that abstained for
            # want of a stock length — is settled for all of its bays at once,
            # and re-entering it bay by bay would report the same thing n times.
            #
            # The remaining case (derived, per bay, because THIS bay and its
            # neighbour do not fit one piece) advances by one and no further: bay
            # widths vary, and a 4000 mm bay refusing to pair with its neighbour
            # says nothing about the two 1000 mm bays after it.
            if n > 1:
                i += n
            elif slot.continuity != "derived" or derived_n is None:
                i += len(chain)
            else:
                i += 1
    return runs, notes
