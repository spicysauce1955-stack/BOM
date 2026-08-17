"""Matching catalog items to a part's specification.

A part declares what it NEEDS; an item declares what it IS; an item may serve the
part when its specs cover the requirement. This module is the "may serve" step,
and it produces `EligibleItem`s — the shape a slot has always carried and a run
has always frozen — so nothing downstream of eligibility changes.

That is the whole design: the matcher sits ABOVE the mechanism that already
exists rather than replacing it. `resolve_supply`, `select_supply`, `fulfill()`,
the parts ledger, the material drawer and the decision graph are untouched, and
freezing comes free because a run already snapshots its members.

The predicate is the owned `Expr` AST and the owned evaluator (ADR-0005). There
is no second rule language here, and there is no matching vocabulary in code: a
predicate names the attrs it reads, so a company that stocks something new adds a
product and a rule, not a release.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fenceai.catalog.model import Catalog
from fenceai.fencemodel.model import Eligibility, EligibleItem, PanelSpec
from fenceai.knowledge.ast import MissingField, evaluate_expr

if TYPE_CHECKING:
    from fenceai.fencemodel.resolve import PanelContext


def match_eligibility(
    eligibility: Eligibility, catalog: Catalog, facts: dict,
) -> Eligibility:
    """Resolve a spec-declared eligibility into concrete members.

    Authored eligibility passes through untouched — the two modes are exclusive
    and `validate_model` refuses a slot that sets both.

    `facts` is the context the predicate is evaluated against, beside the
    candidate itself: `{"item": <that product's attrs>, "panel": {...}}`. Every
    relation this design needs is item-against-PANEL rather than item-against-
    item, which is what removes any need for a resolution order — a post is
    matched against the panel's rail positions, a cap against an already-chosen
    post. There is never a pair of open choices to solve at once.

    The returned eligibility carries NO predicate. Members are the frozen answer;
    a predicate riding along into a stored run would let a later reader re-run it
    against a moved catalog and get a different candidate set for the same run,
    which is exactly what `catalog_hash` narrowing relies on being impossible.
    """
    if eligibility.predicate is None:
        return eligibility
    members = [
        EligibleItem(sku=sku)
        for sku in sorted(catalog.products)
        if _covers(eligibility.predicate, catalog.products[sku], facts)
    ]
    return eligibility.model_copy(update={"members": members, "predicate": None})


# What an item IS, as a predicate sees it: the catalog author's open `attrs` bag,
# plus two RESERVED keys that always win.
#
# `consumption` earns its place because "bought by the length" is the difference
# between a product that can back a rail slot and one that cannot, and it is a
# typed field rather than an attr — without it a rail's requirement is
# inexpressible and every author would have to hand-tag their bar stock. `sku` is
# there so a predicate can name a specific product without leaving the mechanism.
#
# Reserved rather than merged politely: if an attrs key shadowed one of these,
# two products could disagree about what `item.consumption` even means.
_RESERVED = ("sku", "consumption")


def _item_ctx(product) -> dict:
    """Everything this item declares about itself, under one namespace.

    Typed capabilities sit beside the open `attrs` bag rather than under a prefix
    of their own: a predicate asks "how wide is its face", and where the catalog
    happens to keep that answer is not the author's problem. Typing them for CODE
    must not put them out of reach of DATA.

    A capability the product does not declare is OMITTED, not passed as None —
    `_covers` reads a missing field as "has not covered the requirement", which
    is the honest answer for a post whose face width nobody recorded. A None
    would compare as a value and quietly satisfy `!=`.
    """
    declared = {k: v for k, v in product.capabilities.model_dump().items()
                if v is not None}
    return {**product.attrs, **declared, "sku": product.sku,
            "consumption": product.consumption.kind}


def panel_facts(ctx: "PanelContext") -> dict:
    """What a predicate may know about the bay it is being fitted to.

    One definition, so "what can an eligibility rule read about the panel" is
    answerable by reading this function rather than by grepping call sites. Every
    entry is settled BEFORE the panel is resolved — which is also the constraint
    that keeps posts resolvable later: a post's opening cannot depend on the
    opening its own face helps define.
    """
    return {"panel": {
        "height_mm": ctx.height_mm,
        "centre_width_mm": ctx.centre_width_mm,
        "clear_width_mm": ctx.clear_width_mm,
        "vertical": ctx.vertical,
    }}


def post_panel_facts(
    *, model_id: str, height_mm: int, vertical: str, rail_positions_mm: list[int],
) -> dict:
    """What a POST's predicate may know about the bay it stands beside.

    A strictly smaller set than `panel_facts`, and the difference is the cycle
    rule: a bay's clear opening is measured TO its posts' faces, so a post chosen
    BY that opening would be choosing itself. Everything here is settled from the
    bay's HEIGHT, before any post is known, which is what makes the resolution
    order a DAG.

    The keys are `POST_PREDICATE_PANEL_FACTS` — the set `validate_model` refuses
    a post predicate for reading outside of. Two statements of one set would drift
    the moment either moved, so a test pins them equal.
    """
    return {"panel": {
        "model_id": model_id,
        "height_mm": height_mm,
        "vertical": vertical,
        "rail_positions_mm": rail_positions_mm,
    }}


def chosen_post_facts(product) -> dict:
    """What a CAP's predicate may know: the post it caps, already chosen.

    Ordered, not circular — which is the whole reason `cap` nests inside
    `PostSlot`. A cap asks about its post because the post was resolved first;
    nothing ever asks a post about its cap.
    """
    return {"post": _item_ctx(product)}


def match_spec(spec: PanelSpec, catalog: Catalog, facts: dict) -> PanelSpec:
    """Every spec-declared eligibility in one panel spec, resolved once.

    A spec with no predicate anywhere is returned AS IS rather than deep-copied:
    every shipped model authors its members, so this must cost nothing on the
    path the compatibility gate protects.
    """
    holders = _holders(spec)
    if not any(h.requirement.eligibility.predicate is not None for h in holders):
        return spec
    resolved = spec.model_copy(deep=True)
    for holder in _holders(resolved):
        holder.requirement.eligibility = match_eligibility(
            holder.requirement.eligibility, catalog, facts,
        )
    return resolved


def _holders(spec: PanelSpec) -> list:
    """Everything in a spec that carries a requirement. Mirrors
    `model._requirements`, which returns keys rather than the objects to mutate."""
    return [
        *spec.frame,
        *(spec.infill.pattern if spec.infill else []),
        *spec.fixings,
    ]


def _covers(predicate, product, facts: dict) -> bool:
    """Does this item's own spec satisfy the requirement?

    A `MissingField` is a NO, not a "not applicable". The knowledge evaluator
    reads it the other way because there the question is whether a rule fires
    against a context that may legitimately lack the field. Here the question is
    whether an item covers a requirement, and an item that cannot answer has not
    covered it — a product declaring no `material` must not be swept into a slot
    that asked for vinyl.

    Sorted by SKU with the default priority and approval: `resolve_supply` groups
    by the members' `(sku, priority, approval)` signature and grouping decides
    which product is chosen, so a varying order would change the answer and not
    merely the JSON. Preference between matched items is `select_supply`'s
    planned-cost decision, which already writes the node that explains it.
    """
    try:
        return bool(evaluate_expr(predicate, {**facts, "item": _item_ctx(product)}))
    except MissingField:
        return False
