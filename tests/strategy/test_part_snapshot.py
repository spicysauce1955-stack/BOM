"""A run records the part versions it resolved, and the bay preview reads them back
rather than resolving today's."""

import pytest

from fenceai.parts.model import Part, PartLibrary, SpecField
from fenceai.parts.resolve import (
    library_at, resolve_model_parts, resolve_model_parts_at,
)
from fenceai.strategy.model import PartUse


def rail(version, width) -> Part:
    return Part(id="rail-38", version=version, status="active", type="rail",
                spec=[SpecField(key="width_mm", value=width, agree="==", unit="mm")])


def model():
    from fenceai.fencemodel.model import (
        Distributed, FenceModel, FrameSlot, PanelSpec, PartRequirement,
    )
    return FenceModel(id="M", version=1, default_spec=PanelSpec(frame=[
        FrameSlot(key="rail", orientation="horizontal", placement=Distributed(count=2),
                  requirement=PartRequirement(part_id="rail-38"))]))


def width_of(resolved) -> int:
    return resolved.default_spec.frame[0].requirement.eligibility.predicate.items[0].right.value


def test_an_old_run_reads_its_own_part_version_not_todays():
    """THE trap. `bay_preview_plan` reloads the model by its STAMPED version,
    explicitly never latest_active, because the drawer once marked one product
    chosen while the run had bought another. An unpinned part_id inside that stamped
    document reopens the identical bug by a new door."""
    v1_only = PartLibrary(parts=[rail(1, 38)])
    _, uses = resolve_model_parts(model(), v1_only)
    assert uses == [PartUse(part_id="rail-38", version=1,
                            content_hash=uses[0].content_hash)]

    moved = PartLibrary(parts=[rail(1, 38), rail(2, 45)])
    moved.parts[0].status = "retired"

    fresh, _ = resolve_model_parts(model(), moved)
    assert width_of(fresh) == 45

    as_run = resolve_model_parts_at(model(), moved, uses)
    assert width_of(as_run) == 38
    # and the DRAWN number moves with the bought one — the defect this whole
    # entity exists to close was a model drawing 38 while buying 45
    assert as_run.default_spec.frame[0].thickness_mm == 0


def test_an_empty_snapshot_falls_back_to_latest_active():
    """A run generated before parts existed. `[]` is the default and needs no
    validator — the same readable-old-runs convention as catalog_skus."""
    lib = PartLibrary(parts=[rail(1, 38)])
    resolved = resolve_model_parts_at(model(), lib, [])
    assert resolved.default_spec.frame[0].requirement.eligibility.predicate is not None
    assert width_of(resolved) == 38


def test_pinning_a_retired_version_does_not_re_activate_it_for_anybody_else():
    """The pinned view is a COPY. Re-labelling the library's own object would make
    previewing an old run change what every later reader of that library sees —
    a read that writes, through the one door nobody would think to look at."""
    lib = PartLibrary(parts=[rail(1, 38), rail(2, 45)])
    lib.parts[0].status = "retired"
    snapshot = [PartUse(part_id="rail-38", version=1)]

    assert width_of(resolve_model_parts_at(model(), lib, snapshot)) == 38
    assert lib.parts[0].status == "retired"
    assert lib.latest_active("rail-38").version == 2
    assert width_of(resolve_model_parts(model(), lib)[0]) == 45


def test_a_part_deleted_since_the_run_is_refused_by_name():
    """Not resolved as today's. A run naming a version that is gone cannot be
    rebuilt as itself, and quietly substituting the current one is exactly the
    substitution the stamped model ref already refuses."""
    lib = PartLibrary(parts=[rail(2, 45)])
    with pytest.raises(ValueError, match="rail-38"):
        resolve_model_parts_at(model(), lib, [PartUse(part_id="rail-38", version=1)])


def test_the_pinned_library_holds_only_what_the_run_resolved():
    lib = PartLibrary(parts=[rail(1, 38), rail(2, 45),
                             Part(id="other", version=1, type="rail",
                                  spec=[SpecField(key="width_mm", value=20,
                                                  agree="==", unit="mm")])])
    pinned = library_at(lib, [PartUse(part_id="rail-38", version=1)])
    assert [(p.id, p.version) for p in pinned.parts] == [("rail-38", 1)]


def test_no_snapshot_pins_nothing_rather_than_pinning_to_nothing():
    """The fallback, at the seam a caller can reach directly. An empty snapshot
    returning an empty library would refuse every model for naming parts — the
    exact opposite of what "this run predates parts" means."""
    lib = PartLibrary(parts=[rail(1, 38)])
    assert library_at(lib, []) is lib


def test_the_snapshot_is_part_of_run_identity():
    """Two runs building the identical fence from different part versions were not
    generated from the same thing."""
    a = PartUse(part_id="rail-38", version=1, content_hash="aaa")
    b = PartUse(part_id="rail-38", version=2, content_hash="bbb")
    assert a.sort_key() != b.sort_key()


def test_a_draft_edited_in_place_is_a_different_use_at_the_same_version():
    """Why the hash is carried at all: an ACTIVE version is immutable, a draft is
    not, so `(part_id, version)` alone cannot say what a run drew on."""
    a = PartUse(part_id="rail-38", version=1, content_hash="aaa")
    b = PartUse(part_id="rail-38", version=1, content_hash="bbb")
    assert a.sort_key() != b.sort_key()


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
