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
