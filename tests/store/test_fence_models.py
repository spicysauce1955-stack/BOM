"""Fence-model persistence: drafts are editable, published versions are frozen,
and the document's own `status` never disagrees with its row."""

from __future__ import annotations

import pytest

from fenceai.fencemodel.demo import demo_models
from fenceai.fencemodel.model import FenceModel
from fenceai.store.db import Store


def model(model_id: str = "M-T", version: int = 1, status: str = "draft", **kw) -> FenceModel:
    return FenceModel(id=model_id, version=version, status=status, **kw)


def test_roundtrip_is_lossless():
    store = Store(":memory:")
    m = model(name_i18n={"en": "Test", "he": "בדיקה"})
    store.save_fence_model(m)
    assert store.load_fence_model("M-T", 1).model_dump() == m.model_dump()
    assert store.load_fence_model("M-T", 2) is None
    assert store.load_fence_model("M-MISSING", 1) is None


def test_a_draft_may_be_overwritten_in_place():
    store = Store(":memory:")
    store.save_fence_model(model(name_i18n={"en": "First"}))
    store.save_fence_model(model(name_i18n={"en": "Second"}))
    assert store.load_fence_model("M-T", 1).name_i18n == {"en": "Second"}


def test_a_published_version_refuses_to_be_rewritten():
    store = Store(":memory:")
    store.save_fence_model(model(status="active", name_i18n={"en": "Shipped"}))
    with pytest.raises(ValueError, match="M-T@v1"):
        store.save_fence_model(model(status="active", name_i18n={"en": "Rewritten"}))
    assert store.load_fence_model("M-T", 1).name_i18n == {"en": "Shipped"}

    store.set_fence_model_status("M-T", 1, "retired", actor="expert")
    with pytest.raises(ValueError, match="M-T@v1"):
        store.save_fence_model(model(status="retired"))


def test_status_change_rewrites_the_document_too():
    store = Store(":memory:")
    store.save_fence_model(model(status="draft"))
    store.set_fence_model_status("M-T", 1, "active", actor="expert")

    assert store.load_fence_model("M-T", 1).status == "active"
    (column,) = store._conn.execute(
        "SELECT status FROM fence_models WHERE model_id='M-T' AND version=1"
    ).fetchone()
    assert column == "active"
    # the library reads documents, so a doc that lagged its row would make a
    # retired model still resolve as the latest active one
    assert store.fence_model_library().latest_active("M-T").version == 1
    store.set_fence_model_status("M-T", 1, "retired", actor="expert")
    assert store.fence_model_library().latest_active("M-T") is None


def test_status_change_is_audited():
    store = Store(":memory:")
    store.save_fence_model(model())
    store.set_fence_model_status("M-T", 1, "active", actor="expert")
    entry = store.audit_entries(1)[0]
    assert entry["action"] == "fence_model_status:active"
    assert entry["ref"] == "M-T@v1"
    assert entry["actor"] == "expert"


def test_unknown_status_and_unknown_model_are_refused():
    store = Store(":memory:")
    store.save_fence_model(model())
    with pytest.raises(ValueError):
        store.set_fence_model_status("M-T", 1, "published", actor="expert")
    with pytest.raises(KeyError):
        store.set_fence_model_status("M-MISSING", 1, "active", actor="expert")
    assert store.load_fence_model("M-T", 1).status == "draft"


def test_library_is_every_row_ordered():
    store = Store(":memory:")
    store.save_fence_model(model("M-B", 1, "active"))
    store.save_fence_model(model("M-A", 2, "active"))
    store.save_fence_model(model("M-A", 1, "retired"))
    lib = store.fence_model_library()
    refs = [m.ref for m in lib.models]
    assert refs.index("M-A@v1") < refs.index("M-A@v2") < refs.index("M-B@v1")
    assert lib.latest_active("M-A").version == 2


def test_next_version_starts_at_one_and_follows_the_maximum():
    store = Store(":memory:")
    assert store.next_fence_model_version("M-NEW") == 1
    store.save_fence_model(model("M-NEW", 1, "active"))
    store.save_fence_model(model("M-NEW", 5, "active"))
    assert store.next_fence_model_version("M-NEW") == 6
    assert store.next_fence_model_version("M-OTHER") == 1


def test_a_fresh_store_is_seeded_with_the_demo_models(tmp_path):
    path = str(tmp_path / "seed.db")
    store = Store(path)
    lib = store.fence_model_library()
    for model_id, m in demo_models().items():
        seeded = lib.get(model_id, m.version)
        assert seeded is not None
        assert seeded.status == "active"          # selectable without an extra step
        assert lib.latest_active(model_id) is not None
    store.close()


def test_seeding_never_overwrites_what_is_already_there(tmp_path):
    path = str(tmp_path / "reopen.db")
    store = Store(path)
    model_id, seeded = next(iter(demo_models().items()))
    edited = seeded.model_copy(update={"version": seeded.version + 1, "status": "draft"})
    store.save_fence_model(edited)
    before = [m.ref for m in store.fence_model_library().models]
    store.close()

    reopened = Store(path)
    lib = reopened.fence_model_library()
    assert [m.ref for m in lib.models] == before      # no duplicate rows
    assert lib.get(model_id, edited.version).status == "draft"
    reopened.close()
