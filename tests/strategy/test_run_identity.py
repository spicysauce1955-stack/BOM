"""A run id is a content address. Anything that changes what the run MEANS has to
be inside it, or INSERT OR IGNORE serves a stale document under a reused id."""

import hashlib

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.strategy.model import GenerationRun, ModelUse
from tests.conftest import straight_topology


def test_the_run_records_the_model_snapshot_and_the_catalog_hash():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    assert [(u.model_id, u.version) for u in result.run.model_snapshot] == [("M-LEGACY", 1)]
    # the pair alone cannot identify a document a draft may rewrite in place
    assert len(result.run.model_snapshot[0].content_hash) == 12
    assert len(result.run.catalog_hash) == 16


def test_a_run_stamped_before_content_was_hashed_still_reads():
    """Runs are stored as whole JSON documents; model_snapshot shipped as
    [(id, version)] and a shape change must not make every earlier run
    unreadable."""
    run = GenerationRun.model_validate({"id": "run_x", "model_snapshot": [["M-LEGACY", 1]]})
    assert run.model_snapshot == [ModelUse(model_id="M-LEGACY", version=1)]
    assert run.model_snapshot[0].content_hash == ""


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
