"""The same behaviour, twice, once per database.

Not a port test — a parity test. Everything asserted here is something
`store/db.py` already promises on SQLite; the point is that Postgres
promises it identically, so the dialect shim cannot drift without a
red test.
"""

from __future__ import annotations

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
    store.save_project(Project(id="p1", name="One"))
    store.save_project(Project(id="p2", name="Two"))
    entries = store.audit_entries(100)
    seqs = [r["seq"] for r in entries]
    assert seqs == sorted(seqs, reverse=True)
    assert len(set(seqs)) == len(seqs)
    assert entries[0]["ref"] == "p2"


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
