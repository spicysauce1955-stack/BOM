"""Parts are the third citizen of a pattern knowledge and fence models already
follow: content immutable, status the only mutation, publishing retires its
predecessor."""

import pytest

from fenceai.parts.model import Part, SpecField
from fenceai.store.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "t.db"))


def rail(version=1, status="active", width=38) -> Part:
    return Part(id="rail-38", version=version, type="rail", status=status,
                spec=[SpecField(key="width_mm", value=width, agree="==", unit="mm")])


def test_a_part_round_trips(store):
    store.save_part(rail())
    assert store.load_part("rail-38", 1).width_mm == 38


def test_a_draft_may_be_rewritten_in_place(store):
    store.save_part(rail(status="draft"))
    store.save_part(rail(status="draft", width=45))
    assert store.load_part("rail-38", 1).width_mm == 45


def test_a_published_version_is_immutable(store):
    store.save_part(rail())
    with pytest.raises(ValueError, match="immutable"):
        store.save_part(rail(width=45))


def test_publishing_retires_its_predecessor(store):
    store.save_part(rail(version=1))
    store.save_part(rail(version=2, status="draft"))
    store.set_part_status("rail-38", 2, "active")
    assert store.load_part("rail-38", 1).status == "retired"
    assert store.load_part("rail-38", 2).status == "active"


def test_an_illegal_status_transition_is_refused(store):
    store.save_part(rail(version=1))
    store.set_part_status("rail-38", 1, "retired")
    with pytest.raises(ValueError, match="illegal status transition"):
        store.set_part_status("rail-38", 1, "draft")


def test_the_library_answers_latest_active(store):
    store.save_part(rail(version=1))
    store.save_part(rail(version=2, status="draft"))
    lib = store.part_library()
    assert lib.latest_active("rail-38").version == 1
    store.set_part_status("rail-38", 2, "active")
    assert store.part_library().latest_active("rail-38").version == 2


def test_next_version_counts_from_what_exists(store):
    assert store.next_part_version("rail-38") == 1
    store.save_part(rail(version=1))
    assert store.next_part_version("rail-38") == 2


def test_saving_writes_an_audit_row(store):
    store.save_part(rail())
    assert any(r["ref"] == "rail-38@v1" for r in store.audit_entries())


# ---- the second door into "active" (fix wave, F1/F3/F4/M3) -------------------

def test_saving_a_second_active_version_is_refused(store):
    """`Part.status` DEFAULTS to "active", so `save_part` was a door into the state
    `set_part_status` guards — and it skipped the retire-predecessor rule entirely.
    `rail-38` ended with [(1,'active'), (2,'active')] and `latest_active`'s
    `max(version)` then hid the contradiction instead of reporting it."""
    store.save_part(rail(version=1))
    with pytest.raises(ValueError, match="second active version"):
        store.save_part(rail(version=2, width=45))
    assert [p.version for p in store.part_library().parts
            if p.id == "rail-38" and p.status == "active"] == [1]


def test_reactivating_the_version_that_is_already_active_is_not_a_second_one(store):
    """The refusal counts OTHER versions. Rewriting a draft that happens to be the
    only active row is not the ambiguity this guards."""
    store.save_part(rail(version=1, status="draft"))
    store.set_part_status("rail-38", 1, "active")
    assert store.part_library().latest_active("rail-38").version == 1


def test_a_failed_activation_leaves_no_retired_predecessor_behind(store):
    """The activate path retires every other active version and THEN writes the
    target, under one commit. Without a rollback the retires sat uncommitted and
    the next store call's commit landed them: the id ends with ZERO active
    versions and every model naming it fails generation."""
    store.save_part(rail(version=1))
    store.save_part(rail(version=2, status="draft", width=45))

    real = store._set_part_status_nocommit

    def boom(part_id, version, status, actor):
        if version == 2:
            raise RuntimeError("disk went away")
        return real(part_id, version, status, actor)

    store._set_part_status_nocommit = boom
    with pytest.raises(RuntimeError):
        store.set_part_status("rail-38", 2, "active")
    store._set_part_status_nocommit = real
    # the retire of v1 was rolled back with the failed write, not left to be
    # committed by whoever calls next
    store.save_part(rail(version=3, status="draft"))
    assert store.load_part("rail-38", 1).status == "active"
    assert store.part_library().latest_active("rail-38").version == 1


def test_a_draft_of_an_in_use_part_can_still_be_discarded(store, tmp_path):
    """Retirement is refused when it would leave the ID with nothing, because a
    model names the id and resolution takes `latest_active`. Asking the question
    of the VERSION refused every abandoned draft of every in-use part — and
    `draft -> {active, retired}` are the only transitions it has, so the draft was
    stuck forever."""
    # the store SEEDS the demo models and their parts, so M-SLAT is active and
    # `rail-rail-3000@v1` is the version its rail slot resolves
    store.save_part(Part(id="rail-rail-3000", version=2, status="draft", type="rail",
                         spec=[SpecField(key="sku", value=["RAIL-3000"], agree="among")]))
    store.set_part_status("rail-rail-3000", 2, "retired")
    assert store.load_part("rail-rail-3000", 2).status == "retired"
    # and the active version that the model actually resolves is untouched
    assert store.part_library().latest_active("rail-rail-3000").version == 1
    with pytest.raises(ValueError, match="still named by"):
        store.set_part_status("rail-rail-3000", 1, "retired")


def test_a_part_no_product_covers_is_refused_at_publish_not_at_generation(store):
    """`validate_part`'s docstring promises "refusals a part earns at authoring
    time" and design §3.3 promises the same, but its only caller was
    `validate_model` — i.e. generation, which hands the author a 422 on a job they
    were pricing instead of a refusal on the part they were writing."""
    from fenceai.catalog.demo import demo_catalog

    store.save_catalog(demo_catalog())
    unobtainable = Part(id="rail-x", version=1, type="rail",
                        spec=[SpecField(key="material", value="unobtainium")])
    with pytest.raises(ValueError, match="no product in the catalog covers"):
        store.save_part(unobtainable)
    # a DRAFT may hold anything — that is what lets an author write a spec before
    # the item exists
    store.save_part(unobtainable.model_copy(update={"status": "draft"}))
    with pytest.raises(ValueError, match="no product in the catalog covers"):
        store.set_part_status("rail-x", 1, "active")
