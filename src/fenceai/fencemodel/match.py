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

from fenceai.catalog.model import Catalog, DivisibleLinear
from fenceai.core.units import Mm
from fenceai.fencemodel.model import Eligibility, EligibleItem, PanelSpec
from fenceai.knowledge.ast import (
    And, MissingField, evaluate_expr, lookup, register_function,
)

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
_RESERVED = ("sku", "consumption", "stock_length_mm")


def stock_length_mm(product) -> Mm | None:
    """How long a piece can you get from ONE purchase unit — the single definition.

    Bar stock carries it on its consumption (`purchase_length_mm`); a fixed piece
    carries it as a capability. Before this, neither was reachable by a predicate —
    `_item_ctx` merged attrs, capabilities, sku and consumption KIND, so a bar's
    length was invisible — while `_can_supply_length` reached into the consumption
    object for it. Two definitions of one fact would disagree the moment either
    moved, so `_can_supply_length` is now expressed in terms of this one.

    None means "declares no length anywhere", and `_item_ctx` OMITS the key rather
    than passing None: a None would compare as a value and quietly satisfy `>= 0`.
    """
    if isinstance(product.consumption, DivisibleLinear):
        return product.consumption.purchase_length_mm
    return product.capabilities.length_mm


@register_function("covers")
def _covers_fn(item_value, part_value, *, ctx=None) -> bool:
    """The ITEM's declared set includes everything the PART declares.

    A scalar on either side is a one-element set, which is what lets one operator
    serve "my token is among yours" and "your holes include mine" without the author
    telling them apart. Its mirror — the item's value is one of the ones the part
    lists — is `among`, and that one compiles to `In` because there the computed side
    is the item. Two operators, because neither subsumes the other: `covers` asks
    about a set the ITEM declares, `among` about a set the PART declares.
    """
    have = set(item_value) if isinstance(item_value, list) else {item_value}
    need = set(part_value) if isinstance(part_value, list) else {part_value}
    return need <= have


# `_item_ctx` memoised by the identity of the PRODUCT it describes.
#
# Migrating authored member lists to predicates turned matching into a full-catalog
# scan per slot per bay: on a 120 m run against a 4623-product catalog that is
# 957 000 calls, 2.35 s of a 2.5 s generation, almost all of it a `model_dump()` of
# three optional integers. The context is a pure function of the product, so this
# computes the same dict fewer times and nothing else.
#
# Keyed by the product's IDENTITY rather than by its sku, because a catalog is
# mutated by REPLACING a product (`catalog.products[sku] = ...`, the /api/catalog
# route and half the strategy tests) — an sku key would serve the old answer for
# the new product, which is the one failure a memo must not have. The product is
# held STRONGLY beside its context so its id cannot be recycled underneath the key
# while the entry lives; `products` are documents that are replaced and never
# edited in place, which is what makes identity a sound key at all.
#
# Cleared wholesale at a bound rather than evicted one at a time: this is a memo
# over one generation's catalog, not a cache anybody is tuning, and a fresh catalog
# arrives with every request.
_ITEM_CTX: dict[int, tuple[object, dict]] = {}
_ITEM_CTX_MAX = 20_000


def _item_ctx(product) -> dict:
    key = id(product)
    hit = _ITEM_CTX.get(key)
    if hit is not None and hit[0] is product:
        return hit[1]
    ctx = _build_item_ctx(product)
    if len(_ITEM_CTX) >= _ITEM_CTX_MAX:
        _ITEM_CTX.clear()
    _ITEM_CTX[key] = (product, ctx)
    return ctx


def _build_item_ctx(product) -> dict:
    """Everything this item declares about itself, under one namespace.

    Typed capabilities sit beside the open `attrs` bag rather than under a prefix
    of their own: a predicate asks "how wide is its face", and where the catalog
    happens to keep that answer is not the author's problem. Typing them for CODE
    must not put them out of reach of DATA.

    A capability the product does not declare is OMITTED, not passed as None —
    `_covers` reads a missing field as "has not covered the requirement", which
    is the honest answer for a post whose face width nobody recorded. A None
    would compare as a value and quietly satisfy `!=`.

    `_RESERVED` keys are filtered OUT of `attrs` before anything is merged in,
    not merely overwritten after — an unconditional assignment (`sku`,
    `consumption`) can't be shadowed by an attrs entry either way, but
    `stock_length_mm` is only set when the product HAS one, so if attrs were
    merged first a `stock_length_mm` an author left in attrs would survive on
    every product that declares no real length, and a `supplies` predicate
    (`item.stock_length_mm >= 0`) would admit it on a stale attrs value.
    """
    declared = {k: v for k, v in product.capabilities.model_dump().items()
                if v is not None}
    ctx = {k: v for k, v in product.attrs.items() if k not in _RESERVED}
    ctx.update(declared)
    ctx["sku"] = product.sku
    ctx["consumption"] = product.consumption.kind
    length = stock_length_mm(product)
    if length is not None:
        ctx["stock_length_mm"] = length
    return ctx


def item_value(product, path: str):
    """The value a predicate reading `path` would see on this product.

    Exists so a caller diagnosing a failed match reads the item exactly as the
    matcher did — through `_item_ctx`, capabilities merged and undeclared fields
    absent — rather than reaching into `attrs` and getting a different answer for
    the same question.
    """
    return lookup({"item": _item_ctx(product)}, path)


def panel_facts(ctx: "PanelContext") -> dict:
    """What a predicate may know about the bay it is being fitted to.

    One definition, so "what can an eligibility rule read about the panel" is
    answerable by reading this function rather than by grepping call sites. Every
    entry is settled BEFORE the panel is resolved — which is also the constraint
    that keeps posts resolvable later: a post's opening cannot depend on the
    opening its own face helps define.

    `site` joins on the same terms and satisfies that constraint trivially: a
    whole-site fact is settled before the fence is drawn, let alone laid out. It
    is here because "this bracket only where it freezes" is an item-against-SITE
    relation and there was no way to say it — the predicate came back
    `MissingField`, `_covers` read that as "has not covered the requirement",
    and the slot silently admitted nothing.
    """
    return {
        "panel": {
            "height_mm": ctx.height_mm,
            "centre_width_mm": ctx.centre_width_mm,
            "clear_width_mm": ctx.clear_width_mm,
            "vertical": ctx.vertical,
        },
        "site": dict(ctx.site),
    }


def sole_excluding_term(
    predicate, catalog: Catalog, facts: dict,
) -> tuple[object, list[str]] | None:
    """Which single TERM of a predicate excluded every candidate, and who it hit.

    `(term, near-miss skus)` when dropping exactly ONE conjunct admits somebody,
    and `None` otherwise — either because the predicate is not a conjunction, or
    because more than one term is doing the excluding, or because dropping any
    one of them still admits nobody.

    That distinction is the whole value of the diagnostic and it mirrors the split
    the codebase already draws between `no_feasible_item` ("candidates were tried
    and none fits") and `no_eligible_item` ("nothing is a candidate"): "your posts
    are routed 50 mm from where this panel wants its rails" is actionable, and
    "no post found" is a mystery. A merged answer would be the mystery.
    """
    if not isinstance(predicate, And) or len(predicate.items) < 2:
        return None
    found: tuple[object, list[str]] | None = None
    for index, term in enumerate(predicate.items):
        rest = And(items=[t for j, t in enumerate(predicate.items) if j != index])
        skus = [m.sku for m in
                match_eligibility(Eligibility(predicate=rest), catalog, facts).members]
        if not skus:
            continue
        if found is not None:
            return None     # more than one term is a discriminator; no single cause
        found = (term, skus)
    return found


def post_panel_facts(
    *, model_id: str, height_mm: int, vertical: str, rail_positions_mm: list[int],
    kind: str, site: dict,
) -> dict:
    """What a POST's predicate may know: the bay it stands beside, and WHERE IT
    STANDS.

    `panel` is a strictly smaller set than `panel_facts`, and the difference is
    the cycle rule: a bay's clear opening is measured TO its posts' faces, so a
    post chosen BY that opening would be choosing itself. Everything under
    `panel` is settled from the bay's HEIGHT, before any post is known, which is
    what makes the resolution order a DAG.

    `post` is the post's own position, and it is NOT part of that cycle — which
    is why it can be here at all. A post's KIND is not derived from the panel:
    it comes from the topology (does this node end a run, turn a corner, or sit
    mid-run), and it is settled before any bay is laid out, let alone resolved.
    It has to be readable, because a routed post is cut at the factory and WHICH
    FACES are cut is decided by exactly this: an end post is routed on one face,
    a line post on two opposite faces, a corner post on two adjacent ones. A
    model that could not read it would name one post SKU for a whole run and
    order every end and every corner wrong.

    The keys are `POST_PREDICATE_PANEL_FACTS` and `POST_PREDICATE_POST_FACTS` —
    the sets `validate_model` refuses a post predicate for reading outside of.
    Two statements of one set would drift the moment either moved, so a test pins
    them equal.

    `mounting` is deliberately NOT here, though it is settled just as early.
    A post's mounting is resolved from knowledge inside `_make_post`, AFTER the
    model's post is chosen, and a `force_mounting` override can move it; putting
    it in front of the predicate would mean resolving it a second time in a
    second place, and the two answers could differ for one post. Mounting also
    already reaches the BOM on its own path (`_resolve_mounting` buys the plate),
    so nothing is inexpressible without it. If a line ever does need it, resolve
    it ONCE at the call sites and pass it in — do not resolve it twice.

    `site` is the third namespace, and the cycle rule does not narrow it at all:
    a whole-site fact is settled before the fence is drawn, so it cannot depend
    on the post it helps choose.

    REQUIRED, with no default, and that is the point rather than an oversight. A
    caller with no site passes `{}` and SAYS so; a caller that forgot cannot
    compile. Defaulting it to `None` collapsed *nobody answered this dimension*
    into *nobody bound this namespace* — the two cases
    `knowledge/evaluator.py::_assert_namespaces_bound` exists to keep apart — and
    collapsing them here would leave the defect this binding closed re-openable
    at any new call site, silently, because an unbound namespace reads as
    not-applicable and the slot falls through to the company default. What makes
    an unanswered dimension not-applicable is that dimension's ABSENCE from the
    dict (`SiteConditions.facts`), never the dict's own.
    """
    return {
        "panel": {
            "model_id": model_id,
            "height_mm": height_mm,
            "vertical": vertical,
            "rail_positions_mm": rail_positions_mm,
        },
        "post": {"kind": kind},
        "site": dict(site),
    }


def chosen_post_facts(product, position: dict) -> dict:
    """What a CAP's predicate may know: the post it caps, already chosen — and
    the same position facts the post itself was chosen by.

    Ordered, not circular — which is the whole reason `cap` nests inside
    `PostSlot`. A cap asks about its post because the post was resolved first;
    nothing ever asks a post about its cap.

    `position` merges into the SAME `post` namespace and WINS over the product's
    attrs, on the same reasoning as `_RESERVED`: `post.kind` has to mean the same
    thing in a cap's predicate as in a post's, or one namespace carries two
    vocabularies and an author has no way to tell which one answered. A cap for
    corner posts only is then expressible, and it reads exactly like the post
    rule that produced the post.
    """
    return {"post": {**_item_ctx(product), **position}}


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
    `model.spec_requirements`, which returns keys rather than the objects to mutate."""
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
