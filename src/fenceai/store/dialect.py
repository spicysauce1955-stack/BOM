"""Where SQLite and Postgres disagree, and nowhere else.

`store/db.py` holds one SQL statement per thing it does, and this module exists
so that stays true — a new statement is a new capability, never a second
spelling of one that is already there. (This line used to fix the count at 63;
it was 64 by the time anyone next read it and 66 after
`create_user_guarded`, so the number said "stale" where the invariant it stood
for had not moved at all. The invariant is the thing to check.)
Every statement there is written once, in SQLite's spelling, and
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

`INSERT OR IGNORE` is NOT on the list. Both statements that needed it
(`save_run`, `save_supply_run`) are written `ON CONFLICT(id) DO NOTHING`, the
form both databases already understand — one fewer difference to carry is
better than one more translation to trust.

THE CONFLICT TARGET IS LOAD-BEARING, and this docstring used to claim the
opposite: it said SQLite had accepted `ON CONFLICT DO NOTHING` since 3.24,
which is false. 3.24 added UPSERT but REQUIRED a conflict target; the
targetless spelling only arrived in 3.35.0 (2021-03-12). The rewrite away from
`INSERT OR IGNORE` therefore raised this app's minimum SQLite from "every
version" to 3.35 without saying so, and on a host shipping 3.24–3.34 —
Ubuntu 20.04, RHEL 8 — the first generation save died with
`sqlite3.OperationalError: near "DO": syntax error`. The container image never
saw it (bookworm ships 3.40), so this was a trap for a developer rather than
for the deploy, which is exactly the kind of floor a docstring has to get
right. Naming `(id)` — the PRIMARY KEY and the only unique constraint on
either table, so the target and the actual conflict are the same thing — is
valid from 3.24 AND accepted by Postgres, so the property survives with no
version floor at all.

Four differences in the SQL this module translates — a fifth exists, but is
not ours to translate: `sqlite3` and `psycopg` name their own exception
classes, with no shared base beyond `Exception` (`sqlite3.IntegrityError` is
not a `psycopg.IntegrityError` and vice versa). That is a fact about the two
driver libraries, not a SQL difference, so a caller that needs to catch a
constraint violation across both backends picks the class per backend
itself rather than asking this module for one — see
`tests/fulfillment/test_quotes.py::test_quote_ids_are_append_only`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    name: str
    #: How this database spells the `audit_log.seq` column.
    serial_pk: str
    #: Statements run before the schema, if any.
    prelude: str
    #: Which database this is. Named for the DATABASE rather than for one
    #: of its consequences: it decides two independent things — whether
    #: `?` becomes `%s` AND which JSON operator to write — and a name
    #: describing only the first makes the second read like a bug.
    is_postgres: bool

    def placeholders(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.is_postgres else sql

    def json_field(self, col: str, key: str) -> str:
        if self.is_postgres:
            return f"{col}::jsonb->>'{key}'"
        # Concatenated rather than an f-string: `$` immediately before `{`
        # reads as a bug every time somebody re-reads it.
        return "json_extract(" + col + ", '$." + key + "')"


SQLITE = Dialect(
    name="sqlite",
    serial_pk="INTEGER PRIMARY KEY AUTOINCREMENT",
    prelude="PRAGMA journal_mode=WAL;",
    is_postgres=False,
)

POSTGRES = Dialect(
    name="postgres",
    serial_pk="BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
    prelude="",
    is_postgres=True,
)

#: What `FENCEAI_DB` looks like when it names a server rather than a file.
_POSTGRES_SCHEMES = ("postgres://", "postgresql://")


def dialect_for(dsn: str) -> Dialect:
    """Which database is `FENCEAI_DB` naming?

    A URL scheme rather than a flag, so one variable carries both the choice
    and the address and the two can never disagree.

    A DSN that LOOKS like a URL but names a scheme this module does not know
    is refused rather than read as a filename. `postgresql+psycopg://…`, a
    typo, or a stale value would otherwise be taken for a relative SQLite
    path: the app boots healthy, seeds itself onto the container's ephemeral
    disk, serves nobody's data, and loses every write at the next redeploy —
    a silent wrong answer where a refusal at startup costs one line in a log.
    A bare path is still a path; only `<scheme>://` triggers the check.
    """
    scheme, sep, _ = dsn.partition("://")
    if sep and f"{scheme}://" not in _POSTGRES_SCHEMES:
        raise ValueError(
            f"unknown database URL scheme {scheme!r}: expected one of "
            f"{', '.join(_POSTGRES_SCHEMES)} or a SQLite file path"
        )
    return POSTGRES if dsn.startswith(_POSTGRES_SCHEMES) else SQLITE


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
        """Run one statement, and roll back if it is refused.

        The rollback is not tidiness, it is the difference between one failed
        write and a dead process. psycopg runs an implicit transaction and an
        error ABORTS it: every later statement, reads included, then raises
        `InFailedSqlTransaction: current transaction is aborted, commands
        ignored until end of transaction block` until somebody rolls back.
        `Store` holds ONE connection for the whole process and the deployment
        pins Cloud Run to one instance, so without this a single duplicate
        quote id or repeated email would turn the app into a 500 machine —
        for reads too — until the container was replaced.

        It earns its place on SQLite as well, where the failure is quieter
        and worse: a refused statement leaves whatever was uncommitted before
        it still pending, to be swept into some LATER call's `commit()` as if
        it had been asked for. Rolling back here means a refused write costs
        the caller that write and nothing else, on both databases.

        The error always propagates; a rollback that fails itself is
        swallowed so it cannot stand in front of the exception that matters.

        Handing back the driver's raw cursor — rather than wrapping it — is
        safe while four things hold, and each is checkable by reading
        `store/db.py`:

        1. every column is TEXT or INTEGER, so no type adapter differs
           between the drivers (no DATE, NUMERIC, BLOB or JSON column);
        2. `fetchone()`/`fetchall()` is called only on a statement that
           returns rows — psycopg raises on a non-returning one where
           `sqlite3` answers `None`;
        3. `rowcount` is read only after DML, never after a SELECT, where
           psycopg reports it before the rows have been consumed;
        4. `Conn` stays one cursor per `execute`, so no two result sets are
           ever live at once and a cursor is never reused after the next
           statement has moved on.

        Break any of them and the wrapper stops being optional.
        """
        try:
            return self._raw.execute(self.dialect.placeholders(sql), params)
        except Exception:
            try:
                self._raw.rollback()
            except Exception:
                pass  # never let a failed rollback hide the real failure
            raise

    def executescript(self, sql: str) -> None:
        """Several statements at once, for schema creation only.

        `sqlite3` has `executescript`; psycopg does not, but accepts several
        statements in one `execute` when there are no parameters — which
        schema DDL never has.

        The rollback is `execute`'s, for `execute`'s reason and no other: a
        failed statement leaves a Postgres connection idle-in-failed-
        transaction, where every subsequent statement on it raises, so the
        wrapper exists to keep one failure from turning the connection into a
        500 machine. This method had no such wrapper while its only sibling
        did, WITH a written justification — which is the kind of asymmetry a
        later reader resolves in the wrong direction, by deciding the
        justification must not have applied here.

        It does apply here. `CREATE TABLE IF NOT EXISTS` is not race-safe on
        Postgres: two instances booting against one schema can raise
        `duplicate key value violates unique constraint
        "pg_type_typname_nsp_index"`. Unreachable today — the deployment pins
        `max-instances=1` — but the escape route is worse than `execute`'s,
        because this runs from `Store.__init__`, so the exception leaves before
        `state.store` is assigned and nothing ever closes the connection.
        """
        try:
            if self.dialect is SQLITE:
                self._raw.executescript(sql)
            else:
                self._raw.execute(sql)
        except Exception:
            try:
                self._raw.rollback()
            except Exception:
                pass  # never let a failed rollback hide the real failure
            raise
        self._raw.commit()

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()
