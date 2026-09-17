# ADR-0012: One SQL, two databases — a `Dialect`/`Conn` shim, not an ORM

Status: accepted · 2026-09-17

## Decision

`store/db.py` now speaks Postgres as well as SQLite. It does so without knowing which:
every one of its SQL statements is still written once, in SQLite's spelling, and
`store/dialect.py` translates on the way to the server.

* **`Dialect`** — a frozen dataclass holding the four places the two databases disagree:
  placeholder spelling (`?` / `%s`), JSON field extraction (`json_extract(doc,'$.k')` /
  `doc::jsonb->>'k'`), the `audit_log.seq` column type (`INTEGER PRIMARY KEY
  AUTOINCREMENT` / `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`), and the pre-schema
  prelude (`PRAGMA journal_mode=WAL;` / nothing). `SQLITE` and `POSTGRES` are the only
  two instances and there is no seam for a third.
* **`Conn`** — one connection, deliberately not a pool, which translates each statement
  and hands back the driver's cursor. `dialect_for(dsn)` picks the database from the DSN's
  URL scheme, so one `FENCEAI_DB` variable carries both the choice and the address and the
  two can never disagree; a DSN that looks like a URL with a scheme it does not know is
  refused rather than read as a file path.
* **The rule that keeps this small:** a difference between the two databases lives in
  `Dialect` or `Conn`, with its own test, and never as a conditional in `store/db.py`.
  `store/db.py` contains no `if postgres` and no import of either driver.
* **Both backends are tested, always.** The `backend` fixture parameterises every test
  that opens a database, so ~345 tests run twice; without a server the Postgres half
  skips and SQLite carries the suite, which keeps a laptop with nothing installed
  comfortable. CI is required to provide one, and a test asserts that.

Relations: this does not replace ADR-0008, it fires the trigger ADR-0008 named. Everything
that ADR decided about the SHAPE of persistence — JSON documents in typed tables,
append-only knowledge and audit tables, a thin repository layer, domain code that never
touches SQL — is unchanged and is what made the swap containable. What moves is only which
server those statements are sent to. `@_serialized` and `tests/store/test_concurrent_access.py`
also stand exactly as ADR-0008 describes them: the `RLock` is still the in-process
concurrency contract on both backends, and the check-to-use windows that ADR names as
"not covered" are still not covered — Postgres makes closing them possible, it does not
close them.

## Rationale

ADR-0008's own words: "the repository layer keeps a Postgres swap contained when
multi-tenant scale or concurrent-writer needs appear (that is the trigger)". The trigger
fired for a third reason it did not list but implies: the engine is being deployed on GCP,
where the container filesystem is ephemeral. A SQLite file on Cloud Run is not a small
scaling limit, it is data loss at the next redeploy. Cloud SQL is the deployment's answer
and this shim is what lets the code reach it.

**Why a shim rather than an ORM.** An ORM would replace 63 hand-written statements with a
mapping layer, and the value of those statements is that each one is readable next to the
invariant it enforces — `ON CONFLICT DO NOTHING` on `save_run` is the sentence that makes
run identity work, and it is legible today because it is SQL. Introducing SQLAlchemy to
avoid four string differences trades a module anyone can read in one sitting for a
dependency with its own session lifecycle, its own transaction semantics and its own
opinions about the `RLock` this store already relies on. The four differences are a closed
list, and a closed list is the case where a translation layer is cheaper than an
abstraction layer.

**Why not two `Store` implementations.** A `SqliteStore` and a `PostgresStore` would put
the two databases behind one interface and let them drift: every future method would be
written twice, tested twice at best, and the day one of them gained a behaviour the other
lacked, nothing would fail. The point of this slice is not that Postgres works — it is
that the two agree. Keeping one `Store` makes agreement structural rather than
aspirational; the dual-run suite is then checking a claim the code cannot quietly stop
making.

**Why the DSN scheme, not a flag.** Two variables (`FENCEAI_DB_KIND` + `FENCEAI_DB`) can
disagree, and the failure mode of disagreement is booting healthy on the wrong database.

**Why SQLite stays at all.** It is the offline path: tests, the demo, and a developer with
nothing installed. Deleting it would buy one fewer dialect at the cost of requiring a
server to run the suite, which is the thing that keeps the suite run.

## Consequences

**The whole suite has two answers now, and both must be green.** `uv run pytest -q` on a
laptop is half a run: it proves SQLite. The gate is the run with `FENCEAI_TEST_POSTGRES`
set, and CI sets it. A green laptop run is no longer evidence that the deployed database
works — `tests/store/test_dialect.py::test_ci_must_have_a_postgres` exists because a
dual-run suite with no server does not fail, it succeeds at half the work.

**Divergences the SQL did not state are now bugs, and two were found this way.** Ordering
was the first: SQLite sorts NULLs first ascending, Postgres sorts them last, so
`list_corrections` promised in prose an order only one backend delivered — the SQL now says
`NULLS FIRST` out loud. Transaction behaviour was the second and worse: psycopg runs an
implicit transaction and an error ABORTS it, so a refused write left the single
process-wide connection raising `InFailedSqlTransaction` on every later statement,
including reads, until the process was replaced. `Conn.execute` rolls back before
re-raising. Both were invisible to 3806 green tests, because the tests that provoked the
errors stopped at the exception. The general lesson is recorded here rather than in a
comment: **a test that asserts a failure must also assert what still works afterwards**,
or the dual-run cannot see the class of defect it exists to find.

**Adding a statement to `store/db.py` now has a rule.** No SQL string there may contain a
literal `?` or `%` other than as a placeholder — a `LIKE '%x%'` would need escaping for
psycopg and the translation would not know. This is stated in `dialect.py`'s module
docstring, and it is the one way a careless addition can break Postgres silently.

**Handing back the raw driver cursor is a bet with four conditions**, recorded on
`Conn.execute`: every column stays TEXT or INTEGER; `fetchone()` is never called on a
non-returning statement; `rowcount` is read only after DML; and `Conn` stays one cursor per
`execute`. Break any one and `Conn` must start wrapping results instead of passing them
through.

**Not decided here**, and deliberately: no connection pool (`@_serialized` means a second
connection could never be in use, and a pool would obscure that); no reconnection after a
dropped socket, which production will need and which belongs in `Conn`; no migration
tooling — `CREATE TABLE IF NOT EXISTS` still carries schema creation, and importing the
pilot's SQLite data into Cloud SQL is a separate exercise. Nothing here changes the
boundary contract, which is frozen at v1.3 and has no opinion about where rows are stored.

Spec: `docs/superpowers/specs/2026-09-17-gcp-deployment-design.md`.
Plan: `docs/superpowers/plans/2026-09-17-store-dialect-shim.md`.
