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
from fenceai.core.units import Mm
from fenceai.fencemodel.model import Eligibility
from fenceai.strategy.model import Strategy

DEMAND_POLICY_DEFAULTS = {
    "rail_sku": "RAIL-3000",
    "screw_sku": "SCREW-S10",
    "concrete_sku": "CONC-25",
    "cap_sku": "POST-CAP",  # golden-scenarios shared catalog: 1 cap per post
}


class RequirementLine(BaseModel):
    id: str
    sku: str = ""          # RESOLVED by fulfillment from `eligibility`, not authored
    engineering_qty: int
    unit: str  # "each" | "cut" | "application"
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
) -> list[RequirementLine]:
    policy = {**DEMAND_POLICY_DEFAULTS, **(policy or {})}
    lines: list[RequirementLine] = []
    n = 0

    def add(sku: str, qty: int, unit: str, pegs: list[str], **kw) -> None:  # noqa: D401
        nonlocal n
        n += 1
        lines.append(
            RequirementLine(id=f"req{n:04d}", sku=sku, engineering_qty=qty, unit=unit, pegs=pegs, **kw)
        )

    for post in strategy.posts:
        add(post.sku, 1, "each", [post.id], role="post")
        add(policy["cap_sku"], 1, "each", [post.id], role="cap")
        if post.mounting == "ground":
            add(policy["concrete_sku"], 1, "application", [post.id], role="concrete")

    for span in strategy.spans:
        if span.panel is None:
            raise ValueError(
                f"span {span.id} has no panel — regenerate the run; "
                "stored runs from before the fence-model change are read with "
                "their legacy fields intact"
            )
        for slot in span.panel.slots:
            # A cut length makes a line a "cut"; everything else is counted in
            # eaches. NOT a role allowlist: fulfill() derives engineering_unit
            # from the product's consumption kind, never from RequirementLine.unit
            # (fulfillment/fulfill.py:133/156/167/196), and role is free-form
            # fence-model data (fencemodel/model.py:57) — a role-keyed guess can
            # disagree with what fulfill() actually does and double-book the
            # parts ledger, which keys asked/purchased on (sku, unit).
            unit = "cut" if slot.length_mm is not None else "each"
            add(
                "", slot.qty, unit, [span.id],
                cut_length_mm=slot.length_mm, length_basis=slot.length_basis,
                role=slot.role, slot_key=slot.slot_key, eligibility=slot.eligibility,
            )

    for gate in strategy.gates:
        if gate.kit_sku:  # no kit fits this opening — the strategy already said so
            add(gate.kit_sku, 1, "each", [gate.id], role="gate_kit")

    return lines
