"""The four places SQLite and Postgres disagree, as strings.

No database is opened here. The dialect's whole job is rewriting text, and
text is checkable without a server — which is what keeps this file runnable
on a laptop with nothing installed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fenceai.store.dialect import POSTGRES, SQLITE, Conn, dialect_for
from tests.conftest import postgres_available


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


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+psycopg://u@h/db",  # a SQLAlchemy-style driver suffix
        "postgre://u@h/db",  # a typo one character from working
        "mysql://u@h/db",  # a database we do not speak
        "https://example.invalid/db",  # a stale value from somewhere else
    ],
)
def test_a_url_with_an_unknown_scheme_is_refused_not_read_as_a_filename(dsn):
    """The failure this prevents does not look like a failure.

    Treated as a SQLite path, every one of these boots a healthy, fully
    seeded app on an empty file on the container's ephemeral disk: it serves
    nobody's data and loses every write on redeploy, with nothing in any log
    saying so. A refusal at startup is the cheap version of that news.
    """
    with pytest.raises(ValueError) as excinfo:
        dialect_for(dsn)
    assert dsn.split("://")[0] in str(excinfo.value)


@pytest.mark.parametrize(
    "dsn", ["fenceai.db", "./data/x.db", "/var/lib/fenceai/x.db", ":memory:"]
)
def test_a_bare_path_is_still_a_path(dsn):
    """The refusal keys on `<scheme>://`, so nothing without one is touched."""
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


def _refused_insert_leaves_the_connection_usable(conn):
    """One refused statement, then a read and a write that must still work.

    Shared by both backends on purpose: this is a PARITY claim, not a
    Postgres workaround. The rollback in `Conn.execute` is what makes the
    claim true on Postgres (where the aborted transaction would otherwise
    refuse every later statement) and what makes it honest on SQLite (where
    the pending insert would otherwise ride into a later `commit()`).
    """
    conn.executescript("CREATE TABLE t (id TEXT PRIMARY KEY, doc TEXT);")
    conn.execute("INSERT INTO t (id, doc) VALUES (?,?)", ("a", "first"))
    conn.commit()

    with pytest.raises(Exception):  # each driver names it differently
        conn.execute("INSERT INTO t (id, doc) VALUES (?,?)", ("a", "dupe"))

    assert conn.execute("SELECT doc FROM t WHERE id=?", ("a",)).fetchone()[0] == "first"
    conn.execute("INSERT INTO t (id, doc) VALUES (?,?)", ("b", "second"))
    conn.commit()
    assert conn.execute("SELECT doc FROM t WHERE id=?", ("b",)).fetchone()[0] == "second"
    # The refused row is not resurrected by the later commit.
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2


def test_a_refused_statement_does_not_brick_a_sqlite_conn(tmp_path):
    conn = Conn(str(tmp_path / "refused.db"))
    try:
        _refused_insert_leaves_the_connection_usable(conn)
    finally:
        conn.close()


def test_a_refused_statement_does_not_brick_a_postgres_conn(pg_dsn):
    """Without the rollback this raises `InFailedSqlTransaction` on the READ.

    `Store` holds one connection for the life of the process, so that
    exception is not one bad request — it is every request after it.
    """
    conn = Conn(pg_dsn)
    try:
        _refused_insert_leaves_the_connection_usable(conn)
    finally:
        conn.close()


def _refused_script_leaves_the_connection_usable(conn):
    """The same parity claim as `_refused_insert_leaves_the_connection_usable`,
    for the OTHER statement path.

    `Conn.execute` carried a rollback and a written reason; `executescript`
    carried neither, although it is the path `Store.__init__` runs `_SCHEMA`
    down. `CREATE TABLE IF NOT EXISTS` is not race-safe on Postgres — two
    instances booting against one schema can raise `duplicate key value
    violates unique constraint "pg_type_typname_nsp_index"` — and the escape
    is worse there than in `execute`, because the exception leaves
    `Store.__init__` before `state.store` is assigned, so nothing ever closes a
    connection now sitting idle-in-failed-transaction.

    A duplicate `CREATE TABLE` is that failure, reachable without a race.
    """
    conn.executescript("CREATE TABLE s (id TEXT PRIMARY KEY, doc TEXT);")
    conn.execute("INSERT INTO s (id, doc) VALUES (?,?)", ("a", "first"))
    conn.commit()

    with pytest.raises(Exception):  # each driver names it differently
        conn.executescript("CREATE TABLE s (id TEXT PRIMARY KEY, doc TEXT);")

    # Without the rollback this READ is where Postgres says
    # `InFailedSqlTransaction`, and it says it for every later statement too.
    assert conn.execute("SELECT doc FROM s WHERE id=?", ("a",)).fetchone()[0] == "first"
    conn.execute("INSERT INTO s (id, doc) VALUES (?,?)", ("b", "second"))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM s").fetchone()[0] == 2


def test_a_refused_script_does_not_brick_a_sqlite_conn(tmp_path):
    conn = Conn(str(tmp_path / "refused-script.db"))
    try:
        _refused_script_leaves_the_connection_usable(conn)
    finally:
        conn.close()


def test_a_refused_script_does_not_brick_a_postgres_conn(pg_dsn):
    """The half that could actually happen: `_SCHEMA` failing at boot."""
    conn = Conn(pg_dsn)
    try:
        _refused_script_leaves_the_connection_usable(conn)
    finally:
        conn.close()


def test_no_upsert_omits_its_conflict_target():
    """A targetless `ON CONFLICT DO NOTHING` puts a version floor under SQLite.

    3.24 added UPSERT but REQUIRED a conflict target; the targetless spelling
    only arrived in 3.35.0 (2021-03-12). `dialect.py`'s docstring said 3.24 for
    a while and was wrong, and two statements (`save_run`, `save_supply_run`)
    were rewritten from `INSERT OR IGNORE` into that form — so on a host with
    SQLite 3.24–3.34 (Ubuntu 20.04, RHEL 8) the first generation save died with
    `sqlite3.OperationalError: near "DO": syntax error`. The container image
    ships 3.40 and never showed it, which is why a text assertion is the guard:
    no database this suite can reach will fail on the targetless form, so
    nothing else here would catch it coming back.

    Naming the target costs one word and is accepted by both databases, so
    there is no reason for a statement in this file to omit it.
    """
    import re

    from fenceai.store import db

    src = Path(db.__file__).read_text()
    offenders = re.findall(r"ON CONFLICT\s+DO\s+NOTHING", src)
    assert not offenders, (
        "an upsert in store/db.py omits its conflict target, which needs "
        "SQLite 3.35+ — write `ON CONFLICT(<column>) DO NOTHING`, valid from "
        "3.24 and accepted by Postgres unchanged")


def test_a_failing_rollback_never_hides_the_statement_that_failed():
    """The original error is the one worth reporting, always."""

    class Broken:
        def execute(self, sql, params):
            raise RuntimeError("the statement the caller needs to hear about")

        def rollback(self):
            raise RuntimeError("and a rollback that fails on top of it")

    conn = Conn(":memory:")
    conn._raw.close()
    conn._raw = Broken()
    with pytest.raises(RuntimeError, match="the caller needs to hear about"):
        conn.execute("SELECT 1")


#: Variables whose mere PRESENCE means "this is an automated build".
#: `CI` alone was a GitHub Actions assumption: Cloud Build — the CI of the
#: deployment this whole slice exists for — does not set it, so the guard
#: below would have been silently inert in exactly the pipeline that matters
#: most. Every name here is one no build agent leaves unset and no laptop
#: sets, which is the property that keeps a developer's run green.
_CI_MARKERS = (
    "CI",                    # GitHub Actions, GitLab, CircleCI, Travis, and most others
    "CONTINUOUS_INTEGRATION",
    "BUILD_ID",              # Cloud Build, Jenkins
    "GITHUB_ACTIONS",
    "TF_BUILD",              # Azure Pipelines
    "TEAMCITY_VERSION",
)


#: The values that mean "no" even though the variable is set. `CI=false` is a
#: real idiom — it is how a developer says *not here* to tooling that keys on
#: `CI` — and reading it as presence turns that into one red test on their
#: laptop, which is precisely the failure this guard was widened to avoid.
_CI_DENIALS = frozenset({"0", "false", "no", "off"})


def running_in_ci() -> bool:
    """CI is anything that says so, not just GitHub.

    Presence rather than a value, with one exception: `CI=true` is a GitHub
    Actions convention, while Cloud Build's `BUILD_ID` carries a uuid and
    Azure's `TF_BUILD` says `True` with a capital T. Asking for one exact
    string is how the guard became specific to one provider in the first
    place. But a variable set to a word that SPELLS no is a denial, not a
    uuid, and honouring it costs nothing that a build agent would ever send.
    """
    return any(
        value.strip() and value.strip().lower() not in _CI_DENIALS
        for value in (os.environ.get(name, "") for name in _CI_MARKERS)
    )


def test_ci_must_have_a_postgres():
    """In CI, a skipped Postgres half is a broken gate, not a quiet pass.

    This is the one test that asserts something about the ENVIRONMENT rather
    than the code, and it earns that because the failure it catches is
    invisible: a dual-run suite with no server does not fail, it succeeds at
    half the work.
    """
    if not running_in_ci():
        pytest.skip("only meaningful in CI")
    assert postgres_available(), (
        "CI must provide FENCEAI_TEST_POSTGRES and the postgres extra; "
        "without them every Postgres test skips and the gate proves nothing"
    )


def test_the_ci_guard_recognises_more_than_github(monkeypatch):
    """The guard is only worth having where it actually fires.

    Keyed on `CI == "true"`, it skipped silently under Cloud Build, which is
    this deployment's own pipeline — a gate that proves nothing and says
    nothing. The other half of the property is asserted too: a laptop with
    none of these set must still skip, or every developer's run goes red for
    an environment they never claimed to be in.
    """
    for name in _CI_MARKERS:
        monkeypatch.delenv(name, raising=False)
    assert not running_in_ci()          # a laptop is never CI

    for name in _CI_MARKERS:
        monkeypatch.setenv(name, "some-build-4711")
        assert running_in_ci(), f"{name} must be recognised as CI"
        monkeypatch.delenv(name)


def test_a_variable_that_spells_no_is_not_ci(monkeypatch):
    """`CI=false` is a developer saying *not here*, and must be believed.

    Read as mere presence it did the opposite of what it says, and the person
    it went red for was the one developer careful enough to set it.
    """
    for name in _CI_MARKERS:
        monkeypatch.delenv(name, raising=False)
    for denial in ("0", "false", "False", "no", "off", "  FALSE  ", ""):
        monkeypatch.setenv("CI", denial)
        assert not running_in_ci(), f"CI={denial!r} must not read as CI"
    monkeypatch.setenv("CI", "true")
    assert running_in_ci()
