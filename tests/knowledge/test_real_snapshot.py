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
        pytest.skip(f"published snapshot not available at {SNAPSHOT}")
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
