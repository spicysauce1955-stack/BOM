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
