"""A correction is one turn of a conversation, so it has to keep its place in it.

Two things were missing and neither shows up until you try to READ corrections
back: nothing stamped `created_at`, and `list_corrections` ordered by `id` —
which is `corr_<uuid4 hex>`, i.e. effectively random. A thread rendered from
that is a conversation with its turns shuffled.

The clock lives in the store, exactly as it does for a quote (`save_quote`), so
the domain stays free of `datetime.now()` and a caller cannot forget.
"""

from __future__ import annotations

from fenceai.learning.model import Correction
from fenceai.store.db import Store


def _store() -> Store:
    return Store(":memory:")


def _corr(cid: str, comment: str, created_at: str = "") -> Correction:
    return Correction(id=cid, project_id="p1", generation_run_id="run_1",
                      comment=comment, created_at=created_at)


def test_the_store_stamps_when_a_correction_was_made():
    """The domain never calls a clock; the store does, as it already does for a
    quote. A caller that forgot would leave a comment with no place in time."""
    store = _store()
    store.save_correction(_corr("corr_a", "first"))
    [got] = store.list_corrections("p1")
    assert got.created_at, "a correction with no timestamp cannot be threaded"


def test_a_stamp_the_caller_supplied_is_kept():
    """Same rule `save_quote` follows: the store fills a BLANK, it does not
    overwrite a time somebody else established."""
    store = _store()
    store.save_correction(_corr("corr_a", "first", created_at="2020-01-01T00:00:00+00:00"))
    [got] = store.list_corrections("p1")
    assert got.created_at == "2020-01-01T00:00:00+00:00"


def test_corrections_come_back_in_the_order_they_were_MADE():
    """THE defect. `ORDER BY id` on a uuid is a shuffle, and the ids below are
    deliberately in the reverse of their real order — sorted by id they read
    backwards, which is what a reader would have seen."""
    store = _store()
    store.save_correction(_corr("corr_zzz", "first", "2026-01-01T00:00:00+00:00"))
    store.save_correction(_corr("corr_aaa", "second", "2026-01-02T00:00:00+00:00"))
    store.save_correction(_corr("corr_mmm", "third", "2026-01-03T00:00:00+00:00"))
    assert [c.comment for c in store.list_corrections("p1")] == \
        ["first", "second", "third"]


def test_a_correction_with_no_stamp_still_has_a_place():
    """Rows written before the stamp existed must not vanish or jump to the end
    of every thread. Sorting on (created_at, id) puts them first — which is
    where they belong, being older than anything stamped — and keeps the order
    total, so two comments in the same second cannot swap between two reads."""
    store = _store()
    store.save_correction(Correction(id="corr_old", project_id="p1",
                                     generation_run_id="run_1", comment="ancient",
                                     created_at=""))
    # written directly, bypassing the stamp the way an old row would have been
    store._conn.execute(
        "UPDATE corrections SET doc = ? WHERE id = 'corr_old'",
        (Correction(id="corr_old", project_id="p1", generation_run_id="run_1",
                    comment="ancient", created_at="").model_dump_json(),))
    store.save_correction(_corr("corr_new", "recent", "2026-01-02T00:00:00+00:00"))
    assert [c.comment for c in store.list_corrections("p1")] == ["ancient", "recent"]


def test_two_turns_in_the_same_instant_keep_a_stable_order():
    """The docstring above claims the order is TOTAL; nothing tested it, because
    no fixture had two equal stamps. Equal times fall back to the id, so two
    reads cannot disagree — a thread that reshuffled between renders would be a
    conversation nobody could quote."""
    store = _store()
    same = "2026-01-01T00:00:00+00:00"
    store.save_correction(_corr("corr_zzz", "written first", same))
    store.save_correction(_corr("corr_aaa", "written second", same))
    once = [c.id for c in store.list_corrections("p1")]
    twice = [c.id for c in store.list_corrections("p1")]
    assert once == twice == ["corr_aaa", "corr_zzz"]


def test_two_writers_do_not_lose_a_turn():
    """`Store` serialises every public method and nothing proved it for this
    table. A conversation that dropped a turn under two writers would lose
    evidence, which is the one thing this system never does."""
    import threading

    store = _store()
    def write(tag: str):
        for i in range(20):
            store.save_correction(_corr(f"corr_{tag}{i:02d}", f"{tag}{i}"))
    threads = [threading.Thread(target=write, args=(t,)) for t in ("a", "b")]
    for t in threads: t.start()
    for t in threads: t.join()
    got = store.list_corrections("p1")
    assert len(got) == 40
    assert len({c.id for c in got}) == 40
    assert [c.id for c in store.list_corrections("p1")] == [c.id for c in got]
