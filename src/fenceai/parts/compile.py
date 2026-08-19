"""A part's authored spec, as the owned Expr AST.

Authoring sugar, not a second rule engine (ADR-0005). Everything here emits nodes
`knowledge/ast.py` already defines and `evaluate_expr` already evaluates, and the
result is a CONJUNCTION of simple terms — which is not incidental: it is the shape
`sole_excluding_term` needs to name the one term that excluded everybody.
"""

from __future__ import annotations

from fenceai.knowledge.ast import And, Between, Cmp, Expr, FieldRef, FnCall, In, Lit
from fenceai.parts.model import Part, SpecField


def compile_spec(part: Part) -> Expr:
    return And(items=[compile_field(f) for f in part.spec])


def compile_field(f: SpecField) -> Expr:
    path = f"item.{f.key}"
    if f.agree == "supplies":
        # ONE term, not a disjunction over consumption kinds: `stock_length_mm` is
        # defined for both (see match._item_ctx). An item declaring neither a
        # purchase length nor a capability length has no such key, `lookup` raises
        # MissingField, and `_covers` reads that as "has not covered the
        # requirement". The comparison IS the null check, through the mechanism the
        # matcher already relies on rather than a second one.
        return Cmp(cmp=">=", left=FieldRef(path="item.stock_length_mm"), right=Lit(value=0))
    if f.agree == "covers":
        # The ITEM's declared set must include everything the part declares. The
        # other side is computed, which is exactly why `In` cannot express it —
        # `In.options` is a literal list — and why this is the function seam's first
        # real user.
        return FnCall(name="covers", args=[FieldRef(path=path), Lit(value=f.value)])
    if f.agree == "among":
        # The mirror: the ITEM's value is one of the ones the PART lists. `In`
        # already holds a computed item against a literal options list, so this
        # needs no machinery at all.
        return In(item=FieldRef(path=path), options=list(f.value))
    if f.agree == "between":
        low, high = f.value
        return Between(item=FieldRef(path=path), low=low, high=high)
    return Cmp(cmp=f.agree, left=FieldRef(path=path), right=Lit(value=f.value))
