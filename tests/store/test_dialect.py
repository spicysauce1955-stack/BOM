"""The four places SQLite and Postgres disagree, as strings.

No database is opened here. The dialect's whole job is rewriting text, and
text is checkable without a server — which is what keeps this file runnable
on a laptop with nothing installed.
"""

from __future__ import annotations

import pytest

from fenceai.store.dialect import POSTGRES, SQLITE, Conn, dialect_for


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
