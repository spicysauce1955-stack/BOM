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
        add(1, [post.id], role="cap", eligibility=chosen(policy["cap_sku"]))
        if post.mounting == "ground":
            add(1, [post.id], role="concrete",
                eligibility=chosen(policy["concrete_sku"]))

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

    for gate in strategy.gates:
        if gate.kit_sku:  # no kit fits this opening — the strategy already said so
            add(1, [gate.id], role="gate_kit", eligibility=chosen(gate.kit_sku))

    return lines
