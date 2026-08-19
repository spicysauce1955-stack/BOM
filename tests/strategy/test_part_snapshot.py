"""A run records the part versions it resolved, and the bay preview reads them back
rather than resolving today's.

The pinned resolution here is spelled exactly as production spells it —
`resolve_model_parts(model, library_at(library, snapshot))` — because
`preview_panel` needs the pinned LIBRARY as well as the document (it validates
against the same versions it draws), and a test taking a shorter path than the
code it guards is a test of a path nobody runs.
"""

import pytest

from fenceai.parts.model import Part, PartLibrary, SpecField
from fenceai.parts.resolve import content_hash, library_at, resolve_model_parts
from fenceai.strategy.model import PartUse


def rail(version, width, thickness) -> Part:
    """One rail part at two versions. Both dimensions move between them, because
    the width decides which product is BOUGHT (through the compiled predicate) and
    the thickness is DRAWN (through `_apply_dimensions` onto the frame slot) — and
    a model drawing one number while buying another is the defect this whole entity
    exists to close."""
    return Part(id="rail-38", version=version, status="active", type="rail",
                spec=[SpecField(key="width_mm", value=width, agree="==", unit="mm"),
                      SpecField(key="thickness_mm", value=thickness,
                                agree="==", unit="mm")])


V1, V2 = rail(1, 38, 20), rail(2, 45, 25)


def model():
    from fenceai.fencemodel.model import (
        Distributed, FenceModel, FrameSlot, PanelSpec, PartRequirement,
    )
    return FenceModel(id="M", version=1, default_spec=PanelSpec(frame=[
        FrameSlot(key="rail", orientation="horizontal", placement=Distributed(count=2),
                  requirement=PartRequirement(part_id="rail-38"))]))


def bought_width(resolved) -> int:
    """The width the PREDICATE screens products by — what the run buys."""
    return resolved.default_spec.frame[0].requirement.eligibility.predicate.items[0].right.value


def drawn_thickness(resolved) -> int:
    """The thickness `_apply_dimensions` wrote onto the slot — what the run draws."""
    return resolved.default_spec.frame[0].thickness_mm


def resolved_at(lib, snapshot):
    """The production path, spelled out: pin the library, then resolve against it."""
    resolved, _ = resolve_model_parts(model(), library_at(lib, snapshot))
    return resolved


def test_an_old_run_reads_its_own_part_version_not_todays():
    """THE trap. `bay_preview_plan` reloads the model by its STAMPED version,
    explicitly never latest_active, because the drawer once marked one product
    chosen while the run had bought another. An unpinned part_id inside that stamped
    document reopens the identical bug by a new door."""
    v1_only = PartLibrary(parts=[rail(1, 38, 20)])
    _, uses = resolve_model_parts(model(), v1_only)
    assert uses == [PartUse(part_id="rail-38", version=1,
                            content_hash=content_hash(V1))]

    moved = PartLibrary(parts=[rail(1, 38, 20), rail(2, 45, 25)])
    moved.parts[0].status = "retired"

    fresh, _ = resolve_model_parts(model(), moved)
    assert (bought_width(fresh), drawn_thickness(fresh)) == (45, 25)

    # the run's own version, in BOTH directions: the bought number and the drawn
    # one move together, which is the property that failed when the model carried
    # its own width — it drew 38 while buying 45
    as_run = resolved_at(moved, uses)
    assert (bought_width(as_run), drawn_thickness(as_run)) == (38, 20)


def test_an_empty_snapshot_falls_back_to_latest_active():
    """A run generated before parts existed. `[]` is the default and needs no
    validator — the same readable-old-runs convention as catalog_skus."""
    lib = PartLibrary(parts=[rail(1, 38, 20)])
    resolved = resolved_at(lib, [])
    assert resolved.default_spec.frame[0].requirement.eligibility.predicate is not None
    assert bought_width(resolved) == 38


def test_pinning_a_retired_version_does_not_re_activate_it_for_anybody_else():
    """The pinned view is a COPY. Re-labelling the library's own object would make
    previewing an old run change what every later reader of that library sees —
    a read that writes, through the one door nobody would think to look at."""
    lib = PartLibrary(parts=[rail(1, 38, 20), rail(2, 45, 25)])
    lib.parts[0].status = "retired"
    snapshot = [PartUse(part_id="rail-38", version=1)]

    assert bought_width(resolved_at(lib, snapshot)) == 38
    assert lib.parts[0].status == "retired"
    assert lib.latest_active("rail-38").version == 2
    assert bought_width(resolve_model_parts(model(), lib)[0]) == 45


def test_a_part_deleted_since_the_run_is_refused_by_name():
    """Not resolved as today's. A run naming a version that is gone cannot be
    rebuilt as itself, and quietly substituting the current one is exactly the
    substitution the stamped model ref already refuses."""
    lib = PartLibrary(parts=[rail(2, 45, 25)])
    with pytest.raises(ValueError, match="rail-38"):
        resolved_at(lib, [PartUse(part_id="rail-38", version=1)])


def test_the_pinned_library_holds_only_what_the_run_resolved():
    lib = PartLibrary(parts=[rail(1, 38, 20), rail(2, 45, 25),
                             Part(id="other", version=1, type="rail",
                                  spec=[SpecField(key="width_mm", value=20,
                                                  agree="==", unit="mm")])])
    pinned = library_at(lib, [PartUse(part_id="rail-38", version=1)])
    assert [(p.id, p.version) for p in pinned.parts] == [("rail-38", 1)]


def test_no_snapshot_pins_nothing_rather_than_pinning_to_nothing():
    """The fallback, at the seam a caller can reach directly. An empty snapshot
    returning an empty library would refuse every model for naming parts — the
    exact opposite of what "this run predates parts" means."""
    lib = PartLibrary(parts=[rail(1, 38, 20)])
    assert library_at(lib, []) is lib


def test_a_snapshot_orders_by_part_then_version_then_content():
    """`generate()` sorts the snapshot with this key before stamping it, so the key
    decides the stored order — and the stored order is a digest input.

    Ordering by version or content BEFORE part_id would interleave two parts'
    histories, and the same run walked in a different segment order would stamp a
    differently-ordered snapshot and hash to a different id.
    """
    uses = [
        PartUse(part_id="screw", version=1, content_hash="a"),
        PartUse(part_id="rail-38", version=2, content_hash="a"),
        PartUse(part_id="rail-38", version=1, content_hash="z"),
        PartUse(part_id="rail-38", version=1, content_hash="a"),
    ]
    assert [u.sort_key() for u in sorted(uses, key=PartUse.sort_key)] == [
        ("rail-38", 1, "a"), ("rail-38", 1, "z"), ("rail-38", 2, "a"),
        ("screw", 1, "a"),
    ]


def test_a_draft_edited_in_place_is_a_different_use_at_the_same_version():
    """Why the hash is in the key at all: an ACTIVE version is immutable, a draft is
    not, so `(part_id, version)` alone cannot say what a run drew on. Dropping the
    hash from `sort_key` would dedupe two genuinely different uses into one."""
    a = PartUse(part_id="rail-38", version=1, content_hash="aaa")
    b = PartUse(part_id="rail-38", version=1, content_hash="bbb")
    assert a.sort_key() != b.sort_key()
    assert len({u.sort_key(): u for u in (a, b)}) == 2


def test_the_content_hash_a_run_stamps_is_the_part_it_read():
    """Not a version number dressed up: two versions of one part hash differently,
    and an edited draft at a FIXED version hashes differently again."""
    edited = rail(1, 38, 99)
    assert content_hash(V1) != content_hash(V2)
    assert content_hash(V1) != content_hash(edited)
    assert content_hash(V1) == content_hash(rail(1, 38, 20))


def test_a_run_stored_before_parts_existed_still_loads():
    from fenceai.strategy.model import GenerationRun
    run = GenerationRun.model_validate_json('{"id": "r1", "project_id": "p"}')
    assert run.part_snapshot == []


def test_the_snapshot_round_trips_through_stored_json():
    """Runs are stored as whole JSON documents and re-read with
    `model_validate_json`, so a field that did not survive the trip would be a
    snapshot that exists only inside the process that generated it."""
    from fenceai.strategy.model import GenerationRun
    run = GenerationRun(id="r1", part_snapshot=[
        PartUse(part_id="rail-38", version=2, content_hash="abc")])
    assert GenerationRun.model_validate_json(run.model_dump_json()).part_snapshot == \
        run.part_snapshot
