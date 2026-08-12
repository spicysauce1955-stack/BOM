# ADR-0008: SQLite (stdlib) document-style persistence behind repositories

Status: accepted · 2026-08-09

## Decision
Single SQLite database via stdlib `sqlite3`. Aggregates (project, topology, strategy+decision
graph document, catalog items) stored as JSON documents in typed tables; knowledge versions,
corrections, candidates, and audit records in append-only tables. Thin repository layer;
domain code never touches SQL. WAL mode; one DB file per deployment (path configurable,
`:memory:` in tests).

## Rationale
Research B assumed Postgres; mission §18 forbids infrastructure without a concrete use case.
All required query shapes are per-project/per-tenant-small; SQLite supports JSON and recursive
CTEs if needed. The repository layer keeps a Postgres swap contained when multi-tenant scale
or concurrent-writer needs appear (that is the trigger).

## Consequences
No cross-process write concurrency beyond WAL's single-writer — fine for V1 single-instance
deployment. Documented as a known limitation.

**In-process concurrency is serialized, and that is part of the decision, not an
implementation detail.** One `sqlite3.Connection` opened `check_same_thread=False` is shared
by every request, because FastAPI runs sync endpoints in a threadpool — and a connection is
not safe for interleaved statements. The failure is not only a 500 on whichever request lost:
repository methods that read a document, edit it and write it back (`set_fence_model_status`,
`accept_quote`) can have another thread's `commit()` land in the middle, committing a
transaction nobody finished. `Store` is therefore wrapped by `@_serialized` (`store/db.py`):
a re-entrant lock held for the whole of every public method.

A connection PER THREAD is the obvious alternative and it is wrong here — `:memory:` is the
test path, where per-thread connections mean per-thread *databases*. The real fix for
genuine write concurrency is the Postgres swap this ADR already names as the trigger; until
then, one *call* at a time is the contract, and `tests/store/test_concurrent_access.py`
holds it by driving real threads rather than by asserting a lock exists.

**What that does not cover, stated so nobody reads more into it:** the lock makes each store
call atomic, not each route. A route that reads and then writes through two calls still has a
check-to-use window — `publish_fence_model` loads a model, checks it is a draft and then sets
its status; `put_fence_model_draft` reads the library, computes the next free version and
saves to it. Two concurrent saves for a new model can compute the same version and one wins.
Closing that needs a transaction spanning the sequence (or the Postgres swap), and it is a
separate change from this one.
