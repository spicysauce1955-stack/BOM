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
from fenceai.knowledge.parameters import expand
from fenceai.knowledge.snapshot import (
    Snapshot, SnapshotRefused, fixture_digest, ingest, load,
)
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
    assert snapshot.contract_version == "1.3.0"
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
    for.

    `source_docs` left it the same way, and the word it was filed under had been
    actively misleading: it is not an unimplemented feature but the join target
    of every `SourceRef.belongs_to` in the payload and the only carrier of
    `issue_date`, `version_status` and `superseded_by`. Reporting 75 of them as
    "unconsumed" told the other team we had no use for the join their whole
    provenance model hangs off."""
    assert ingest(snapshot).unconsumed == {}
    assert len(snapshot.source_docs) == 3


def test_the_fixture_digest_is_stable_and_is_not_the_contracts_snapshot_id(snapshot):
    """This used to be called `snapshot_id_for` and to claim it was "the one
    property of a snapshot this side can verify without trusting the sender".

    It is not, and the claim was the dangerous part. §1.2 defines `snapshot_id`
    as a sha256 over the canonical member list and §1.4 adds `policy_version` to
    it; this hashes `parameters` alone. Against the first real snapshot it
    returns `0bd95701…` where the payload declares `3ae88642…` — so anything
    gating on it would have read a conforming snapshot as drift. Renamed to what
    it does: catch a fixture that moved under a test."""
    assert fixture_digest(snapshot) == fixture_digest(snapshot)
    assert len(fixture_digest(snapshot)) == 64
    assert fixture_digest(snapshot) != snapshot.snapshot_id


# -- ingestion -----------------------------------------------------------------

def test_tables_become_ordinary_knowledge(snapshot):
    """One version, not four, and the source policy is why (§1.4).

    The fixture's three `max_span_mm` rows are a `structural_parameter` at
    `curation_level: 1`, and the shipped policy requires level 2 for anything
    structural — nobody has checked those numbers against the page. So they do not
    become knowledge at all. `slope_method` is an `installation_step`, which
    carries no curation bar, so it survives.

    That split is deliberate in the fixture: one change exercises a refusal and
    an admission at once."""
    out = ingest(snapshot, as_of="2026-08-25")
    assert [v.object_id for v in out.knowledge.versions] == [
        "slope_method@model/M-VINYL#0"]
    assert all(v.origin == "published" for v in out.knowledge.versions)


def test_the_source_that_admitted_a_value_is_recorded_on_the_run(snapshot):
    """§1.4 BINDING: `admitted_by` is recorded **on the run**, never on the
    published row — it depends on the task the value is being used for, which only
    the planner knows.

    So it rides on `KnowledgeBase`, which is what `generate()` already receives.
    An ABSENT verdict means "not judged" and must never be read as "judged and
    passed": authored knowledge has no provenance to judge, so it has no entry
    here, and a renderer has to show those two states differently."""
    out = ingest(snapshot, as_of="2026-08-25")
    version = out.knowledge.versions[0]
    verdict = out.knowledge.admitted_for(version)
    assert verdict is not None
    assert verdict.source_class == "manufacturer_installation_instruction"
    assert verdict.curation_level == 1
    # the rejected rows produced no version, so there is nothing to vouch for
    assert len(out.knowledge.admitted) == 1


def test_published_and_discovered_gaps_are_one_list_but_counted_apart(snapshot):
    """They are the same type by contract. But "your table declares a hole" and
    "your table contradicts itself" are different messages to send back."""
    out = ingest(snapshot, as_of="2026-08-25")
    assert len(out.gaps) == 9
    assert out.discovered == 6
    # the platform's own gaps come FIRST — what it chose to tell us, before our
    # findings about its data
    assert [g.because.code for g in out.gaps[:3]] == [
        "gate_not_modelled", "readers_disagreed_on_bracket",
        "parameter_condition_excluded"]


def test_an_unchecked_row_that_is_also_expired_reports_both(snapshot):
    """Validity and admissibility are separate questions about the same row, and
    the order they are asked in has a cost.

    The fixture's `max_span_mm` row 2 is BOTH below the curation bar and backed by
    an NOA that expired in 2025. Judging admissibility first and stopping would
    report only *"a reviewer should check this against the source image"* — sending
    a reviewer to open a crop for a document that lapsed two years ago. That is
    precisely the wasted bounded work the review queue exists to avoid, so both
    are reported."""
    codes = [g.because.code for g in ingest(snapshot, as_of="2026-08-25").gaps]
    assert codes.count("source_below_min_curation") == 3
    assert "parameter_authority_lapsed" in codes


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
    points = [g.because.params["point"] for g in ingest(snapshot).gaps
              if g.because.code == "uncovered_parameter_point"]
    # structured (§1.1 `ParamRef.point`), not a pre-joined English fragment —
    # `hvhz` is a bool and stays one, where the old string carried Python's
    # `True` into a Hebrew sentence
    assert sorted(points, key=lambda p: str(p["hvhz"])) == [
        {"exposure_category": "D", "hvhz": False},
        {"exposure_category": "D", "hvhz": True},
    ]


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
    assert excluded[0].because.params["point"] == {
        "exposure_category": "B", "hvhz": True}
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
    the whole expansion exists for, exercised over a whole document.

    The rows are raised to `curation_level: 2` first, because that is what makes
    them ADMISSIBLE for a structural parameter under the shipped policy (§1.4) —
    and admissible is the precondition for this property being exercisable at all.
    The fixture ships them at level 1 on purpose, so the refusal path has
    something to refuse; `test_the_fixtures_own_rows_fall_back_when_unchecked`
    below is that half. Between them, both outcomes of the same gate are pinned.

    This is not the test bending to fit the policy. A published row that nobody
    has checked SHOULD NOT drive a generation, so the only honest way to test
    "published rows drive generation" is with rows a reviewer has signed off."""
    from fenceai.fencemodel.demo import demo_models
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.fencemodel.selection import FenceModelChoice
    from fenceai.parts.demo import demo_parts
    from fenceai.parts.model import PartLibrary

    checked = snapshot.model_copy(deep=True)
    for table in checked.parameters:
        for row in table.rows:
            row.provenance.curation_level = 2
    out = ingest(checked, as_of="2026-08-25")
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
    versions, gaps, _ = expand(table)

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
    """A document-scoped warning whose ref names no document that came with the
    payload. Deliberately NOT a gap: a gap is a hole in what we were told and
    closes by somebody adding knowledge, while this is a payload contradicting
    its own schema and closes by an edit at the sender.

    The rule this exercises was narrowed after the first real snapshot falsified
    the old one. It used to be "an annexe-scoped warning may not name anything at
    all", which flagged **276 of 289** real warnings — every one of which named
    its own document's `content_hash`, which is the only thing that lets an
    annexe say which guide a sentence came from. What survives is the half that
    can be checked: an annexe-scoped ref names a document, and one resolving to
    nothing in hand is the defect."""
    bad = snapshot.model_copy(deep=True)
    bad.warnings[0].attaches_to.ref = "some-line"
    out = ingest(bad, as_of="2026-08-25")
    assert len(out.warning_defects) == 1
    assert "not one of the documents" in out.warning_defects[0]
    # ...and it is still CARRIED. A malformed warning is not a warning to drop.
    assert len(out.warnings) == len(bad.warnings)


def test_an_annexe_warning_naming_its_own_document_is_carried_without_complaint(snapshot):
    """The regression for the 276-of-289 flood. The publisher sets
    `attaches_to = {kind: "document", ref: <its own content_hash>}`, and that ref
    resolves through the same `source_docs` join §1.2.1's closure rule uses."""
    good = snapshot.model_copy(deep=True)
    good.warnings[0].attaches_to.kind = "document"
    good.warnings[0].attaches_to.ref = good.source_docs[0].content_hash
    assert ingest(good, as_of="2026-08-25").warning_defects == []


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


# -- the door: version gate, closure, quarantine (v1.2) ------------------------

def test_a_snapshot_from_an_unknown_major_is_refused_at_the_door():
    """§3.2 obligation 3 is OUR promise, not theirs: *"refuse a snapshot built
    against an unknown major — loudly, at load, not silently at generate."*

    It was never kept. `contract_version` was parsed and read nowhere, so a
    payload declaring `9.9.9` loaded without a word and the mismatch surfaced
    later as a heap of unlabelled type errors about whichever field happened to
    have moved. A minor difference still loads, by the contract's own registry
    rule that additions are never breaking."""
    with pytest.raises(SnapshotRefused) as caught:
        load({"snapshot_id": "X", "contract_version": "9.9.9"})
    assert caught.value.code == "contract_major_unsupported"
    assert "9.9.9" in str(caught.value)

    # A LATER minor loads: the contract's registry rule is that additions are
    # never breaking, so a payload built against a newer point release is fine.
    later_minor, _ = load({"snapshot_id": "X", "contract_version": "1.9.0"})
    assert later_minor.snapshot_id == "X"


def test_a_snapshot_cut_before_the_typed_date_is_refused_in_one_sentence():
    """Amendment 002 was not an addition — it changed four date fields from
    strings to `Date` — so the registry rule that additions are never breaking
    does not cover it, and a pre-v1.2 payload cannot be read.

    The first real snapshot is exactly this: `3ae88642…` declares `1.1.0` and
    carries `"04/24/2025"` where a `Date` now belongs. Without a minor floor it
    produced 113 unlabelled type errors about a field nobody was asking about,
    when the actual answer is one sentence naming the amendment and whose move
    it is. Refusing here is also what stops the tempting wrong fix: a parser on
    this side would resolve `05/04/2023` by house convention and manufacture a
    fact the source does not state."""
    with pytest.raises(SnapshotRefused) as caught:
        load({"snapshot_id": "X", "contract_version": "1.1.0"})
    assert caught.value.code == "contract_minor_predates_typed_date"
    assert "re-cut" in str(caught.value)


def test_a_gap_that_does_not_parse_is_quarantined_not_fatal_and_not_dropped():
    """The third option, and both alternatives are worse.

    Failing the load costs every valid table and warning in the payload over gap
    shape drift — which is not hypothetical: the first real snapshot's 81 gaps
    all carry a bare-string `subject`, against 4 valid tables and 289 valid
    warnings. Dropping them silently puts a hole in the one list whose
    completeness is the whole promise (§3.2.4). So they are carried as authoring
    text for the sender, counted, and visible."""
    snap, defects = load({
        "snapshot_id": "X",
        "gaps": [
            {"id": "g1", "kind": "missing_value", "subject": "element-1234",
             "because": {"code": "c"}, "would_close": "a value"},
            {"id": "g2", "kind": "missing_value",
             "subject": {"kind": "param", "id": "max_span_mm"},
             "because": {"code": "c"}, "would_close": "a value"},
        ],
    })
    assert len(snap.gaps) == 1, "the conforming gap still loads"
    assert len(defects) == 1
    assert "published gap 0" in defects[0] and "subject" in defects[0]
    assert ingest(snap, gap_defects=defects).gap_defects == defects


def test_a_hole_the_publisher_already_declared_is_not_counted_twice(snapshot):
    """The first real snapshot publishes all 16 of its `condition_point_uncovered`
    gaps AND carries the same 16 points in `table.uncovered`, from which
    `expand()` independently derives its own — 32 gaps for 16 holes, every one
    appearing twice in a curator's queue.

    `GapSubject.key()` is what makes them recognisable as one hole: parameter,
    scope and point together. That identity is exactly what v1.2's `ParamRef`
    added, which is the argument for having implemented the type rather than
    widening `id` into a longer string."""
    doubled = snapshot.model_copy(deep=True)
    table = doubled.parameters[0]
    point = table.uncovered[0]
    derived = expand(table, tenant=doubled.tenant)[1]
    mine = next(g for g in derived if g.subject.point == point)
    doubled.gaps.append(mine.model_copy(deep=True, update={"id": "THEIRS"}))

    out = ingest(doubled)
    keys = [g.subject.key() for g in out.gaps]
    assert len(keys) == len(set(keys)), "one hole, one gap"
    assert out.deduped == 1
    # theirs survives, ours is the one suppressed: it is their declaration
    assert "THEIRS" in {g.id for g in out.gaps}


def test_every_cited_document_resolves_inside_the_snapshot(snapshot):
    """§1.2.1 BINDING, and it is machine-checkable in ten lines. §3.2.2 forbids
    Planning from calling Discovery during a run, so a `belongs_to` that resolves
    to nothing in the payload reproduces the exact defect the field was added to
    close, with extra fields.

    The first real snapshot PASSES this — 543 cited refs, 75 distinct hashes, 0
    dangling — which is the right outcome for a check on a promise being kept,
    and no reason not to have the check."""
    assert snapshot.dangling_refs() == []

    broken = snapshot.model_copy(deep=True)
    broken.source_docs = []
    assert broken.dangling_refs(), "a ref with nothing to join to must be visible"


def test_a_knowledge_global_snapshot_states_a_null_tenant():
    """§1.1: `TenantId  str | null`, where `null` is tenant-agnostic. As `str`
    this rejected a conforming Knowledge-global payload outright, and `""` is a
    third fact — a tenant named empty string — not a spelling of absent."""
    snap, _ = load({"snapshot_id": "X", "tenant": None})
    assert snap.tenant is None


def test_the_fixtures_own_rows_fall_back_when_unchecked(snapshot):
    """The other half of the gate, and the behaviour a person actually sees.

    The fixture's `max_span_mm` rows are exactly what the shipped policy refuses:
    a `structural_parameter` at `curation_level: 1`, where the bar is 2. So they
    become no knowledge at all, and the generator's EXISTING "nothing covered
    max_span_mm" path takes over — `FALLBACK_MAX_SPAN_MM`, a gap node, and a
    warning on every bay built to it.

    **No new fallback machinery was written for this slice.** That path was built
    for a hole of exactly this shape, and a refused source is one. The number
    moving here is the point: 1500 mm bays under a published maximum become 1500
    mm bays under a conservative assumption, and the plan says which it used."""
    from fenceai.fencemodel.demo import demo_models
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.fencemodel.selection import FenceModelChoice
    from fenceai.parts.demo import demo_parts
    from fenceai.parts.model import PartLibrary
    from fenceai.strategy.generator import FALLBACK_MAX_SPAN_MM

    out = ingest(snapshot, as_of="2026-08-25")
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    kb.versions.extend(out.knowledge.versions)

    result = generate(
        straight_topology(6000), KnowledgeBase(versions=kb.versions),
        demo_catalog(), site=SiteConditions(exposure_category="C", hvhz=False),
        models=FenceModelLibrary(models=list(demo_models().values())),
        parts=PartLibrary(parts=demo_parts()),
        default_model=FenceModelChoice(model_id="M-VINYL"))

    # laid out to the fallback, not to the refused published maximum
    assert all(s.width_mm <= FALLBACK_MAX_SPAN_MM for s in result.strategy.spans)
    # ...and the run says so, rather than quietly assuming
    codes = {w.code for w in result.strategy.warnings}
    assert "uncovered_max_span" in codes

    # the refusal itself is reported, with the work that would close it
    refused = [g for g in out.gaps
               if g.because.code == "source_below_min_curation"]
    assert len(refused) == 3
    assert "reviewer" in refused[0].would_close
    assert refused[0].cites, "a refusal names the document it refused"


def test_the_verdict_reaches_the_decision_graph_and_absence_means_unjudged(snapshot):
    """Step 4 of the slice: what backed a number is visible in the explanation.

    Nothing new is invented in the graph. `governed_by` edges have always carried
    a fact's ref, so every decision a published fact governed was already
    traceable to it; the verdict joins onto that same ref. That is why showing it
    cost no new plumbing and no signature change.

    The second assertion is the one that matters more. An authored company rule
    has NO verdict, and that must render differently from a judged pass — an
    absent verdict means "never judged", and a surface that showed the two alike
    would claim a provenance check nobody performed on a rule we wrote
    ourselves."""
    from fenceai.fencemodel.demo import demo_models
    from fenceai.fencemodel.library import FenceModelLibrary
    from fenceai.fencemodel.selection import FenceModelChoice
    from fenceai.parts.demo import demo_parts
    from fenceai.parts.model import PartLibrary

    checked = snapshot.model_copy(deep=True)
    for table in checked.parameters:
        for row in table.rows:
            row.provenance.curation_level = 2
    out = ingest(checked, as_of="2026-08-25")
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    kb.versions.extend(out.knowledge.versions)

    result = generate(
        straight_topology(6000),
        KnowledgeBase(versions=kb.versions, admitted=out.knowledge.admitted),
        demo_catalog(), site=SiteConditions(exposure_category="C", hvhz=False),
        models=FenceModelLibrary(models=list(demo_models().values())),
        parts=PartLibrary(parts=demo_parts()),
        default_model=FenceModelChoice(model_id="M-VINYL"))

    fact_nodes = [n for n in result.graph.nodes
                  if n.action == "knowledge_version"]
    judged = {n.payload["knowledge_ref"]: n.payload["admitted_by"]
              for n in fact_nodes if n.payload.get("admitted_by")}
    unjudged = [n.payload["knowledge_ref"] for n in fact_nodes
                if not n.payload.get("admitted_by")]

    published = next(r for r in judged if r.startswith("max_span_mm@"))
    assert judged[published]["source_class"] == \
        "manufacturer_installation_instruction"
    assert judged[published]["curation_level"] == 2

    # authored rules are present and carry NO verdict — not a failing one
    assert any(ref.startswith("K-") for ref in unjudged)
    assert not any(ref.startswith("K-") for ref in judged)
