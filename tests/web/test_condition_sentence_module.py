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
  cmpsFor, CONDITION_CMPS, CONDITION_ENUM_OPTIONS, CONDITION_FIELDS, fieldType,
  readSentence, SITE_CONDITION_FIELDS, writeSentence,
} from "./js/condition-sentence.js";

const HEIGHT_AT_LEAST_1800 = {
  op: "cmp", cmp: ">=",
  left: {op: "field", path: "panel.height_mm"},
  right: {op: "lit", value: 1800},
};

const HVHZ_TRUE = {
  op: "cmp", cmp: "==",
  left: {op: "field", path: "site.hvhz"},
  right: {op: "lit", value: true},
};

const EXPOSURE_IS_C = {
  op: "cmp", cmp: "==",
  left: {op: "field", path: "site.exposure_category"},
  right: {op: "lit", value: "C"},
};

console.log(JSON.stringify({
  fields: CONDITION_FIELDS,
  site_fields: SITE_CONDITION_FIELDS,
  enum_options: CONDITION_ENUM_OPTIONS,
  cmps: CONDITION_CMPS,
  number_cmps: cmpsFor("panel.height_mm"),
  bool_cmps: cmpsFor("site.hvhz"),
  enum_cmps: cmpsFor("site.exposure_category"),
  field_types: {
    height: fieldType("panel.height_mm"),
    width: fieldType("panel.width_mm"),
    hvhz: fieldType("site.hvhz"),
    exposure: fieldType("site.exposure_category"),
  },
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
  // the numeric path, pinned exactly, so a boolean/enum change cannot regress it
  numeric_pin: writeSentence({path: "panel.height_mm", cmp: ">=", value: "1800"}),
  // a boolean field: read, round-trip, and a written `false` (not falsy zero)
  read_hvhz: readSentence(HVHZ_TRUE),
  round_trip_hvhz: writeSentence(readSentence(HVHZ_TRUE)),
  written_hvhz_false: writeSentence({path: "site.hvhz", cmp: "==", value: false}),
  // an unknown comparison on a boolean falls back to equality, not `>=`
  unknown_cmp_hvhz: writeSentence({path: "site.hvhz", cmp: ">=", value: true}),
  // an enum field: read and round-trip
  read_exposure: readSentence(EXPOSURE_IS_C),
  round_trip_exposure: writeSentence(readSentence(EXPOSURE_IS_C)),
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


def test_every_written_condition_says_what_the_author_picked(s):
    """The comparison and the field the author chose, in the document.

    "It validates and returns a bool" is not the claim: a `writeSentence` that
    ignored `cmp` entirely and wrote `>=` every time satisfies that, and turns
    every variant an author writes into the same one — silently, because the
    select still shows what they picked."""
    assert [raw["cmp"] for raw in s["written"]] == s["cmps"]
    assert all(raw["left"] == {"op": "field", "path": "panel.width_mm"}
               for raw in s["written"])
    assert all(raw["right"] == {"op": "lit", "value": 2400} for raw in s["written"])


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


def test_every_numeric_fact_a_bay_carries_is_offered(s):
    """The other direction: a field the context supplies and the sentence does
    not offer is a variant an author cannot write at all, and nothing else would
    notice it going missing."""
    from fenceai.fencemodel.resolve import PanelContext

    supplied = PanelContext(centre_width_mm=2500, clear_width_mm=2400,
                            height_mm=1800).condition_ctx()
    numeric = {f"{head}.{key}"
               for head, facts in supplied.items()
               for key, value in facts.items() if isinstance(value, int)}
    assert set(s["fields"]) == numeric


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


def test_the_comparisons_offered_are_exactly_the_schemas_own(s):
    """EQUALITY, in both directions. A subset assertion passes with the list
    narrowed to one — five comparisons vanish from the variant editor and every
    test stays green — which is the trap `test_panel_model_module` documents for
    the other closed vocabularies."""
    from typing import get_args

    from fenceai.knowledge.ast import Cmp

    assert set(s["cmps"]) == set(get_args(Cmp.model_fields["cmp"].annotation))


def test_the_comparisons_offered_are_the_ones_the_evaluator_honours(s):
    """A comparison the sentence writes and `evaluate_expr` does not know is a
    condition that raises inside generation rather than choosing a variant."""
    for cmp in s["cmps"]:
        expr = EXPR.validate_python({"op": "cmp", "cmp": cmp,
                                     "left": {"op": "field", "path": "panel.height_mm"},
                                     "right": {"op": "lit", "value": 1800}})
        assert evaluate_expr(expr, {"panel": {"height_mm": 1800}}) in (True, False)


# --- site.* : a bool and an enum, added beside the bay's numeric fields -----


def test_the_site_fields_are_a_bool_and_an_enum_not_numbers(s):
    assert s["site_fields"] == ["site.hvhz", "site.exposure_category"]
    assert s["field_types"] == {
        "height": "number", "width": "number",
        "hvhz": "boolean", "exposure": "enum",
    }


def test_the_site_fields_are_facts_a_bay_actually_carries(s):
    """The same guarantee `test_the_offered_fields_are_facts_a_bay_actually_carries`
    makes for the numeric fields, one level down: a path nothing supplies is a
    variant that never fires."""
    from fenceai.project.site import SITE_DIMENSIONS

    for path in s["site_fields"]:
        head, _, tail = path.partition(".")
        assert head == "site", path
        assert tail in SITE_DIMENSIONS, path


def test_the_enum_options_are_the_schemas_own_tokens(s):
    """`SiteConditions.exposure_category` exactly — the closed vocabulary this
    sentence offers must not silently narrow (or widen past) the schema's own,
    the same trap `test_the_comparisons_offered_are_exactly_the_schemas_own`
    documents for the comparisons."""
    from typing import Literal, get_args, get_origin

    from fenceai.project.site import SiteConditions

    annotation = SiteConditions.model_fields["exposure_category"].annotation
    literal = next(a for a in get_args(annotation) if get_origin(a) is Literal)
    assert set(s["enum_options"]["site.exposure_category"]) == set(get_args(literal))


def test_a_boolean_or_an_enum_field_offers_only_equality(s):
    """`site.hvhz >= true` validates and means nothing — the same trap a blank
    numeric value falls into, one type over."""
    assert s["bool_cmps"] == ["==", "!="]
    assert s["enum_cmps"] == ["==", "!="]


def test_a_numeric_field_keeps_every_comparison(s):
    assert s["number_cmps"] == s["cmps"]


def test_a_boolean_condition_reads_as_an_actual_bool(s):
    read = s["read_hvhz"]
    assert read == {"path": "site.hvhz", "cmp": "==", "value": True}
    assert read["value"] is True  # not 1 — JSON keeps bool and int distinct


def test_a_boolean_condition_round_trips_to_the_same_ast(s):
    assert s["round_trip_hvhz"] == {
        "op": "cmp", "cmp": "==",
        "left": {"op": "field", "path": "site.hvhz"},
        "right": {"op": "lit", "value": True},
    }
    assert s["round_trip_hvhz"]["right"]["value"] is True


def test_writing_false_stays_false_not_a_falsy_zero(s):
    written = s["written_hvhz_false"]
    assert written["right"] == {"op": "lit", "value": False}
    assert written["right"]["value"] is False


def test_an_unknown_comparison_on_a_boolean_falls_back_to_equality(s):
    assert s["unknown_cmp_hvhz"]["cmp"] == "=="


def test_an_enum_condition_reads_and_round_trips_as_the_same_token(s):
    read = s["read_exposure"]
    assert read == {"path": "site.exposure_category", "cmp": "==", "value": "C"}
    assert isinstance(read["value"], str)
    assert s["round_trip_exposure"] == {
        "op": "cmp", "cmp": "==",
        "left": {"op": "field", "path": "site.exposure_category"},
        "right": {"op": "lit", "value": "C"},
    }


def test_boolean_and_enum_conditions_are_expressions_the_backend_accepts(s):
    """What the round trip alone does not claim: pydantic has to take it, and
    the evaluator has to answer it — against the real `site.*` namespace
    `SiteConditions.facts()` builds, not a fixture dict."""
    hvhz_expr = EXPR.validate_python(s["round_trip_hvhz"])
    assert evaluate_expr(hvhz_expr, {"site": {"hvhz": True}}) is True
    assert evaluate_expr(hvhz_expr, {"site": {"hvhz": False}}) is False

    exposure_expr = EXPR.validate_python(s["round_trip_exposure"])
    assert evaluate_expr(exposure_expr, {"site": {"exposure_category": "C"}}) is True
    assert evaluate_expr(exposure_expr, {"site": {"exposure_category": "B"}}) is False


def test_the_numeric_path_is_unchanged(s):
    """Pinned exactly, so a boolean/enum change to `writeSentence` cannot
    regress the one path every shipped model and fixture actually uses."""
    assert s["numeric_pin"] == {
        "op": "cmp", "cmp": ">=",
        "left": {"op": "field", "path": "panel.height_mm"},
        "right": {"op": "lit", "value": 1800},
    }
    assert s["numeric_pin"]["right"]["value"] == 1800
    assert not isinstance(s["numeric_pin"]["right"]["value"], bool)
