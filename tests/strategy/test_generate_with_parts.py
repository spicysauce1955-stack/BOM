"""What `generate(parts=…)` does, and what it stamps.

`generator.py` could not be imported at all while the demo models were mid-migration,
so the wiring that resolves a model's parts and records what it resolved landed with
no test over the real entry point. This is that test, and the run-identity half of it
is the one nothing else pins: `part_snapshot` was added to the digest so that two runs
built from different part versions cannot collide, and a digest that quietly stopped
reading it would still produce a green suite everywhere else.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.knowledge.demo import demo_knowledge
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

SLAT = FenceModelChoice(model_id="M-SLAT")
LIBRARY = FenceModelLibrary(models=[M_LEGACY, M_SLAT])


def parts() -> PartLibrary:
    return PartLibrary(parts=demo_parts())


def run(part_library=None, **kw):
    return generate(straight_topology(5000), demo_knowledge(), demo_catalog(),
                    models=LIBRARY, default_model=SLAT,
                    parts=part_library if part_library is not None else parts(),
                    **kw)


def bom_of(result):
    return price_strategy(result.strategy, demo_catalog(),
                          demand_skus=result.run.demand_skus,
                          preset=result.run.objective_preset).bom


# --- resolution ---------------------------------------------------------------

def test_a_generated_slot_buys_the_product_its_part_names():
    """The whole point of the entity, at the only place it is spendable: the model
    document names `infill-slat-100` and nothing else, and SLAT-100 reaches the BOM
    because the PART said so."""
    result = run()
    panel = result.strategy.spans[0].panel
    by_key = {s.slot_key: s for s in panel.slots}
    assert [m.sku for m in by_key["slat"].eligibility.members] == ["SLAT-100"]
    assert [m.sku for m in by_key["rail"].eligibility.members] == ["RAIL-3000"]
    assert [m.sku for m in by_key["screw"].eligibility.members] == ["SCREW-S10"]
    # and the role and the width came from the part too, not from the slot
    assert by_key["slat"].role == "infill"
    assert "SLAT-100" in {line.sku for line in bom_of(result).lines}


def test_the_run_stamps_every_part_it_resolved():
    result = run()
    stamped = {u.part_id: u for u in result.run.part_snapshot}
    assert set(stamped) == {"infill-slat-100", "rail-rail-3000", "screw-screw-s10"}
    assert all(u.version == 1 for u in stamped.values())
    assert all(u.content_hash for u in stamped.values()), \
        "a draft is mutable, so the version number alone is not what a run read"


def test_a_model_naming_no_part_is_untouched_by_a_library():
    """M-LEGACY's eligibility is knowledge's, rebuilt per run. Passing a library
    must not overwrite it — that seam is the reason a `DefaultComponent` still
    reaches the BOM."""
    legacy = generate(straight_topology(5000), demo_knowledge(), demo_catalog(),
                      models=LIBRARY, parts=parts(),
                      default_model=FenceModelChoice(model_id="M-LEGACY"))
    rail = next(s for s in legacy.strategy.spans[0].panel.slots if s.role == "rail")
    assert [m.sku for m in rail.eligibility.members] == ["RAIL-3000"]
    assert legacy.run.part_snapshot == [], "it resolved no part, so it stamps none"


# --- run identity -------------------------------------------------------------

def _library_at_version(version: int) -> PartLibrary:
    """The same demo library with one part republished at a NEW version and an
    IDENTICAL spec.

    Identical on purpose: it changes the snapshot and nothing else, so a digest that
    had stopped reading `part_snapshot` would hand back the same run id and this
    test would be the only thing that noticed.
    """
    return PartLibrary(parts=[
        p.model_copy(deep=True, update={"version": version})
        if p.id == "rail-rail-3000" else p
        for p in demo_parts()])


def test_the_same_library_twice_is_the_same_run():
    assert run().run.id == run().run.id


def test_a_new_part_version_changes_the_run_id_without_changing_the_fence():
    """Two runs building the identical fence from different part versions were not
    generated from the same thing. That is the whole reason `part_snapshot` is a
    digest input — without it the second run's INSERT OR IGNORE would drop silently
    and every later read would serve the first run's answer."""
    before, after = run(), run(_library_at_version(2))

    assert [u.version for u in after.run.part_snapshot
            if u.part_id == "rail-rail-3000"] == [2]
    assert before.run.id != after.run.id

    # ... and the fence itself did not move, which is what makes the id the only
    # thing this test could be measuring
    assert bom_of(before).model_dump() == bom_of(after).model_dump()
    assert [s.panel.model_dump() for s in before.strategy.spans] \
        == [s.panel.model_dump() for s in after.strategy.spans]


def test_the_run_id_does_not_move_when_the_snapshot_does_not():
    """The other half, and the half that fails if the digest were made to include
    something incidental: a part the models do not name is not part of what this run
    was generated from."""
    unnamed = PartLibrary(parts=[
        p.model_copy(deep=True, update={"version": 9})
        if p.id == "rail-38-vinyl" else p
        for p in demo_parts()])
    assert run().run.id == run(unnamed).run.id


# --- the order a run stamps (fix wave, T3) ------------------------------------

def two_model_run(part_library=None):
    """One fence, two models, so the snapshot is assembled from TWO segments.

    That is what makes the order a real question. `resolve_model_parts` already
    returns each model's own uses sorted, so a single-model run stamps a sorted
    list whether `generate()` sorts or not — the ordering test has to reach a run
    where the walk order and the sort order genuinely disagree.
    """
    from fenceai.fencemodel.demo import M_VINYL
    from fenceai.topology.model import FenceModelPayload
    from tests.conftest import add_interval_event

    topo = straight_topology(5000)
    add_interval_event(topo, "run1", "ev_m", 0, 2500,
                       FenceModelPayload(model_id="M-VINYL"))
    return generate(topo, demo_knowledge(), demo_catalog(),
                    models=FenceModelLibrary(models=[M_LEGACY, M_SLAT, M_VINYL]),
                    default_model=SLAT,
                    parts=part_library if part_library is not None else parts())


def test_a_generated_run_stamps_its_snapshot_in_sort_key_order():
    """The stored order is a digest input, so it decides the run id — and the walk
    order is not it. M-VINYL is laid out first and contributes
    `rail-rail-v-3000` before M-SLAT contributes `rail-rail-3000`, so an unsorted
    snapshot and a sorted one are different lists for the same fence.
    """
    snapshot = two_model_run().run.part_snapshot
    assert [u.part_id for u in snapshot] == [
        "infill-slat-100", "infill-slat-v-150",
        "rail-rail-3000", "rail-rail-v-3000", "screw-screw-s10",
    ]
    assert snapshot == sorted(snapshot, key=type(snapshot[0]).sort_key)


def test_one_part_reached_from_two_segments_is_stamped_once():
    """Deduped, because the same part reached through two segments is one fact
    about the run — and a repeated entry would split the digest between two
    identical fences depending on how the walk happened to go."""
    snapshot = two_model_run().run.part_snapshot
    assert len({(u.part_id, u.version) for u in snapshot}) == len(snapshot)
    # M-SLAT and M-VINYL both reach `screw-screw-s10`? they do not — but M-SLAT
    # is the model of BOTH bays right of the change, and it is reached twice
    assert sum(1 for u in snapshot if u.part_id == "rail-rail-3000") == 1


def test_the_same_version_saying_something_else_is_a_different_run():
    """What `content_hash` is actually for, now that the docstring says so.

    A version NUMBER is not enough on its own: two libraries can both call a part
    `rail-rail-3000@v1` and mean different documents, and `(part_id, version)` alone
    would hash them to one run — whose second INSERT OR IGNORE drops silently, so
    every later read serves the first run's answer for the second run's fence.

    The edit is deliberately one that changes NOTHING about the fence: RAIL-3000 is
    the only aluminium rail the sku row already admitted, so the BOM, the panels and
    the geometry are identical and the run id is the only thing this test could be
    measuring.
    """
    from fenceai.parts.model import SpecField

    edited = PartLibrary(parts=[
        p.model_copy(deep=True, update={
            "spec": [*p.spec, SpecField(key="material", value="aluminium")]})
        if p.id == "rail-rail-3000" else p
        for p in demo_parts()])

    before, after = run(), run(edited)
    assert [u.version for u in after.run.part_snapshot] == \
        [u.version for u in before.run.part_snapshot], "no version moved"
    assert [u.content_hash for u in after.run.part_snapshot] != \
        [u.content_hash for u in before.run.part_snapshot]
    assert before.run.id != after.run.id

    assert bom_of(before).model_dump() == bom_of(after).model_dump()
    assert [s.panel.model_dump() for s in before.strategy.spans] \
        == [s.panel.model_dump() for s in after.strategy.spans]
