"""Engineering demand derived from a strategy (material-optimization.md).

Pure: strategy + catalog -> requirement lines, every line pegged to the strategy
elements that caused it. Knowledge-resolved quantities (rails/screws per span) were
already resolved during generation and live on the Span — demand needs no knowledge
access (module map, critic finding 7). Purchasing knows nothing yet — that's
fulfillment.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.core.errors import ReadRefused
from fenceai.core.units import Mm
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.strategy.model import Strategy

DEMAND_POLICY_DEFAULTS = {
    "rail_sku": "RAIL-3000",
    "screw_sku": "SCREW-S10",
    "concrete_sku": "CONC-25",
    "cap_sku": "POST-CAP",  # golden-scenarios shared catalog: 1 cap per post
}


class DemandLine(BaseModel):
    """What the fence NEEDS. One lifecycle state, not two.

    Deliberately no `sku` and no `unit`. Which product satisfies this is
    `resolve_supply`'s answer, and the unit is a property of the product it
    chooses — demand guessed the unit three different ways (beside the sku, from
    `role`, from `length_mm is not None`) and was wrong each time, reporting the
    same demand as unassigned AND from-stock at once.

    Both were once fields here, defaulted to `""` and filled in later by mutating
    this object. That made the type claim a product through the whole half of its
    life where it had none, and left "a blank sku never reaches `fulfill()`"
    resting on caller discipline — which `fulfill()`'s refusal records having been
    broken at all three routes by a three-word edit, with zero test failures.

    `eligibility` is always populated, including for the products KNOWLEDGE
    chose. A post's sku is not less of a choice for having been made earlier, and
    expressing it as a one-member eligibility is what lets `resolve_supply` stop
    branching on whether a line already knows its own answer.
    """

    id: str
    engineering_qty: int
    cut_length_mm: Mm | None = None
    length_basis: str | None = None  # "width" | "slope" (Research A pitfall 4)
    pegs: list[str] = []  # strategy element ids
    # what this line IS, structurally. Presentation depends on it — a customer
    # proposal names posts and panels but describes fixings and concrete rather
    # than itemising them — and guessing that from a SKU string would be a lie.
    role: str = ""  # post | cap | concrete | rail | screw | infill | gate_kit
    slot_key: str = ""     # sub-element identity: which part of the panel this is
    eligibility: Eligibility = Eligibility()


def derive_requirements(
    strategy: Strategy,
    catalog: Catalog,
    policy: dict | None = None,
) -> list[DemandLine]:
    policy = {**DEMAND_POLICY_DEFAULTS, **(policy or {})}
    lines: list[DemandLine] = []
    n = 0

    def add(qty: int, pegs: list[str], **kw) -> None:  # noqa: D401
        nonlocal n
        n += 1
        lines.append(
            DemandLine(id=f"req{n:04d}", engineering_qty=qty, pegs=pegs, **kw)
        )

    def chosen(sku: str) -> Eligibility:
        """A product KNOWLEDGE already chose, said the same way as every other
        answer to "which items could supply this". It is still a choice — one
        with a single candidate — and saying it this way is what keeps
        `resolve_supply` to one path and one feasibility gate."""
        return Eligibility(members=[EligibleItem(sku=sku)])

    for post in strategy.posts:
        add(1, [post.id], role="post", eligibility=chosen(post.sku))
        # the MODEL's cap if its line ships one, the company default otherwise.
        # `post.cap_sku` is "" for every fence built before a model could own its
        # post, which is exactly when the company default is the right answer.
        add(1, [post.id], role="cap",
            eligibility=chosen(post.cap_sku or policy["cap_sku"]))
        if post.mounting == "ground":
            add(1, [post.id], role="concrete",
                eligibility=chosen(policy["concrete_sku"]))

    # Members the run already decided are ONE piece across several bays
    # (contract obligation 14, derived in `strategy/continuity.py`). Demand does
    # not decide this and does not re-derive it: it reads the answer and buys
    # what the answer says. A rail running through three bays is one piece bought
    # once — emitting the per-bay line as well would order three.
    continuous = {(span_id, member.slot_key)
                  for member in strategy.member_runs
                  for span_id in member.span_ids}

    for span in strategy.spans:
        if span.panel is None:
            # A run stored before the fence-model change has rail_count and
            # screws_count but no panel. Falling back to those would make demand
            # disagree with what the run recorded, so the read is refused — but
            # as code + params, because "no structure yet" (what the tab said
            # while this surfaced as a raw English ValueError) is false: there
            # IS structure, it just cannot be read without regenerating.
            raise ReadRefused(
                code="run_predates_fence_model",
                message=f"span {span.id} has no panel — regenerate the run; "
                        "stored runs from before the fence-model change are read "
                        "with their legacy fields intact",
                span_id=span.id,
            )
        for slot in span.panel.slots:
            if (span.id, slot.slot_key) in continuous:
                # bought once for the whole member run, below — not once per bay
                continue
            # No unit here. A slot's cut length says the part is cut TO a length,
            # not that its product is bought BY the metre: an indivisible post
            # carrying attrs.length_mm is explicitly allowed to back a
            # length_rule slot (validate_model._can_supply_length) and is still
            # counted in eaches. Only the chosen product knows, and the product
            # is not chosen yet — resolve_supply stamps the unit when it is.
            add(
                slot.qty, [span.id],
                cut_length_mm=slot.length_mm, length_basis=slot.length_basis,
                role=slot.role, slot_key=slot.slot_key, eligibility=slot.eligibility,
            )

    for member in strategy.member_runs:
        # ONE line, pegged to every bay the piece crosses. `qty` is the slot's own
        # count and is NOT multiplied by the bays: two rails run the length of the
        # member run, they do not become two per bay. That multiplication is
        # exactly the over-ordering obligation 14 exists to stop.
        add(
            member.qty, list(member.span_ids),
            cut_length_mm=member.length_mm, length_basis=member.length_basis,
            role=member.role, slot_key=member.slot_key,
            eligibility=_first_span_eligibility(strategy, member),
        )

    for gate in strategy.gates:
        if gate.kit_sku:  # no kit fits this opening — the strategy already said so
            add(1, [gate.id], role="gate_kit", eligibility=chosen(gate.kit_sku))

    return lines


def _first_span_eligibility(strategy: Strategy, member) -> Eligibility:
    """The candidate set the member run was derived against.

    Read off the first bay it covers rather than stored a second time on the
    member run: the derivation only groups bays whose candidate sets are
    identical (`continuity._chain_break`), so every bay in the run answers this
    the same way, and one copy cannot drift from the other.
    """
    span = next((s for s in strategy.spans if s.id == member.span_ids[0]), None)
    slot = next((s for s in (span.panel.slots if span and span.panel else [])
                 if s.slot_key == member.slot_key), None)
    if slot is None:
        # A stored strategy whose member run names a bay or a slot that is no
        # longer there. Refused with a code for the same reason
        # `run_predates_fence_model` is, a few lines up: a bare `next()` would
        # raise StopIteration inside a generator expression and reach the route
        # as an unexplained RuntimeError, and the remedy — regenerate — is one
        # the reader can act on only if they are told it.
        raise ReadRefused(
            code="member_run_unreadable",
            message=f"member run {member.id} names span "
                    f"{member.span_ids[0]} / slot {member.slot_key}, which this "
                    "strategy does not have — regenerate the run",
            member_id=member.id, span_id=member.span_ids[0],
            slot_key=member.slot_key,
        )
    return slot.eligibility
