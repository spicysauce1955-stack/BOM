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
from pydantic import ValidationError

from fenceai.catalog.demo import demo_catalog
from fenceai.core.dates import Date
from fenceai.core.gaps import SourceRef
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.evaluator import resolve_param, resolve_token
from fenceai.knowledge.model import KnowledgeBase
from fenceai.knowledge.source_policy import SHIPPED_DEFAULT
from fenceai.knowledge.parameters import (
    ParameterRow, ParameterTable, Provenance, Quantity, Token, expand, to_mm,
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
            # §1.1 `Date`, BINDING since v1.2: the normalised form and the
            # source's own stamp travel together, for the reason
            # `Quantity.value_raw` already exists.
            "valid_from": {"iso": "2024-01-01", "value_raw": ["01/01/2024"]},
            "valid_until": {"iso": "2027-01-01", "value_raw": ["01/01/2027"]},
            "authority": "ASCE 7-16",
        }],
        "uncovered": [{"exposure_category": "D", "hvhz": True}],
    })
    row = table.rows[0]
    assert row.value.value_raw == ['47"']
    assert row.provenance.cites[0].belongs_to == "sha256:abc"
    assert table.uncovered == [{"exposure_category": "D", "hvhz": True}]
    assert (row.valid_from.iso, row.valid_from.value_raw) == \
        ("2024-01-01", ["01/01/2024"])


def test_a_tokens_own_lexeme_parses_and_survives_the_round_trip():
    """`Token` is not a bare string — it carries `value_raw`, the sentence the
    document actually used, the same reason `Quantity` carries its own. Losing it
    would reintroduce the loss N3 was accepted to prevent, this time for tokens."""
    table = ParameterTable.model_validate({
        "parameter": "slope_method", "value_type": "token(stepped_only|racked)",
        "rows": [{"value": {
            "key": "stepped_only",
            "value_raw": ["They should be only installed using the slope method"],
        }}],
    })
    row = table.rows[0]
    assert row.value.key == "stepped_only"
    assert row.value.value_raw == [
        "They should be only installed using the slope method"]
    # ...and the same object, unchanged, after a JSON round trip
    reloaded = ParameterTable.model_validate_json(table.model_dump_json())
    assert reloaded.rows[0].value == row.value


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
    versions, gaps, _ = expand(_span_table())
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
    versions, _, _ = expand(_span_table())
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
                           value=Token(key="stepped_only"))],
    )
    versions, gaps, _ = expand(table)
    assert not gaps
    kb = KnowledgeBase(versions=versions)
    res = resolve_token(kb, {"scope": {}, "site": {"exposure_category": "C"}},
                        "slope_method")
    assert res.winner.actions[0].value == "stepped_only"


def test_a_token_outside_the_declared_set_is_a_gap_not_a_coercion():
    table = ParameterTable(
        parameter="slope_method", value_type="token(stepped_only|racked)",
        rows=[ParameterRow(value=Token(key="whatever_the_fitter_thinks"))],
    )
    versions, gaps, _ = expand(table)
    assert not versions
    assert [g.because.code for g in gaps] == ["parameter_value_nonconforming"]
    assert gaps[0].kind == "disputed" and gaps[0].on == "value"


def test_a_token_row_on_a_quantity_table_is_a_gap_not_a_crash():
    """`value_type` is declared ONCE, on the table. A row shaped for the OTHER
    half of the union — a `Token` where the table declared `quantity(mm)` — is
    the table contradicting itself, exactly like an out-of-set token, and must
    not raise."""
    table = _span_table(rows=[ParameterRow(value=Token(key="stepped_only"))])
    versions, gaps, _ = expand(table)
    assert not versions
    assert [g.because.code for g in gaps] == ["parameter_value_nonconforming"]


def test_a_quantity_row_on_a_token_table_is_a_gap_not_a_crash():
    """The mirror case: a table declared `token(...)` receiving a `Quantity`
    row."""
    table = ParameterTable(
        parameter="slope_method", value_type="token(stepped_only|racked)",
        rows=[ParameterRow(value=Quantity(amount_milli=1200000, unit="mm"))],
    )
    versions, gaps, _ = expand(table)
    assert not versions
    assert [g.because.code for g in gaps] == ["parameter_value_nonconforming"]


def test_a_length_resolver_never_receives_a_word():
    """The reason `SetToken` is a separate action rather than a union-typed
    `value`: a resolver asking for a length must not typecheck against a word."""
    table = ParameterTable(
        parameter="slope_method", value_type="token(racked)",
        rows=[ParameterRow(value=Token(key="racked"))],
    )
    kb = KnowledgeBase(versions=expand(table)[0])
    assert resolve_param(kb, {"scope": {}}, "slope_method").winner is None


# -- what the table DECLARES it does not know -----------------------------------

def test_uncovered_points_become_gaps_never_silence():
    """§1.3 BINDING: points no row covers are listed, never silently omitted."""
    table = _span_table(uncovered=[{"exposure_category": "D"}])
    _, gaps, _ = expand(table)
    assert [g.because.code for g in gaps] == ["uncovered_parameter_point"]
    assert gaps[0].subject.id == "max_span_mm"


def test_every_gap_a_table_produces_names_the_tenant_it_expanded_under():
    """`GapSubject.tenant` is the field the Knowledge team's review added to match
    `EntityRef`. `expand()` accepts a `tenant` and it must reach every gap kind
    this module builds, not just be threaded in and dropped."""
    uncovered = expand(_span_table(uncovered=[{"exposure_category": "D"}]),
                       tenant="acme")[1]
    assert uncovered[0].subject.tenant == "acme"

    lapsed = expand(_span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_until=Date(iso="2025-01-01"))]), as_of="2026-01-01", tenant="acme")[1]
    assert lapsed[0].subject.tenant == "acme"

    nonconforming = expand(ParameterTable(
        parameter="slope_method", value_type="token(stepped_only|racked)",
        rows=[ParameterRow(value=Token(key="nope"))]), tenant="acme")[1]
    assert nonconforming[0].subject.tenant == "acme"

    unmappable = expand(_span_table(scope={"kind": "orchard_row", "id": "X"}),
                        tenant="acme")[1]
    assert unmappable[0].subject.tenant == "acme"


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
        valid_until=Date(iso="2025-01-01"), authority="ASCE 7-10")])

    versions, gaps, _ = expand(table, as_of="2026-08-25")
    assert len(versions) == 1, "the row still applies; it is not a hole"
    assert [g.because.code for g in gaps] == ["parameter_authority_lapsed"]
    assert gaps[0].because.params["as_of"] == "2026-08-25"

    # ...and against an as_of BEFORE it lapsed, nothing is reported
    assert not expand(table, as_of="2024-06-01")[1]


def test_no_as_of_means_no_expiry_judgement_rather_than_todays_date():
    """Generation is a pure function. A clock read inside it would make the same
    project against the same snapshot warn differently on different days."""
    table = _span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_until=Date(iso="1999-01-01"))])
    assert not expand(table)[1]


def test_an_unnormalisable_valid_until_is_never_ordered():
    """§1.1 BINDING (v1.2): **a `null` `iso` is never ordered, and never treated
    as earliest or latest.**

    The first real snapshot (`3ae88642…`, 2026-08-30) published `valid_until` as
    `MM/DD/YYYY` — `"04/04/2028"`. As a bare string compared against an ISO
    `as_of`, `"04/04/2028" < "2026-08-30"` is TRUE, so a row valid four more
    years was reported LAPSED. Amendment 002 is that defect, and the `Date` type
    is its fix: the lexeme now arrives beside `iso: null` instead of pretending
    to be one, and a rule reaching for it finds nothing to order.

    The important half is the SECOND assertion. "Not lapsed" alone would also
    pass if null sorted as the latest possible date; the row must be absent from
    the judgement in both directions, not merely absolved in one."""
    unreadable = Date(iso=None, value_raw=["04/04/2028"])
    table = _span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_until=unreadable, authority="NOA-123")])
    versions, gaps, _ = expand(table, as_of="2026-08-30")
    assert len(versions) == 1
    assert not gaps, "a date this side cannot read must not be judged lapsed"

    # ...and it is not being treated as the LATEST date either: the same null in
    # `valid_from` must not make the row not-yet-in-force.
    assert not expand(_span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_from=unreadable)]), as_of="2026-08-30")[1]

    # The lexeme survives verbatim, which is the whole point of carrying it: a
    # curator reads what the document said and resolves it by hand.
    assert table.rows[0].valid_until.value_raw == ["04/04/2028"]

    # ...and the ISO case a day either side of `as_of` still works exactly as before
    assert expand(_span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_until=Date(iso="2026-08-29"))]), as_of="2026-08-30")[1]
    assert not expand(_span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_until=Date(iso="2026-08-31"))]), as_of="2026-08-30")[1]


def test_a_date_that_only_looks_like_one_is_refused_at_the_door():
    """The guard this replaces was a SHAPE regex, and a shape regex says yes to
    `2025-13-45` — which then compares lexicographically against a real date
    perfectly happily and reports a row lapsed on the strength of a month that
    does not exist. `iso` means an ISO-8601 calendar date or it means nothing."""
    with pytest.raises(ValidationError):
        Date(iso="2025-13-45")
    with pytest.raises(ValidationError):
        Date(iso="04/04/2028")   # a lexeme belongs in `value_raw`, not in `iso`


def test_a_row_not_yet_in_force_is_marked_rather_than_applied_silently():
    """The lapsed check's twin, and it did not exist: `valid_from` was declared
    on the row and read NOWHERE in `src/`, so a row whose authority takes effect
    in 2030 was expanded and applied against a 2026 run with no marker at all.

    It fails in the more dangerous direction than a lapse does. A lapsed row
    still produces a warned line a reader can see; a not-yet-in-force row
    produced a confident answer with nothing to see. Marked, never dropped —
    the same discipline, because dropping it would turn an authority that is not
    yet in force into a coverage hole, and those are different facts."""
    table = _span_table(rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        valid_from=Date(iso="2030-01-01"), authority="ASCE 7-28")])

    versions, gaps, _ = expand(table, as_of="2026-08-30")
    assert len(versions) == 1, "the row is not a hole; it is not yet in force"
    assert [g.because.code for g in gaps] == ["parameter_not_yet_in_force"]

    # ...and once the run's pinned date reaches it, nothing is reported
    assert not expand(table, as_of="2030-06-01")[1]


def test_an_as_of_this_engine_cannot_read_is_refused_not_downgraded():
    """`as_of` is OUR pinned run date, not published data. A typo'd one silently
    downgraded to "no judgement" would switch off every expiry check in the run
    without a sound, which is a worse failure than the one it would prevent."""
    with pytest.raises(ValueError):
        expand(_span_table(), as_of="30/08/2026")


# -- the first real publish (`3ae88642…`, 2026-08-30) exercised two more gaps ---

def test_scope_tenant_published_as_null_is_accepted_and_unused():
    """A published `EntityRef` states `tenant: null` for "no tenant" rather than
    omitting the key — the first real snapshot does this on every table. Only
    `kind`/`id` are ever read from `scope`, so `None` must parse rather than
    fail the whole table at the door."""
    table = ParameterTable.model_validate({
        "parameter": "footing_depth_mm",
        "scope": {"kind": "fence_model", "id": "mfr/example", "tenant": None},
        "value_type": "quantity(mm)",
        "rows": [{"value": {"amount_milli": 762000, "unit": "mm"}}],
    })
    versions, gaps, _ = expand(table)
    assert len(versions) == 1
    assert not gaps


def test_fence_model_is_a_recognised_entity_kind():
    """`product_line`/`model` were guesses made before either side had a real
    table to check them against. The first real snapshot's `scope.kind` is
    `fence_model` — a registry addition alongside the other two, not a
    replacement, since nothing says the next publisher will not use one of
    those instead."""
    table = _span_table(scope={"kind": "fence_model", "id": "mfr/example"})
    versions, gaps, _ = expand(table)
    assert not gaps, "a recognised kind must not report as unmappable"
    assert versions[0].scope == {"series": "mfr/example"}


# -- identity: a row's ref must name which table it came out of ----------------

def test_the_same_parameter_under_two_scopes_expands_to_two_identities():
    """The defect this pins was found in the first real snapshot and nowhere
    else: it publishes `footing_depth_mm` TWICE, once scoped to Barrette and once
    to CertainTeed, citing different approvals — one `superseded_by` the other.

    `object_id` was `f"{parameter}#{index}"`, so 16 published rows resolved to 8
    identities. That is not a cosmetic collision. The decision graph cites
    `version.ref`, so an explanation could not say which manufacturer's approval
    it used; `snapshot_set()` stamps a run's knowledge identity from the same
    pair, so a run could not tell "Barrette and CertainTeed" from "Barrette
    twice"; and one `overrides_objects` entry would have defeated both rows.

    All 16 values happened to agree, which is exactly why nothing failed."""
    barrette = _span_table(scope={"kind": "fence_model", "id": "mfr/barrette"})
    certainteed = _span_table(scope={"kind": "fence_model", "id": "mfr/certainteed"})

    refs = {(v.object_id, v.version)
            for t in (barrette, certainteed) for v in expand(t)[0]}
    assert len(refs) == 4, "two rows from each of two tables are four identities"
    assert all("mfr/" in object_id for object_id, _ in refs)


def test_two_scopes_declaring_the_same_hole_are_two_gaps_not_one():
    """The same collision one type over. Two tables for one parameter, each
    declaring the same uncovered point, are two holes for a curator to close —
    one per product — and a gap id built from `{parameter}:{point}` alone made
    the second vanish behind the first, silently halving the queue."""
    point = [{"exposure_category": "D"}]
    a = expand(_span_table(scope={"kind": "fence_model", "id": "mfr/a"},
                           uncovered=point))[1]
    b = expand(_span_table(scope={"kind": "fence_model", "id": "mfr/b"},
                           uncovered=point))[1]
    assert a[0].id != b[0].id
    assert a[0].subject.key() != b[0].subject.key()


def test_an_uncovered_point_travels_structured_never_pre_rendered():
    """§1.1 `ParamRef.point` is a mapping, and it stays one. It used to be joined
    into `"exposure_category=D, hvhz=True"` and handed to a locale template as a
    param — English dimension names and Python's `True`, interpolated verbatim
    into the Hebrew sentence. A renderer formats a mapping from its parts; it
    must never be given a pre-joined fragment in one language."""
    gap = expand(_span_table(uncovered=[{"exposure_category": "D", "hvhz": True}]))[1][0]
    assert gap.because.params["point"] == {"exposure_category": "D", "hvhz": True}
    assert gap.subject.point == {"exposure_category": "D", "hvhz": True}
    # a bool must survive as a bool — under a `str | int` annotation pydantic
    # admits it through the int arm and the sentence renders "hvhz=1"
    assert gap.subject.point["hvhz"] is True


# -- the two contract fields that were parsed and then dropped -----------------

def test_a_hit_policy_this_engine_cannot_honour_is_refused_not_approximated():
    """§1.3 declares four policies and this engine implements one. The other
    three were accepted and ignored: every row became an ordinary rule and
    evaluator precedence picked a winner, so a `collect_min` table of 1000 and
    2000 returned whichever fired first rather than 1000.

    Refusing is the same call `_scope_for` already makes about a scope we cannot
    aim — a confident wrong number is worse than an honest absent one — and it
    closes by a schema change HERE, so the gap is `closes_by="planning"`."""
    versions, gaps, _ = expand(_span_table(hit_policy="collect_min"))
    assert not versions, "a policy we cannot honour must not silently expand"
    assert [g.because.code for g in gaps] == ["parameter_hit_policy_unsupported"]
    assert gaps[0].closes_by == "planning"

    # `unique` is the one this engine can honour, and it still expands
    assert expand(_span_table(hit_policy="unique"))[0]


def test_overlapping_rows_under_unique_are_reported_against_the_table():
    """§1.3 BINDING: under `unique` no two rows may match the same domain point,
    and *"the check will tell you when that is false."* It did not exist. The
    contradiction surfaced only at run time as a `Conflict` on a warned line —
    attributed to this engine, rather than to the table that declared something
    untrue about itself."""
    table = _span_table(rows=[
        ParameterRow(conditions={"exposure_category": "C"},
                     value=Quantity(amount_milli=1200000, unit="mm")),
        ParameterRow(conditions={"exposure_category": "C"},
                     value=Quantity(amount_milli=2000000, unit="mm")),
    ])
    gaps = expand(table)[1]
    assert [g.because.code for g in gaps] == ["parameter_rows_overlap"]
    assert gaps[0].kind == "disputed" and gaps[0].on == "conditions"


def test_a_fallback_row_cannot_contradict_a_row_that_states_conditions():
    """`is_fallback()` existed to be excluded from this check and the check was
    never written, so the method had no caller in `src/` at all. A `stated` row
    with no conditions asserts nothing about the points it lands on — 66% of the
    structural facts in the class §1.4 admits are that shape — so it overlaps
    nothing by definition."""
    table = _span_table(rows=[
        ParameterRow(conditions={"exposure_category": "C"},
                     value=Quantity(amount_milli=1200000, unit="mm")),
        ParameterRow(conditions={}, condition_basis="stated",
                     value=Quantity(amount_milli=2000000, unit="mm")),
    ])
    assert not expand(table)[1]


def test_a_published_value_is_titled_by_its_own_lexeme():
    """`%g` is six SIGNIFICANT digits, so it misstated exactly the values worth
    checking — `1234567` thousandths rendered as `1234.57 mm`, wrong by 0.43 mm,
    and `1000000000` as `1e+06 mm`. And §1.1 says the source's own lexeme exists
    to be shown: `34"` is what a curator matches against the page."""
    lexeme = expand(_span_table(rows=[ParameterRow(
        value=Quantity(amount_milli=863600, unit="mm", value_raw=['34"']))]))[0]
    assert '34"' in lexeme[0].title

    bare = expand(_span_table(rows=[ParameterRow(
        value=Quantity(amount_milli=1234567, unit="mm"))]))[0]
    assert "1234.567 mm" in bare[0].title
    assert "e+" not in bare[0].title


def test_a_task_we_have_not_registered_is_used_and_flagged_not_refused():
    """The slice's riskiest decision, and it had no test at all until a review
    said so.

    `TaskCode` is a registry we own (§1.4). A table declaring a task we have not
    added would otherwise have every row REFUSED for a hole in our own list
    rather than any defect in their data — a failure mode that looks exactly like
    the publisher being wrong. So the rows are used and a gap says we could not
    judge them.

    The cost is stated rather than hidden, and that is what the last two
    assertions are for: nothing records a verdict for these rows, so no surface
    can claim their source was checked."""
    table = _span_table(task="thermal_movement_allowance", rows=[ParameterRow(
        conditions={"exposure_category": "C"},
        value=Quantity(amount_milli=1200000, unit="mm"),
        provenance=Provenance(source_class="marketing", curation_level=0,
                              cites=[SourceRef(id="s1", belongs_to="h1")]))])

    versions, gaps, admitted = expand(table, policy=SHIPPED_DEFAULT)

    # used: `marketing` at level 0 would be refused outright for a structural
    # parameter, so this row surviving is the decision working
    assert len(versions) == 1
    # flagged: exactly ONE gap for the table, not one per row
    assert [g.because.code for g in gaps] == ["parameter_task_unrecognised"]
    assert gaps[0].closes_by == "planning"
    assert gaps[0].because.params["task"] == "thermal_movement_allowance"
    # and unjudged: nothing vouches for it
    assert admitted == {}


def test_one_gap_per_table_for_an_unregistered_task_not_one_per_row():
    """Sixteen identical notes about one missing registry entry is noise; one is
    a work item. Asserted separately from the behaviour above because the count
    is the property that regresses when the check moves into the row loop."""
    many = _span_table(task="thermal_movement_allowance", rows=[
        ParameterRow(conditions={"exposure_category": c},
                     value=Quantity(amount_milli=1200000, unit="mm"),
                     provenance=Provenance(
                         source_class="marketing", curation_level=0,
                         cites=[SourceRef(id="s1", belongs_to="h1")]))
        for c in ("B", "C", "D")])
    gaps = expand(many, policy=SHIPPED_DEFAULT)[1]
    assert [g.because.code for g in gaps] == ["parameter_task_unrecognised"]


def test_a_source_class_we_have_not_registered_is_flagged_per_row():
    """Per ROW, unlike the task, because a table may mix classes and which row
    carries the unregistered one is what a reader needs.

    The contrast with the test above is the point: an unregistered TASK is a fact
    about the whole table, an unregistered CLASS is a fact about one row."""
    mixed = _span_table(task="structural_parameter", rows=[
        ParameterRow(conditions={"exposure_category": "B"},
                     value=Quantity(amount_milli=1800000, unit="mm"),
                     provenance=Provenance(
                         source_class="engineering_letter", curation_level=0,
                         cites=[SourceRef(id="s1", belongs_to="h1")])),
        ParameterRow(conditions={"exposure_category": "C"},
                     value=Quantity(amount_milli=1200000, unit="mm"),
                     provenance=Provenance(
                         source_class="sealed_approval", curation_level=2,
                         cites=[SourceRef(id="s2", belongs_to="h2")])),
    ])
    versions, gaps, admitted = expand(mixed, policy=SHIPPED_DEFAULT)
    codes = [g.because.code for g in gaps]
    assert codes.count("source_class_unrecognised") == 1
    # both rows are used: the unregistered one unjudged, the known one admitted
    assert len(versions) == 2
    assert len(admitted) == 1


# -- amendment 007: a condition dimension that is a quantity --------------------

def test_an_interval_condition_compiles_to_real_comparisons():
    """The whole point of 007, and the defect it closes.

    Before it, `fence_height` crossed as the English phrase `"Up to 48\\""` and
    compiled to `bay.fence_height == 'Up to 48"'`. A bay's height here is an
    integer in millimetres, so that comparison was false for every project that
    would ever run — and because it merely never matched, it reported as *not
    applicable* rather than as broken. Sixteen published rows were inert and
    nothing said so.

    The bound is converted through `to_mm`, so the comparison is against the same
    integer millimetres the rest of the engine stores."""
    from fenceai.knowledge.ast import field_paths
    from fenceai.knowledge.parameters import Interval, _condition_for

    table = _span_table(
        condition_scope={"fence_height": "bay"},
        domain={"fence_height": "range(mm)"},
        rows=[ParameterRow(conditions={"fence_height": Interval(
            max=Quantity(amount_milli=1219200, unit="mm", value_raw=['48"']),
            max_inclusive=True, value_raw=['Up to 48"'])},
            value=Quantity(amount_milli=1200000, unit="mm"))])

    expr = _condition_for(table, table.rows[0])
    assert field_paths(expr) == {"bay.fence_height"}
    dumped = expr.model_dump(mode="json")
    assert dumped["cmp"] == "<="
    assert dumped["right"]["value"] == 1219, "48 inches, in whole millimetres"


def test_the_inclusivity_flags_pick_the_operator_rather_than_being_assumed():
    """The publisher states them because the band between two stated brackets is
    theirs to define. 48″ and 49″ leave 25.4 mm between them, and whether that is
    a dead zone or whole-inch rounding is a fact only they hold — so an exclusive
    bound must compile to `<`, not to `<=` with a shrug."""
    from fenceai.knowledge.parameters import Interval, _condition_for

    def op(**flags):
        t = _span_table(
            condition_scope={"fence_height": "bay"},
            rows=[ParameterRow(conditions={"fence_height": Interval(
                min=Quantity(amount_milli=1244600, unit="mm"), **flags)},
                value=Quantity(amount_milli=1200000, unit="mm"))])
        return _condition_for(t, t.rows[0]).model_dump(mode="json")["cmp"]

    assert op(min_inclusive=True) == ">="
    assert op(min_inclusive=False) == ">"


def test_an_interval_unbounded_on_both_sides_constrains_nothing():
    """Contributing no term is the honest reading. A term that is always true
    would appear in the explanation as a condition somebody stated."""
    from fenceai.knowledge.parameters import Interval, _condition_for

    table = _span_table(
        condition_scope={"fence_height": "bay"},
        rows=[ParameterRow(conditions={"fence_height": Interval()},
                           value=Quantity(amount_milli=1200000, unit="mm"))])
    assert _condition_for(table, table.rows[0]) is None


# -- amendment 006: a paired value lands its default point ---------------------

def test_a_paired_table_lands_the_point_it_builds_and_is_judged_like_any_row():
    """This table used to be REFUSED, and the refusal was right for as long as
    this engine had nowhere to put a second admissible answer. It has one now:
    the alternatives are design points, the shortest span is the one we build,
    and the deeper-hole option is offered beside it with what it saves.

    Two properties are asserted here that a `paired_points` unit test cannot
    reach. Both actions land on ONE version, so the evaluator can never resolve a
    610 mm hole beside the 2235 mm span from the other alternative — a fence the
    sealed approval does not cover. And the row is judged by §1.4 like every
    other published row: `sealed_approval` at curation 2 for a structural
    parameter is admitted, and nothing about being paired exempts it.

    The alternative is not discarded, which is what 006 was ratified to protect:
    `paired_points` still returns both, and `tests/knowledge/test_paired_points.py`
    holds that half."""
    table = ParameterTable(
        parameter="footing_schedule", task="structural_parameter",
        value_type="paired(footing_depth_mm:mm, max_span_mm:mm)",
        rows=[ParameterRow(
            conditions={"exposure_category": "C"},
            provenance=Provenance(
                cites=[SourceRef(id="doc-1", belongs_to="doc-1")],
                source_class="sealed_approval", curation_level=2),
            value=[[Quantity(amount_milli=609600, unit="mm", value_raw=['24"']),
                    Quantity(amount_milli=1676400, unit="mm", value_raw=['66"'])],
                   [Quantity(amount_milli=914400, unit="mm", value_raw=['36"']),
                    Quantity(amount_milli=2235200, unit="mm", value_raw=['88"'])]])])

    versions, gaps, admitted = expand(table, policy=SHIPPED_DEFAULT)
    assert gaps == []
    assert len(versions) == 1
    assert {(a.param, a.value) for a in versions[0].actions} == {
        ("footing_depth_mm", 610), ("max_span_mm", 1676)}
    assert versions[0].title == 'footing_schedule = 24" · 66"'
    assert set(admitted) == {versions[0].ref}, "a paired row is judged, not exempt"
