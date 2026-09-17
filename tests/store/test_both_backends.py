"""The same behaviour, twice, once per database.

Not a port test — a parity test. Everything asserted here is something
`store/db.py` already promises on SQLite; the point is that Postgres
promises it identically, so the dialect shim cannot drift without a
red test.
"""

from __future__ import annotations

import json

from fenceai.learning.model import Correction
from fenceai.project.model import Project


def test_a_project_survives_a_round_trip(store):
    store.save_project(Project(id="p1", name="Test job"), actor="user:dana")
    loaded = store.load_project("p1")
    assert loaded is not None
    assert loaded.id == "p1"
    assert loaded.name == "Test job"


def test_saving_twice_updates_rather_than_duplicates(store):
    store.save_project(Project(id="p1", name="Test job"))
    store.save_project(Project(id="p1", name="Renamed"))
    assert len(store.list_projects()) == 1
    assert store.load_project("p1").name == "Renamed"
    assert sum(1 for r in store.audit_entries(100) if r["ref"] == "p1") == 2


def test_an_unknown_project_is_None_not_an_error(store):
    assert store.load_project("nope") is None


def test_the_audit_log_is_newest_first_with_a_unique_sequence(store):
    """Enough rows to step the sequence past a WIDTH change, deliberately.

    `seq` must be a number on both backends, and the cheap way to prove it is
    not one is to make lexicographic order disagree with numeric order — which
    only happens where the number of characters changes, because `"9" > "10"`
    as text. Two projects could never reach such a step; this walks the
    sequence past whichever one comes next, so the check does not depend on
    how many rows seeding happened to leave behind. It was crossing 9-to-10
    only by that accident, and a larger or smaller seed would have quietly
    removed its teeth without turning it red.
    """
    first = store.audit_entries(1)[0]["seq"]
    # The next power of ten above the sequence's next value: land past it.
    boundary = 10 ** len(str(first + 1))
    refs = [f"p{n}" for n in range(1, max(13, boundary - first + 2))]
    assert len(refs) > 10
    for ref in refs:
        store.save_project(Project(id=ref, name=ref.upper()))

    entries = store.audit_entries(10_000)
    seqs = [r["seq"] for r in entries]
    assert all(isinstance(x, int) for x in seqs)       # never the string "10"
    assert len(set(seqs)) == len(seqs)
    assert seqs == sorted(seqs, key=int, reverse=True)
    # ...and NUMERIC order is not lexicographic order here, so a TEXT column
    # sorting itself could not have produced this list.
    assert seqs != sorted(seqs, key=str, reverse=True)

    # The straddling pair, named rather than inferred: consecutive seqs whose
    # string comparison points the other way, in the order the writes happened.
    straddles = [
        (a, b) for a, b in zip(seqs, seqs[1:]) if a == b + 1 and str(a) < str(b)
    ]
    assert straddles, "the sequence never crossed a change of width"

    # Newest first, so our writes come back reversed.
    ours = [r["ref"] for r in entries if r["ref"] in set(refs)]
    assert ours == list(reversed(refs))


def test_the_seeds_are_present_on_a_fresh_store(store):
    assert len(store.part_library().parts) == 8
    assert store.fence_model_library().listing()


def test_a_correction_thread_orders_by_created_at_then_id_on_both_backends(store):
    """`list_corrections` sorts on `json_field('doc', 'created_at')`, the one
    `Dialect` difference that changes SQL *semantics* rather than syntax
    (`json_extract` vs. the `::jsonb->>` operator) and, before this test, the
    one with no execution coverage at all.

    Saved out of both chronological AND id order, so a backend that dropped
    the ORDER BY (returning insertion order) or that accidentally sorted on
    `id` alone (ids are deliberately non-alphabetical against their
    timestamps) would both go red.
    """
    store.save_correction(
        Correction(id="mid", project_id="p1", generation_run_id="run1",
                   created_at="2024-01-03T00:00:00Z")
    )
    store.save_correction(
        Correction(id="alpha", project_id="p1", generation_run_id="run1",
                   created_at="2024-01-02T00:00:00Z")
    )
    store.save_correction(
        Correction(id="zeta", project_id="p1", generation_run_id="run1",
                   created_at="2024-01-01T00:00:00Z")
    )
    # A different project's correction, saved in the middle of the sequence,
    # timestamped so an unfiltered read would interleave it — this is the
    # branch that builds a different SQL string around the same ORDER BY.
    store.save_correction(
        Correction(id="other", project_id="p2", generation_run_id="run1",
                   created_at="2024-01-02T12:00:00Z")
    )
    # Two corrections sharing one `created_at`: the id must break the tie,
    # and do so the SAME way on every read, or the order is not total.
    store.save_correction(
        Correction(id="b_dup", project_id="p1", generation_run_id="run1",
                   created_at="2024-01-04T00:00:00Z")
    )
    store.save_correction(
        Correction(id="a_dup", project_id="p1", generation_run_id="run1",
                   created_at="2024-01-04T00:00:00Z")
    )

    expected_p1 = ["zeta", "alpha", "mid", "a_dup", "b_dup"]
    assert [c.id for c in store.list_corrections("p1")] == expected_p1
    # Read again: the tie must resolve identically, not merely "some" order.
    assert [c.id for c in store.list_corrections("p1")] == expected_p1

    unfiltered = store.list_corrections()
    assert [c.id for c in unfiltered] == [
        "zeta", "alpha", "other", "mid", "a_dup", "b_dup"
    ]


def test_a_correction_with_no_timestamp_sorts_first_on_both_backends(store):
    """The docstring's promise, against the one default the two databases
    disagree on.

    SQLite sorts NULLs FIRST ascending; Postgres sorts them LAST. Both are
    correct per the standard's "implementation-defined" and neither is
    negotiable, so the SQL says which one it wants. Without `NULLS FIRST` this
    passes on SQLite and fails on Postgres — and the failure it stands for is
    not a red test but a silent one: importing the pilot's SQLite corrections
    into Cloud SQL, which is this whole slice's purpose, would move every
    unstamped turn from the top of its thread to the bottom.

    The unstamped row is written through the connection rather than through
    `save_correction`, because `save_correction` stamps a blank — a row with
    NO `created_at` key can only come from a database that predates the field,
    which is exactly the data this is about.
    """
    legacy = Correction(id="legacy", project_id="p1", generation_run_id="run0")
    doc = legacy.model_dump()
    doc.pop("created_at")  # as the column was written before the field existed
    store._conn.execute(
        "INSERT INTO corrections (id, project_id, doc) VALUES (?,?,?)",
        (legacy.id, legacy.project_id, json.dumps(doc)),
    )
    store._conn.commit()

    store.save_correction(
        Correction(id="stamped", project_id="p1", generation_run_id="run0",
                   created_at="2024-01-01T00:00:00Z")
    )
    # An id that sorts BEFORE the unstamped row alphabetically, so a backend
    # that dropped the timestamp sort entirely cannot pass by accident.
    store.save_correction(
        Correction(id="a_later", project_id="p1", generation_run_id="run0",
                   created_at="2024-06-01T00:00:00Z")
    )

    assert [c.id for c in store.list_corrections("p1")] == [
        "legacy", "stamped", "a_later"
    ]
    assert [c.id for c in store.list_corrections()][0] == "legacy"
