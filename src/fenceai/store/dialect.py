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

import sqlite3
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

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()
