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


def test_the_preset_does_NOT_change_the_run_id():
    """A design is what it is regardless of how it will be bought.

    `objective_preset` is read by nothing in generate() — only by resolve_supply,
    the panel preview and the impact preview. Keeping it in the digest made the
    design id move for a supply reason, which is the mirror image of one run id
    printing two BOMs: design identity moving when the fence did not, while
    supply identity did not move at all.
    """
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    b = generate(topo, kb, demo_catalog(), policy={"objective_preset": "honour_priority"})
    assert a.run.id == b.run.id
    # the run still REPORTS the preset it was generated under; it simply is not
    # what the run IS
    assert b.run.objective_preset == "honour_priority"


def test_a_design_policy_field_still_changes_the_run_id():
    """The guard against over-correcting. `policy` carries design inputs too, and
    the digest strips exactly ONE key from it — a change that dropped the whole
    dict would make two genuinely different fences hash the same, and this test
    is the difference between the two mistakes."""
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    b = generate(topo, kb, demo_catalog(), policy={"default_height_mm": 2100})
    assert a.run.id != b.run.id


def test_identical_inputs_still_give_identical_ids():
    topo, kb = straight_topology(3000), demo_knowledge()
    assert generate(topo, kb, demo_catalog()).run.id == \
        generate(topo, kb, demo_catalog()).run.id


def test_the_planning_behaviour_version_is_part_of_a_runs_identity(monkeypatch):
    """The digest held DATA versions and no ALGORITHM version, so a legitimate
    change to how a fence is laid out produced a different strategy under the
    SAME id — and `INSERT OR IGNORE` then served the old stored document for
    ever. Bumping the constant is how a planning change says "this means
    something new"."""
    from fenceai.strategy import generator

    topo, kb = straight_topology(3000), demo_knowledge()
    before = generate(topo, kb, demo_catalog()).run.id
    monkeypatch.setattr(generator, "PLANNING_BEHAVIOR_VERSION", "planning-vNEXT")
    assert generate(topo, kb, demo_catalog()).run.id != before


def test_the_digest_version_is_part_of_a_runs_identity(monkeypatch):
    """Same argument one level down: if what goes INTO the digest changes, or how
    it is serialised changes, two runs that mean different things can still hash
    the same."""
    from fenceai.strategy import generator

    topo, kb = straight_topology(3000), demo_knowledge()
    before = generate(topo, kb, demo_catalog()).run.id
    monkeypatch.setattr(generator, "RUN_DIGEST_VERSION", "digest-vNEXT")
    assert generate(topo, kb, demo_catalog()).run.id != before
