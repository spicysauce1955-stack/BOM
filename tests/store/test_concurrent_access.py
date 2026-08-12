"""One connection, one caller at a time.

FastAPI runs sync endpoints in a threadpool, so one process serves several
requests at once through the single `sqlite3.Connection` `Store` opens with
`check_same_thread=False`. Interleaved statements on one connection are not a
theoretical hazard: the browser suite caught a `GET /inventory` answering 500
while a fence-model draft was being saved, and the same overlap reproduced
standalone at 48 failures in ~540 requests.

Half of `Store`'s methods are read-then-write sequences — `set_fence_model_status`
SELECTs a document and UPDATEs it, `accept_quote` supersedes the old quote and
inserts the new one. Measured against an unguarded `Store`, those blow up loudly
(20 runs, 20 raised), so the raised-exception assertions are what catch the
defect TODAY. The doc-versus-row check below has never fired on its own; it is
kept because it is the one that would catch a future silent corruption, and it
is cheap — not because it is what is failing now.

These tests drive real concurrency rather than asserting that a lock exists,
because the invariant is "no interleaving", not "there is a lock attribute":
an implementation that dropped the guard from one method would keep the
attribute and fail here.
"""

from __future__ import annotations

import threading

import pytest

from fenceai.fencemodel.model import FenceModel
from fenceai.project.model import Project
from fenceai.store.db import Store


def _run(workers: list) -> list:
    """Run every worker at once and return whatever they blew up with."""
    errors: list = []
    barrier = threading.Barrier(len(workers))

    def wrap(fn):
        def run():
            barrier.wait()          # start together; nobody wins by being first
            try:
                fn()
            except Exception as e:  # noqa: BLE001 — the failure IS the finding
                errors.append(repr(e))
        return run

    threads = [threading.Thread(target=wrap(fn)) for fn in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def test_concurrent_readers_and_writers_do_not_break_the_connection():
    store = Store(":memory:")
    store.save_project(Project(id="p1", name="p"))

    def write(n):
        def go():
            for i in range(40):
                store.save_fence_model(
                    FenceModel(id=f"M-{n}", version=i + 1, status="draft"))
        return go

    def read():
        for _ in range(40):
            store.fence_model_library()
            store.load_inventory("p1")
            store.list_projects()
            store.knowledge_base()

    errors = _run([write(0), write(1), write(2), read, read, read])
    assert errors == [], errors[:3]
    # "nobody raised" is not "everything was written": a lost INSERT is the
    # quiet half of the same defect
    written = [m for m in store.fence_model_library().models
               if m.id in {"M-0", "M-1", "M-2"}]
    assert len(written) == 120


def test_a_read_then_write_sequence_is_not_interleaved_with_another():
    """`set_fence_model_status` loads the document, edits it and writes the row
    and the doc together. Two of them running at once on one connection can
    commit each other's half — and the doc lagging its row is exactly what that
    method's docstring says must never happen, because a retired model whose
    document still says "active" keeps resolving as the latest active one."""
    store = Store(":memory:")
    for version in range(1, 21):
        store.save_fence_model(FenceModel(id="M-A", version=version, status="draft"))

    def flip(status):
        def go():
            for version in range(1, 21):
                store.set_fence_model_status("M-A", version, status)
        return go

    errors = _run([flip("active"), flip("retired"), flip("active")])
    assert errors == [], errors[:3]
    # every row's document must agree with its row. Kept as the check for a
    # future SILENT corruption; measured never to fire on its own today (see
    # the module docstring), so it is not what proves the guard works.
    authored = [m for m in store.fence_model_library().models if m.id == "M-A"]
    assert len(authored) == 20      # beside the models a fresh store seeds
    for m in authored:
        row_status = store._conn.execute(
            "SELECT status FROM fence_models WHERE model_id=? AND version=?",
            (m.id, m.version),
        ).fetchone()[0]
        assert m.status == row_status, (m.ref, m.status, row_status)


def test_seeding_from_the_constructor_still_works_under_the_guard():
    """`__init__` calls `seed_fence_models`, which calls `save_fence_model` —
    two guarded methods deep. A non-re-entrant lock does not fail here, it
    DEADLOCKS, and a hanging test reports nothing (there is no pytest-timeout in
    this project). So the constructor runs on its own thread with a deadline,
    and the assertion is that it finished."""
    built: list[Store] = []
    thread = threading.Thread(target=lambda: built.append(Store(":memory:")))
    thread.daemon = True     # never hold the suite open on a deadlocked store
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), "Store.__init__ deadlocked — is the lock re-entrant?"
    assert built and built[0].fence_model_library().models, "a fresh store seeds its models"


def test_the_guard_refuses_a_member_it_cannot_protect():
    """`_serialized` wraps plain functions. A `property` is not callable and a
    `staticmethod` is, so a filter on `callable` would silently leave the first
    unguarded and hand the second a bogus `self`. Both failures are invisible,
    so the decorator raises instead of skipping."""
    from fenceai.store.db import _serialized

    with pytest.raises(TypeError, match="property"):
        @_serialized
        class WithProperty:
            @property
            def oops(self):
                return 1

    with pytest.raises(TypeError, match="staticmethod"):
        @_serialized
        class WithStatic:
            @staticmethod
            def oops():
                return 1
