"""The first real published snapshot this engine can consume, unmodified.

Every earlier test in this package works against a fixture WE wrote, or against
a real snapshot with its remaining publisher-side work simulated locally. This
one takes the document exactly as the Knowledge Platform produced it and asserts
that nothing has to be done to it first.

It is skipped rather than failed when the file is absent: the snapshot lives in
the other team's repository and this suite must pass for someone who has only
this one checked out. A skip says "not verifiable here"; a failure would say
"broken", and they are different facts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fenceai.knowledge.snapshot import (
    SnapshotRefused, canonical_snapshot_id, ingest, load, snapshot_id_matches,
)

SNAPSHOT = Path(
    "/home/user/Workspace/fence-rag/workspace/snapshots"
    "/a4181dbf2e781b25017399a0b89632b81d5f14d433d99393bffa28f7e0a7a706.json")


@pytest.fixture()
def raw() -> dict:
    if not SNAPSHOT.exists():
        pytest.skip(
            f"published snapshot not available at {SNAPSHOT}. The id is PINNED "
            f"on purpose — a test that followed 'whatever is newest' would "
            f"silently start asserting about a different document. When the "
            f"Knowledge Platform re-cuts, update the constant deliberately.")
    return json.loads(SNAPSHOT.read_text())


def test_the_published_snapshot_loads_with_nothing_done_to_it(raw):
    """The milestone, and the reason it is worth its own file.

    Every previous attempt needed something first. The first real snapshot
    (`3ae88642`) failed with 113 validation errors. Its re-cut (`9e760aae`)
    needed amendment 002 applied to a local copy before it would parse. This one
    needs nothing — and the assertion that matters is `gap_defects == []`,
    because a load that quarantined 65 gaps would also "succeed"."""
    snapshot, gap_defects = load(raw)
    assert gap_defects == [], "every published gap parses"
    assert len(snapshot.parameters) == 9
    assert len(snapshot.gaps) == 65
    assert len(snapshot.source_docs) == 75


def test_every_cited_document_resolves(raw):
    """§1.2.1's closure rule, against real data rather than a fixture. It has
    held every time it has been checked, which is the correct outcome for a check
    on a promise being kept."""
    snapshot, _ = load(raw)
    assert snapshot.dangling_refs() == []


def test_the_declared_snapshot_id_is_verifiable(raw):
    """§1.2, and it took a paragraph from the publisher to make possible.

    Our own digest hashed `parameters` alone and could never agree with anyone;
    it claimed in its docstring to be "the one property of a snapshot this side
    can verify without trusting the sender" and verified nothing. The
    canonicalisation was asked for in `conversation.md` T30 §6 and answered in
    T38, so this is the first time either side can check a document against the
    id it declares."""
    assert snapshot_id_matches(raw) is True
    assert canonical_snapshot_id(raw) == raw["snapshot_id"]


def test_a_payload_that_does_not_match_its_own_id_is_refused(raw):
    """The failure this catches is invisible to every other check: change one
    field and the document is still well-formed everywhere, so nothing downstream
    notices that it is no longer the snapshot its id names."""
    tampered = dict(raw, tenant="somebody-else")
    with pytest.raises(SnapshotRefused) as caught:
        load(tampered)
    assert caught.value.code == "snapshot_id_mismatch"


def test_an_unnormalisable_date_arrives_null_beside_its_own_lexeme(raw):
    """§1.1's BINDING null rule, honoured by the publisher on the exact string
    the contract cites.

    `05/04/2023` is ambiguous on its face, and amendment 002 exists so that
    nobody resolves it by house convention. It publishes as `iso: null` with the
    lexeme intact — so a curator can read what the document said, and no rule
    reaching for a date finds a guess."""
    snapshot, _ = load(raw)
    unreadable = [d.issue_date for d in snapshot.source_docs
                  if d.issue_date is not None and d.issue_date.iso is None]
    assert unreadable, "the publisher has at least one ambiguous stamp"
    assert any("05/04/2023" in d.value_raw for d in unreadable)


def test_a_published_gap_is_addressable(raw):
    """Amendment 004's whole purpose. Before it, all 65 subjects were bare
    strings, so a gap could be counted and not acted on — nobody could be sent to
    the thing it concerned."""
    snapshot, _ = load(raw)
    kinds = {g.subject.ref_kind for g in snapshot.gaps}
    assert kinds == {"element", "source_document"}
    assert all(g.subject.id for g in snapshot.gaps)
    # ...and each subject has a stable identity, which is what dedup keys on
    assert len({g.subject.key() for g in snapshot.gaps}) > 1


def test_ingesting_it_produces_usable_knowledge_and_names_what_it_cannot(raw):
    """What the whole chain is for. 16 rows become knowledge with a source
    verdict each; the five `paired` tables are refused with a gap naming the work
    that would let us use them, rather than approximated into a number."""
    snapshot, defects = load(raw)
    out = ingest(snapshot, as_of="2026-08-31", gap_defects=defects)

    refs = {(v.object_id, v.version) for v in out.knowledge.versions}
    assert len(out.knowledge.versions) == 16
    assert len(refs) == 16, "no two published rows share an identity"
    assert len(out.knowledge.admitted) == 16, "every row's source was judged"

    codes = {g.because.code for g in out.gaps}
    assert "parameter_paired_unsupported" in codes
    assert out.warning_defects == []


# -- the parts snapshot (`b2f2fe45…`, obligation 5's first vertical slice) ------

PARTS_SNAPSHOT = Path(
    "/home/user/Workspace/fence-rag/workspace/snapshots"
    "/b2f2fe45326f42dac10d0d0203337b917b6613e1c8d04f0c6dd39806f54beb03.json")


@pytest.fixture()
def parts_raw() -> dict:
    if not PARTS_SNAPSHOT.exists():
        pytest.skip(f"parts snapshot not available at {PARTS_SNAPSHOT} — pinned "
                    f"deliberately, see the note on the fixture above")
    return json.loads(PARTS_SNAPSHOT.read_text())


def test_the_first_snapshot_carrying_parts_loads_and_verifies(parts_raw):
    """Obligation 5 closed for one vertical slice: 11 `Part`s and 5 `PartType`
    extensions, every parent chain terminating in the spine.

    This cut is kept pinned even though `f4d40fb8` supersedes it, because it is
    the only one carrying the two `specfield_wire_shape_unresolved` gaps — see
    `test_a_because_param_may_be_a_list`.

    **The `unconsumed` assertion changed here on purpose.** It read
    `{"part_types": 5, "parts": 11}` while this docstring said *"we do not
    consume them yet — that is item 7"*. Item 7 is built, so the same payload
    now reports nothing unconsumed: the parts are filed against the spine and
    every spec value is judged. In THIS cut both spec-bearing rails still hold
    `spec: []` — the values were withheld pending C15 — so there is nothing to
    admit, and `part_specs` being empty is the payload's state rather than a
    consumer that does nothing."""
    snapshot, gap_defects = load(parts_raw)
    assert snapshot_id_matches(parts_raw) is True
    assert gap_defects == []
    assert len(snapshot.parameters) == 9
    assert snapshot.dangling_refs() == []

    out = ingest(snapshot, as_of="2026-09-03", gap_defects=gap_defects)
    assert out.unconsumed == {}
    assert len(out.knowledge.versions) == 16
    assert len(snapshot.parts) == 11 and len(snapshot.part_types) == 5
    assert out.part_specs == [], "this cut published no spec values yet"
    assert out.part_defects == [], "every parent chain reaches the spine"


def test_a_because_param_may_be_a_list(parts_raw):
    """§1.2.1 puts no ceiling on what a `because` param is, and this snapshot is
    where that stopped being theoretical: a `specfield_wire_shape_unresolved`
    gap names the candidate shapes it could not choose between, which is a list
    of strings.

    Our `params` type allowed a scalar or a mapping and not a list, so both gaps
    were quarantined — the third time a shape the contract permits was rejected
    by a narrower type of ours. Worth a test rather than a widened annotation
    alone, because the renderer has to format it too: `String(v)` on an array
    produces comma-joined output with no spaces, which looks deliberate and is
    not."""
    snapshot, gap_defects = load(parts_raw)
    assert gap_defects == []
    listed = [g for g in snapshot.gaps
              if isinstance(g.because.params.get("candidate_shapes"), list)]
    assert len(listed) == 2
    assert all(g.closes_by == "planning" for g in listed), (
        "the shape question is ours to settle, not a curator's")


# -- the spec-values snapshot (`f4d40fb8…`, item 7's first real data) -----------

SPEC_SNAPSHOT = Path(
    "/home/user/Workspace/fence-rag/workspace/snapshots"
    "/f4d40fb886c4d3c764058f53344239ee94a244b2f95230b26a1cf12cad785773.json")


@pytest.fixture()
def spec_raw() -> dict:
    if not SPEC_SNAPSHOT.exists():
        pytest.skip(f"spec-values snapshot not available at {SPEC_SNAPSHOT} — "
                    f"pinned deliberately, see the note on the first fixture. "
                    f"This is the cut that closed C15 (`conversation.md` T43): "
                    f"`SpecField.value: Quantity | Token`, with the two real "
                    f"stock lengths published.")
    return json.loads(SPEC_SNAPSHOT.read_text())


def test_the_first_published_spec_values_are_judged_and_joined(spec_raw):
    """Item 7, end to end, against the first data that could exercise it.

    Two `nominal_length_mm` values, each cited to two real documents. The
    numbers are the ones T42 computed independently from the publisher's own
    lexemes — 16 ft × 304.8 = 4876.8 mm and 12 ft × 304.8 = 3657.6 mm — which is
    obligation 4's own worked example landing on whole thousandths rather than
    needing a rounding rule."""
    snapshot, gap_defects = load(spec_raw)
    assert snapshot_id_matches(spec_raw) is True
    assert gap_defects == []

    out = ingest(snapshot, as_of="2026-09-03", gap_defects=gap_defects)
    by_part = {s.part_id: s for s in out.part_specs}
    assert set(by_part) == {"shared/bt-rail-pr-3rail-white",
                            "shared/bt-rail-pr-3rail-color"}

    white = by_part["shared/bt-rail-pr-3rail-white"]
    assert white.key == "nominal_length_mm"
    assert white.value.amount_milli == 4876800
    assert white.value.value_raw == ["16 foot lengths"]
    assert by_part["shared/bt-rail-pr-3rail-color"].value.amount_milli == 3657600


def test_a_published_spec_value_is_judged_for_a_component_dimension(spec_raw):
    """§1.4 applied to a spec field for the first time. `manufacturer_
    installation_instruction` is rank 3 for `component_dimension` in the shipped
    default table — the rank the Knowledge team's own revision moved it to — and
    curation level 0 clears that row's bar, so these are ADMITTED rather than
    carried unjudged."""
    snapshot, defects = load(spec_raw)
    out = ingest(snapshot, as_of="2026-09-03", gap_defects=defects)

    for spec in out.part_specs:
        assert spec.task == "component_dimension"
        assert spec.admitted_by.rank == 3
        assert spec.admitted_by.source_class == \
            "manufacturer_installation_instruction"
        assert spec.admitted_by.curation_level == 0


def test_the_winning_citation_is_the_one_the_contract_names(spec_raw):
    """Both documents behind these values are the same class, both `unknown`,
    both undated — so §1.4's rank, curation and date steps all tie and the
    winner is decided by `content_hash`, the terminator amendment 005 added.

    Pinning the actual hash is the point: with a non-total key the winner was
    whichever citation the payload happened to list first, and two
    implementations of this contract would stamp different `admitted_by`."""
    snapshot, defects = load(spec_raw)
    out = ingest(snapshot, as_of="2026-09-03", gap_defects=defects)

    winners = {s.admitted_by.content_hash for s in out.part_specs}
    assert winners == {
        "00c965f58d3030b7e7c8a6c8c0b7e99f1579c5599dc476c8f6a62dd88c6cdd58"}
    assert all(s.admitted_by.issue_date is None for s in out.part_specs), \
        "these two documents carry no issue_date, so the date step is skipped"


def test_the_join_reaches_the_documents_that_came_with_the_payload(spec_raw):
    """§1.2.1's closure rule doing the work it exists for. Each value leans on
    two documents, and both resolve inside the snapshot — so a run can see their
    class and status without calling Discovery, which §3.2.2 forbids."""
    snapshot, defects = load(spec_raw)
    out = ingest(snapshot, as_of="2026-09-03", gap_defects=defects)

    assert snapshot.dangling_refs() == []
    for spec in out.part_specs:
        assert len(spec.sources) == 2
        assert all(d.source_class == "manufacturer_installation_instruction"
                   for d in spec.sources)
        assert all(d.version_status == "unknown" for d in spec.sources)


def test_the_whole_payload_is_now_accounted_for(spec_raw):
    """`unconsumed` is empty for the first time against a real snapshot, and
    every claim behind that is asserted here rather than implied: the parts file
    against the spine, the extensions' parent chains reach it, and nothing was
    dropped for being a shape we could not read."""
    snapshot, defects = load(spec_raw)
    out = ingest(snapshot, as_of="2026-09-03", gap_defects=defects)

    assert out.unconsumed == {}
    assert out.part_defects == []
    assert out.inactive_parts == []
    assert len(snapshot.parts) == 11
    assert len(snapshot.part_types) == 5


def test_each_admitted_value_says_that_nothing_here_can_apply_it(spec_raw):
    """The honest half. Both values are admitted and neither reaches a bill of
    materials, because no product in this catalog can claim to be a published
    `Part` — the demo rails are 3000 mm and 3600 mm stock, and matching them to
    `shared/bt-rail-pr-3rail-white` on nothing but a plausible name is exactly
    the class of correlation T41's own withdrawn first draft was."""
    snapshot, defects = load(spec_raw)
    out = ingest(snapshot, as_of="2026-09-03", gap_defects=defects)

    unapplied = [g for g in out.gaps
                 if g.because.code == "published_spec_unapplied"]
    assert len(unapplied) == 2
    assert {g.because.params["part_type"] for g in unapplied} == {"shared/rail"}
    assert all(g.closes_by == "planning" for g in unapplied)


def test_the_specfield_shape_question_closed_without_an_amendment(spec_raw):
    """C15's outcome, pinned where it can be checked rather than only recorded.

    The previous cut gapped both values with `specfield_wire_shape_unresolved`
    (`closes_by: planning`) because §2.2 published `38 | null` with a sibling
    `unit` — a bare `_mm` field obligation 4 has always forbidden. T42 answered
    that no amendment was needed (the type is not in `contract.md`; §1.2
    delegates it) and that a flat `Quantity` was one case too broad, since §2.2's
    own `key` list names `colour`. Both gaps are gone from this cut and the
    values publish as `Quantity`."""
    snapshot, _ = load(spec_raw)

    codes = {g.because.code for g in snapshot.gaps}
    assert "specfield_wire_shape_unresolved" not in codes
    assert len(snapshot.gaps) == 67
