"""`ParameterTable` — the contract's §1.3 type, and what loading one produces.

Two things are being defended here, and they fail differently.

**Contract fidelity.** These are the platform's types, not ours. The last time
this repo built a boundary type from memory it invented a `SourceRef` with the
wrong fields under the contract's own name — the exact defect that type's BINDING
clause exists to close — and nothing caught it because the generator only ever
emits, never receives. So the parsing tests come first and use the contract's own
shapes verbatim.

**The expansion.** A published table becomes ordinary `KnowledgeVersion`s that the
existing evaluator resolves beside everything else. If that holds, published
knowledge needs no privileged path into the generator; if it does not, the engine
grows a second selection mechanism, which is the thing the whole knowledge design
exists to avoid.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.evaluator import resolve_param, resolve_token
from fenceai.knowledge.model import KnowledgeBase
from fenceai.knowledge.parameters import (
    ParameterRow, ParameterTable, Provenance, Quantity, expand, to_mm,
)
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _span_table(**kw) -> ParameterTable:
    base = dict(
        parameter="max_span_mm",
        task="structural",
        value_type="quantity(mm)",
        domain={"exposure_category": ["B", "C"]},
        domain_basis="measured",
        condition_scope={"exposure_category": "site"},
        rows=[
            ParameterRow(conditions={"exposure_category": "B"},
                         value=Quantity(amount_milli=1800000, unit="mm")),
            ParameterRow(conditions={"exposure_category": "C"},
                         value=Quantity(amount_milli=1200000, unit="mm")),
        ],
    )
    return ParameterTable(**{**base, **kw})


# -- the one named conversion point (§1.1 BINDING) ------------------------------

@pytest.mark.parametrize("milli,expected", [
    (2463800, 2464),   # the contract's own example: floored, this buys a post
    (2463200, 2463),
    (2500, 3),         # half-UP; Python's round() is banker's and gives 2
    (1500, 2),
    (0, 0),
    (-2500, -3),
])
def test_thousandths_round_they_do_not_truncate(milli, expected):
    """§1.1, BINDING, and the reason it is binding: a span limit passes through
    `n = ceil(run_length / max_span)`, so 2463.8 floored to 2463 rather than
    rounded to 2464 buys an extra post, footing and pour on a 9.8 m run."""
    assert to_mm(Quantity(amount_milli=milli, unit="mm")) == expected


def test_a_unit_this_engine_does_not_store_is_refused_not_converted():
    """Silently applying a factor nobody wrote down is how a number arrives at
    rest in the wrong unit."""
    with pytest.raises(ValueError, match="deg_milli"):
        to_mm(Quantity(amount_milli=1000, unit="deg_milli"))


# -- the contract's shapes parse ------------------------------------------------

def test_a_published_table_parses_from_the_contracts_own_shape():
    table = ParameterTable.model_validate({
        "parameter": "max_span_mm",
        "scope": {"kind": "product_line", "id": "M-VINYL"},
        "task": "structural",
        "hit_policy": "unique",
        "value_type": "quantity(mm)",
        "domain": {"exposure_category": ["B", "C", "D"], "hvhz": [True, False]},
        "domain_basis": "measured",
        "condition_scope": {"exposure_category": "site", "hvhz": "site"},
        "rows": [{
            "conditions": {"exposure_category": "C", "hvhz": False},
            "condition_basis": "stated",
            "value": {"amount_milli": 1200000, "unit": "mm", "value_raw": ['47"']},
            "provenance": {
                "cites": [{"id": "src-1", "belongs_to": "sha256:abc"}],
                "source_class": "manufacturer", "curation_level": 2,
                "version_status": "active",
            },
            "valid_from": "2024-01-01", "valid_until": "2027-01-01",
            "authority": "ASCE 7-16",
        }],
        "uncovered": [{"exposure_category": "D", "hvhz": True}],
    })
    row = table.rows[0]
    assert row.value.value_raw == ['47"']
    assert row.provenance.cites[0].belongs_to == "sha256:abc"
    assert table.uncovered == [{"exposure_category": "D", "hvhz": True}]


def test_admitted_by_is_not_a_field_on_provenance():
    """§1.1 is explicit: `admitted_by` is an output of a RUN (§1.4). A field for
    it on published data would be somewhere to record an answer this side has not
    computed."""
    assert "admitted_by" not in Provenance.model_fields


def test_value_type_declares_the_column_once():
    """It sits on the TABLE so one column cannot hold both `10000 deg_milli` and
    `not_rackable` — `not_rackable` is not an angle, it is a different parameter."""
    assert _span_table().token_values() is None
    tokens = ParameterTable(parameter="slope_method",
                            value_type="token(stepped_only|racked|either)")
    assert tokens.token_values() == {"stepped_only", "racked", "either"}


# -- expansion: a table becomes ordinary knowledge ------------------------------

def test_rows_expand_into_published_knowledge_versions():
    versions, gaps = expand(_span_table())
    assert len(versions) == 2
    # THE seam: a loader that used the constructor would make published rows look
    # home-grown, and two that tie and disagree would raise
    assert all(v.origin == "published" for v in versions)
    assert not gaps


def test_a_condition_key_binds_in_the_namespace_its_scope_declares():
    """Obligation 13. A key scoped `site` reads `site.*`; one scoped `post` reads
    `post.*` and is therefore selected when a post exists, not at expansion."""
    from fenceai.knowledge.ast import field_paths

    table = _span_table(
        condition_scope={"exposure_category": "site"},
        rows=[ParameterRow(conditions={"exposure_category": "C"},
                           value=Quantity(amount_milli=1200000, unit="mm"))],
    )
    version = expand(table)[0][0]
    assert field_paths(version.condition) == {"site.exposure_category"}

    by_post = _span_table(
        condition_scope={"role": "post"},
        rows=[ParameterRow(conditions={"role": "corner"},
                           value=Quantity(amount_milli=1200000, unit="mm"))],
    )
    assert field_paths(expand(by_post)[0][0].condition) == {"post.role"}


def test_an_expanded_table_drives_a_real_generation():
    """The property the whole expansion exists for: published knowledge resolves
    through the SAME evaluator, so it needs no privileged channel."""
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    versions, _ = expand(_span_table())
    kb.versions.extend(versions)

    b = generate(straight_topology(6000), kb, demo_catalog(),
                 site=SiteConditions(exposure_category="B"))
    c = generate(straight_topology(6000), kb, demo_catalog(),
                 site=SiteConditions(exposure_category="C"))
    assert [s.width_mm for s in b.strategy.spans] == [1500, 1500, 1500, 1500]
    assert [s.width_mm for s in c.strategy.spans] == [1200] * 5


def test_a_fallback_row_is_recognisable():
    """Obligation 15: `stated` with EMPTY conditions means the document gave none.
    Such a row asserts nothing about the points it lands on, and 66% of the
    structural facts in the class §1.4 admits are exactly this shape."""
    fallback = ParameterRow(condition_basis="stated",
                            value=Quantity(amount_milli=1800000, unit="mm"))
    assumed = ParameterRow(condition_basis="assumed", conditions={},
                           value=Quantity(amount_milli=1800000, unit="mm"))
    assert fallback.is_fallback()
    assert not assumed.is_fallback()
    # ...and it expands to a rule with no condition, so it applies everywhere and
    # loses to any conditioned row on specificity
    version = expand(_span_table(rows=[fallback]))[0][0]
    assert version.condition is None


# -- tokens ---------------------------------------------------------------------

def test_a_token_valued_parameter_lands_as_a_token():
    """`SetParam.value` is an `int`, so `slope_method = stepped_only` had nowhere
    to go — one of the five mechanisms specified with no implementation."""
    table = ParameterTable(
        parameter="slope_method",
        value_type="token(stepped_only|racked)",
        condition_scope={"exposure_category": "site"},
        rows=[ParameterRow(conditions={"exposure_category": "C"},
                           value="stepped_only")],
    )
    versions, gaps = expand(table)
    assert not gaps
    kb = KnowledgeBase(versions=versions)
    res = resolve_token(kb, {"scope": {}, "site": {"exposure_category": "C"}},
                        "slope_method")
    assert res.winner.actions[0].value == "stepped_only"


def test_a_token_outside_the_declared_set_is_a_gap_not_a_coercion():
    table = ParameterTable(
        parameter="slope_method", value_type="token(stepped_only|racked)",
        rows=[ParameterRow(value="whatever_the_fitter_thinks")],
    )
    versions, gaps = expand(table)
    assert not versions
    assert [g.code for g in gaps] == ["parameter_value_nonconforming"]
    assert gaps[0].kind == "disputed" and gaps[0].on == "value"


def test_a_length_resolver_never_receives_a_word():
    """The reason `SetToken` is a separate action rather than a union-typed
    `value`: a resolver asking for a length must not typecheck against a word."""
    table = ParameterTable(
        parameter="slope_method", value_type="token(racked)",
        rows=[ParameterRow(value="racked")],
    )
    kb = KnowledgeBase(versions=expand(table)[0])
    assert resolve_param(kb, {"scope": {}}, "slope_method").winner is None


# -- what the table DECLARES it does not know -----------------------------------

def test_uncovered_points_become_gaps_never_silence():
    """§1.3 BINDING: points no row covers are listed, never silently omitted."""
    table = _span_table(uncovered=[{"exposure_category": "D"}])
    _, gaps = expand(table)
    assert [g.code for g in gaps] == ["uncovered_parameter_point"]
    assert gaps[0].subject.ref == "max_span_mm"


def test_domain_basis_changes_what_an_uncovered_point_MEANS():
    """Against a `measured` domain the table really does not cover the point;
    against a `declared` one we may not know the table's real extent. Different
    facts, and they send a curator to different work — which is the whole reason
    the contract carries the field."""
    measured = expand(_span_table(domain_basis="measured",
                                  uncovered=[{"exposure_category": "D"}]))[1][0]
    declared = expand(_span_table(domain_basis="declared",
                                  uncovered=[{"exposure_category": "D"}]))[1][0]
    assert measured.would_close != declared.would_close
    assert "re-read of the source" in declared.would_close


# -- validity is judged against a pinned as_of, never a clock (obligation 16) ----

def test_a_lapsed_row_is_marked_against_as_of_and_still_expanded():
    """Dropping it would turn a lapsed authority into a coverage hole, and those
    are different facts with different fixes."""
    table = _span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_until="2025-01-01", authority="ASCE 7-10")])

    versions, gaps = expand(table, as_of="2026-08-25")
    assert len(versions) == 1, "the row still applies; it is not a hole"
    assert [g.code for g in gaps] == ["parameter_authority_lapsed"]
    assert gaps[0].params["as_of"] == "2026-08-25"

    # ...and against an as_of BEFORE it lapsed, nothing is reported
    assert not expand(table, as_of="2024-06-01")[1]


def test_no_as_of_means_no_expiry_judgement_rather_than_todays_date():
    """Generation is a pure function. A clock read inside it would make the same
    project against the same snapshot warn differently on different days."""
    table = _span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_until="1999-01-01")])
    assert not expand(table)[1]
