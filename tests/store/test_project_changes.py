"""The store writes a change entry beside every save that changes a job.

`save_project` is the one door every route saves a job through, so it is where
the entry is taken: against the document actually stored, in the same commit as
the save. Runs on every backend the `dsn` fixture is configured for.
"""

from __future__ import annotations

from fenceai.project.model import Project
from fenceai.store.db import Store


def _codes(entry: dict) -> list[str]:
    return [c["code"] for c in entry["changes"]]


def test_the_first_save_of_a_job_is_its_creation(store):
    store.save_project(Project(id="p1", name="Levi"), actor="user:u_dana")
    [entry] = store.project_changes("p1")
    assert entry["actor"] == "user:u_dana"
    assert entry["changes"] == [{"code": "job_created", "params": {"name": "Levi"}}]
    assert entry["at"]


def test_a_save_that_changes_nothing_writes_no_entry_but_still_an_audit_row(store):
    project = Project(id="p1", name="Levi")
    store.save_project(project, actor="user:u_dana")
    audited = len(store.audit_entries(1000))
    project.topology.revision += 1          # a save, not a change
    store.save_project(project, actor="user:u_yossi")
    assert len(store.project_changes("p1")) == 1
    assert len(store.audit_entries(1000)) == audited + 1


def test_each_changing_save_is_one_entry_newest_first(store):
    project = Project(id="p1", name="Levi")
    store.save_project(project, actor="user:u_dana")
    project.name = "Levi family"
    store.save_project(project, actor="user:u_yossi")
    project.status = "waiting"
    store.save_project(project, actor="user:u_dana")
    entries = store.project_changes("p1")
    assert [_codes(e) for e in entries] == [
        ["status_changed"], ["name_changed"], ["job_created"]]
    assert [e["actor"] for e in entries] == ["user:u_dana", "user:u_yossi", "user:u_dana"]
    assert entries[0]["seq"] > entries[1]["seq"] > entries[2]["seq"]


def test_the_entry_carries_the_value_before_the_save(store):
    """The whole point: the stored row is overwritten, the entry keeps the old value."""
    project = Project(id="p1", name="Levi")
    store.save_project(project, actor="user:u_dana")
    project.name = "Cohen"
    store.save_project(project, actor="user:u_yossi")
    assert store.load_project("p1").name == "Cohen"
    assert store.project_changes("p1")[0]["changes"] == [
        {"code": "name_changed", "params": {"from": "Levi", "to": "Cohen"}}]


def test_the_limit_keeps_the_newest(store):
    project = Project(id="p1", name="v0")
    store.save_project(project, actor="user:u")
    for n in range(1, 6):
        project.name = f"v{n}"
        store.save_project(project, actor="user:u")
    entries = store.project_changes("p1", limit=2)
    assert [e["changes"][0]["params"]["to"] for e in entries] == ["v5", "v4"]


def test_one_jobs_history_holds_none_of_another_jobs(store):
    store.save_project(Project(id="p1", name="Levi"), actor="user:u")
    store.save_project(Project(id="p2", name="Cohen"), actor="user:u")
    assert [e["changes"][0]["params"]["name"] for e in store.project_changes("p1")] == [
        "Levi"]
    assert store.project_changes("nope") == []


def test_the_history_survives_reopening_the_store(tmp_path):
    path = str(tmp_path / "fence.db")
    first = Store(path)
    project = Project(id="p1", name="Levi")
    first.save_project(project, actor="user:u")
    project.name = "Cohen"
    first.save_project(project, actor="user:u")
    first.close()
    again = Store(path)
    try:
        assert [_codes(e) for e in again.project_changes("p1")] == [
            ["name_changed"], ["job_created"]]
    finally:
        again.close()
