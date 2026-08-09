"""Engineering demand derived from a strategy (material-optimization.md).

Pure: strategy + knowledge + catalog -> requirement lines, every line pegged to the
strategy elements that caused it. Purchasing knows nothing yet — that's fulfillment.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.core.units import Mm
from fenceai.knowledge.evaluator import resolve_param
from fenceai.knowledge.model import KnowledgeBase
from fenceai.strategy.model import Strategy

DEMAND_POLICY_DEFAULTS = {
    "rail_sku": "RAIL-3000",
    "screw_sku": "SCREW-S10",
    "concrete_sku": "CONC-25",
}


class RequirementLine(BaseModel):
    id: str
    sku: str
    engineering_qty: int
    unit: str  # "each" | "cut" | "application"
    cut_length_mm: Mm | None = None
    length_basis: str | None = None  # "width" | "slope" (Research A pitfall 4)
    pegs: list[str] = []  # strategy element ids


def derive_requirements(
    strategy: Strategy,
    knowledge: KnowledgeBase,
    catalog: Catalog,
    policy: dict | None = None,
) -> list[RequirementLine]:
    policy = {**DEMAND_POLICY_DEFAULTS, **(policy or {})}
    lines: list[RequirementLine] = []
    n = 0

    def add(sku: str, qty: int, unit: str, pegs: list[str], **kw) -> None:
        nonlocal n
        n += 1
        lines.append(
            RequirementLine(id=f"req{n:04d}", sku=sku, engineering_qty=qty, unit=unit, pegs=pegs, **kw)
        )

    for post in strategy.posts:
        add(post.sku, 1, "each", [post.id])
        if post.mounting == "ground":
            add(policy["concrete_sku"], 1, "application", [post.id])

    screws_per_span = _param(knowledge, "screws_per_span", default=8)
    for span in strategy.spans:
        cut_len = span.slope_len_mm if span.rail_cut_basis == "slope" else span.width_mm
        add(
            policy["rail_sku"], span.rail_count, "cut", [span.id],
            cut_length_mm=cut_len, length_basis=span.rail_cut_basis,
        )
        add(policy["screw_sku"], screws_per_span, "each", [span.id])

    for gate in strategy.gates:
        add(gate.kit_sku, 1, "each", [gate.id])

    return lines


def _param(kb: KnowledgeBase, param: str, default: int) -> int:
    res = resolve_param(kb, {"scope": {}}, param)
    if res.winner:
        return next(a.value for a in res.winner.actions if a.kind == "set_param")
    return default
