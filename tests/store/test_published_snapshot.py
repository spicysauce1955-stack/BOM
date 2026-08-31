"""The published snapshot, stored and read back.

The door three slices were built behind. What these tests defend is not that a
snapshot can be saved — it is that **what a run sees after a reload is the same
as what it saw on the way in.** That was the broken path: `knowledge_base()`
returned `KnowledgeBase(versions=…)` and dropped the source verdicts by
construction, so everything the admissibility gate computed died at the store
boundary with nothing failing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fenceai.knowledge.snapshot import Snapshot, SnapshotRefused, ingest, load
from fenceai.store.db import Store

FIXTURE = (Path(__file__).resolve().parents[2]
           / "docs" / "integration-contract" / "fixtures" / "snapshot-example.json")


@pytest.fixture()
def raw() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture()
def store() -> Store:
    return Store(":memory:")


def test_no_snapshot_loaded_is_an_ordinary_state(store):
    """How every installation starts, and how one works with the Knowledge
    Platform unreachable (§3.2.2). Authored knowledge still resolves; the
    published half is simply absent."""
    assert store.active_snapshot() is None
    base = store.knowledge_base()
    assert base.snapshot_id == ""
    assert base.admitted == {}


def test_the_verdicts_survive_a_reload(store, raw):
    """**The assertion this whole slice exists for.**

    A verdict computed at load and lost at the store boundary is worse than no
    verdict: the plan claims provenance on a fresh run and silently drops it on a
    stored one. So what matters is not that the numbers are right once — it is
    that reading the store back gives the same answer as ingesting directly.
    """
    snapshot, _ = load(raw)
    direct = ingest(snapshot)
    store.save_snapshot(snapshot)

    reloaded = store.knowledge_base()
    assert reloaded.snapshot_id == snapshot.snapshot_id
    assert reloaded.admitted == direct.knowledge.admitted
    assert reloaded.declined == direct.knowledge.declined
    assert reloaded.admitted, "the fixture admits at least one row"


def test_authored_and_published_knowledge_arrive_together(store, raw):
    """Published rows resolve beside authored ones in ONE base, which is the
    property the whole expansion exists for — no privileged channel. A base that
    returned only the published half would silently retire every company rule."""
    from fenceai.knowledge.model import KnowledgeVersion

    store.insert_knowledge_version(KnowledgeVersion(
        object_id="K-LOCAL", version=1, type="company_rule", title="ours"))
    snapshot, _ = load(raw)
    store.save_snapshot(snapshot)

    ids = {v.object_id for v in store.knowledge_base().versions}
    assert "K-LOCAL" in ids
    assert any(i.startswith("slope_method@") for i in ids)


def test_the_verdict_is_re_derived_not_frozen(store, raw):
    """The design's load-bearing decision, asserted rather than asserted-in-prose.

    A verdict is a function of `(snapshot, policy, task)`. Storing it would record
    an answer the next policy edit makes false. So the store keeps the DOCUMENT:
    edit the document's provenance, save it again under the same id, and the
    verdict must move with it — which a frozen copy could not do.
    """
    snapshot, _ = load(raw)
    store.save_snapshot(snapshot)
    before = store.knowledge_base()

    # the same snapshot id, its rows now checked by a person
    checked = snapshot.model_copy(deep=True)
    for table in checked.parameters:
        for row in table.rows:
            row.provenance.curation_level = 2
    store.save_snapshot(checked)
    after = store.knowledge_base()

    assert len(after.admitted) > len(before.admitted), (
        "raising curation must admit rows the policy previously refused")
    assert after.snapshot_id == before.snapshot_id, "same document, same id"


def test_a_snapshot_that_no_longer_parses_does_not_lock_out_authored_knowledge(store):
    """A stored document that stops parsing — a schema this engine has moved past
    — must not take the whole base down. Raising here would mean one bad document
    locking a user out of their own company rules, which they can neither see nor
    fix from that state."""
    from fenceai.knowledge.model import KnowledgeVersion

    store.insert_knowledge_version(KnowledgeVersion(
        object_id="K-LOCAL", version=1, type="company_rule", title="ours"))
    store._conn.execute(
        "INSERT INTO knowledge_snapshots (snapshot_id, loaded_at, doc) VALUES (?,?,?)",
        ("BROKEN", "2026-08-31", '{"not": "a snapshot"}'))
    store._conn.execute(
        "INSERT INTO active_snapshot (only_row, snapshot_id) VALUES (1,'BROKEN')")
    store._conn.commit()

    base = store.knowledge_base()
    assert [v.object_id for v in base.versions] == ["K-LOCAL"]
    assert base.snapshot_id == ""


def test_the_real_snapshot_is_refused_by_version_with_one_sentence(raw):
    """What the first person to use this actually hits.

    `3ae88642` predates §1.1's typed `Date` and needs re-cutting by the Knowledge
    Platform. The refusal must name the amendment and say whose move it is — and
    must NOT be a parser explaining that `04/24/2025` is not a dictionary."""
    pre_v12 = dict(raw, contract_version="1.1.0")
    with pytest.raises(SnapshotRefused) as caught:
        load(pre_v12)
    assert caught.value.code == "contract_minor_predates_typed_date"
    assert "re-cut" in str(caught.value)
