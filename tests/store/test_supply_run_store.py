"""A SupplyRun is append-only and idempotent by digest, exactly as a
GenerationRun is: the same design against the same yard under the same objective
is ONE fact, however many times it is read."""

from fenceai.fulfillment.fulfill import Bom
from fenceai.fulfillment.supply_run import SupplyRun
from fenceai.store.db import Store


def _sup(**kw) -> SupplyRun:
    base = dict(id="sup_aaa", design_id="run_abc", inventory_hash="inv0",
                catalog_hash="cat0", objective_preset="least_cost",
                supply_version="supply-v1", bom=Bom())
    return SupplyRun(**{**base, **kw})


def test_a_supply_run_round_trips():
    store = Store(":memory:")
    store.save_supply_run(_sup())
    loaded = store.load_supply_run("sup_aaa")
    assert loaded is not None
    assert loaded.design_id == "run_abc"
    assert loaded.objective_preset == "least_cost"
    assert loaded.supply_version == "supply-v1"


def test_an_unknown_supply_run_is_none_not_an_error():
    assert Store(":memory:").load_supply_run("sup_nope") is None


def test_the_store_stamps_created_at():
    store = Store(":memory:")
    store.save_supply_run(_sup())
    assert store.load_supply_run("sup_aaa").created_at


def test_saving_the_same_id_twice_does_not_write_twice():
    """INSERT OR IGNORE, for the reason save_run uses it: /bom resolves supply on
    every read, and a project priced daily must not accumulate a row per read of
    an unchanged yard."""
    store = Store(":memory:")
    store.save_supply_run(_sup())
    store.save_supply_run(_sup(design_id="run_DIFFERENT"))
    assert store.load_supply_run("sup_aaa").design_id == "run_abc"
    assert len(store.list_supply_runs("run_abc")) == 1


def test_supply_runs_are_listed_per_design():
    store = Store(":memory:")
    store.save_supply_run(_sup(id="sup_a", design_id="run_one"))
    store.save_supply_run(_sup(id="sup_b", design_id="run_one"))
    store.save_supply_run(_sup(id="sup_c", design_id="run_two"))
    assert {r["id"] for r in store.list_supply_runs("run_one")} == {"sup_a", "sup_b"}
    assert [r["id"] for r in store.list_supply_runs("run_two")] == ["sup_c"]


def test_writing_a_supply_run_is_audited():
    store = Store(":memory:")
    store.save_supply_run(_sup(), actor="expert")
    assert any(e["action"] == "save_supply_run" and e["ref"] == "sup_aaa"
               for e in store.audit_entries())


def test_saving_a_repeat_returns_the_FIRST_stored_row():
    """The id is the content, so the only field two identical supply runs can
    legitimately differ by is `created_at`. A caller that echoed its own object
    would report a timestamp the database does not have, and two reads of an
    unchanged fence would differ by it — which is exactly how a /bom response
    comparison meant to prove "a stored run cannot be repriced" fails for a
    reason that has nothing to do with pricing."""
    store = Store(":memory:")
    first = store.save_supply_run(_sup())
    second = store.save_supply_run(_sup(created_at=""))
    assert second.created_at == first.created_at
    assert second == first
