"""Ingesting a whole published snapshot — the door, and the fixture at it.

Nothing has ever come through this door. The Knowledge Platform is still
designing, so `docs/integration-contract/fixtures/snapshot-example.json` is this
repo's reading of contract §1.2/§1.3 rather than something observed.

That makes these tests two different things at once, and the distinction matters
when one of them fails:

* the tests over the FIXTURE check that our reading of the contract is
  self-consistent and that the loader survives a whole document. A failure here
  is ours.
* the fixture itself is a QUESTION for the other team. If a real snapshot ever
  disagrees with it, the contract is right, the fixture is a bug, and the useful
  output is the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase
from fenceai.knowledge.snapshot import Snapshot, ingest, snapshot_id_for
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

FIXTURE = (Path(__file__).resolve().parents[2]
           / "docs" / "integration-contract" / "fixtures" / "snapshot-example.json")


@pytest.fixture()
def snapshot() -> Snapshot:
    return Snapshot.model_validate(json.loads(FIXTURE.read_text()))


# -- the fixture is a fixture, and must stay obviously so ----------------------

def test_the_fixture_cannot_be_mistaken_for_published_data(snapshot):
    """A file that could pass for something that arrived over the wire is how a
    hypothesis quietly becomes a fact nobody checked."""
    assert snapshot.snapshot_id.startswith("FIXTURE-")
    assert snapshot.tenant == "not-a-real-tenant"
    assert all(c.id.startswith("FIXTURE-")
               for t in snapshot.parameters for r in t.rows
               for c in r.provenance.cites)


# -- the whole payload parses --------------------------------------------------

def test_the_contracts_whole_payload_parses(snapshot):
    """§1.2, every field. The ones this engine does not consume are ACCEPTED and
    left alone — a private model for them would be a shape nobody agreed to, and
    it would look like support."""
    assert snapshot.regime == "us_astm"
    assert snapshot.contract_version == "1.1.0"
    assert len(snapshot.parameters) == 2
    assert len(snapshot.gaps) == 3


def test_what_arrives_and_is_not_consumed_is_counted_not_hidden(snapshot):
    """A snapshot carrying 40 parts into an engine with no part consumer is a fact
    the operator should see — and, while the other team is designing, the most
    useful thing we can tell them about their own payload.

    `warnings` used to be on this list and is not any more, which is the only
    honest way for an entry to leave it: build-order item 8 gave them somewhere
    to go (`report/annexe.py`), so they are consumed rather than counted. The
    assertion is kept EXACT rather than narrowed to the remaining key, because a
    member silently rejoining this list is exactly the regression it watches
    for."""
    assert ingest(snapshot).unconsumed == {"source_docs": 3}


def test_a_declared_id_can_be_checked_against_its_own_members(snapshot):
    """The one property of a snapshot this side can verify without trusting the
    sender. The fixture's id is deliberately NOT a real hash, so this asserts the
    computation exists and is stable rather than that the fixture passes it."""
    assert snapshot_id_for(snapshot) == snapshot_id_for(snapshot)
    assert len(snapshot_id_for(snapshot)) == 64


# -- ingestion -----------------------------------------------------------------

def test_tables_become_ordinary_knowledge(snapshot):
    out = ingest(snapshot, as_of="2026-08-25")
    # 3 max_span rows + 1 slope_method fallback row
    assert len(out.knowledge.versions) == 4
    assert all(v.origin == "published" for v in out.knowledge.versions)


def test_published_and_discovered_gaps_are_one_list_but_counted_apart(snapshot):
    """They are the same type by contract. But "your table declares a hole" and
    "your table contradicts itself" are different messages to send back."""
    out = ingest(snapshot, as_of="2026-08-25")
    assert len(out.gaps) == 6
    assert out.discovered == 3
    # the platform's own gaps come FIRST — what it chose to tell us, before our
    # findings about its data
    assert [g.because.code for g in out.gaps[:3]] == [
        "gate_not_modelled", "readers_disagreed_on_bracket",
        "parameter_condition_excluded"]


def test_the_lapsed_row_is_found_against_the_pinned_as_of(snapshot):
    """The fixture carries an NOA that expired in 2025 on purpose."""
    lapsed = [g for g in ingest(snapshot, as_of="2026-08-25").gaps
              if g.because.code == "parameter_authority_lapsed"]
    assert len(lapsed) == 1
    assert lapsed[0].because.params["authority"] == "NOA 19-0101.01"
    # ...and against an as_of before it expired, it is not a finding
    assert not [g for g in ingest(snapshot, as_of="2024-06-01").gaps
                if g.because.code == "parameter_authority_lapsed"]


def test_no_as_of_makes_no_expiry_judgement(snapshot):
    """Generation is pure; a clock here would make one project against one
    snapshot warn differently on different days."""
    assert not [g for g in ingest(snapshot).gaps
                if g.because.code == "parameter_authority_lapsed"]


def test_the_uncovered_points_the_table_declares_are_reported(snapshot):
    """§1.3 BINDING: points no row covers are listed, never silently omitted. The
    fixture declares exposure D in both HVHZ states."""
    points = {g.because.params["point"] for g in ingest(snapshot).gaps
              if g.because.code == "uncovered_parameter_point"}
    assert points == {"exposure_category=D, hvhz=False",
                      "exposure_category=D, hvhz=True"}


def test_an_excluded_point_is_published_directly_not_synthesised_as_uncovered(snapshot):
    """`(exposure_category=B, hvhz=true)` is not in `uncovered` at all — the
    source affirmatively excludes it (both non-HVHZ rows are bracketed
    `NON HVHZ`), which is a fact only the publisher knows and therefore its gap
    to raise directly, not this loader's to synthesise from a bare domain point.
    Settled with the Knowledge team rather than a new `GapKind` — no new `Gap`
    kind, no new field on `ParameterTable.uncovered`; just a specific
    `because.code` on a gap they publish like any other."""
    excluded = [g for g in ingest(snapshot).gaps
                if g.because.code == "parameter_condition_excluded"]
    assert len(excluded) == 1
    assert excluded[0].because.params["point"] == "exposure_category=B, hvhz=True"
    assert excluded[0].subject.id == "max_span_mm"
    # published, not discovered — this engine did not derive it
    assert excluded[0] in snapshot.gaps


def test_a_published_gate_gap_keeps_closes_by_planning(snapshot):
    """Obligation 18: a gate is published as a `Gap`, never as a `FenceModel`.
    Two of the eight kinds close by a schema change HERE, and a queue that showed
    a curator that row would be showing them work they cannot do."""
    gate = next(g for g in snapshot.gaps if g.kind == "unmodellable_entity")
    assert gate.closes_by == "planning"


# -- the point of all of it ----------------------------------------------------

def test_an_ingested_snapshot_drives_a_real_generation(snapshot):
    """Published knowledge resolves through the SAME evaluator as authored rules,
    so it needs no privileged channel into the generator. This is the property
    the whole expansion exists for, exercised over a whole document."""
    from fenceai.fencemodel.demo import demo_models
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.fencemodel.selection import FenceModelChoice
    from fenceai.parts.demo import demo_parts
    from fenceai.parts.model import PartLibrary

    out = ingest(snapshot, as_of="2026-08-25")
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    kb.versions.extend(out.knowledge.versions)
    # built to M-VINYL, because the table is SCOPED to that product line — a
    # fence of another line must not pick up its spans, and that is the whole
    # content of the EntityRef the table carries
    kw = dict(models=FenceModelLibrary(models=list(demo_models().values())),
              parts=PartLibrary(parts=demo_parts()),
              default_model=FenceModelChoice(model_id="M-VINYL"))

    def bays(**site):
        result = generate(straight_topology(6000), KnowledgeBase(versions=kb.versions),
                          demo_catalog(), site=SiteConditions(**site), **kw)
        return [s.width_mm for s in result.strategy.spans]

    # 72" / 48" / 36" maxima from one published table, selected by the project's
    # own site conditions. The MAXIMUM is not the bay width: 1829 mm over a 6 m
    # run is four equal 1500 mm bays, which is what "derived, not authored" means
    # in practice.
    assert bays(exposure_category="B", hvhz=False) == [1500] * 4
    assert bays(exposure_category="C", hvhz=False) == [1200] * 5
    assert len(bays(exposure_category="C", hvhz=True)) == 7

    # ...and every bay respects the maximum the row it came from states
    for site, limit in ((dict(exposure_category="B", hvhz=False), 1829),
                        (dict(exposure_category="C", hvhz=False), 1219),
                        (dict(exposure_category="C", hvhz=True), 914)):
        assert max(bays(**site)) <= limit


def test_a_table_scoped_to_a_product_line_is_aimed_at_it(snapshot):
    """A table's `scope` is an EntityRef — `{kind, id}` — and the evaluator's
    scope is bound DIMENSIONS, `{"series": …}`. They share a word and are not the
    same thing.

    Copying one into the other produced a rule that could never fire:
    `_scope_matches` requires every key to be present in the context and nothing
    binds `kind` or `id`. Unit tests could not see it, because a table built in a
    test carries no scope — it took ingesting a whole document, which is exactly
    what the fixture is for.
    """
    versions = ingest(snapshot).knowledge.versions
    assert versions and all(v.scope == {"series": "M-VINYL"} for v in versions)


def test_a_scope_we_cannot_aim_is_refused_not_widened():
    """Dropping an unmappable scope would leave the table applying to EVERY
    product, which is the silent wrong answer. It closes by a schema change HERE,
    so `closes_by` is `planning` — showing a curator that row would be showing
    them work they cannot do."""
    from fenceai.knowledge.parameters import ParameterRow, ParameterTable, Quantity, expand

    table = ParameterTable(
        parameter="max_span_mm", scope={"kind": "orchard_row", "id": "X"},
        value_type="quantity(mm)",
        rows=[ParameterRow(value=Quantity(amount_milli=1200000, unit="mm"))])
    versions, gaps = expand(table)

    assert versions == [], "a table we cannot aim must not apply everywhere"
    assert [g.because.code for g in gaps] == ["parameter_scope_unmappable"]
    assert gaps[0].closes_by == "planning"


# -- warnings: typed at the door, and placed rather than counted ---------------

def test_the_fixtures_warnings_parse_as_the_contracts_own_type(snapshot):
    """They used to arrive as `Any` and be counted as unconsumed. Build-order
    item 8 gave them somewhere to go, so they are parsed — and a `text_raw`,
    `lang` or `attaches_to` missing from a published warning now fails HERE,
    loudly at the door, rather than at the reader it was written for."""
    assert len(snapshot.warnings) == 9
    assert {w.attaches_to.kind for w in snapshot.warnings} == {
        "document", "step", "product", "model", "maintenance", "warranty", "procedure"}


def test_a_published_warnings_severity_word_is_not_normalised(snapshot):
    """CAUTION beside WARNING, in one document, arriving intact. The fixture
    carries both precisely because an engine that mapped either onto its own
    severity enum would make this assertion pass while destroying the
    distinction."""
    assert {w.severity_lexeme for w in snapshot.warnings} >= {"CAUTION", "WARNING"}


def test_ingest_carries_every_warning_through_and_vouches_for_none(snapshot):
    """`Ingested.warnings` is the list `report/annexe.py` places. NOT merged into
    `knowledge`: nothing selects between two warnings and nothing defeats one, so
    a `KnowledgeVersion` would put them in front of the evaluator, which is the
    one place they have no business being."""
    out = ingest(snapshot, as_of="2026-08-25")
    assert len(out.warnings) == len(snapshot.warnings)
    assert out.warning_defects == []
    assert not any(v.object_id.startswith("W-") for v in out.knowledge.versions)


def test_a_published_warning_that_contradicts_its_own_schema_is_reported(snapshot):
    """A document-scoped warning that also names a line. Deliberately NOT a gap:
    a gap is a hole in what we were told and closes by somebody adding knowledge,
    while this is a payload contradicting its own schema and closes by an edit at
    the sender. Different remedy, different audience."""
    bad = snapshot.model_copy(deep=True)
    bad.warnings[0].attaches_to.ref = "some-line"
    out = ingest(bad, as_of="2026-08-25")
    assert len(out.warning_defects) == 1
    assert "renders once in the annexe" in out.warning_defects[0]
    # ...and it is still CARRIED. A malformed warning is not a warning to drop.
    assert len(out.warnings) == len(bad.warnings)


def test_the_fixtures_warnings_place_where_the_contract_says(snapshot):
    """The fixture exists to be placed, not only parsed — that is what makes it
    evidence rather than an example. Three identical footnotes collapse to one
    entry, the procedure-scoped one is reported unplaceable because this engine
    models no procedures, and nothing is lost."""
    from fenceai.report.annexe import place_warnings

    placement = place_warnings(
        ingest(snapshot).warnings,
        steps=["FIXTURE-step-set-posts"], skus=["FIXTURE-SKU-PANEL-1"],
        model_refs=["M-VINYL"])
    assert placement.carried() == len(snapshot.warnings)
    footnote = [p for p in placement.at("annexe") if p.instances > 1]
    assert len(footnote) == 1 and footnote[0].instances == 3
    assert len(placement.at("unplaceable")) == 1
    assert placement.not_in_plan == 0


def test_a_published_warning_may_arrive_with_no_citation(snapshot):
    """One of the fixture's nine has no `cites`, and the count of these is the
    most useful thing this side can send back while the other team designs:
    §1.1 makes `SourceRef.id` opaque and unbuildable, so nobody without the
    Discovery surface can mint one."""
    assert sum(1 for w in snapshot.warnings if not w.cites) == 1
