"""Fulfillment: engineering demand + inventory -> purchase BOM + cut plans + allocations.

Pure over an inventory snapshot; soft allocation only (ADR-0007). Every BOM line and
allocation pegs back to requirement lines (demand pegging, Research C).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.core.units import Cents, Mm
from fenceai.demand.derive import RequirementLine
from fenceai.fulfillment.cutplan import CutPiece, CutPlan, RemnantStock, plan_cuts


class InventoryItem(BaseModel):
    id: str
    sku: str
    kind: Literal["full_stock", "remnant", "opened_package"] = "full_stock"
    qty: int = 1  # count of units (full_stock/opened_package remaining eaches)
    length_mm: Mm | None = None  # remnant length


class Inventory(BaseModel):
    items: list[InventoryItem] = []

    def for_sku(self, sku: str) -> list[InventoryItem]:
        return sorted((i for i in self.items if i.sku == sku), key=lambda i: i.id)


class Allocation(BaseModel):
    inventory_item_id: str
    sku: str
    qty: int = 0
    length_used_mm: Mm | None = None
    pegs: list[str] = []


class BomLine(BaseModel):
    sku: str
    name: str
    purchase_qty: int
    purchase_unit: str
    engineering_qty: int
    engineering_unit: str
    unit_price_cents: Cents
    total_cents: Cents
    overage_qty: int = 0
    pegs: list[str] = []
    notes: list[str] = []


class Bom(BaseModel):
    lines: list[BomLine] = []
    cut_plans: dict[str, CutPlan] = {}
    allocations: list[Allocation] = []
    projected_remnants: list[InventoryItem] = []
    total_cents: Cents = 0


def fulfill(
    requirements: list[RequirementLine],
    catalog: Catalog,
    inventory: Inventory | None = None,
) -> Bom:
    inventory = inventory or Inventory()
    bom = Bom()
    by_sku: dict[str, list[RequirementLine]] = {}
    for r in requirements:
        by_sku.setdefault(r.sku, []).append(r)

    for sku in sorted(by_sku):
        reqs = by_sku[sku]
        product = catalog.products.get(sku)
        pegs = [r.id for r in reqs]
        if product is None:
            # unknown SKU: priced at zero and flagged — never a deep KeyError and
            # never a silent drop (critic finding 15)
            demand = sum(r.engineering_qty for r in reqs)
            bom.lines.append(
                BomLine(
                    sku=sku, name=f"UNKNOWN: {sku}", purchase_qty=demand,
                    purchase_unit="each", engineering_qty=demand,
                    engineering_unit="each", unit_price_cents=0, total_cents=0,
                    pegs=pegs, notes=["unknown product — not in catalog"],
                )
            )
            continue
        sem = product.consumption

        if sem.kind == "divisible_linear":
            pieces = [
                CutPiece(length_mm=r.cut_length_mm, requirement_id=r.id)
                for r in reqs
                for _ in range(r.engineering_qty)
                if r.cut_length_mm is not None
            ]
            remnants = [
                RemnantStock(inventory_item_id=i.id, length_mm=i.length_mm)
                for i in inventory.for_sku(sku)
                if i.kind == "remnant" and i.length_mm
            ]
            plan = plan_cuts(sku, sem, pieces, remnants)
            bom.cut_plans[sku] = plan
            for bar in plan.bars:
                if bar.source != "new":
                    bom.allocations.append(
                        Allocation(
                            inventory_item_id=bar.source, sku=sku,
                            length_used_mm=sum(p.length_mm for p in bar.pieces),
                            pegs=[p.requirement_id for p in bar.pieces],
                        )
                    )
                if bar.leftover_reusable:
                    bom.projected_remnants.append(
                        InventoryItem(
                            id=f"remnant:{sku}:{len(bom.projected_remnants) + 1}",
                            sku=sku, kind="remnant", length_mm=bar.leftover_mm,
                        )
                    )
            if plan.new_bar_count:
                bom.lines.append(
                    _line(
                        product, plan.new_bar_count, "bar",
                        engineering_qty=len(pieces), engineering_unit="cut",
                        pegs=pegs,
                        notes=[] if plan.certified_optimal else
                        [f"heuristic plan: {plan.new_bar_count} bars vs LP lower bound {plan.lp_lower_bound}"],
                    )
                )

        elif sem.kind == "packaged_discrete":
            demand = sum(r.engineering_qty for r in reqs)
            opened = sum(
                i.qty for i in inventory.for_sku(sku) if i.kind == "opened_package"
            )
            for i in inventory.for_sku(sku):
                if i.kind == "opened_package" and i.qty:
                    used = min(i.qty, demand)
                    bom.allocations.append(
                        Allocation(inventory_item_id=i.id, sku=sku, qty=used, pegs=pegs)
                    )
            net = max(0, demand - opened)
            packages = -(-net // sem.qty_per_package)
            if packages:
                bom.lines.append(
                    _line(
                        product, packages, f"box of {sem.qty_per_package}",
                        engineering_qty=demand, engineering_unit=sem.engineering_unit,
                        overage=packages * sem.qty_per_package - net, pegs=pegs,
                    )
                )

        elif sem.kind == "coverage_based":
            applications = sum(r.engineering_qty for r in reqs)
            raw = applications * sem.qty_per_application.num
            purchase = -(-raw // sem.qty_per_application.den)
            if purchase:
                bom.lines.append(
                    _line(
                        product, purchase, sem.purchase_unit,
                        engineering_qty=applications, engineering_unit=sem.engineering_unit,
                        pegs=pegs,
                    )
                )

        else:  # indivisible_discrete and assembly_kit purchase as whole units
            demand = sum(r.engineering_qty for r in reqs)
            on_hand = sum(i.qty for i in inventory.for_sku(sku) if i.kind == "full_stock")
            allocated = min(demand, on_hand)
            if allocated:
                remaining = allocated
                for i in inventory.for_sku(sku):
                    if i.kind == "full_stock" and remaining:
                        used = min(i.qty, remaining)
                        remaining -= used
                        bom.allocations.append(
                            Allocation(inventory_item_id=i.id, sku=sku, qty=used, pegs=pegs)
                        )
            net = demand - allocated
            if net:
                notes = []
                if sem.kind == "assembly_kit":
                    notes = [
                        "kit includes: "
                        + ", ".join(f"{c.qty}x {c.sku}" for c in sem.components)
                    ]
                bom.lines.append(
                    _line(
                        product, net, "each", engineering_qty=demand,
                        engineering_unit="each", pegs=pegs, notes=notes,
                    )
                )

    bom.total_cents = sum(l.total_cents for l in bom.lines)
    return bom


def _line(
    product,
    purchase_qty: int,
    purchase_unit: str,
    *,
    engineering_qty: int,
    engineering_unit: str,
    pegs: list[str],
    overage: int = 0,
    notes: list[str] | None = None,
) -> BomLine:
    return BomLine(
        sku=product.sku, name=product.name,
        purchase_qty=purchase_qty, purchase_unit=purchase_unit,
        engineering_qty=engineering_qty, engineering_unit=engineering_unit,
        unit_price_cents=product.price_cents,
        total_cents=product.price_cents * purchase_qty,
        overage_qty=overage, pegs=pegs, notes=notes or [],
    )
