"""The same behaviour, twice, once per database.

Not a port test — a parity test. Everything asserted here is something
`store/db.py` already promises on SQLite; the point is that Postgres
promises it identically, so the dialect shim cannot drift without a
red test.
"""

from __future__ import annotations

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
