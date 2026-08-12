"""A run id is a content address. Anything that changes what the run MEANS has to
be inside it, or INSERT OR IGNORE serves a stale document under a reused id."""

import hashlib

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def test_the_run_records_the_model_snapshot_and_the_catalog_hash():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    assert result.run.model_snapshot == [("M-LEGACY", 1)]
    assert len(result.run.catalog_hash) == 16


def test_a_catalog_change_changes_the_run_id():
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    catalog = demo_catalog()
    catalog.products["RAIL-3000"].price_cents = 9999
    b = generate(topo, kb, catalog)
    assert a.run.id != b.run.id


def test_the_preset_changes_the_run_id():
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    b = generate(topo, kb, demo_catalog(), policy={"objective_preset": "honour_priority"})
    assert a.run.id != b.run.id


def test_identical_inputs_still_give_identical_ids():
    topo, kb = straight_topology(3000), demo_knowledge()
    assert generate(topo, kb, demo_catalog()).run.id == \
        generate(topo, kb, demo_catalog()).run.id
