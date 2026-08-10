"""Quote snapshot store tests (fulfillment/quote.py + store)."""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.ids import new_id
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.quote import Quote
from fenceai.knowledge.demo import demo_knowledge
from fenceai.store.db import Store
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def make_quote(project_id="p1", label="") -> Quote:
    catalog = demo_catalog()
    result = generate(straight_topology(6000), demo_knowledge(), catalog)
    reqs = derive_requirements(result.strategy, catalog)
    bom = fulfill(reqs, catalog)
    return Quote(
        id=new_id("quote"), project_id=project_id, run_id=result.run.id, label=label,
        knowledge_snapshot_hash=result.run.snapshot_hash,
        requirements=reqs, bom=bom, total_cents=bom.total_cents,
    )


def test_quote_roundtrip_is_lossless():
    store = Store(":memory:")
    q = make_quote(label="first offer")
    store.save_quote(q)
    loaded = store.load_quote(q.id)
    assert loaded.model_dump() == q.model_dump()
    assert loaded.bom.total_cents == loaded.total_cents
    assert loaded.requirements  # full pegged demand travels with the quote


def test_accept_supersedes_previous_accepted():
    store = Store(":memory:")
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


def test_accept_scoped_per_project():
    store = Store(":memory:")
    a, b = make_quote(project_id="pa"), make_quote(project_id="pb")
    store.save_quote(a)
    store.save_quote(b)
    store.accept_quote(a.id)
    store.accept_quote(b.id)
    assert store.load_quote(a.id).status == "accepted"  # other project untouched
    assert store.load_quote(b.id).status == "accepted"


def test_quote_ids_are_append_only():
    store = Store(":memory:")
    q = make_quote()
    store.save_quote(q)
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store.save_quote(q)  # same id can never be overwritten
