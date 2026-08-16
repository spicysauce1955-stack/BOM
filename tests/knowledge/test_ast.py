"""The condition AST itself, apart from the evaluator that runs it."""

from __future__ import annotations

from fenceai.knowledge.ast import (
    And, Between, Cmp, FieldRef, FnCall, In, Lit, Not, Or, field_paths,
)


def test_field_paths_reports_every_context_path_an_expression_reads():
    """Needed to tell a bay-INDEPENDENT eligibility predicate (checkable when the
    model is authored) from one that reads the panel it is being fitted to (only
    answerable per bay). Walks every branch of the union, so a new node type that
    can hold a sub-expression cannot hide a read."""
    expr = And(items=[
        Cmp(cmp="==", left=FieldRef(path="item.material"), right=Lit(value="vinyl")),
        Or(items=[
            Not(item=Cmp(cmp=">", left=FieldRef(path="item.width_mm"),
                         right=FieldRef(path="panel.clear_width_mm"))),
            In(item=FieldRef(path="item.finish"), options=["mill"]),
        ]),
        Between(item=FieldRef(path="panel.height_mm"), low=0, high=3000),
        FnCall(name="abs", args=[FieldRef(path="item.face_width_mm")]),
    ])
    assert field_paths(expr) == {
        "item.material", "item.width_mm", "panel.clear_width_mm",
        "item.finish", "panel.height_mm", "item.face_width_mm",
    }


def test_field_paths_of_a_literal_is_empty():
    assert field_paths(Lit(value=1)) == set()
