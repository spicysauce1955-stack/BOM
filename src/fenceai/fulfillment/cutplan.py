"""1D cut planning: FFD/best-fit with kerf-aware capacity, remnant-first allocation,
and an LP lower-bound optimality certificate (ADR-0007).

Kerf model: each piece costs (length + kerf) against capacity (stock + kerf) — this
credits back the unneeded kerf after the final cut (Research C).
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.catalog.model import DivisibleLinear
from fenceai.core.units import Mm


class CutPiece(BaseModel):
    length_mm: Mm
    requirement_id: str


class PlannedBar(BaseModel):
    source: str  # "new" | inventory item id (remnant)
    stock_length_mm: Mm
    pieces: list[CutPiece] = []
    kerf_total_mm: Mm = 0
    leftover_mm: Mm = 0
    leftover_reusable: bool = False


class CutPlan(BaseModel):
    sku: str
    bars: list[PlannedBar] = []
    new_bar_count: int = 0
    lp_lower_bound: int = 0
    certified_optimal: bool = False
    waste_mm: Mm = 0


class RemnantStock(BaseModel):
    inventory_item_id: str
    length_mm: Mm


def plan_cuts(
    sku: str,
    semantics: DivisibleLinear,
    pieces: list[CutPiece],
    remnants: list[RemnantStock] | None = None,
) -> CutPlan:
    kerf = semantics.kerf_mm
    stock = semantics.purchase_length_mm
    remnants = sorted(remnants or [], key=lambda r: (r.length_mm, r.inventory_item_id))

    for p in pieces:
        if p.length_mm + kerf > stock + kerf:
            raise ValueError(f"piece {p.length_mm} mm exceeds stock length {stock} mm for {sku}")

    # deterministic FFD order: longest first, then stable requirement id
    ordered = sorted(pieces, key=lambda p: (-p.length_mm, p.requirement_id))

    class _Bin:
        __slots__ = ("source", "capacity", "used", "pieces", "stock_len", "is_new")

        def __init__(self, source: str, stock_len: Mm, is_new: bool):
            self.source = source
            self.stock_len = stock_len
            self.capacity = stock_len + kerf
            self.used = 0
            self.pieces: list[CutPiece] = []
            self.is_new = is_new

        def fits(self, cost: Mm) -> bool:
            return self.used + cost <= self.capacity

        def residual(self) -> Mm:
            return self.capacity - self.used

    bins: list[_Bin] = [_Bin(r.inventory_item_id, r.length_mm, is_new=False) for r in remnants]
    for piece in ordered:
        cost = piece.length_mm + kerf
        candidates = [b for b in bins if b.fits(cost)]
        if candidates:
            # best-fit: smallest residual after placement; remnants win ties so long
            # remnants are consumed before opening new stock never increases bars
            best = min(candidates, key=lambda b: (b.residual() - cost, b.is_new, b.source))
        else:
            best = _Bin("new", stock, is_new=True)
            bins.append(best)
        best.used += cost
        best.pieces.append(piece)

    bars: list[PlannedBar] = []
    waste = 0
    for b in bins:
        if not b.pieces:
            continue
        cut_sum = sum(p.length_mm for p in b.pieces)
        kerf_total = kerf * len(b.pieces)
        # leftover after all cuts including the kerf that separates the offcut;
        # negative means the final piece ended flush with the bar end
        leftover = max(0, b.stock_len - cut_sum - kerf * len(b.pieces))
        reusable = leftover >= semantics.min_reusable_remnant_mm
        if not reusable:
            waste += leftover
        bars.append(
            PlannedBar(
                source=b.source, stock_length_mm=b.stock_len, pieces=b.pieces,
                kerf_total_mm=kerf_total, leftover_mm=leftover, leftover_reusable=reusable,
            )
        )

    new_bars = sum(1 for b in bars if b.source == "new")
    total_cost = sum(p.length_mm + kerf for p in pieces)
    # credit only the remnant capacity actually consumed by the plan — crediting all
    # remnant capacity produced false "not optimal" verdicts (critic finding 13)
    used_remnant_capacity = sum(
        p.length_mm + kerf for b in bars if b.source != "new" for p in b.pieces
    )
    lp_bound = max(0, -(-(total_cost - used_remnant_capacity) // (stock + kerf)))
    return CutPlan(
        sku=sku, bars=bars, new_bar_count=new_bars,
        lp_lower_bound=lp_bound, certified_optimal=new_bars == lp_bound,
        waste_mm=waste,
    )
