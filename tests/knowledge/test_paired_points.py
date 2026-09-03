"""The five refused tables, consumed.

Both assertions rev 1 made here passed on a positional reader and on
`points[0]`, because the fixture's declared order matched its value order and
its shortest span was also its first pair. These fixtures break both ties: one
declares its columns in the opposite order to the values a real table would put
there, and one publishes its pairs shortest-span-LAST.

The values are the first published snapshot's own — Barrette's `footing_schedule`
at exposure B, non-HVHZ: 24" holes at 66" centres, or 30" holes at 97".
"""

from __future__ import annotations

import pytest

from fenceai.knowledge.parameters import (
    ParameterRow, ParameterTable, Quantity, default_point, expand,
    paired_columns, paired_points,
)

D24 = Quantity(amount_milli=609600, unit="mm", value_raw=['24"'])
S66 = Quantity(amount_milli=1676400, unit="mm", value_raw=['66"'])
D30 = Quantity(amount_milli=762000, unit="mm", value_raw=['30"'])
S97 = Quantity(amount_milli=2463800, unit="mm", value_raw=['97"'])


def _table(value_type: str, pairs: list[list[Quantity]]) -> ParameterTable:
    return ParameterTable(
        parameter="footing_schedule", task="structural_parameter",
        value_type=value_type,
        condition_scope={"exposure_category": "site"},
        rows=[ParameterRow(conditions={"exposure_category": "B"}, value=pairs)],
    )


@pytest.fixture()
def paired_real() -> ParameterTable:
    """The published shape, verbatim: depth declared first, shallowest first."""
    return _table("paired(footing_depth_mm:mm, max_span_mm:mm)",
                  [[D24, S66], [D30, S97]])


@pytest.fixture()
def paired_desc_first() -> ParameterTable:
    """The SAME value list under the opposite declaration.

    A publisher may name the span column first. Nothing about the numbers says
    so — 610 and 1676 are both plausible depths and both plausible spans — which
    is exactly why the reader must obey the declaration and not the position.
    """
    return _table("paired(max_span_mm:mm, footing_depth_mm:mm)",
                  [[D24, S66], [D30, S97]])


@pytest.fixture()
def paired_span_desc() -> ParameterTable:
    """The same two pairs, published widest-span FIRST."""
    return _table("paired(footing_depth_mm:mm, max_span_mm:mm)",
                  [[D30, S97], [D24, S66]])


def test_the_column_names_come_from_the_declared_value_type(paired_desc_first):
    """`paired(max_span_mm:mm, footing_depth_mm:mm)` with the SAME value list as
    the ordinary declaration. A positional reader swaps depth and span here and
    passes every test that compares a set of keys."""
    p = paired_points(paired_desc_first, paired_desc_first.rows[0])[0]
    assert p.bindings == {"max_span_mm": 610, "footing_depth_mm": 1676}


def test_the_default_is_the_shortest_span_not_the_first_pair(paired_span_desc):
    """Pairs published shortest-LAST, so `points[0]` is the wrong answer."""
    points = paired_points(paired_span_desc, paired_span_desc.rows[0])
    assert [p.bindings["max_span_mm"] for p in points] == [2464, 1676]
    assert default_point(points).bindings["max_span_mm"] == 1676
    assert default_point(points).is_default


def test_each_point_carries_the_sources_own_words(paired_real):
    """Obligation 5: the display keeps the lexeme. `24"` rides with 610."""
    p = paired_points(paired_real, paired_real.rows[0])[0]
    assert p.lexemes["footing_depth_mm"] == '24"'
    assert p.bindings["footing_depth_mm"] == 610


def test_the_refusal_is_gone(paired_real):
    _, gaps, _ = expand(paired_real, as_of="2026-09-03")
    assert "parameter_paired_unsupported" not in {g.because.code for g in gaps}


# -- what the points then land as ----------------------------------------------

def test_the_default_point_lands_as_one_published_version(paired_real):
    """§5.1: a parameter point becomes a `KnowledgeVersion`, so `resolve_param`
    still decides — precedence, hard ties and defeat edges all keep working.

    One version per ROW carrying both actions, not one per parameter: the pair
    is a single statement of the source's, and splitting it would let the
    evaluator resolve a 610 mm hole beside a 2464 mm span, which is a fence the
    document never approved.
    """
    versions, gaps, _ = expand(paired_real, as_of="2026-09-03")
    assert gaps == []
    assert len(versions) == 1
    assert {(a.param, a.value) for a in versions[0].actions} == {
        ("footing_depth_mm", 610), ("max_span_mm", 1676)}


def test_the_alternative_is_not_what_lands(paired_span_desc):
    """The publication order must not decide it. This table lists the 30"/97"
    pair first, and 24"/66" is still what the engine builds."""
    versions, _, _ = expand(paired_span_desc, as_of="2026-09-03")
    assert {(a.param, a.value) for a in versions[0].actions} == {
        ("footing_depth_mm", 610), ("max_span_mm", 1676)}


def test_a_version_title_keeps_the_sources_own_words(paired_real):
    """Obligation 5 again, one surface further on: a title reading
    `footing_schedule = 610 · 1676` has thrown away what a reader checks."""
    versions, _, _ = expand(paired_real, as_of="2026-09-03")
    assert versions[0].title == 'footing_schedule = 24" · 66"'


# -- the declaration is data too, and may be wrong -----------------------------

def test_a_member_declared_in_a_unit_we_do_not_store_is_refused():
    """`paired(footing_depth_mm:in, max_span_mm:mm)` is a table declaring inches
    at rest. Refused as nonconforming rather than read as millimetres — the
    whole point of parsing the declaration is that we believe it."""
    table = _table("paired(footing_depth_mm:in, max_span_mm:mm)", [[D24, S66]])
    assert paired_columns(table.value_type) == []
    versions, gaps, _ = expand(table, as_of="2026-09-03")
    assert versions == []
    assert [g.because.code for g in gaps] == ["parameter_value_nonconforming"]


def test_a_row_whose_pairs_do_not_match_the_declared_width_is_refused():
    """Two columns declared, three quantities in a pair. Nothing here is
    salvageable by dropping the extra: which two of the three were meant is a
    fact only the publisher holds."""
    table = _table("paired(footing_depth_mm:mm, max_span_mm:mm)",
                   [[D24, S66, D30]])
    assert paired_points(table, table.rows[0]) == []
    versions, gaps, _ = expand(table, as_of="2026-09-03")
    assert versions == []
    assert [g.because.code for g in gaps] == ["parameter_value_nonconforming"]


def test_a_default_over_no_points_is_no_answer():
    """`default_point([])` is None, not an IndexError — a caller asking which
    point an empty row defaults to is asking a question with an answer."""
    assert default_point([]) is None
