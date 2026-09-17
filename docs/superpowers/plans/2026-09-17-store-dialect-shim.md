# Store Dialect Shim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `Store` speak Postgres as well as SQLite, with the ~390 tests that open a database running against both, so the deployed dialect cannot drift from the tested one.

**Architecture:** One `Dialect` value object holds the four places the two databases disagree, and one `Conn` wrapper owns the connection and translates SQL on the way through. `store/db.py` keeps all 63 of its SQL strings exactly as written — the `?` placeholders included — because no SQL string in the file contains a literal `?` or `%`, so translation at a single choke point is safe. `FENCEAI_DB` picks the backend: a value starting `postgres://` or `postgresql://` means Postgres, anything else is a SQLite path.

**Tech Stack:** Python 3.12, `sqlite3` (stdlib, 3.45.1), `psycopg[binary]` 3.2+ as an optional extra, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-17-gcp-deployment-design.md` — this plan implements **slice 1** of §8. Read §4 before starting.

## Global Constraints

- **Integer millimetres and cents at rest** (ADR-0002). This port introduces no numeric type conversion anywhere: every `doc` column is JSON text today and stays JSON text.
- **No behaviour change on SQLite.** After every task, `uv run pytest -q` must be green with no Postgres server present. SQLite remains the zero-setup default — CLAUDE.md's offline property is not spent here.
- **`@_serialized` stays.** Every public `Store` method is wrapped by the class decorator so each call is atomic under one `RLock`. Nothing in this plan removes, weakens or bypasses that. See `store/db.py:100-153` for why it exists.
- **Measured against `origin/main` at `f4c2fb4`** on 2026-09-17. `store/db.py` is byte-identical to the tree the spec was written from, so every count in this plan about the store holds; the suite-wide counts were re-measured (3114 test functions, 28 `TestClient` files, ~340 API tests).
- **One connection, not a pool.** See "Deviations from the spec" below.
- **Commit after every task.** Do not batch.
- **Never `git add -A`** — another session commits in this repo. Stage the exact paths each task names.

## Deviations from the spec, and why

Two things in the spec do not survive contact with the code. Both are flagged here rather than silently reconciled, per CLAUDE.md. **Get the product owner's agreement before starting Task 3**; Tasks 1–2 are unaffected either way.

1. **§4 says `postgres://` "selects the Postgres dialect and a connection pool". This plan uses a single connection.** A pool buys nothing here: `@_serialized` already funnels every store call through one `RLock`, so a second connection could never be in use. A pool would add a moving part whose only effect is to make the `RLock`'s guarantee harder to reason about. The spec sentence should be amended to "and a single connection, serialized exactly as SQLite's is."

2. **§8 slice 1 says CI proves the dialects agree, but §8 slice 5 is where CI gets built.** Slice 1's dual-run is worth little if nothing runs it. Task 7 therefore adds a *minimal, test-only* GitHub Actions workflow — no build, no registry, no deploy, which all stay in slice 5. If the product owner would rather have no CI until slice 5, drop Task 7 and the dual-run is local-only until then.

## Deferred, deliberately

- **Reconnection.** A long-lived Postgres connection will eventually be dropped by a Cloud SQL restart or an idle timeout; SQLite has no equivalent failure. Handling it belongs in slice 3, where a real server is running and the retry can be tested against an actual drop rather than a mock. Named here so it is not rediscovered as a production surprise.
- **`store/migrations/`.** Spec §4 leaves this a baseline-only seam. Not created in this slice.
- **The 14 read-modify-write sites** of spec §3. Prerequisite for unpinning `max-instances`, not for this slice.

## File Structure

| File | Responsibility |
|---|---|
| `src/fenceai/store/dialect.py` **(create)** | The `Dialect` value object, the two instances, `dialect_for(dsn)`, and the `Conn` wrapper that owns a connection and translates SQL. Nothing about fences. |
| `src/fenceai/store/db.py` **(modify)** | Uses `Conn` instead of `sqlite3.connect`. Its 63 SQL strings are untouched except two `INSERT OR IGNORE` and one `json_extract`. |
| `tests/store/test_dialect.py` **(create)** | The dialect's string behaviour — pure, no database, no server. |
| `tests/conftest.py` **(modify)** | `postgres_available()`, and the `pg_dsn`, `backend` and `dsn` fixtures. Shared by every directory that opens a database. |
| `tests/api/conftest.py` **(modify)** | The existing autouse `_isolated_store` gains the backend parameter — the single seam through which all ~340 API tests dual-run. |
| `tests/store/conftest.py` **(create)** | A `store` fixture so the nine dual-running files stop calling `Store(":memory:")` themselves. |
| `pyproject.toml` **(modify)** | `postgres` optional extra; `postgres` pytest marker. |
| `.github/workflows/tests.yml` **(create, Task 7)** | Runs the suite twice-over with a Postgres service container. |

---

## Task 1: The dialect, as pure strings

Everything in this task is testable with no database and no server. That is the point of doing it first.

**Files:**
- Create: `src/fenceai/store/dialect.py`
- Test: `tests/store/test_dialect.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Dialect` (frozen dataclass with fields `name: str`, `serial_pk: str`, `prelude: str`, `_rewrite_placeholders: bool` and methods `placeholders(sql: str) -> str`, `json_field(col: str, key: str) -> str`); module constants `SQLITE: Dialect` and `POSTGRES: Dialect`; `dialect_for(dsn: str) -> Dialect`.

- [ ] **Step 1: Write the failing tests**

Create `tests/store/test_dialect.py`:

```python
"""The four places SQLite and Postgres disagree, as strings.

No database is opened here. The dialect's whole job is rewriting text, and
text is checkable without a server — which is what keeps this file runnable
on a laptop with nothing installed.
"""

from __future__ import annotations

import pytest

from fenceai.store.dialect import POSTGRES, SQLITE, dialect_for


def test_sqlite_leaves_question_marks_alone():
    sql = "SELECT doc FROM projects WHERE id=?"
    assert SQLITE.placeholders(sql) == sql


def test_postgres_rewrites_every_question_mark():
    sql = "INSERT INTO audit_log (at, actor, action, ref) VALUES (?,?,?,?)"
    assert POSTGRES.placeholders(sql) == (
        "INSERT INTO audit_log (at, actor, action, ref) VALUES (%s,%s,%s,%s)"
    )


def test_postgres_does_not_disturb_a_statement_with_no_parameters():
    sql = "SELECT doc FROM corrections"
    assert POSTGRES.placeholders(sql) == sql


def test_the_two_dialects_extract_json_differently():
    assert SQLITE.json_field("doc", "created_at") == "json_extract(doc, '$.created_at')"
    assert POSTGRES.json_field("doc", "created_at") == "doc::jsonb->>'created_at'"


def test_only_sqlite_has_a_journal_prelude():
    assert SQLITE.prelude == "PRAGMA journal_mode=WAL;"
    assert POSTGRES.prelude == ""


def test_the_audit_sequence_is_spelled_per_dialect():
    assert SQLITE.serial_pk == "INTEGER PRIMARY KEY AUTOINCREMENT"
    assert POSTGRES.serial_pk == "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"


@pytest.mark.parametrize("dsn", ["postgres://u@h/db", "postgresql://u@h/db"])
def test_a_postgres_url_selects_postgres(dsn):
    assert dialect_for(dsn) is POSTGRES


@pytest.mark.parametrize("dsn", ["fenceai.db", ":memory:", "/var/lib/fenceai/x.db"])
def test_anything_else_is_a_sqlite_path(dsn):
    assert dialect_for(dsn) is SQLITE
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/store/test_dialect.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'fenceai.store.dialect'`.

- [ ] **Step 3: Write `src/fenceai/store/dialect.py`**

Only the `Dialect` half. `Conn` arrives in Step 5.

```python
"""Where SQLite and Postgres disagree, and nowhere else.

`store/db.py` holds 63 SQL statements and this module exists so that number
stays 63. Every statement there is written once, in SQLite's spelling, and
translated on the way to a Postgres server — which is safe precisely because
no SQL string in that file contains a literal `?` or `%`. Check that before
adding one: a `LIKE '%x%'` would have to be escaped for psycopg, and the
translation below would not know.

Four differences, and they are the whole list:

    placeholders   `?`                          `%s`
    json field     json_extract(doc,'$.k')      doc::jsonb->>'k'
    audit sequence INTEGER PRIMARY KEY          BIGINT GENERATED ALWAYS
                   AUTOINCREMENT                AS IDENTITY PRIMARY KEY
    prelude        PRAGMA journal_mode=WAL;     (none)

`INSERT OR IGNORE` is NOT on the list. SQLite has accepted `ON CONFLICT DO
NOTHING` since 3.24 and ships 3.45 here, so both statements that needed it
were rewritten into the form both databases already understand — one fewer
difference to carry is better than one more translation to trust.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    name: str
    #: How this database spells the `audit_log.seq` column.
    serial_pk: str
    #: Statements run before the schema, if any.
    prelude: str
    #: True when `?` must become `%s`.
    _rewrite_placeholders: bool

    def placeholders(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._rewrite_placeholders else sql

    def json_field(self, col: str, key: str) -> str:
        if self._rewrite_placeholders:
            return f"{col}::jsonb->>'{key}'"
        # Concatenated rather than an f-string: `$` immediately before `{`
        # reads as a bug every time somebody re-reads it.
        return "json_extract(" + col + ", '$." + key + "')"


SQLITE = Dialect(
    name="sqlite",
    serial_pk="INTEGER PRIMARY KEY AUTOINCREMENT",
    prelude="PRAGMA journal_mode=WAL;",
    _rewrite_placeholders=False,
)

POSTGRES = Dialect(
    name="postgres",
    serial_pk="BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
    prelude="",
    _rewrite_placeholders=True,
)

#: What `FENCEAI_DB` looks like when it names a server rather than a file.
_POSTGRES_SCHEMES = ("postgres://", "postgresql://")


def dialect_for(dsn: str) -> Dialect:
    """Which database is `FENCEAI_DB` naming?

    A URL scheme rather than a flag, so one variable carries both the choice
    and the address and the two can never disagree.
    """
    return POSTGRES if dsn.startswith(_POSTGRES_SCHEMES) else SQLITE
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
uv run pytest tests/store/test_dialect.py -q
```

Expected: 11 passed (six plain tests plus five parameterized cases).

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/store/dialect.py tests/store/test_dialect.py
git commit -m "feat(store): a Dialect for the four places SQLite and Postgres differ"
```

---

## Task 2: `Store` goes through a `Conn`, still on SQLite

No Postgres yet. The whole suite must stay green, which is what proves the refactor is behaviour-preserving.

**Files:**
- Modify: `src/fenceai/store/dialect.py` (add `Conn`)
- Modify: `src/fenceai/store/db.py:34-99` (`_SCHEMA`), `:156-180` (`__init__`, `close`), `:703`, `:746`, `:799`
- Test: `tests/store/test_dialect.py`

**Interfaces:**
- Consumes: `Dialect`, `SQLITE`, `POSTGRES`, `dialect_for` from Task 1.
- Produces: `Conn(dsn: str)` with attributes `dialect: Dialect` and methods `execute(sql: str, params: tuple = ()) -> cursor`, `executescript(sql: str) -> None`, `commit() -> None`, `close() -> None`. `Store.__init__` keeps its signature `(self, path: str = ":memory:")`.

- [ ] **Step 1: Write the failing test**

Append to `tests/store/test_dialect.py`:

```python
from fenceai.store.dialect import Conn


def test_a_sqlite_conn_round_trips_a_row_through_question_marks():
    conn = Conn(":memory:")
    assert conn.dialect is SQLITE
    conn.executescript("CREATE TABLE t (id TEXT PRIMARY KEY, doc TEXT);")
    conn.execute("INSERT INTO t (id, doc) VALUES (?,?)", ("a", "{}"))
    conn.commit()
    row = conn.execute("SELECT doc FROM t WHERE id=?", ("a",)).fetchone()
    assert row[0] == "{}"
    conn.close()


def test_executescript_applies_the_prelude_and_the_schema_together(tmp_path):
    """A FILE, not `:memory:`.

    An in-memory database reports `journal_mode=memory` and cannot be put in
    WAL at all, so the `:memory:` spelling of this test fails while the
    prelude is working perfectly — which is a false red pointing at the
    wrong thing.
    """
    conn = Conn(str(tmp_path / "wal.db"))
    conn.executescript(conn.dialect.prelude + "CREATE TABLE t (id TEXT);")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()
```

- [ ] **Step 2: Run it and watch it fail**

```bash
uv run pytest tests/store/test_dialect.py -q
```

Expected: `ImportError: cannot import name 'Conn'`.

- [ ] **Step 3: Add `Conn` to `src/fenceai/store/dialect.py`**

Add `import sqlite3` to the imports at the top of the file, beside `from dataclasses import dataclass`. Then append:

```python
class Conn:
    """One connection, and the one place SQL is translated.

    Deliberately NOT a pool. `store/db.py`'s `@_serialized` funnels every
    public call through a single `RLock`, so a second connection could never
    be in use — a pool here would add a moving part whose only effect is to
    make that guarantee harder to see. When Postgres arrives in production,
    reconnection after a dropped socket belongs here; see the plan's
    "Deferred" section for why it is not built yet.
    """

    def __init__(self, dsn: str):
        self.dialect = dialect_for(dsn)
        if self.dialect is SQLITE:
            # `check_same_thread=False` only silences sqlite3's guard; the
            # `RLock` in `Store` is what actually makes this safe. See
            # `store/db.py`'s `_serialized` docstring.
            self._raw = sqlite3.connect(dsn, check_same_thread=False)
        else:
            import psycopg  # imported here so SQLite users need not install it

            self._raw = psycopg.connect(dsn)

    def execute(self, sql: str, params: tuple = ()):
        return self._raw.execute(self.dialect.placeholders(sql), params)

    def executescript(self, sql: str) -> None:
        """Several statements at once, for schema creation only.

        `sqlite3` has `executescript`; psycopg does not, but accepts several
        statements in one `execute` when there are no parameters — which
        schema DDL never has.
        """
        if self.dialect is SQLITE:
            self._raw.executescript(sql)
        else:
            self._raw.execute(sql)
        self._raw.commit()

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()
```

`psycopg` 3 gives `Connection.execute(sql, params)` returning a cursor, exactly like `sqlite3` — which is why `Conn.execute` can be one line and why `db.py`'s `.fetchone()` / `.fetchall()` / `.rowcount` call sites need no change.

- [ ] **Step 4: Run it and watch it pass**

```bash
uv run pytest tests/store/test_dialect.py -q
```

Expected: 13 passed.

Tasks 1 and 2's module and tests were executed before this plan was written
(the WAL test above is the one error that found), so 13 is a count that was
observed rather than predicted. From Task 3 onward the code in this plan is
unrun — treat it accordingly.

- [ ] **Step 5: Make `_SCHEMA` carry the dialect's sequence spelling**

In `src/fenceai/store/db.py`, find the `audit_log` table inside `_SCHEMA` (around line 73):

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, ref TEXT NOT NULL);
```

Replace the column definition with a marker:

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    seq __SERIAL_PK__, at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, ref TEXT NOT NULL);
```

A `__SERIAL_PK__` marker and `str.replace`, not `str.format`: `_SCHEMA` is 66 lines of SQL that future hands will edit, and a stray `{` in a `CHECK` constraint one day would turn `.format()` into a confusing `KeyError` far from the edit.

- [ ] **Step 6: Rewrite `Store.__init__` and `close` to use `Conn`**

Replace `src/fenceai/store/db.py:156-180`. The long comment above `self._lock` explains a real bug and must be kept verbatim; only the two connection lines change.

```python
@_serialized
class Store:
    def __init__(self, path: str = ":memory:"):
        # `check_same_thread=False` only silences sqlite3's guard; it does not
        # make the connection safe. FastAPI runs sync endpoints in a threadpool,
        # so two overlapping fetches interleaved statements on one cursor and
        # raised `InterfaceError: bad parameter or other API misuse` straight out
        # of a route — a real 500 in the browser that NO pytest test can see,
        # because TestClient serialises requests. The browser smoke suite was the
        # only detector, and it was red here while green on main.
        self._lock = threading.RLock()
        self._conn = Conn(path)
        self._conn.executescript(
            self._conn.dialect.prelude
            + _SCHEMA.replace("__SERIAL_PK__", self._conn.dialect.serial_pk)
        )
        # Parts BEFORE models: a seeded model names a part_id, and a store whose
        # models arrived first would, for the length of one call, hold a published
        # model that resolves to nothing. Nothing reads the store between the two
        # lines today, and the ordering is the cheap way to keep that true.
        self.seed_parts()
        self.seed_fence_models()
```

`Conn.executescript` commits, so the bare `self._conn.commit()` that followed the old `executescript` goes away. `close()` is unchanged — `Conn.close()` has the same name.

Add the import near the top of `db.py`, beside the existing `import sqlite3` (which may now be removed if nothing else in the file uses it — check with `grep -n "sqlite3" src/fenceai/store/db.py` and only remove it if the sole remaining use was the connect call):

```python
from fenceai.store.dialect import Conn
```

- [ ] **Step 7: Normalise the two `INSERT OR IGNORE` statements**

At `src/fenceai/store/db.py:703` and `:746`. Both currently read `INSERT OR IGNORE INTO <table> (...) VALUES (...)`. Change each to `INSERT INTO <table> (...) VALUES (...) ON CONFLICT DO NOTHING` — for example line 703 becomes:

```python
            "INSERT INTO generation_runs (id, project_id, created_at, doc) "
            "VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
```

Both tables have a single-column `TEXT PRIMARY KEY`, so a bare `ON CONFLICT DO NOTHING` covers exactly the conflict `INSERT OR IGNORE` was covering. The docstring at line 726 explains *why* the insert ignores duplicates — the id is the content — and stays true; update its wording from "INSERT OR IGNORE" to "ON CONFLICT DO NOTHING" so the prose matches the statement above it.

- [ ] **Step 8: Route the one `json_extract` through the dialect**

At `src/fenceai/store/db.py:799`, replace:

```python
        order = "ORDER BY json_extract(doc, '$.created_at'), id"
```

with:

```python
        order = f"ORDER BY {self._conn.dialect.json_field('doc', 'created_at')}, id"
```

The surrounding docstring's argument — that the sort is total because `id` breaks ties — is unaffected and stays.

- [ ] **Step 9: Run the whole suite on SQLite**

```bash
uv run pytest -q
```

Expected: everything that passed before still passes; no Postgres involved. If `tests/store/test_concurrent_access.py` fails, stop — that file drives real threads against `Store` and is the detector for the `RLock` invariant this task must not have touched.

- [ ] **Step 10: Run the release gate**

```bash
uv run pytest tests/scenarios -q
```

Expected: green.

- [ ] **Step 11: Commit**

```bash
git add src/fenceai/store/dialect.py src/fenceai/store/db.py tests/store/test_dialect.py
git commit -m "refactor(store): Store speaks through a Conn, one translation point"
```

---

## Task 3: Postgres actually connects

**Get the product owner's agreement on the two deviations above before starting this task.**

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/conftest.py`
- Test: `tests/store/test_dialect.py`

**Interfaces:**
- Consumes: `Conn`, `dialect_for` from Task 2.
- Produces: in `tests/conftest.py` — `postgres_base_dsn() -> str | None`, `postgres_available() -> bool`, and a `backend` fixture parameterized over `("sqlite", "postgres")` that skips the Postgres parameter when no server is configured.

- [ ] **Step 1: Add the optional extra and the marker**

In `pyproject.toml`, after the `[project]` block's `dependencies`:

```toml
[project.optional-dependencies]
# Only a deployment needs this. `uv sync` without it keeps the offline
# property CLAUDE.md states: the app and the whole suite run on SQLite with
# nothing installed and nothing running.
postgres = ["psycopg[binary]>=3.2,<4"]
```

And extend the existing markers line in `[tool.pytest.ini_options]`:

```toml
markers = [
    "live: tests requiring a live Anthropic API key",
    "postgres: tests requiring a reachable Postgres server (FENCEAI_TEST_POSTGRES)",
]
```

- [ ] **Step 2: Install it**

```bash
uv sync --extra postgres
```

- [ ] **Step 3: Start a Postgres to develop against**

```bash
docker run -d --name fenceai-test-pg -e POSTGRES_PASSWORD=test -p 5432:5432 postgres:16
export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres
```

If Docker is not available, any reachable Postgres 16 will do; only the URL matters.

- [ ] **Step 4: Write the failing test**

Append to `tests/store/test_dialect.py`:

```python
def test_a_postgres_conn_round_trips_a_row_through_rewritten_placeholders(pg_dsn):
    """The same assertions as the SQLite round-trip, against a real server.

    Worth its own test rather than a parameterised one: this is the first
    moment `?` -> `%s` is checked against a database that would reject the
    untranslated form, which is the only thing that proves the translation
    is doing work rather than being consistent with itself.
    """
    conn = Conn(pg_dsn)
    assert conn.dialect is POSTGRES
    conn.executescript("CREATE TABLE t (id TEXT PRIMARY KEY, doc TEXT);")
    conn.execute("INSERT INTO t (id, doc) VALUES (?,?)", ("a", "{}"))
    conn.commit()
    row = conn.execute("SELECT doc FROM t WHERE id=?", ("a",)).fetchone()
    assert row[0] == "{}"
    conn.close()
```

- [ ] **Step 5: Run it and watch it fail**

```bash
uv run pytest tests/store/test_dialect.py -q
```

Expected: `fixture 'pg_dsn' not found`.

- [ ] **Step 6: Add the backend plumbing to `tests/conftest.py`**

Append to the existing `tests/conftest.py` (keep everything already there):

```python
import os
import uuid

#: A Postgres the suite may use. Unset on a laptop with nothing installed,
#: which is the case that must stay comfortable: the Postgres parameter
#: skips and SQLite carries the whole suite.
_PG_ENV = "FENCEAI_TEST_POSTGRES"


def postgres_base_dsn() -> str | None:
    return os.environ.get(_PG_ENV) or None


def postgres_available() -> bool:
    """Is there a server AND a driver? Both, or the answer is no.

    Checked by connecting rather than by reading the variable, so a stale
    export pointing at a container somebody stopped skips cleanly instead of
    failing 350 tests with a connection error apiece.
    """
    dsn = postgres_base_dsn()
    if dsn is None:
        return False
    try:
        import psycopg
    except ImportError:
        return False
    try:
        with psycopg.connect(dsn, connect_timeout=3) as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture()
def pg_dsn():
    """A DSN pointing at a schema of this test's own, dropped afterwards.

    A schema rather than a database: `CREATE DATABASE` cannot run inside a
    transaction and costs a connection round-trip apiece, and `Store` issues
    `CREATE TABLE IF NOT EXISTS` at construction, so an empty schema is
    already the clean slate every test wants.
    """
    if not postgres_available():
        pytest.skip(f"no Postgres: set {_PG_ENV} and install the postgres extra")
    import psycopg

    base = postgres_base_dsn()
    name = f"t_{uuid.uuid4().hex[:16]}"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{name}"')
    sep = "&" if "?" in base else "?"
    try:
        yield f"{base}{sep}options=-csearch_path%3D{name}"
    finally:
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{name}" CASCADE')


@pytest.fixture(params=["sqlite", "postgres"])
def backend(request):
    """Every test that opens a database runs twice under this fixture.

    The two dialects agreeing is the whole reason SQLite is allowed to stay,
    so the agreement is asserted by the suite rather than by review.
    """
    if request.param == "postgres" and not postgres_available():
        pytest.skip(f"no Postgres: set {_PG_ENV} and install the postgres extra")
    return request.param


@pytest.fixture()
def dsn(backend, tmp_path, request):
    """The `FENCEAI_DB` value for whichever backend this run is using."""
    if backend == "sqlite":
        return str(tmp_path / "test.db")
    return request.getfixturevalue("pg_dsn")
```

Add `import pytest` at the top of `tests/conftest.py` if it is not already imported — it is, since the file already defines fixtures.

- [ ] **Step 7: Run it and watch it pass**

```bash
uv run pytest tests/store/test_dialect.py -q
```

Expected: 14 passed. Then confirm the skip path is clean:

```bash
env -u FENCEAI_TEST_POSTGRES uv run pytest tests/store/test_dialect.py -q
```

Expected: 13 passed, 1 skipped — never an error.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/store/test_dialect.py uv.lock
git commit -m "feat(store): psycopg as an optional extra, and a schema-per-test Postgres fixture"
```

---

## Task 4: A whole `Store` on Postgres

The first test that exercises the real schema — `__SERIAL_PK__`, the seeds, the audit log — against Postgres.

**Files:**
- Create: `tests/store/conftest.py`
- Create: `tests/store/test_both_backends.py`

**Interfaces:**
- Consumes: `backend`, `dsn` fixtures from Task 3; `Store` from `fenceai.store.db`.
- Produces: a `store` fixture in `tests/store/conftest.py` yielding a `Store` open on whichever backend the `backend` fixture selected, closed afterwards.

- [ ] **Step 1: Write the failing test**

Create `tests/store/conftest.py`:

```python
"""A `Store` on whichever backend this run is testing.

Closed afterwards, because a Postgres connection left open holds the schema
that `pg_dsn` is about to DROP CASCADE, and the drop would block.
"""

from __future__ import annotations

import pytest

from fenceai.store.db import Store


@pytest.fixture()
def store(dsn):
    s = Store(dsn)
    try:
        yield s
    finally:
        s.close()
```

Create `tests/store/test_both_backends.py`:

```python
"""The same behaviour, twice, once per database.

Not a port test — a parity test. Everything asserted here is something
`store/db.py` already promises on SQLite; the point is that Postgres
promises it identically, so the dialect shim cannot drift without a
red test.
"""

from __future__ import annotations

from fenceai.project.model import Project


def test_a_project_survives_a_round_trip(store, backend):
    project = Project(id="p1")
    store.save_project(project, actor="user:dana")
    loaded = store.load_project("p1")
    assert loaded is not None
    assert loaded.id == "p1"


def test_saving_twice_updates_rather_than_duplicates(store):
    store.save_project(Project(id="p1"))
    store.save_project(Project(id="p1"))
    assert store.load_project("p1") is not None
    assert len([r for r in store.audit_entries(100) if r["ref"] == "p1"]) == 2


def test_an_unknown_project_is_None_not_an_error(store):
    assert store.load_project("nope") is None


def test_the_audit_sequence_increases(store):
    store.save_project(Project(id="p1"))
    store.save_project(Project(id="p2"))
    seqs = [r["seq"] for r in store.audit_entries(100)]
    assert seqs == sorted(seqs, reverse=True) or seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_the_seeds_are_present_on_a_fresh_store(store):
    assert store.list_parts()
    assert store.list_fence_models()
```

**These assertions are written without having run them.** `audit_entries`, `list_parts` and `list_fence_models` are real methods on `Store`, but their exact return shape — dicts versus models, key names, sort direction — has not been verified here. Before implementing, run `uv run python -c "from fenceai.store.db import Store; s=Store(); print(s.audit_entries(5)); print(type(s.list_parts()))"` and correct the assertions to match what the store actually returns. Do not weaken an assertion to make it pass; fix it to assert the real behaviour.

- [ ] **Step 2: Run it on SQLite and watch it pass or tell you the shapes are wrong**

```bash
env -u FENCEAI_TEST_POSTGRES uv run pytest tests/store/test_both_backends.py -q
```

Expected: 5 passed, 5 skipped. If an assertion is wrong about a return shape, fix the assertion here — this run is what that fix is for.

- [ ] **Step 3: Run it on Postgres and watch it fail**

```bash
uv run pytest tests/store/test_both_backends.py -q
```

Expected: the Postgres half fails. The likely first failure is the `__SERIAL_PK__` schema or a type mismatch in the seeds. Read the error; do not guess.

- [ ] **Step 4: Fix what the failures name**

No code is prescribed here because the failures are not yet known. Expected candidates, in likelihood order:

1. `_SCHEMA` still containing a SQLite-only spelling other than the four in `Dialect` — if so, that is a fifth difference and it belongs in `Dialect` with a test in `tests/store/test_dialect.py`, not patched inline.
2. A `commit()` missing where SQLite's looser transaction handling hid it.
3. `psycopg` returning `memoryview` or `datetime` where `sqlite3` returned `str` — if so, the fix belongs at the `Conn` boundary so `db.py` keeps one spelling.

Whatever the cause, the rule is the same: a difference between the databases goes in `Dialect` or `Conn` with its own test; it never goes in `db.py` as a branch.

- [ ] **Step 5: Run both halves green**

```bash
uv run pytest tests/store/test_both_backends.py -q
```

Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/store/conftest.py tests/store/test_both_backends.py src/fenceai/store/dialect.py src/fenceai/store/db.py
git commit -m "test(store): a Store round-trips on Postgres as it does on SQLite"
```

---

## Task 5: The nine remaining direct-`Store` files dual-run

**Files:**
- Modify: `tests/store/test_supply_run_store.py`, `tests/store/test_correction_thread.py`, `tests/store/test_fence_models.py`, `tests/store/test_published_snapshot.py`, `tests/store/test_parts_store.py`, `tests/identity/test_store.py`, `tests/parts/test_resolve.py`, `tests/parts/test_migration.py`, `tests/fulfillment/test_quotes.py`
- Create: `tests/identity/conftest.py`, `tests/parts/conftest.py`, `tests/fulfillment/conftest.py`
- Leave alone: `tests/store/test_concurrent_access.py` — see Step 4.

- [ ] **Step 1: Find every construction site**

```bash
grep -rn "Store(" tests/ | grep -v "tests/store/conftest.py"
```

- [ ] **Step 2: Give the three other directories the same `store` fixture**

`tests/identity/conftest.py`, `tests/parts/conftest.py` and `tests/fulfillment/conftest.py` each get the identical five-line fixture from Task 4's `tests/store/conftest.py`. Repeated rather than hoisted to `tests/conftest.py`: making a `store` fixture ambient for all 2880 tests would let a test that never meant to open a database acquire one, and the ~2500 pure domain tests staying database-free is the property that keeps the suite fast.

```python
from __future__ import annotations

import pytest

from fenceai.store.db import Store


@pytest.fixture()
def store(dsn):
    s = Store(dsn)
    try:
        yield s
    finally:
        s.close()
```

- [ ] **Step 3: Replace each `Store(":memory:")` with the fixture**

In each of the nine test files, delete the local construction and take `store` as a parameter. A test that reads

```python
def test_something():
    store = Store(":memory:")
    store.save_part(...)
```

becomes

```python
def test_something(store):
    store.save_part(...)
```

Where a file builds a `Store` inside its own fixture, change that fixture to depend on `store` and return it rather than constructing one. Remove the now-unused `from fenceai.store.db import Store` import from any file that no longer names it.

- [ ] **Step 4: Leave `tests/store/test_concurrent_access.py` on SQLite**

Its own docstring says it exists to prove "no interleaving" by driving real threads at one `sqlite3.Connection`, and its numbers — 48 failures in ~540 requests against an unguarded store — are measurements of that connection's behaviour. Pointing it at Postgres would not test the same hazard, and a green run there would be evidence of nothing.

Add a note at the top of the file recording that decision, so the next person does not read its absence from the dual-run as an oversight:

```python
# Deliberately SQLite-only. The hazard measured here is interleaved
# statements on one `sqlite3.Connection`; Postgres does not have it, so a
# green run there would assert nothing. The `RLock` this file defends is
# backend-independent and is exercised on both by every other store test.
```

- [ ] **Step 5: Run both halves**

```bash
env -u FENCEAI_TEST_POSTGRES uv run pytest tests/store tests/identity tests/parts tests/fulfillment -q
uv run pytest tests/store tests/identity tests/parts tests/fulfillment -q
```

Expected: green with skips in the first, roughly double the test count in the second.

- [ ] **Step 6: Run the whole suite**

```bash
uv run pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add tests/store tests/identity tests/parts tests/fulfillment
git commit -m "test: the store suites run on both backends"
```

---

## Task 6: The ~340 API tests dual-run

One fixture is the seam for all of them.

**Files:**
- Modify: `tests/api/conftest.py:36-43`

- [ ] **Step 1: Parameterize the autouse fixture**

`tests/api/conftest.py` already sets `FENCEAI_DB` for every API test via an autouse fixture. Change it to take the `dsn` fixture — which is already parameterized over both backends — instead of building a path itself.

```python
@pytest.fixture(autouse=True)
def _isolated_store(dsn, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", dsn)
    # The stub AI port too, for the same reason: a test that reaches an
    # interpretation must not depend on what the ambient environment configured.
    # `fenceai/ai/` keeps the whole system working offline and the stub is what
    # makes that true (CLAUDE.md), so it is the honest default here.
    monkeypatch.setenv("FENCEAI_AI", "stub")
```

- [ ] **Step 2: Extend the file's docstring**

The docstring explains at length why every API test gets its own database. Add a paragraph, because the fixture now does a second thing:

```
Since the GCP port it also chooses the BACKEND. The `dsn` fixture is
parameterized over SQLite and Postgres, so every test in this directory runs
once per database wherever a server is configured — which is what makes the
dialect shim in `store/dialect.py` an asserted property rather than a
reviewed one. With no server, the Postgres half skips and this directory
behaves exactly as it did before.
```

- [ ] **Step 3: Run the API suite on SQLite alone**

```bash
env -u FENCEAI_TEST_POSTGRES uv run pytest tests/api -q
```

Expected: the same passes as before, plus an equal number of skips.

- [ ] **Step 4: Run it on both**

```bash
uv run pytest tests/api -q
```

Expected: roughly 680 passing. Watch for tests that set `FENCEAI_DB` themselves — the original docstring says a test wanting particular contents "still sets `FENCEAI_DB` itself in its own fixture; `monkeypatch` is function-scoped and the later setting wins". Any such test now pins itself to SQLite while still running twice, so its Postgres run is a duplicate rather than a failure. Find them and decide per test:

```bash
grep -rn "FENCEAI_DB" tests/api/
```

- [ ] **Step 5: Run the whole suite and the gate**

```bash
uv run pytest -q
uv run pytest tests/scenarios -q
```

- [ ] **Step 6: Commit**

```bash
git add tests/api
git commit -m "test(api): every API test runs on both backends"
```

---

## Task 7: CI runs both

See "Deviations from the spec" — this is a test-only workflow. Building, pushing and deploying stay in slice 5.

**Files:**
- Create: `.github/workflows/tests.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      # Without this the Postgres half of every dual-run test SKIPS, and the
      # suite goes green having proved nothing about the deployed dialect.
      FENCEAI_TEST_POSTGRES: postgresql://postgres:test@localhost:5432/postgres
      FENCEAI_AI: stub
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --extra postgres
      - name: Full suite, both backends
        run: uv run pytest -q
      - name: Release gate
        run: uv run pytest tests/scenarios -q
```

- [ ] **Step 2: Guard against the silent-skip failure**

The workflow's own comment names the hazard: if `FENCEAI_TEST_POSTGRES` were ever dropped, every Postgres test would skip and CI would be green while testing one dialect. Make that impossible to do quietly — add a test to `tests/store/test_dialect.py`:

```python
def test_ci_must_have_a_postgres():
    """In CI, a skipped Postgres half is a broken gate, not a quiet pass.

    This is the one test that asserts something about the ENVIRONMENT rather
    than the code, and it earns that because the failure it catches is
    invisible: a dual-run suite with no server does not fail, it succeeds at
    half the work.
    """
    if os.environ.get("CI") != "true":
        pytest.skip("only meaningful in CI")
    assert postgres_available(), (
        "CI must provide FENCEAI_TEST_POSTGRES and the postgres extra; "
        "without them every Postgres test skips and the gate proves nothing"
    )
```

This needs `import os` and, at the top of the file, `from tests.conftest import postgres_available` — or, if that import does not resolve under this suite's layout, move `postgres_available` into a small `tests/support.py` imported by both. Run it and see which works rather than assuming.

- [ ] **Step 3: Verify locally that the guard behaves both ways**

```bash
CI=true uv run pytest tests/store/test_dialect.py::test_ci_must_have_a_postgres -q
CI=true env -u FENCEAI_TEST_POSTGRES uv run pytest tests/store/test_dialect.py::test_ci_must_have_a_postgres -q
```

Expected: the first passes, the second fails with the message above.

- [ ] **Step 4: Commit and push, then watch the run**

```bash
git add .github/workflows/tests.yml tests/store/test_dialect.py
git commit -m "ci: run the full suite against both backends"
git push
```

Confirm in the Actions tab that the run reports roughly double the database-touching tests, not a pile of skips.

---

## Task 8: Update the docs that now lie

**Files:**
- Modify: `.env.example`
- Modify: `CLAUDE.md`
- Modify: `plan/current-status.md`
- Modify: `docs/superpowers/specs/2026-09-17-gcp-deployment-design.md`

- [ ] **Step 1: `.env.example`**

Replace the `FENCEAI_DB` comment:

```
# Where the data lives. A path is SQLite (the default, and all a laptop needs);
# a postgres:// or postgresql:// URL is a Postgres server, which is what the
# deployment uses. One variable carries both the choice and the address.
#FENCEAI_DB=fenceai.db
```

- [ ] **Step 2: `CLAUDE.md`**

The Commands section gains the Postgres path, since a contributor now has two ways to run the suite:

```
- `uv run pytest -q` — full test suite (SQLite only unless a Postgres is configured)
- `FENCEAI_TEST_POSTGRES=postgresql://... uv run pytest -q` — the same suite, both
  backends; the ~350 tests that open a database run twice. `uv sync --extra postgres`
  first. CI always does this; a laptop need not.
```

Under the backend principles, after the integer-millimetres line:

```
- **One set of SQL, two databases.** `store/db.py` is written in SQLite's spelling
  and `store/dialect.py` translates; the four differences live there and nowhere
  else. Adding a SQL string containing a literal `?` or `%` breaks the translation
  — if you need one, it becomes a fifth `Dialect` member with a test, not a branch
  in `db.py`.
```

- [ ] **Step 3: `plan/current-status.md`**

Add a slice-1 entry recording what landed, the new test count on both backends, and that slices 2–5 of the deployment spec are unbuilt.

- [ ] **Step 4: Resolve the two deviations in the spec**

Per CLAUDE.md, a plan and a spec must not be left disagreeing. Amend §4's "and a connection pool" to "and a single connection, serialized exactly as SQLite's is", and amend §8 so slice 1 owns the test-only CI workflow and slice 5 owns build/push/deploy. Add a line to §1 of the spec noting that the `INSERT OR IGNORE` difference was eliminated rather than translated, so the table of five differences is now four.

- [ ] **Step 5: Run the architecture fitness tests**

```bash
uv run pytest tests/architecture -q
```

CLAUDE.md records that these run only in the full suite and that a new route needs the doc table updated. No route is added here, but run them — `store/dialect.py` is a new module in a package the fitness tests have opinions about.

- [ ] **Step 6: Commit**

```bash
git add .env.example CLAUDE.md plan/current-status.md docs/superpowers/specs/2026-09-17-gcp-deployment-design.md
git commit -m "docs: two databases, one set of SQL"
```

---

## Task 9: Review

- [ ] **Step 1: Run both project reviewers**

They mutate the code, so run them before declaring the slice done — green at 3184 tests has hidden two blockers and a live defect before.

Dispatch `architecture-critic` and `test-reviewer` against the diff from the branch point, asking specifically:
- Does `store/dialect.py` hold every difference, or has one leaked into `db.py` as a branch?
- Do the dual-run tests assert behaviour, or only that both backends do *something*?
- Is `@_serialized`'s guarantee intact, and does `tests/store/test_concurrent_access.py` still detect its removal?

- [ ] **Step 2: Run the browser smoke suite**

```bash
uv run --with websocket-client python tools/ui_smoke.py
```

It is the only detector for the class of bug the `RLock` exists to prevent — pytest cannot see it, because `TestClient` serialises requests.

- [ ] **Step 3: Full suite, both backends, and the gate**

```bash
uv run pytest -q
FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest -q
uv run pytest tests/scenarios -q
```

- [ ] **Step 4: Boot the app with nothing configured**

The spec's slice-1 checkpoint is not "tests pass" — it is that the app still
starts on SQLite with zero setup. Prove it in the state a fresh contributor
would be in:

```bash
cd "$(mktemp -d)" && git clone /home/user/.superset/projects/BOM fenceai-clean && cd fenceai-clean
uv sync                       # note: NO --extra postgres
env -u FENCEAI_TEST_POSTGRES -u FENCEAI_DB uv run uvicorn fenceai.api.app:app --port 8123
```

Open `http://localhost:8123`, confirm the UI loads in Hebrew, and confirm a
`fenceai.db` file appeared. Then stop the server and delete the clone. If this
needs a single extra step — a package, a running daemon, an environment
variable — the offline property has been spent and the slice is not done.

- [ ] **Step 5: Stop here**

Slice 1 is done. Slice 2 — identity becoming Google's — is a product change and gets its own plan, its own review and its own checkpoint. Do not start it in this branch.
