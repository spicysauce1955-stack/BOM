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
