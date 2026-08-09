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
