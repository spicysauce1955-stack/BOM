"""A variant's condition as a sentence (static/js/condition-sentence.js).

The stored shape is and stays `Expr` (knowledge/ast.py). This module reads the
ONE shape every shipped model uses — a field compared to a literal — into three
fields, and writes it back; anything else reads as `null`, and the raw JSON box
stays in charge of it. That fallback IS the parity guarantee: a condition the
sentence cannot say is left alone rather than rewritten into one it can.

Judged by the real schema and the real evaluator, not by a fixture. A sentence
producing JSON pydantic rejects is a 422 the author cannot see coming; one
producing a VALID expression that means something else is worse.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pydantic import TypeAdapter

from fenceai.knowledge.ast import Expr, evaluate_expr

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

EXPR = TypeAdapter(Expr)

SCRIPT = """
import {
  CONDITION_CMPS, CONDITION_FIELDS, readSentence, writeSentence,
} from "./js/condition-sentence.js";

const HEIGHT_AT_LEAST_1800 = {
  op: "cmp", cmp: ">=",
  left: {op: "field", path: "panel.height_mm"},
  right: {op: "lit", value: 1800},
};

console.log(JSON.stringify({
  fields: CONDITION_FIELDS,
  cmps: CONDITION_CMPS,
  read: readSentence(HEIGHT_AT_LEAST_1800),
  round_trip: writeSentence(readSentence(HEIGHT_AT_LEAST_1800)),
  // the shapes the sentence cannot say: an `and`, a field-to-field comparison,
  // a literal on the left, and nothing at all
  not_a_sentence: [
    readSentence({op: "and", items: [HEIGHT_AT_LEAST_1800]}),
    readSentence({op: "cmp", cmp: ">=",
                  left: {op: "field", path: "a"}, right: {op: "field", path: "b"}}),
    readSentence({op: "cmp", cmp: ">=",
                  left: {op: "lit", value: 1}, right: {op: "field", path: "a"}}),
    readSentence(null),
  ],
  written: CONDITION_CMPS.map((cmp) =>
    writeSentence({path: "panel.width_mm", cmp, value: 2400})),
  // a value the author has half-typed must not become a string in the AST
  blank_value: writeSentence({path: "panel.height_mm", cmp: ">=", value: ""}),
  // ... nor may an unknown comparison silently become one that is not asked for
  unknown_cmp: writeSentence({path: "panel.height_mm", cmp: "~=", value: 10}),
}));
"""


@pytest.fixture(scope="module")
def s():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_shipped_condition_reads_as_a_sentence(s):
    """The condition `defaultVariant()` builds, and the one every demo model
    carries — if the sentence cannot say THAT, it says nothing anybody uses."""
    assert s["read"] == {"path": "panel.height_mm", "cmp": ">=", "value": 1800}


def test_the_sentence_round_trips_to_the_same_ast(s):
    assert s["round_trip"] == {
        "op": "cmp", "cmp": ">=",
        "left": {"op": "field", "path": "panel.height_mm"},
        "right": {"op": "lit", "value": 1800},
    }


def test_anything_the_sentence_cannot_say_reads_as_nothing(s):
    """The parity guarantee: such a condition keeps the raw JSON box rather than
    being silently rewritten into one the three controls can express."""
    assert s["not_a_sentence"] == [None, None, None, None]


def test_every_written_condition_is_an_expression_the_backend_accepts(s):
    """What the round trip alone does not claim: pydantic has to take it, and
    the evaluator has to answer it."""
    for raw in s["written"]:
        expr = EXPR.validate_python(raw)
        assert evaluate_expr(expr, {"panel": {"width_mm": 2400}}) in (True, False)


def test_a_blank_value_is_a_number_not_a_string(s):
    """`{"op":"lit","value":""}` validates and then compares a string to a
    millimetre — an expression that is accepted and means nothing."""
    assert s["blank_value"]["right"] == {"op": "lit", "value": 0}


def test_an_unknown_comparison_falls_back_rather_than_being_written(s):
    assert s["unknown_cmp"]["cmp"] == ">="


def test_the_offered_fields_are_facts_a_bay_actually_carries(s):
    """A path nothing supplies is a variant that never fires — `choose_variant`
    treats a missing field as "not applicable" rather than as an error, so the
    author would get silence and no way to see why."""
    from fenceai.fencemodel.resolve import PanelContext

    supplied = PanelContext(centre_width_mm=2500, clear_width_mm=2400,
                            height_mm=1800).condition_ctx()
    for path in s["fields"]:
        head, _, tail = path.partition(".")
        assert head in supplied, path
        assert tail in supplied[head], path
        assert isinstance(supplied[head][tail], int), (
            f"{path} is not a number, so it does not belong in a numeric sentence")


def test_the_comparisons_offered_are_the_ones_the_evaluator_honours(s):
    """A comparison the sentence writes and `evaluate_expr` does not know is a
    condition that raises inside generation rather than choosing a variant."""
    for cmp in s["cmps"]:
        expr = EXPR.validate_python({"op": "cmp", "cmp": cmp,
                                     "left": {"op": "field", "path": "panel.height_mm"},
                                     "right": {"op": "lit", "value": 1800}})
        assert evaluate_expr(expr, {"panel": {"height_mm": 1800}}) in (True, False)
