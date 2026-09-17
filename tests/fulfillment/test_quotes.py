"""Quote snapshot store tests (fulfillment/quote.py + store)."""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.ids import new_id
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.fulfillment.quote import Quote
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def make_quote(project_id="p1", label="") -> Quote:
    catalog = demo_catalog()
    result = generate(straight_topology(6000), demo_knowledge(), catalog)
    # the real pipeline, not derive+fulfill by hand: skipping resolve_supply
    # leaves every panel line with a blank sku, which fulfill() now refuses
    priced = price_strategy(result.strategy, catalog,
                            demand_skus=result.run.demand_skus)
    return Quote(
        id=new_id("quote"), project_id=project_id, run_id=result.run.id, label=label,
        knowledge_snapshot_hash=result.run.snapshot_hash,
        catalog_hash=result.run.catalog_hash,
        requirements=priced.requirements, bom=priced.bom,
        total_cents=priced.bom.total_cents,
    )


def test_quote_roundtrip_is_lossless(store):
    q = make_quote(label="first offer")
    store.save_quote(q)
    loaded = store.load_quote(q.id)
    assert loaded.model_dump() == q.model_dump()
    assert loaded.bom.total_cents == loaded.total_cents
    assert loaded.requirements  # full pegged demand travels with the quote


def test_accept_supersedes_previous_accepted(store):
    q1, q2 = make_quote(), make_quote()
    store.save_quote(q1)
    store.save_quote(q2)
    store.accept_quote(q1.id)
    assert store.latest_accepted_quote("p1").id == q1.id
    store.accept_quote(q2.id)
    assert store.load_quote(q1.id).status == "superseded"
    assert store.latest_accepted_quote("p1").id == q2.id
    # superseded quotes cannot be re-accepted
    with pytest.raises(ValueError):
        store.accept_quote(q1.id)
    with pytest.raises(KeyError):
        store.accept_quote("quote_missing")


def test_accept_scoped_per_project(store):
    a, b = make_quote(project_id="pa"), make_quote(project_id="pb")
    store.save_quote(a)
    store.save_quote(b)
    store.accept_quote(a.id)
    store.accept_quote(b.id)
    assert store.load_quote(a.id).status == "accepted"  # other project untouched
    assert store.load_quote(b.id).status == "accepted"


def test_quote_ids_are_append_only(store, backend):
    """`id` is `PRIMARY KEY` with a plain `INSERT` (no `OR IGNORE` / `ON
    CONFLICT`), so a repeat is refused rather than silently accepted — but the
    two drivers name that refusal with unrelated exception classes (there is
    no shared base between `sqlite3` and `psycopg`), so which one to expect
    is a fact about the backend, not about the store."""
    q = make_quote()
    store.save_quote(q)
    if backend == "sqlite":
        import sqlite3
        error = sqlite3.IntegrityError
    else:
        import psycopg
        error = psycopg.IntegrityError

    with pytest.raises(error):
        store.save_quote(q)  # same id can never be overwritten

    # A refused write must cost the caller that one write and nothing else.
    # psycopg runs an implicit transaction and an error ABORTS it: until
    # somebody rolls back, every later statement — reads included — raises
    # `InFailedSqlTransaction`. `Store` holds one process-wide connection, so
    # without the rollback in `Conn.execute` a single duplicate id turns the
    # whole app into a 500 machine until the process is replaced. Asserted
    # after the refusal rather than at `pytest.raises`, because a suite that
    # stops at the exception is exactly how that survived 3806 green tests.
    assert store.load_quote(q.id).id == q.id  # a read still works
    fresh = make_quote(label="after the refusal")
    store.save_quote(fresh)  # and a legitimate write still lands
    assert store.load_quote(fresh.id).label == "after the refusal"
