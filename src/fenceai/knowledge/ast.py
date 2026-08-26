"""Closed condition AST (ADR-0005). Never eval() authored strings.

Conditions are data; this module owns the only interpreter. FnCall resolves against
the whitelist registered in `FUNCTIONS` — domain code registers pure functions there.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Literal, Union

from pydantic import BaseModel, Field


class FieldRef(BaseModel):
    op: Literal["field"] = "field"
    path: str  # dotted lookup into the evaluation context


class Lit(BaseModel):
    op: Literal["lit"] = "lit"
    value: Any


class Cmp(BaseModel):
    op: Literal["cmp"] = "cmp"
    cmp: Literal["==", "!=", "<", "<=", ">", ">="]
    left: "Expr"
    right: "Expr"


class And(BaseModel):
    op: Literal["and"] = "and"
    items: list["Expr"]


class Or(BaseModel):
    op: Literal["or"] = "or"
    items: list["Expr"]


class Not(BaseModel):
    op: Literal["not"] = "not"
    item: "Expr"


class In(BaseModel):
    op: Literal["in"] = "in"
    item: "Expr"
    options: list[Any]


class Between(BaseModel):
    op: Literal["between"] = "between"
    item: "Expr"
    low: int
    high: int


class FnCall(BaseModel):
    op: Literal["fn"] = "fn"
    name: str
    args: list["Expr"] = []


Expr = Annotated[
    Union[FieldRef, Lit, Cmp, And, Or, Not, In, Between, FnCall],
    Field(discriminator="op"),
]

for _m in (Cmp, And, Or, Not, In, Between, FnCall):
    _m.model_rebuild()

# Whitelisted pure functions, registered by domain modules.
FUNCTIONS: dict[str, Callable[..., Any]] = {}


def register_function(name: str):
    def deco(fn):
        FUNCTIONS[name] = fn
        return fn

    return deco


class MissingField(Exception):
    """Context lacks a field the condition needs — treated as 'not applicable'."""


def lookup(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise MissingField(path)
    return cur


def walk(expr: Expr):
    """Every node of this expression, parents before children.

    Beside `field_paths` and matching it branch for branch, for its reason: a new
    node type that this does not walk silently NARROWS every caller's check
    rather than breaking it, so the two must be read together and changed
    together.

    `Expr` is an `Annotated[Union[...]]` discriminated union and not a class, so
    `isinstance` cannot be used to find sub-expressions — a structural match is
    the only honest way to do this, and doing it once here keeps a second,
    quietly divergent walker from appearing in a validator.
    """
    yield expr
    match expr:
        case Cmp():
            yield from walk(expr.left)
            yield from walk(expr.right)
        case And() | Or():
            for item in expr.items:
                yield from walk(item)
        case Not() | In() | Between():
            yield from walk(expr.item)
        case FnCall():
            for arg in expr.args:
                yield from walk(arg)


def field_paths(expr: Expr) -> set[str]:
    """Every context path this expression reads.

    Structural, not evaluated — it answers "what would this need to know?"
    without needing it. `validate_model` uses it to tell an eligibility predicate
    that can be checked when a model is AUTHORED (it reads only `item.*`) from
    one that can only be answered per bay (it reads `panel.*`), so authoring
    never refuses a slot for failing a question it was not asked.

    Every branch that can hold a sub-expression is walked, so a new node type
    cannot hide a read: getting this wrong silently narrows the check rather than
    breaking it.
    """
    match expr:
        case FieldRef():
            return {expr.path}
        case Cmp():
            return field_paths(expr.left) | field_paths(expr.right)
        case And() | Or():
            return set().union(*(field_paths(i) for i in expr.items)) if expr.items else set()
        case Not():
            return field_paths(expr.item)
        case In() | Between():
            return field_paths(expr.item)
        case FnCall():
            return set().union(*(field_paths(a) for a in expr.args)) if expr.args else set()
    return set()


def evaluate_expr(expr: Expr, ctx: dict[str, Any]) -> Any:
    match expr:
        case FieldRef():
            return lookup(ctx, expr.path)
        case Lit():
            return expr.value
        case Cmp():
            l, r = evaluate_expr(expr.left, ctx), evaluate_expr(expr.right, ctx)
            return {
                "==": l == r, "!=": l != r,
                "<": l < r, "<=": l <= r, ">": l > r, ">=": l >= r,
            }[expr.cmp]
        case And():
            return all(evaluate_expr(i, ctx) for i in expr.items)
        case Or():
            return any(evaluate_expr(i, ctx) for i in expr.items)
        case Not():
            return not evaluate_expr(expr.item, ctx)
        case In():
            return evaluate_expr(expr.item, ctx) in expr.options
        case Between():
            v = evaluate_expr(expr.item, ctx)
            return expr.low <= v <= expr.high
        case FnCall():
            fn = FUNCTIONS.get(expr.name)
            if fn is None:
                raise MissingField(f"fn:{expr.name}")
            return fn(*(evaluate_expr(a, ctx) for a in expr.args), ctx=ctx)
    raise TypeError(f"unknown expr {expr!r}")
