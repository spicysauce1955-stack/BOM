"""The library answers "which model does this choice mean" — purely, so a test,
a preview and the store all get the same answer from the same rows."""

from __future__ import annotations

from fenceai.fencemodel.demo import demo_models
from fenceai.fencemodel.library import FenceModelLibrary, content_hash
from fenceai.fencemodel.model import FenceModel


def model(model_id: str, version: int, status: str = "active", **kw) -> FenceModel:
    return FenceModel(id=model_id, version=version, status=status, **kw)


def test_latest_active_is_the_highest_active_version():
    lib = FenceModelLibrary(models=[
        model("M-A", 1), model("M-A", 3), model("M-A", 2),
    ])
    assert lib.latest_active("M-A").version == 3


def test_latest_active_ignores_drafts_and_retired():
    lib = FenceModelLibrary(models=[
        model("M-A", 1, "retired"),
        model("M-A", 2),
        model("M-A", 3, "retired"),
        model("M-A", 4, "draft"),
    ])
    assert lib.latest_active("M-A").version == 2


def test_latest_active_is_none_when_nothing_is_published():
    lib = FenceModelLibrary(models=[model("M-A", 1, "draft")])
    assert lib.latest_active("M-A") is None
    assert lib.latest_active("M-MISSING") is None


def test_get_is_exact_and_scoped_to_the_id():
    lib = FenceModelLibrary(models=[model("M-A", 1), model("M-B", 2)])
    assert lib.get("M-A", 1).ref == "M-A@v1"
    assert lib.get("M-A", 2) is None
    assert lib.get("M-B", 1) is None


def test_resolve_without_a_pin_follows_the_latest_active():
    lib = FenceModelLibrary(models=[model("M-A", 1), model("M-A", 2)])
    assert lib.resolve("M-A", None).version == 2
    assert lib.resolve("M-MISSING", None) is None


def test_a_pin_outranks_status_so_a_stamped_run_stays_reproducible():
    lib = FenceModelLibrary(models=[
        model("M-A", 1, "retired"), model("M-A", 2), model("M-A", 3, "draft"),
    ])
    assert lib.resolve("M-A", 1).version == 1   # retired, still exactly what the run meant
    assert lib.resolve("M-A", 3).version == 3
    assert lib.resolve("M-A", 9) is None        # a pin to nothing is not a fallback


def test_listing_is_one_row_per_model_sorted_by_id():
    lib = FenceModelLibrary(models=[
        model("M-B", 1), model("M-A", 1), model("M-A", 2),
    ])
    rows = lib.listing()
    assert [r.id for r in rows] == ["M-A", "M-B"]
    assert [r.active_version for r in rows] == [2, 1]


def test_listing_reports_a_draft_beside_the_active_version():
    lib = FenceModelLibrary(models=[
        model("M-A", 1, name_i18n={"en": "First", "he": "ראשון"}),
        model("M-A", 2, "draft", name_i18n={"en": "Next", "he": "הבא"}),
    ])
    (row,) = lib.listing()
    assert row.active_version == 1
    assert row.has_draft is True
    # the editor opens THIS version rather than guessing active+1
    assert row.draft_version == 2
    assert row.versions == [1, 2]
    assert row.status == "active"
    assert row.name_i18n == {"en": "First", "he": "ראשון"}   # the version a chooser gets


def test_listing_still_shows_a_model_with_no_active_version():
    lib = FenceModelLibrary(models=[
        model("M-A", 1, "retired", name_i18n={"en": "Old"}),
        model("M-A", 2, "draft", name_i18n={"en": "Unpublished"}),
    ])
    (row,) = lib.listing()
    assert row.active_version is None            # nothing to choose
    assert row.has_draft is True
    assert row.draft_version == 2
    assert row.versions == [1, 2]
    assert row.status == "draft"
    assert row.name_i18n == {"en": "Unpublished"}


def test_the_draft_version_is_the_drafts_own_number_not_a_guess():
    """The reason the field exists. A retired version ABOVE the active one makes
    `active_version + 1` name a version that is not the draft — and `max(versions)`
    name it too — so the editor would open the wrong document, or none.

    Constructed so that BOTH wrong implementations fail: active v1, draft v3,
    retired v4."""
    lib = FenceModelLibrary(models=[
        model("M-A", 1, "active"), model("M-A", 3, "draft"), model("M-A", 4, "retired"),
    ])
    (row,) = lib.listing()
    assert row.active_version == 1
    assert row.draft_version == 3      # not 2 (active + 1), and not 4 (max)
    assert row.versions == [1, 3, 4]


def test_two_drafts_report_the_one_a_new_save_would_land_on():
    """`next_fence_model_version` counts from MAX, so a library that somehow
    carries two drafts must name the higher one — the lower is a document a save
    would never reach."""
    lib = FenceModelLibrary(models=[
        model("M-A", 1, "active"), model("M-A", 2, "draft"), model("M-A", 3, "draft"),
    ])
    (row,) = lib.listing()
    assert row.draft_version == 3


def test_content_hash_is_stable_across_dumps():
    m = demo_models()["M-LEGACY"]
    assert content_hash(m) == content_hash(m)
    assert content_hash(m) == content_hash(FenceModel.model_validate(m.model_dump()))
    assert len(content_hash(m)) == 12


def test_content_hash_separates_documents_sharing_an_id_and_version():
    a = model("M-A", 1, name_i18n={"en": "One"})
    b = model("M-A", 1, name_i18n={"en": "Two"})
    assert content_hash(a) != content_hash(b)


def test_every_demo_model_is_reachable():
    # Written against the dict, never against a count: the demo catalog of
    # models grows, and a test that pins its size would fail on the growth
    # rather than on a defect.
    demo = demo_models()
    lib = FenceModelLibrary(models=list(demo.values()))
    assert demo, "the demo catalog of models must not be empty"
    for model_id, m in demo.items():
        assert lib.get(model_id, m.version).ref == m.ref
        assert lib.resolve(model_id, m.version).ref == m.ref
    assert [r.id for r in lib.listing()] == sorted(demo)
