"""Shared fixtures: demo catalog/knowledge and topology builders."""

from __future__ import annotations

import os
import uuid

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.topology.model import (
    IntervalEvent,
    Node,
    PointEvent,
    Run,
    Topology,
)
from fenceai.topology.station import make_anchor


@pytest.fixture
def catalog():
    return demo_catalog()


@pytest.fixture
def knowledge():
    return demo_knowledge()


def straight_topology(length_mm: int, run_id: str = "run1") -> Topology:
    """A single straight run of the given length along the x axis."""
    return Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=length_mm, y_mm=0),
        ],
        runs=[Run(id=run_id, start_node_id="n1", end_node_id="n2")],
    )


def add_point_event(topo: Topology, run_id: str, event_id: str, station_mm: int, payload) -> None:
    run = topo.run(run_id)
    run.point_events.append(
        PointEvent(id=event_id, anchor=make_anchor(topo, run, station_mm), payload=payload)
    )


def add_interval_event(
    topo: Topology, run_id: str, event_id: str, start_mm: int, end_mm: int, payload
) -> None:
    run = topo.run(run_id)
    run.interval_events.append(
        IntervalEvent(
            id=event_id,
            start_anchor=make_anchor(topo, run, start_mm),
            end_anchor=make_anchor(topo, run, end_mm),
            payload=payload,
        )
    )


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
