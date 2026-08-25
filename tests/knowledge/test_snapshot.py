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
    assert len(snapshot.gaps) == 2


def test_what_arrives_and_is_not_consumed_is_counted_not_hidden(snapshot):
    """A snapshot carrying 40 warnings into an engine with no warning consumer is
    a fact the operator should see — and, while the other team is designing, the
    most useful thing we can tell them about their own payload."""
    assert ingest(snapshot).unconsumed == {"warnings": 1, "source_docs": 2}


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
    assert len(out.gaps) == 5
    assert out.discovered == 3
    # the platform's own gaps come FIRST — what it chose to tell us, before our
    # findings about its data
    assert [g.code for g in out.gaps[:2]] == [
        "gate_not_modelled", "readers_disagreed_on_bracket"]


def test_the_lapsed_row_is_found_against_the_pinned_as_of(snapshot):
    """The fixture carries an NOA that expired in 2025 on purpose."""
    lapsed = [g for g in ingest(snapshot, as_of="2026-08-25").gaps
              if g.code == "parameter_authority_lapsed"]
    assert len(lapsed) == 1
    assert lapsed[0].params["authority"] == "NOA 19-0101.01"
    # ...and against an as_of before it expired, it is not a finding
    assert not [g for g in ingest(snapshot, as_of="2024-06-01").gaps
                if g.code == "parameter_authority_lapsed"]


def test_no_as_of_makes_no_expiry_judgement(snapshot):
    """Generation is pure; a clock here would make one project against one
    snapshot warn differently on different days."""
    assert not [g for g in ingest(snapshot).gaps
                if g.code == "parameter_authority_lapsed"]


def test_the_uncovered_points_the_table_declares_are_reported(snapshot):
    """§1.3 BINDING: points no row covers are listed, never silently omitted. The
    fixture declares exposure D in both HVHZ states."""
    points = {g.params["point"] for g in ingest(snapshot).gaps
              if g.code == "uncovered_parameter_point"}
    assert points == {"exposure_category=D, hvhz=False",
                      "exposure_category=D, hvhz=True"}


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
    assert [g.code for g in gaps] == ["parameter_scope_unmappable"]
    assert gaps[0].closes_by == "planning"
